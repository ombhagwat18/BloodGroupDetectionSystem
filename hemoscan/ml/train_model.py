"""Re-creates the notebook's VGG-inspired model and exports models/fingerprint_model.h5.

    python ml/train_model.py --data ml/data/dataset_blood_group --epochs 10

`--data` is the folder with one sub-folder per class (A+, A-, AB+, AB-, B+, B-, O+, O-), exactly the
Kaggle "Merge_data" layout used in Fingerprint_Final.ipynb. Later, point it at images captured with
YOUR R307 (same folder layout, saved by the dashboard) to adapt the model to the real sensor.
"""
import argparse
from pathlib import Path

import tensorflow as tf
from tensorflow.keras import layers, models


def vgg_inspired(input_shape=(64, 64, 3), num_classes=8):
    inputs = layers.Input(shape=input_shape)
    x = inputs
    for filters in (64, 128, 256, 512):
        x = layers.Conv2D(filters, 3, padding="same", activation="relu")(x)
        x = layers.Conv2D(filters, 3, padding="same", activation="relu")(x)
        x = layers.MaxPooling2D(2)(x)
    x = layers.Flatten()(x)
    x = layers.Dense(512, activation="relu")(x)
    x = layers.Dropout(0.5)(x)
    x = layers.Dense(256, activation="relu")(x)
    x = layers.Dropout(0.5)(x)
    return models.Model(inputs, layers.Dense(num_classes, activation="softmax")(x))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "backend" / "models" / "fingerprint_model.h5"))
    a = ap.parse_args()

    kw = dict(labels="inferred", label_mode="categorical", batch_size=32, image_size=(64, 64),
              shuffle=True, seed=42, validation_split=0.4)
    train = tf.keras.preprocessing.image_dataset_from_directory(a.data, subset="training", **kw)
    val = tf.keras.preprocessing.image_dataset_from_directory(a.data, subset="validation", **kw)
    print("classes:", train.class_names)  # must be A+, A-, AB+, AB-, B+, B-, O+, O-
    norm = lambda x, y: (tf.cast(x, tf.float32) / 255.0, y)  # noqa: E731
    train, val = train.map(norm), val.map(norm)
    n = tf.data.experimental.cardinality(val).numpy()
    test, val = val.take(n // 2), val.skip(n // 2)

    model = vgg_inspired()
    model.compile(optimizer=tf.keras.optimizers.Adam(0.00015), loss="categorical_crossentropy", metrics=["accuracy"])
    model.fit(train, validation_data=val, epochs=a.epochs)
    print("test:", model.evaluate(test))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    model.save(a.out)
    print("saved", a.out)


if __name__ == "__main__":
    main()
