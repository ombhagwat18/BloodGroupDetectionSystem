"""Train and compare every candidate model under one identical, leak-free protocol; export the winner.

    python ml/train_model.py                              # all candidates
    python ml/train_model.py --models vgg_light,mobilenetv2 --epochs 15

Protocol (same for every model):
  * exact-duplicate images removed BEFORE splitting
  * stratified 70 / 15 / 15 train / val / test split on the original images (seed 42)
  * augmentation (small shift / rotation / zoom) on training data only
  * preprocessing identical to the live API (backend/app/imaging.py)
  * winner = highest VALIDATION accuracy among deployable (Keras) models; the test set is only reported
Outputs: backend/models/fingerprint_model.h5 (winner), backend/models/metrics.json, docs/model_comparison.png
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
import cv2
import numpy as np
import tensorflow as tf
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from tensorflow.keras import layers, models

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.imaging import to_model_input  # noqa: E402  (shared with the live API)
from app.ml import CLASSES  # noqa: E402

N = len(CLASSES)
IMAGENET_MEAN = [103.939, 116.779, 123.68]  # Keras ResNet50 / caffe-style, BGR (our 3 channels are identical)


# ----------------------------------------------------------------------------- data
def load_grays(root):
    grays, y, seen, dups = [], [], set(), 0
    for ci, cls in enumerate(CLASSES):
        for f in sorted((Path(root) / cls).glob("*")):
            raw = f.read_bytes()
            h = hashlib.md5(raw).hexdigest()
            if h in seen:
                dups += 1
                continue
            img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            seen.add(h)
            grays.append(img)
            y.append(ci)
    print("loaded %d images, dropped %d exact duplicates" % (len(grays), dups))
    return grays, np.array(y)


def arrays(grays, idx, size):
    return np.stack([to_model_input(grays[i], size)[0] for i in idx])


# ----------------------------------------------------------------------------- architectures (all take inputs in [0,1])
def vgg_light(size):
    """Notebook's VGG-inspired CNN at half width + BatchNorm."""
    x = inp = layers.Input((size, size, 3))
    for f in (32, 64, 128, 256):
        for _ in range(2):
            x = layers.ReLU()(layers.BatchNormalization()(layers.Conv2D(f, 3, padding="same", use_bias=False)(x)))
        x = layers.MaxPooling2D(2)(x)
    x = layers.Dropout(0.5)(layers.Dense(512, activation="relu")(layers.Flatten()(x)))
    x = layers.Dropout(0.5)(layers.Dense(256, activation="relu")(x))
    return models.Model(inp, layers.Dense(N, activation="softmax")(x))


def _res_block(x, f, stride):
    s = x
    x = layers.ReLU()(layers.BatchNormalization()(layers.Conv2D(f, 3, strides=stride, padding="same", use_bias=False)(x)))
    x = layers.BatchNormalization()(layers.Conv2D(f, 3, padding="same", use_bias=False)(x))
    if stride != 1 or s.shape[-1] != f:
        s = layers.BatchNormalization()(layers.Conv2D(f, 1, strides=stride, use_bias=False)(s))
    return layers.ReLU()(layers.add([x, s]))


def resnet_small(size):
    """Small ResNet from scratch (notebook 01's residual design, narrower and shallower)."""
    x = inp = layers.Input((size, size, 3))
    x = layers.ReLU()(layers.BatchNormalization()(layers.Conv2D(32, 3, padding="same", use_bias=False)(x)))
    for f, stride in ((32, 1), (32, 1), (64, 2), (64, 1), (128, 2), (128, 1), (256, 2), (256, 1)):
        x = _res_block(x, f, stride)
    x = layers.Dropout(0.4)(layers.GlobalAveragePooling2D()(x))
    return models.Model(inp, layers.Dense(N, activation="softmax")(x))


def _pretrained(base_fn, size, caffe):
    x = inp = layers.Input((size, size, 3))
    if caffe:  # ResNet50 preprocessing, done inside the model so the API only has to send [0,1] images
        x = layers.Normalization(mean=IMAGENET_MEAN, variance=[1.0] * 3)(layers.Rescaling(255.0)(x))
    else:  # MobileNetV2 expects [-1, 1]
        x = layers.Rescaling(2.0, offset=-1.0)(x)
    base = base_fn(include_top=False, weights="imagenet", input_shape=(size, size, 3), pooling="avg")
    base.trainable = False
    x = layers.Dropout(0.4)(layers.Dense(256, activation="relu")(base(x, training=False)))
    return models.Model(inp, layers.Dense(N, activation="softmax")(x))


def resnet50_transfer(size):
    return _pretrained(tf.keras.applications.ResNet50, size, caffe=True)


def mobilenetv2_transfer(size):
    return _pretrained(tf.keras.applications.MobileNetV2, size, caffe=False)


# name -> (builder, input size, max epochs, description)
CANDIDATES = {
    "vgg_light": (vgg_light, 64, 25, "VGG-inspired CNN, half width + BatchNorm (scratch)"),
    "resnet_small": (resnet_small, 64, 25, "Small ResNet, residual blocks (scratch)"),
    "resnet50_transfer": (resnet50_transfer, 96, 12, "ResNet50 ImageNet, frozen backbone + new head"),
    "mobilenetv2_transfer": (mobilenetv2_transfer, 96, 12, "MobileNetV2 ImageNet, frozen backbone + new head"),
}


# ----------------------------------------------------------------------------- training
def evaluate(probs, y):
    pred = probs.argmax(1)
    return {
        "accuracy": float((pred == y).mean()),
        "macro_f1": float(f1_score(y, pred, average="macro", zero_division=0)),
        "per_class": {c: {k: round(float(v), 4) for k, v in r.items()} for c, r in
                      classification_report(y, pred, target_names=CLASSES, output_dict=True, zero_division=0).items()
                      if c in CLASSES},
        "confusion_matrix": confusion_matrix(y, pred, labels=range(N)).tolist(),
    }


def train_keras(name, grays, split, epochs_cap, batch):
    builder, size, max_ep, desc = CANDIDATES[name]
    tr, va, te = split["train"], split["val"], split["test"]
    ytr, yva, yte = split["y"][tr], split["y"][va], split["y"][te]
    Xtr, Xva, Xte = arrays(grays, tr, size), arrays(grays, va, size), arrays(grays, te, size)
    oh = lambda v: tf.keras.utils.to_categorical(v, N)  # noqa: E731
    aug = tf.keras.Sequential([layers.RandomRotation(0.04, fill_mode="nearest"),
                               layers.RandomTranslation(0.06, 0.06, fill_mode="nearest"),
                               layers.RandomZoom(0.08, fill_mode="nearest")])
    train = (tf.data.Dataset.from_tensor_slices((Xtr, oh(ytr))).shuffle(len(Xtr), seed=42).batch(batch)
             .map(lambda x, t: (tf.clip_by_value(aug(x, training=True), 0, 1), t), num_parallel_calls=tf.data.AUTOTUNE)
             .prefetch(tf.data.AUTOTUNE))
    val = tf.data.Dataset.from_tensor_slices((Xva, oh(yva))).batch(batch)

    tf.keras.backend.clear_session()
    tf.random.set_seed(42)
    model = builder(size)
    model.compile(optimizer=tf.keras.optimizers.Adam(5e-4 if "transfer" not in name else 1e-3),
                  loss="categorical_crossentropy", metrics=["accuracy"])
    t0 = time.time()
    hist = model.fit(train, validation_data=val, epochs=min(max_ep, epochs_cap), verbose=2, callbacks=[
        tf.keras.callbacks.EarlyStopping(monitor="val_accuracy", patience=6, restore_best_weights=True),
        tf.keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=3)])
    secs = time.time() - t0
    res = {"description": desc, "input_size": size, "deployable": True, "params": int(model.count_params()),
           "train_seconds": round(secs), "epochs_run": len(hist.history["loss"]),
           "train_accuracy": float(hist.history["accuracy"][-1]),
           "val_accuracy": float(max(hist.history["val_accuracy"])),
           "val": evaluate(model.predict(Xva, verbose=0), yva), "test": evaluate(model.predict(Xte, verbose=0), yte)}
    return res, model


def baselines(grays, split):
    tr, va, te = split["train"], split["val"], split["test"]
    y = split["y"]
    out = {}
    maj = np.bincount(y[tr]).argmax()
    out["majority_class"] = {"description": "Always predict the most common class (chance reference)", "deployable": False,
                             "val_accuracy": float((y[va] == maj).mean()),
                             "test": {"accuracy": float((y[te] == maj).mean()), "macro_f1": 0.0}}
    from sklearn.svm import SVC
    hog = cv2.HOGDescriptor((64, 64), (16, 16), (8, 8), (8, 8), 9)
    feats = lambda idx: np.stack([hog.compute((to_model_input(grays[i], 64)[0][..., 0] * 255).astype(np.uint8)).ravel() for i in idx])  # noqa: E731
    t0 = time.time()
    svm = SVC(C=10, gamma="scale").fit(feats(tr), y[tr])
    out["hog_svm"] = {"description": "HOG features + RBF SVM (classical, not served by the API)", "deployable": False,
                      "train_seconds": round(time.time() - t0), "val_accuracy": float((svm.predict(feats(va)) == y[va]).mean()),
                      "test": {"accuracy": float((svm.predict(feats(te)) == y[te]).mean()),
                               "macro_f1": float(f1_score(y[te], svm.predict(feats(te)), average="macro"))}}
    return out


def chart(results, selected, path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    names = list(results)
    val = [results[n]["val_accuracy"] * 100 for n in names]
    test = [results[n]["test"]["accuracy"] * 100 for n in names]
    x = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.bar(x - 0.2, val, 0.4, label="Validation", color="#93b4f5")
    ax.bar(x + 0.2, test, 0.4, label="Test", color="#2563eb")
    for i, n in enumerate(names):
        ax.text(i + 0.2, test[i] + 1, "%.1f" % test[i], ha="center", fontsize=9)
        if n == selected:
            ax.text(i, max(val[i], test[i]) + 7, "selected", ha="center", color="#059669", fontweight="bold")
    ax.axhline(100 / N, ls="--", color="#999", lw=1)
    ax.set_xticks(x)
    ax.set_xticklabels([n.replace("_", "\n") for n in names], fontsize=9)
    ax.set_ylabel("Accuracy (%)")
    ax.set_ylim(0, 100)
    ax.set_title("Blood-group models - identical leak-free split (dashed = random guess)")
    ax.legend(loc="upper left")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "ml" / "data" / "dataset_blood_group"))
    ap.add_argument("--models", default=",".join(CANDIDATES), help="comma list of: " + ", ".join(CANDIDATES))
    ap.add_argument("--epochs", type=int, default=100, help="cap on epochs per model (each also has its own limit)")
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--no-baselines", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "backend" / "models" / "fingerprint_model.h5"))
    a = ap.parse_args()
    np.random.seed(42)

    grays, y = load_grays(a.data)
    idx = np.arange(len(y))
    tr, tmp = train_test_split(idx, test_size=0.30, stratify=y, random_state=42)
    va, te = train_test_split(tmp, test_size=0.50, stratify=y[tmp], random_state=42)
    split = {"train": tr, "val": va, "test": te, "y": y}
    print("train %d  val %d  test %d" % (len(tr), len(va), len(te)))

    results, best = {}, (None, -1.0, None)
    if not a.no_baselines:
        results.update(baselines(grays, split))
    for name in a.models.split(","):
        print("\n=== %s ===" % name)
        res, model = train_keras(name, grays, split, a.epochs, a.batch)
        results[name] = res
        res["val_accuracy"] = res["val_accuracy"]
        print("%s: val %.3f  test %.3f  macroF1 %.3f" % (name, res["val_accuracy"], res["test"]["accuracy"], res["test"]["macro_f1"]))
        if res["val_accuracy"] > best[1]:
            best = (name, res["val_accuracy"], model)
        else:
            del model

    name, _, model = best
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(out))
    metrics = {"selected": name, "selection_rule": "highest validation accuracy among deployable models",
               "split": {"train": len(tr), "val": len(va), "test": len(te)},
               "protocol": "de-duplicated, stratified 70/15/15 split on original images; augmentation on train only",
               "classes": CLASSES, "test_accuracy": results[name]["test"]["accuracy"],
               "test": results[name]["test"], "input_size": results[name]["input_size"], "candidates": results}
    (out.parent / "metrics.json").write_text(json.dumps(metrics, indent=2))
    chart(results, name, ROOT / "docs" / "model_comparison.png")
    print("\nSELECTED %s -> %s" % (name, out))
    for n, r in results.items():
        print("  %-22s val %.3f  test %.3f" % (n, r["val_accuracy"], r["test"]["accuracy"]))


if __name__ == "__main__":
    main()
