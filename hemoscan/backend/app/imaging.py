"""R307 image handling: unpack the sensor's 4-bit stream, grade quality, build model input."""
import cv2
import numpy as np

SENSOR_W, SENSOR_H = 256, 288
RAW_BYTES = SENSOR_W * SENSOR_H // 2  # UpImage = 2 pixels per byte (4-bit grey)
MODEL_SIZE = 64  # notebook: image_size=(64, 64)


def unpack_r307(raw: bytes) -> np.ndarray:
    """UpImage payload -> uint8 grey image (288x256). High nibble is the first pixel."""
    if len(raw) != RAW_BYTES:
        raise ValueError("expected %d bytes from R307, got %d" % (RAW_BYTES, len(raw)))
    b = np.frombuffer(raw, dtype=np.uint8)
    px = np.empty(b.size * 2, dtype=np.uint8)
    px[0::2] = b >> 4
    px[1::2] = b & 0x0F
    return (px * 17).reshape(SENSOR_H, SENSOR_W)


def decode_image(data: bytes) -> np.ndarray:
    """PNG/JPG/BMP bytes -> uint8 grey."""
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError("could not decode image")
    return img


def encode_png(gray: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", gray)
    if not ok:
        raise ValueError("png encode failed")
    return buf.tobytes()


def quality(gray: np.ndarray):
    """Return (score 0-100, ok). Rewards contrast and ridge coverage; flags empty/smudged captures."""
    g = gray.astype(np.float32)
    lo, hi = np.percentile(g, [2, 98])
    contrast = min((hi - lo) / 150.0, 1.0)
    # ridge coverage: fraction of pixels clearly darker/lighter than local background
    blur = cv2.GaussianBlur(g, (0, 0), 8)
    coverage = float(np.mean(np.abs(g - blur) > 12))
    cov_score = min(coverage / 0.35, 1.0)
    score = round(100 * (0.5 * contrast + 0.5 * cov_score), 1)
    return score, score >= 35


def to_model_input(gray: np.ndarray, size: int = MODEL_SIZE) -> np.ndarray:
    """Stretch contrast, resize to size x size (default 64), replicate to 3 channels, scale to [0,1] (as in the notebook)."""
    g = gray.astype(np.float32)
    lo, hi = np.percentile(g, [1, 99])
    if hi - lo > 1:
        g = np.clip((g - lo) / (hi - lo), 0, 1) * 255
    g = cv2.resize(g, (size, size), interpolation=cv2.INTER_AREA)
    x = np.repeat(g[..., None], 3, axis=-1) / 255.0
    return x[None].astype(np.float32)
