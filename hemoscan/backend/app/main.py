"""HemoScan API: patients, scans, ESP32 device endpoints, live WebSocket feed."""
import json
import os
import subprocess
import sys
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

from . import auth, db, imaging, ml
from .auth import require
from .hub import hub

DEVICE_KEY = os.environ.get("HEMOSCAN_DEVICE_KEY", "hemoscan-dev-key")
ONLINE_WINDOW = 15  # seconds since last heartbeat
COMMAND_TTL = 60  # queued commands older than this are dropped
MAX_SLOT = 200
GROUPS = ml.CLASSES

app = FastAPI(title="HemoScan API", version="1.0")
# the built dashboard is served from this same origin; only the Vite dev server needs CORS
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])

ANY = [Depends(require())]  # any signed-in user
STAFF = ("admin", "doctor", "operator")  # may register patients, scan and enrol
REVIEWERS = ("admin", "doctor", "lab_tech")  # may confirm / reject a prediction against the lab result


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


# ----------------------------------------------------------------------------- login & users
class LoginIn(BaseModel):
    username: str
    password: str


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    full_name: str = Field("", max_length=120)
    role: str
    password: str = Field(min_length=auth.MIN_PASSWORD, max_length=200)


class UserPatch(BaseModel):
    full_name: Optional[str] = Field(None, max_length=120)
    role: Optional[str] = None
    active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=auth.MIN_PASSWORD, max_length=200)


class PasswordIn(BaseModel):
    current: str
    new: str = Field(min_length=auth.MIN_PASSWORD, max_length=200)


def _check_username(name):
    if not all(ch.isalnum() or ch in "_.-" for ch in name) or not name.isascii():
        raise HTTPException(422, "username may only contain letters, digits, _ . -")


def _check_role(role):
    if role not in auth.ROLES:
        raise HTTPException(422, "role must be one of %s" % (auth.ROLES,))


def _login_response(c, u):
    c.execute("UPDATE users SET last_login=? WHERE id=?", (db.now(), u["id"]))
    return {"token": auth.make_token(u["id"]), "user": auth.public(u)}


@app.get("/api/auth/status")
def auth_status():
    return {"needs_setup": auth.user_count() == 0}


@app.post("/api/auth/setup", status_code=201)
def auth_setup(b: UserIn):
    """Creates the first admin. Only works while there are no users at all."""
    _check_username(b.username)
    with db.conn() as c:
        if c.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            raise HTTPException(409, "setup already done")
        cur = c.execute("INSERT INTO users(username,full_name,role,password_hash,created_at) VALUES(?,?,?,?,?)",
                        (b.username, b.full_name.strip(), "admin", auth.hash_password(b.password), db.now()))
        return _login_response(c, db.row(c.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()))


@app.post("/api/auth/login")
def auth_login(b: LoginIn):
    with db.conn() as c:
        u = db.row(c.execute("SELECT * FROM users WHERE username=?", (b.username.strip(),)).fetchone())
        # same message for unknown user / wrong password / disabled account
        if not u or not u["active"] or not auth.verify_password(b.password, u["password_hash"]):
            raise HTTPException(401, "wrong username or password")
        return _login_response(c, u)


@app.get("/api/auth/me")
def auth_me(user=Depends(require())):
    return auth.public(user)


@app.post("/api/auth/password")
def auth_password(b: PasswordIn, user=Depends(require())):
    if not auth.verify_password(b.current, user["password_hash"]):
        raise HTTPException(403, "current password is wrong")
    with db.conn() as c:
        c.execute("UPDATE users SET password_hash=? WHERE id=?", (auth.hash_password(b.new), user["id"]))
    return {"ok": True}


@app.get("/api/users", dependencies=[Depends(require("admin"))])
def list_users():
    with db.conn() as c:
        return [auth.public(r) for r in c.execute("SELECT * FROM users ORDER BY id")]


@app.post("/api/users", status_code=201, dependencies=[Depends(require("admin"))])
def create_user(b: UserIn):
    _check_role(b.role)
    _check_username(b.username)
    with db.conn() as c:
        if c.execute("SELECT 1 FROM users WHERE username=?", (b.username,)).fetchone():
            raise HTTPException(409, "username already taken")
        cur = c.execute("INSERT INTO users(username,full_name,role,password_hash,created_at) VALUES(?,?,?,?,?)",
                        (b.username, b.full_name.strip(), b.role, auth.hash_password(b.password), db.now()))
        return auth.public(c.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone())


@app.patch("/api/users/{uid}")
def update_user(uid: int, b: UserPatch, admin=Depends(require("admin"))):
    if b.role is not None:
        _check_role(b.role)
    with db.conn() as c:
        u = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not u:
            raise HTTPException(404, "user not found")
        # never leave the system without an active admin (or lock yourself out)
        losing_admin = u["role"] == "admin" and u["active"] and (
            (b.role is not None and b.role != "admin") or b.active is False)
        if losing_admin and auth.active_admins(c) <= 1:
            raise HTTPException(409, "at least one active admin is required")
        if uid == admin["id"] and b.active is False:
            raise HTTPException(409, "you cannot disable your own account")
        if b.full_name is not None:
            c.execute("UPDATE users SET full_name=? WHERE id=?", (b.full_name.strip(), uid))
        if b.role is not None:
            c.execute("UPDATE users SET role=? WHERE id=?", (b.role, uid))
        if b.active is not None:
            c.execute("UPDATE users SET active=? WHERE id=?", (int(b.active), uid))
        if b.password is not None:
            c.execute("UPDATE users SET password_hash=? WHERE id=?", (auth.hash_password(b.password), uid))
        return auth.public(c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())


@app.delete("/api/users/{uid}")
def delete_user(uid: int, admin=Depends(require("admin"))):
    with db.conn() as c:
        u = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not u:
            raise HTTPException(404, "user not found")
        if uid == admin["id"]:
            raise HTTPException(409, "you cannot delete your own account")
        if u["role"] == "admin" and u["active"] and auth.active_admins(c) <= 1:
            raise HTTPException(409, "at least one active admin is required")
        c.execute("DELETE FROM users WHERE id=?", (uid,))
    return {"ok": True}


# ----------------------------------------------------------------------------- health / model
@app.get("/api/health")
def health():
    return {"ok": True, "model": ml.info()["mode"], "time": db.now()}


@app.get("/api/model", dependencies=ANY)
def model_info():
    return ml.info()


# ----------------------------------------------------------------------------- training (live progress for the Models page)
ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "ml" / "data" / "dataset_blood_group"
PROGRESS_FILE = ml.MODEL_PATH.parent / "training_progress.json"
TRAIN_LOG = ml.MODEL_PATH.parent / "training.log"
_train = {"proc": None, "reloaded": True}


class TrainIn(BaseModel):
    models: str = "vgg_light,resnet_small,mobilenetv2_transfer,resnet50_transfer"
    epochs: int = Field(25, ge=1, le=100)


def _running():
    p = _train["proc"]
    return p is not None and p.poll() is None


@app.get("/api/training", dependencies=ANY)
def training_status():
    p = _train["proc"]
    if p is not None and p.poll() == 0 and not _train["reloaded"]:
        ml.reset()  # serve the new model without restarting the API
        _train["reloaded"] = True
    try:
        progress = json.loads(PROGRESS_FILE.read_text())
    except Exception:  # noqa: BLE001
        progress = None
    if progress and progress.get("status") in ("starting", "running") and not _running():
        progress["status"] = "stopped"  # process died or the API restarted mid-run
    log = TRAIN_LOG.read_text(errors="replace").splitlines()[-15:] if TRAIN_LOG.exists() else []
    return {"running": _running(), "dataset_found": DATASET.exists(), "progress": progress,
            "log": log, "metrics": ml.info()["metrics"]}


@app.post("/api/training/start", status_code=202, dependencies=[Depends(require("admin"))])
def training_start(body: TrainIn):
    if _running():
        raise HTTPException(409, "training is already running")
    if not DATASET.exists():
        raise HTTPException(409, "dataset not found in %s" % DATASET)
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    log = open(TRAIN_LOG, "w", encoding="utf-8")
    _train["proc"] = subprocess.Popen(
        [sys.executable, "-u", str(ROOT / "ml" / "train_model.py"), "--models", body.models, "--epochs", str(body.epochs)],
        cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT)
    log.close()  # the child keeps its own handle
    _train["reloaded"] = False
    return {"ok": True, "pid": _train["proc"].pid}


@app.post("/api/training/stop", dependencies=[Depends(require("admin"))])
def training_stop():
    if _running():
        _train["proc"].terminate()
    return {"ok": True}


# ----------------------------------------------------------------------------- patients
def _patient(c, pid):
    r = c.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    if not r:
        raise HTTPException(404, "patient not found")
    return db.row(r)


@app.get("/api/patients", dependencies=ANY)
def list_patients(q: str = ""):
    with db.conn() as c:
        sql = ("SELECT p.*, (SELECT COUNT(*) FROM scans s WHERE s.patient_id=p.id) AS scan_count "
               "FROM patients p")
        args = []
        if q:
            sql += " WHERE p.name LIKE ? OR p.code LIKE ? OR p.phone LIKE ?"
            args = ["%" + q + "%"] * 3
        return [db.row(r) for r in c.execute(sql + " ORDER BY p.id DESC", args)]


@app.post("/api/patients", status_code=201, dependencies=[Depends(require(*STAFF))])
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


@app.get("/api/patients/{pid}", dependencies=ANY)
def get_patient(pid: int):
    with db.conn() as c:
        return _patient(c, pid)


@app.put("/api/patients/{pid}", dependencies=[Depends(require("admin", "doctor"))])
def update_patient(pid: int, p: PatientIn):
    _check_group(p.blood_group or None)
    with db.conn() as c:
        _patient(c, pid)
        c.execute("UPDATE patients SET name=?,age=?,sex=?,phone=?,blood_group=?,allergies=?,conditions=?,notes=? WHERE id=?",
                  (p.name.strip(), p.age, p.sex, p.phone, p.blood_group or None, p.allergies, p.conditions, p.notes, pid))
        return _patient(c, pid)


@app.delete("/api/patients/{pid}", dependencies=[Depends(require("admin"))])
def delete_patient(pid: int):
    with db.conn() as c:
        p = _patient(c, pid)
        if p["sensor_slot"]:  # free the template on the sensor too
            _queue(c, "esp32-01", "delete_slot", {"slot": p["sensor_slot"]})
        c.execute("DELETE FROM patients WHERE id=?", (pid,))
    return {"ok": True}


@app.get("/api/patients/{pid}/scans", dependencies=ANY)
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


@app.get("/api/scans", dependencies=ANY)
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


@app.get("/api/scans/{sid}", dependencies=ANY)
def get_scan(sid: int):
    with db.conn() as c:
        return _scan_full(c, sid)


@app.get("/api/scans/{sid}/image", dependencies=ANY)
def scan_image(sid: int):
    f = db.IMG_DIR / ("%d.png" % sid)
    if not f.exists():
        raise HTTPException(404, "no image")
    return FileResponse(f, media_type="image/png")


@app.patch("/api/scans/{sid}")
def patch_scan(sid: int, body: ScanPatch, user=Depends(require())):
    _check_group(body.confirmed_group)
    if body.status and body.status not in ("pending", "confirmed", "rejected"):
        raise HTTPException(422, "bad status")
    reviewing = bool(body.confirmed_group or body.status)
    assigning = bool(body.unassign or body.patient_id is not None)
    if (reviewing and user["role"] not in REVIEWERS) or (assigning and user["role"] not in ("admin", "doctor")):
        raise HTTPException(403, "your role (%s) is not allowed to do this" % user["role"])
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
        if reviewing:
            c.execute("UPDATE scans SET confirmed_by=? WHERE id=?", (user["username"], sid))
        s = _scan_full(c, sid)
        # a lab-confirmed group fills an empty patient record (never overwrites an existing one)
        if s["status"] == "confirmed" and s["confirmed_group"] and s["patient_id"]:
            c.execute("UPDATE patients SET blood_group=? WHERE id=? AND (blood_group IS NULL OR blood_group='')",
                      (s["confirmed_group"], s["patient_id"]))
        return s


@app.delete("/api/scans/{sid}", dependencies=[Depends(require("admin"))])
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
    pred = await run_in_threadpool(ml.predict, gray)
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


@app.post("/api/scans/upload", status_code=201, dependencies=[Depends(require(*STAFF))])
async def upload_scan(file: UploadFile = File(...), patient_id: Optional[int] = None):
    """Manual upload (bitmap/PNG) - lets you use the dashboard without the ESP32."""
    try:
        gray = imaging.decode_image(await file.read())
    except ValueError as e:
        raise HTTPException(422, str(e))
    return await _ingest(gray, "upload", patient_id)


# ----------------------------------------------------------------------------- dashboard stats
@app.get("/api/stats", dependencies=ANY)
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


@app.get("/api/devices", dependencies=ANY)
def devices():
    with db.conn() as c:
        out = []
        for r in c.execute("SELECT * FROM devices ORDER BY last_seen DESC"):
            d = dict(r)
            d["online"] = (db.now() - (d["last_seen"] or 0)) < ONLINE_WINDOW
            d["sensor_ok"] = bool(d["sensor_ok"])
            out.append(d)
        return out


@app.post("/api/commands", status_code=201, dependencies=[Depends(require(*STAFF))])
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


@app.get("/api/commands", dependencies=ANY)
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
async def ws_endpoint(ws: WebSocket, token: Optional[str] = None):
    if not auth.user_from_token(token):
        await ws.close(code=4401)  # not signed in
        return
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
