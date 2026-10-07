"""Blood-group model wrapper. Loads fingerprint_model.h5 (exported by the notebook) lazily.

Modes: "model" (real predictions), "demo" (HEMOSCAN_DEMO=1, random output - UI shows a warning),
"none" (no model file: scans are stored without a prediction).
"""
import json
import os
import threading
from pathlib import Path
import numpy as np

CLASSES = ["A+", "A-", "AB+", "AB-", "B+", "B-", "O+", "O-"]  # alphabetical = Keras folder order in notebook
MODEL_PATH = Path(os.environ.get("HEMOSCAN_MODEL", Path(__file__).resolve().parent.parent / "models" / "fingerprint_model.h5"))
DEMO = os.environ.get("HEMOSCAN_DEMO") == "1"

_model = None
_error = None
_lock = threading.Lock()
_rng = np.random.default_rng()


def _load():
    global _model, _error
    with _lock:
        if _model is not None or _error is not None:
            return
        if not MODEL_PATH.exists():
            _error = "Model file not found: %s" % MODEL_PATH
            return
        try:
            os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
            from tensorflow.keras.models import load_model
            _model = load_model(str(MODEL_PATH), compile=False)
        except Exception as e:  # noqa: BLE001
            _error = "Failed to load model: %s" % e


def _metrics():
    f = MODEL_PATH.parent / "metrics.json"
    try:
        return json.loads(f.read_text())
    except Exception:  # noqa: BLE001
        return {}


def mode():
    if MODEL_PATH.exists():
        return "model"
    return "demo" if DEMO else "none"


def info():
    m = mode()
    if m == "model":
        _load()
    return {
        "mode": m if (m != "model" or _model is not None) else "none",
        "classes": CLASSES,
        "path": str(MODEL_PATH),
        "error": _error,
        "input": "%dx%dx3" % (input_size(), input_size()),
        "architecture": _metrics().get("selected", "unknown") if _model is not None else "no model loaded",
        "metrics": _metrics(),
    }


def input_size():
    return int(_model.input_shape[1]) if _model is not None else 64


def predict(gray: np.ndarray):
    """gray: uint8 sensor image. Returns dict(predicted, confidence, probs, mode) or None when no model."""
    from .imaging import to_model_input
    m = mode()
    if m == "model":
        _load()
        if _model is None:
            return None
        p = _model.predict(to_model_input(gray, input_size()), verbose=0)[0]
    elif m == "demo":
        p = _rng.dirichlet(np.ones(len(CLASSES)) * 0.6)
    else:
        return None
    p = np.asarray(p, dtype=float)
    return {
        "predicted": CLASSES[int(p.argmax())],
        "confidence": float(p.max()),
        "probs": {c: round(float(v), 4) for c, v in zip(CLASSES, p)},
        "mode": m,
    }
