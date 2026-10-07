"""Pretends to be the ESP32 + R307 so the whole software stack can be tested without hardware.

    python tools/esp32_simulator.py --server http://localhost:8000

Speaks the exact same HTTP protocol as the firmware (heartbeat, poll, event, scan upload in R307
4-bit format, enroll result). Press the buttons in the dashboard and watch it react.
"""
import argparse
import random
import time

import numpy as np
import requests

W, H = 256, 288


def fake_fingerprint(seed):
    """Synthetic ridge pattern in the R307 geometry: swirl of sinusoidal ridges inside an oval."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = W / 2 + rng.uniform(-15, 15), H / 2 + rng.uniform(-15, 15)
    dx, dy = x - cx, y - cy
    r = np.sqrt(dx ** 2 + dy ** 2)
    th = np.arctan2(dy, dx)
    freq = rng.uniform(0.38, 0.5)
    phase = freq * r + rng.integers(1, 4) * th + 0.01 * dx * dy / 20
    img = 0.5 + 0.5 * np.sin(phase)
    img += rng.normal(0, 0.08, img.shape)
    mask = ((dx / 105) ** 2 + (dy / 125) ** 2) < 1
    out = np.where(mask, img, 1.0)
    return (np.clip(out, 0, 1) * 15).astype(np.uint8)  # 4-bit


def pack4(img4):
    flat = img4.reshape(-1)
    return ((flat[0::2] << 4) | flat[1::2]).astype(np.uint8).tobytes()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://localhost:8000")
    ap.add_argument("--device", default="esp32-01")
    ap.add_argument("--key", default="hemoscan-dev-key")
    a = ap.parse_args()
    s = requests.Session()
    s.headers.update({"X-Device-Key": a.key})
    state = {"s": "idle"}
    slots = {}  # slot -> seed (the "templates" stored on the fake sensor)

    def beat():
        s.post(a.server + "/api/device/heartbeat", json={
            "device_id": a.device, "fw": "sim-1.0", "ip": "127.0.0.1", "sensor_ok": True,
            "state": state["s"], "template_count": len(slots)}, timeout=5)

    def event(st, msg="", cid=None):
        state["s"] = st
        s.post(a.server + "/api/device/event", json={"device_id": a.device, "state": st, "message": msg, "command_id": cid}, timeout=5)

    print("simulator up -> %s as %s" % (a.server, a.device))
    last = 0
    while True:
        try:
            if time.time() - last > 5:
                beat()
                last = time.time()
            cmd = s.get(a.server + "/api/device/poll", params={"device_id": a.device}, timeout=5).json()["command"]
            if cmd:
                cid, typ, pl = cmd["id"], cmd["type"], cmd["payload"]
                print("command:", cmd)
                if typ == "capture":
                    event("waiting_finger", "Place finger on the sensor", cid)
                    time.sleep(2.0)
                    event("reading_image", "Reading image from R307", cid)
                    time.sleep(1.0)
                    # an enrolled finger is "recognised" by the sensor (slot > 0); otherwise a stranger
                    slot = random.choice(list(slots)) if (slots and not pl.get("patient_id")) else 0
                    seed = slots[slot] if slot else random.randrange(10 ** 6)
                    r = s.post(a.server + "/api/device/scan", data=pack4(fake_fingerprint(seed)), timeout=30,
                               params={"device_id": a.device, "command_id": cid, "slot": slot, "score": 120 if slot else 0},
                               headers={"Content-Type": "application/octet-stream"})
                    print("  scan ->", r.status_code, r.json().get("predicted"), r.json().get("confidence"))
                    event("idle", "done")
                elif typ == "enroll":
                    event("enrolling", "Place finger (1/2)", cid)
                    time.sleep(2)
                    event("enrolling", "Lift finger, then place again (2/2)", cid)
                    time.sleep(2)
                    slots[pl["slot"]] = random.randrange(10 ** 6)
                    s.post(a.server + "/api/device/enroll_result", json={
                        "device_id": a.device, "command_id": cid, "ok": True, "slot": pl["slot"]}, timeout=5)
                    event("idle", "enrolled")
                elif typ == "delete_slot":
                    slots.pop(pl.get("slot"), None)
            time.sleep(1)
        except requests.RequestException as e:
            print("server unreachable:", e)
            time.sleep(3)
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
