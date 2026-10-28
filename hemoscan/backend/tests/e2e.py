"""End-to-end check against a running server (start it with HEMOSCAN_DEMO=1 and the simulator).

    python tests/e2e.py [http://localhost:8000]

Login: on a brand-new database the test creates an admin "e2e_admin". Otherwise give an existing
admin through HEMOSCAN_TEST_USER / HEMOSCAN_TEST_PASS. It creates (and removes) one user per role.
"""
import os
import sys
import time

import requests

B = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
KEY = {"X-Device-Key": "hemoscan-dev-key"}
PW = "e2e-Passw0rd!"
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


def login(username, password):
    r = requests.post(B + "/api/auth/login", json={"username": username, "password": password})
    return r.json()["token"] if r.status_code == 200 else None


def session(token):
    s = requests.Session()
    s.headers["Authorization"] = "Bearer " + token
    return s


check("health", requests.get(B + "/api/health").json()["ok"])
check("device key enforced", requests.post(B + "/api/device/heartbeat", json={"device_id": "x"}).status_code == 401)

# ---- login and roles
check("api closed without login", requests.get(B + "/api/patients").status_code == 401)
check("garbage token rejected", requests.get(B + "/api/patients", headers={"Authorization": "Bearer abc.def"}).status_code == 401)
if requests.get(B + "/api/auth/status").json()["needs_setup"]:
    r = requests.post(B + "/api/auth/setup", json={"username": "e2e_admin", "full_name": "E2E", "role": "admin", "password": PW})
    check("first-run admin setup", r.status_code == 201)
    admin_token = r.json()["token"]
    check("setup closes after first user", requests.post(B + "/api/auth/setup", json={"username": "x_user", "role": "admin", "password": PW}).status_code == 409)
else:
    admin_token = login(os.environ.get("HEMOSCAN_TEST_USER", ""), os.environ.get("HEMOSCAN_TEST_PASS", ""))
    if not admin_token:
        sys.exit("Users already exist: set HEMOSCAN_TEST_USER and HEMOSCAN_TEST_PASS to an admin account.")
check("wrong password rejected", login("e2e_admin", "nope-nope-nope") is None)
A = session(admin_token)
roles = {}
for role in ("doctor", "lab_tech", "operator"):
    name = "e2e_" + role
    for old in [u for u in A.get(B + "/api/users").json() if u["username"] == name]:
        A.delete(B + "/api/users/%d" % old["id"])
    u = A.post(B + "/api/users", json={"username": name, "role": role, "password": PW}).json()
    roles[role] = (u["id"], session(login(name, PW)))
DOC, LAB, OP = roles["doctor"][1], roles["lab_tech"][1], roles["operator"][1]
check("non-admin cannot list users", DOC.get(B + "/api/users").status_code == 403)
check("operator cannot train", OP.post(B + "/api/training/start", json={}).status_code == 403)
check("lab tech cannot register patients", LAB.post(B + "/api/patients", json={"name": "x"}).status_code == 403)
me = requests.get(B + "/api/auth/me", headers=A.headers).json()
check("last admin protected", A.patch(B + "/api/users/%d" % me["id"], json={"role": "doctor"}).status_code == 409)
check("cannot disable yourself", A.patch(B + "/api/users/%d" % me["id"], json={"active": False}).status_code == 409)

p = A.post(B + "/api/patients", json={"name": "Test Patient", "age": 30, "sex": "F"}).json()
check("create patient", p["code"].startswith("HS-"), p["code"])
check("bad blood group rejected", A.post(B + "/api/patients", json={"name": "x", "blood_group": "Z"}).status_code == 422)

dev = wait(lambda: [d for d in A.get(B + "/api/devices").json() if d["online"]])
check("simulator online", bool(dev))

# enroll -> sensor slot stored on patient
A.post(B + "/api/commands", json={"type": "enroll", "patient_id": p["id"]})
slot = wait(lambda: A.get(B + "/api/patients/%d" % p["id"]).json()["sensor_slot"])
check("enroll assigns slot", bool(slot), slot)

# capture with the sensor recognising the enrolled finger
A.post(B + "/api/commands", json={"type": "capture"})
scan = wait(lambda: (A.get(B + "/api/scans").json() or [None])[0])
check("scan created", bool(scan))
check("scan auto-linked to patient by sensor slot", scan and scan["patient_id"] == p["id"], scan and scan.get("patient_name"))
check("prediction present", scan and scan["predicted"] in ["A+", "A-", "AB+", "AB-", "B+", "B-", "O+", "O-"], scan and (scan["predicted"], scan["mode"]))
check("image served", A.get(B + scan["image_url"]).headers["content-type"] == "image/png")

# confirm flow fills patient blood group
check("operator cannot confirm a result", OP.patch(B + "/api/scans/%d" % scan["id"], json={"confirmed_group": "O+"}).status_code == 403)
r = LAB.patch(B + "/api/scans/%d" % scan["id"], json={"confirmed_group": "O+"}).json()
check("lab tech confirms", r["status"] == "confirmed")
check("confirmer recorded", r.get("confirmed_by") == "e2e_lab_tech", r.get("confirmed_by"))
check("patient blood group filled", A.get(B + "/api/patients/%d" % p["id"]).json()["blood_group"] == "O+")
s = A.get(B + "/api/stats").json()
check("stats", s["scans"] >= 1 and s["agreement_n"] >= 1, (s["scans"], s["agreement"]))

bad = requests.post(B + "/api/device/scan", params={"device_id": "x"}, data=b"123", headers=KEY)
check("bad raw payload rejected", bad.status_code == 422)

check("doctor cannot delete patient", DOC.delete(B + "/api/patients/%d" % p["id"]).status_code == 403)
A.delete(B + "/api/patients/%d" % p["id"])
for uid, _ in roles.values():
    A.delete(B + "/api/users/%d" % uid)
print("\nALL PASSED" if ok else "\nSOME FAILED")
sys.exit(0 if ok else 1)
