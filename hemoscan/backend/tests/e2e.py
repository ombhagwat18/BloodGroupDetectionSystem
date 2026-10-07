"""End-to-end check against a running server (start it with HEMOSCAN_DEMO=1 and the simulator).

    python tests/e2e.py [http://localhost:8000]
"""
import sys
import time

import requests

B = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
KEY = {"X-Device-Key": "hemoscan-dev-key"}
ok = True


def check(name, cond, extra=""):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name, extra)


def wait(fn, t=25):
    end = time.time() + t
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.5)


check("health", requests.get(B + "/api/health").json()["ok"])
check("device key enforced", requests.post(B + "/api/device/heartbeat", json={"device_id": "x"}).status_code == 401)

p = requests.post(B + "/api/patients", json={"name": "Test Patient", "age": 30, "sex": "F"}).json()
check("create patient", p["code"].startswith("HS-"), p["code"])
check("bad blood group rejected", requests.post(B + "/api/patients", json={"name": "x", "blood_group": "Z"}).status_code == 422)

dev = wait(lambda: [d for d in requests.get(B + "/api/devices").json() if d["online"]])
check("simulator online", bool(dev))

# enroll -> sensor slot stored on patient
requests.post(B + "/api/commands", json={"type": "enroll", "patient_id": p["id"]})
slot = wait(lambda: requests.get(B + "/api/patients/%d" % p["id"]).json()["sensor_slot"])
check("enroll assigns slot", bool(slot), slot)

# capture with the sensor recognising the enrolled finger
requests.post(B + "/api/commands", json={"type": "capture"})
scan = wait(lambda: (requests.get(B + "/api/scans").json() or [None])[0])
check("scan created", bool(scan))
check("scan auto-linked to patient by sensor slot", scan and scan["patient_id"] == p["id"], scan and scan.get("patient_name"))
check("prediction present", scan and scan["predicted"] in ["A+", "A-", "AB+", "AB-", "B+", "B-", "O+", "O-"], scan and (scan["predicted"], scan["mode"]))
check("image served", requests.get(B + scan["image_url"]).headers["content-type"] == "image/png")

# confirm flow fills patient blood group
r = requests.patch(B + "/api/scans/%d" % scan["id"], json={"confirmed_group": "O+"}).json()
check("confirm", r["status"] == "confirmed")
check("patient blood group filled", requests.get(B + "/api/patients/%d" % p["id"]).json()["blood_group"] == "O+")
s = requests.get(B + "/api/stats").json()
check("stats", s["scans"] >= 1 and s["agreement_n"] >= 1, (s["scans"], s["agreement"]))

bad = requests.post(B + "/api/device/scan", params={"device_id": "x"}, data=b"123", headers=KEY)
check("bad raw payload rejected", bad.status_code == 422)

requests.delete(B + "/api/patients/%d" % p["id"])
print("\nALL PASSED" if ok else "\nSOME FAILED")
sys.exit(0 if ok else 1)
