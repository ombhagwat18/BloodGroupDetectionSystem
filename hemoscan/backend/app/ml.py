"""Blood-group model wrapper. Loads fingerprint_model.h5 (exported by the notebook) lazily.

Modes: "model" (real predictions), "demo" (HEMOSCAN_DEMO=1, random output - UI shows a warning),
"none" (no model file: scans are stored without a prediction).
"""
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
        "input": "64x64x3",
        "architecture": "VGG-inspired CNN (notebook: ~88% test accuracy on Kaggle dataset)",
    }


def predict(x: np.ndarray):
    """x: (1,64,64,3) float32. Returns dict(predicted, confidence, probs, mode) or None when no model."""
    m = mode()
    if m == "model":
        _load()
        if _model is None:
            return None
        p = _model.predict(x, verbose=0)[0]
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
