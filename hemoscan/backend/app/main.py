"""HemoScan API: patients, scans, ESP32 device endpoints, live WebSocket feed."""
import json
import os
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, imaging, ml
from .hub import hub

DEVICE_KEY = os.environ.get("HEMOSCAN_DEVICE_KEY", "hemoscan-dev-key")
ONLINE_WINDOW = 15  # seconds since last heartbeat
COMMAND_TTL = 60  # queued commands older than this are dropped
MAX_SLOT = 200
GROUPS = ml.CLASSES

app = FastAPI(title="HemoScan API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _startup():
    db.init()


def need_device_key(x_device_key: Optional[str] = Header(None)):
    if x_device_key != DEVICE_KEY:
        raise HTTPException(401, "bad device key")


# ----------------------------------------------------------------------------- schemas
class PatientIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    age: Optional[int] = Field(None, ge=0, le=130)
    sex: Optional[str] = None
    phone: Optional[str] = None
    blood_group: Optional[str] = None
    allergies: str = ""
    conditions: str = ""
    notes: str = ""


class ScanPatch(BaseModel):
    patient_id: Optional[int] = None
    status: Optional[str] = None  # pending | confirmed | rejected
    confirmed_group: Optional[str] = None
    unassign: bool = False


class CommandIn(BaseModel):
    device_id: str = "esp32-01"
    type: str  # capture | enroll | cancel
    patient_id: Optional[int] = None


class Heartbeat(BaseModel):
    device_id: str
    fw: str = ""
    ip: str = ""
    sensor_ok: bool = False
    state: str = "idle"
    template_count: Optional[int] = None


class DeviceEvent(BaseModel):
    device_id: str
    state: str
    message: str = ""
    command_id: Optional[int] = None


class EnrollResult(BaseModel):
    device_id: str
    command_id: int
    ok: bool
    slot: Optional[int] = None
    error: str = ""


def _check_group(g):
    if g is not None and g not in GROUPS:
        raise HTTPException(422, "blood group must be one of %s" % GROUPS)


# ----------------------------------------------------------------------------- health / model
@app.get("/api/health")
def health():
    return {"ok": True, "model": ml.info()["mode"], "time": db.now()}


@app.get("/api/model")
def model_info():
    return ml.info()


# ----------------------------------------------------------------------------- patients
def _patient(c, pid):
    r = c.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    if not r:
        raise HTTPException(404, "patient not found")
    return db.row(r)


@app.get("/api/patients")
def list_patients(q: str = ""):
    with db.conn() as c:
        sql = ("SELECT p.*, (SELECT COUNT(*) FROM scans s WHERE s.patient_id=p.id) AS scan_count "
               "FROM patients p")
        args = []
        if q:
            sql += " WHERE p.name LIKE ? OR p.code LIKE ? OR p.phone LIKE ?"
            args = ["%" + q + "%"] * 3
        return [db.row(r) for r in c.execute(sql + " ORDER BY p.id DESC", args)]


@app.post("/api/patients", status_code=201)
def create_patient(p: PatientIn):
    _check_group(p.blood_group or None)
    with db.conn() as c:
        cur = c.execute(
            "INSERT INTO patients(name,age,sex,phone,blood_group,allergies,conditions,notes,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (p.name.strip(), p.age, p.sex, p.phone, p.blood_group or None, p.allergies, p.conditions, p.notes, db.now()))
        pid = cur.lastrowid
        c.execute("UPDATE patients SET code=? WHERE id=?", ("HS-%05d" % pid, pid))
        return _patient(c, pid)


@app.get("/api/patients/{pid}")
def get_patient(pid: int):
    with db.conn() as c:
        return _patient(c, pid)


@app.put("/api/patients/{pid}")
def update_patient(pid: int, p: PatientIn):
    _check_group(p.blood_group or None)
    with db.conn() as c:
        _patient(c, pid)
        c.execute("UPDATE patients SET name=?,age=?,sex=?,phone=?,blood_group=?,allergies=?,conditions=?,notes=? WHERE id=?",
                  (p.name.strip(), p.age, p.sex, p.phone, p.blood_group or None, p.allergies, p.conditions, p.notes, pid))
        return _patient(c, pid)


@app.delete("/api/patients/{pid}")
def delete_patient(pid: int):
    with db.conn() as c:
        p = _patient(c, pid)
        if p["sensor_slot"]:  # free the template on the sensor too
            _queue(c, "esp32-01", "delete_slot", {"slot": p["sensor_slot"]})
        c.execute("DELETE FROM patients WHERE id=?", (pid,))
    return {"ok": True}


@app.get("/api/patients/{pid}/scans")
def patient_scans(pid: int):
    with db.conn() as c:
        _patient(c, pid)
        return [db.scan_dict(r) for r in c.execute("SELECT * FROM scans WHERE patient_id=? ORDER BY id DESC", (pid,))]


# ----------------------------------------------------------------------------- scans
def _scan_full(c, sid):
    r = c.execute("SELECT s.*, p.name AS patient_name, p.code AS patient_code FROM scans s "
                  "LEFT JOIN patients p ON p.id=s.patient_id WHERE s.id=?", (sid,)).fetchone()
    if not r:
        raise HTTPException(404, "scan not found")
    return db.scan_dict(r)


@app.get("/api/scans")
def list_scans(status: Optional[str] = None, patient_id: Optional[int] = None, limit: int = 200):
    sql = ("SELECT s.*, p.name AS patient_name, p.code AS patient_code FROM scans s "
           "LEFT JOIN patients p ON p.id=s.patient_id WHERE 1=1")
    args = []
    if status:
        sql += " AND s.status=?"
        args.append(status)
    if patient_id:
        sql += " AND s.patient_id=?"
        args.append(patient_id)
    with db.conn() as c:
        return [db.scan_dict(r) for r in c.execute(sql + " ORDER BY s.id DESC LIMIT ?", args + [limit])]


@app.get("/api/scans/{sid}")
def get_scan(sid: int):
    with db.conn() as c:
        return _scan_full(c, sid)


@app.get("/api/scans/{sid}/image")
def scan_image(sid: int):
    f = db.IMG_DIR / ("%d.png" % sid)
    if not f.exists():
        raise HTTPException(404, "no image")
    return FileResponse(f, media_type="image/png")


@app.patch("/api/scans/{sid}")
def patch_scan(sid: int, body: ScanPatch):
    _check_group(body.confirmed_group)
    if body.status and body.status not in ("pending", "confirmed", "rejected"):
        raise HTTPException(422, "bad status")
    with db.conn() as c:
        _scan_full(c, sid)
        if body.unassign:
            c.execute("UPDATE scans SET patient_id=NULL WHERE id=?", (sid,))
        elif body.patient_id is not None:
            _patient(c, body.patient_id)
            c.execute("UPDATE scans SET patient_id=? WHERE id=?", (body.patient_id, sid))
        if body.confirmed_group:
            c.execute("UPDATE scans SET confirmed_group=?, status='confirmed' WHERE id=?", (body.confirmed_group, sid))
        if body.status:
            c.execute("UPDATE scans SET status=? WHERE id=?", (body.status, sid))
        s = _scan_full(c, sid)
        # a lab-confirmed group fills an empty patient record (never overwrites an existing one)
        if s["status"] == "confirmed" and s["confirmed_group"] and s["patient_id"]:
            c.execute("UPDATE patients SET blood_group=? WHERE id=? AND (blood_group IS NULL OR blood_group='')",
                      (s["confirmed_group"], s["patient_id"]))
        return s


@app.delete("/api/scans/{sid}")
def delete_scan(sid: int):
    with db.conn() as c:
        _scan_full(c, sid)
        c.execute("DELETE FROM scans WHERE id=?", (sid,))
    f = db.IMG_DIR / ("%d.png" % sid)
    if f.exists():
        f.unlink()
    return {"ok": True}


async def _ingest(gray, device_id, patient_id=None, slot=None, score=None, command_id=None):
    """Quality-check, classify, store, broadcast. Shared by device uploads and manual uploads."""
    q, q_ok = imaging.quality(gray)
    pred = await run_in_threadpool(ml.predict, imaging.to_model_input(gray))
    with db.conn() as c:
        if patient_id is None and slot:
            r = c.execute("SELECT id FROM patients WHERE sensor_slot=?", (slot,)).fetchone()
            patient_id = r["id"] if r else None
        cur = c.execute(
            "INSERT INTO scans(patient_id,device_id,predicted,confidence,probs,quality,quality_ok,sensor_slot,sensor_score,mode,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (patient_id, device_id,
             pred and pred["predicted"], pred and pred["confidence"], pred and json.dumps(pred["probs"]),
             q, int(q_ok), slot or None, score, pred["mode"] if pred else "none", db.now()))
        sid = cur.lastrowid
        (db.IMG_DIR / ("%d.png" % sid)).write_bytes(imaging.encode_png(gray))
        if command_id:
            c.execute("UPDATE commands SET status='done', result=? WHERE id=?", (json.dumps({"scan_id": sid}), command_id))
        scan = _scan_full(c, sid)
    scan["command_id"] = command_id
    await hub.broadcast("scan_created", scan)
    return scan


@app.post("/api/scans/upload", status_code=201)
async def upload_scan(file: UploadFile = File(...), patient_id: Optional[int] = None):
    """Manual upload (bitmap/PNG) - lets you use the dashboard without the ESP32."""
    try:
        gray = imaging.decode_image(await file.read())
    except ValueError as e:
        raise HTTPException(422, str(e))
    return await _ingest(gray, "upload", patient_id)


# ----------------------------------------------------------------------------- dashboard stats
@app.get("/api/stats")
def stats():
    with db.conn() as c:
        patients = c.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
        scans = [dict(r) for r in c.execute("SELECT predicted, confirmed_group, status, created_at FROM scans")]
        by_group = {g: 0 for g in GROUPS}
        for r in c.execute("SELECT blood_group, COUNT(*) n FROM patients WHERE blood_group IS NOT NULL AND blood_group!='' GROUP BY blood_group"):
            by_group[r["blood_group"]] = r["n"]
    days = Counter(datetime.fromtimestamp(s["created_at"]).strftime("%Y-%m-%d") for s in scans)
    daily = []
    for i in range(13, -1, -1):
        d = datetime.fromtimestamp(time.time() - i * 86400).strftime("%Y-%m-%d")
        daily.append({"date": d[5:], "scans": days.get(d, 0)})
    checked = [s for s in scans if s["confirmed_group"] and s["predicted"]]
    agree = sum(1 for s in checked if s["confirmed_group"] == s["predicted"])
    pred_dist = Counter(s["predicted"] for s in scans if s["predicted"])
    return {
        "patients": patients,
        "scans": len(scans),
        "pending": sum(1 for s in scans if s["status"] == "pending"),
        "confirmed": sum(1 for s in scans if s["status"] == "confirmed"),
        "agreement": (agree / len(checked)) if checked else None,
        "agreement_n": len(checked),
        "patients_by_group": [{"group": g, "count": by_group[g]} for g in GROUPS],
        "predicted_by_group": [{"group": g, "count": pred_dist.get(g, 0)} for g in GROUPS],
        "daily": daily,
    }


# ----------------------------------------------------------------------------- devices & commands
def _queue(c, device_id, type_, payload):
    cur = c.execute("INSERT INTO commands(device_id,type,payload,created_at) VALUES(?,?,?,?)",
                    (device_id, type_, json.dumps(payload), db.now()))
    return cur.lastrowid


def _free_slot(c):
    used = {r[0] for r in c.execute("SELECT sensor_slot FROM patients WHERE sensor_slot IS NOT NULL")}
    used |= {json.loads(r[0]).get("slot") for r in c.execute(
        "SELECT payload FROM commands WHERE type='enroll' AND status IN ('queued','sent')")}
    for s in range(1, MAX_SLOT + 1):
        if s not in used:
            return s
    raise HTTPException(409, "sensor memory full")


@app.get("/api/devices")
def devices():
    with db.conn() as c:
        out = []
        for r in c.execute("SELECT * FROM devices ORDER BY last_seen DESC"):
            d = dict(r)
            d["online"] = (db.now() - (d["last_seen"] or 0)) < ONLINE_WINDOW
            d["sensor_ok"] = bool(d["sensor_ok"])
            out.append(d)
        return out


@app.post("/api/commands", status_code=201)
async def send_command(cmd: CommandIn):
    if cmd.type not in ("capture", "enroll", "cancel"):
        raise HTTPException(422, "unknown command type")
    payload = {}
    with db.conn() as c:
        if cmd.type == "enroll":
            if not cmd.patient_id:
                raise HTTPException(422, "enroll needs patient_id")
            p = _patient(c, cmd.patient_id)
            payload = {"patient_id": p["id"], "slot": p["sensor_slot"] or _free_slot(c)}
        elif cmd.type == "capture" and cmd.patient_id:
            _patient(c, cmd.patient_id)
            payload = {"patient_id": cmd.patient_id}
        cid = _queue(c, cmd.device_id, cmd.type, payload)
    await hub.broadcast("command", {"id": cid, "type": cmd.type, "status": "queued", "device_id": cmd.device_id})
    return {"id": cid, "type": cmd.type, "payload": payload, "status": "queued"}


@app.get("/api/commands")
def list_commands(limit: int = 20):
    with db.conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM commands ORDER BY id DESC LIMIT ?", (limit,))]


@app.post("/api/device/heartbeat", dependencies=[Depends(need_device_key)])
async def heartbeat(h: Heartbeat):
    with db.conn() as c:
        c.execute(
            "INSERT INTO devices(device_id,ip,fw,sensor_ok,state,template_count,last_seen) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(device_id) DO UPDATE SET ip=excluded.ip, fw=excluded.fw, sensor_ok=excluded.sensor_ok, "
            "state=excluded.state, template_count=excluded.template_count, last_seen=excluded.last_seen",
            (h.device_id, h.ip, h.fw, int(h.sensor_ok), h.state, h.template_count, db.now()))
    await hub.broadcast("device", {"device_id": h.device_id, "online": True, "sensor_ok": h.sensor_ok, "state": h.state})
    return {"ok": True, "server_time": db.now()}


@app.get("/api/device/poll", dependencies=[Depends(need_device_key)])
def poll(device_id: str):
    """ESP32 asks for work. Returns {command: null} or the oldest fresh queued command."""
    with db.conn() as c:
        c.execute("UPDATE commands SET status='failed', result='expired' WHERE status='queued' AND created_at<?",
                  (db.now() - COMMAND_TTL,))
        r = c.execute("SELECT * FROM commands WHERE device_id=? AND status='queued' ORDER BY id LIMIT 1", (device_id,)).fetchone()
        if not r:
            return {"command": None}
        c.execute("UPDATE commands SET status='sent' WHERE id=?", (r["id"],))
        return {"command": {"id": r["id"], "type": r["type"], "payload": json.loads(r["payload"] or "{}")}}


@app.post("/api/device/event", dependencies=[Depends(need_device_key)])
async def device_event(e: DeviceEvent):
    if e.command_id and e.state in ("failed", "timeout", "cancelled"):
        with db.conn() as c:
            c.execute("UPDATE commands SET status='failed', result=? WHERE id=?", (e.message, e.command_id))
    await hub.broadcast("device_event", e.dict())
    return {"ok": True}


@app.post("/api/device/scan", dependencies=[Depends(need_device_key)], status_code=201)
async def device_scan(request: Request, device_id: str, command_id: Optional[int] = None,
                      slot: int = 0, score: int = 0, fmt: str = "raw4"):
    """Body = raw R307 UpImage bytes (fmt=raw4, 36864 bytes) or an encoded image (fmt=img)."""
    body = await request.body()
    try:
        gray = imaging.unpack_r307(body) if fmt == "raw4" else imaging.decode_image(body)
    except ValueError as e:
        raise HTTPException(422, str(e))
    patient_id = None
    if command_id:
        with db.conn() as c:
            r = c.execute("SELECT payload FROM commands WHERE id=?", (command_id,)).fetchone()
            if r:
                patient_id = json.loads(r["payload"] or "{}").get("patient_id")
    return await _ingest(gray, device_id, patient_id, slot or None, score or None, command_id)


@app.post("/api/device/enroll_result", dependencies=[Depends(need_device_key)])
async def enroll_result(r: EnrollResult):
    with db.conn() as c:
        row = c.execute("SELECT payload FROM commands WHERE id=?", (r.command_id,)).fetchone()
        if not row:
            raise HTTPException(404, "unknown command")
        payload = json.loads(row["payload"] or "{}")
        if r.ok:
            slot = r.slot or payload.get("slot")
            c.execute("UPDATE patients SET sensor_slot=NULL WHERE sensor_slot=? AND id!=?", (slot, payload["patient_id"]))
            c.execute("UPDATE patients SET sensor_slot=? WHERE id=?", (slot, payload["patient_id"]))
            c.execute("UPDATE commands SET status='done', result=? WHERE id=?", (json.dumps({"slot": slot}), r.command_id))
        else:
            c.execute("UPDATE commands SET status='failed', result=? WHERE id=?", (r.error, r.command_id))
    await hub.broadcast("enroll_result", r.dict())
    return {"ok": True}


# ----------------------------------------------------------------------------- websocket
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()  # keep-alive; dashboards only listen
    except WebSocketDisconnect:
        hub.disconnect(ws)


# ----------------------------------------------------------------------------- built frontend (optional)
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = _dist / path
        return FileResponse(f if path and f.is_file() else _dist / "index.html")
