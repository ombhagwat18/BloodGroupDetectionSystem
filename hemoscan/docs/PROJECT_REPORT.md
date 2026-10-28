# HemoScan — Project Report

*Fingerprint-assisted blood group screening: R307 sensor → ESP32 → CNN → React dashboard*
Report date: 27 Oct 2026

---

## 1. Summary

HemoScan is already a working full-stack system:

- **Hardware:** an R307 sensor and an ESP32 (firmware written, not yet run on real hardware).
- **Backend:** a FastAPI server with a SQLite database.
- **ML:** a training script that compares four CNNs and two baselines under a leak-free protocol.
- **Dashboard:** a React dashboard with live WebSocket updates.

What was missing on this PC, and what this report covers:

| Area | State before | Done now |
|---|---|---|
| Setup on a new PC | Launcher stopped if Python was missing | `start_hemoscan.bat` now installs Python 3.11 / Node LTS through winget, repairs a broken `.venv`, rebuilds the dashboard when its code changes |
| Model accuracy in the dashboard | Not shown | New **Models & Training** tab: accuracy KPIs, live per-epoch graph, model comparison, per-class table, confusion matrix, start/stop training |
| Architecture documentation | 2 diagrams in README | `docs/architecture/`: 10 Mermaid diagrams |
| Fingerprint pattern images | none | `docs/fingerprint_patterns/`: arch, tented arch, left/right loop, whorl, minutiae chart, 24 real samples (3 per blood group) |
| Trained model | **none** (`backend/models/` empty) | Not trained yet: needs the Python environment first (section 2) |

> **The most important finding.** No accepted medical evidence shows that a fingerprint determines blood
> group. A fingerprint also cannot measure blood values such as haemoglobin. HemoScan is therefore a
> **research system that tests a hypothesis**, not a diagnostic device. The project's strongest academic
> contribution is to measure that hypothesis honestly: a leak-free split, comparison with chance level, and
> agreement with lab results (section 4).

---

## 2. System check of this PC

| Item | Found | Status |
|---|---|---|
| CPU / RAM | Intel i7-12700H (14 cores) · 15.6 GB | ✅ enough to train the light CNNs on CPU |
| GPU | NVIDIA RTX 3050 Laptop + Intel Iris Xe | ⚠️ **not used**: TensorFlow ≥ 2.11 has no native GPU support on Windows. TF 2.13 runs on the CPU here. To use the GPU, run training inside WSL2 + CUDA, or pin TF 2.10 (Python ≤ 3.10) |
| Free disk (E:) | 240 GB | ✅ |
| Python on PATH | **not found** (only the Microsoft Store alias) | ❌ the setup script installs Python 3.11 |
| Project `.venv` | exists, but built from `Python38` which was **deleted** | ❌ broken. The script now detects this, deletes it and rebuilds it |
| Python 3.8 itself | end-of-life since Oct 2024 | ⚠️ the script now prefers 3.11 (TF 2.13 supports 3.8-3.11) |
| Node.js / npm | v24.22.1 / 11.19.1 | ✅ |
| Dashboard packages | `frontend/node_modules` present, build passes | ✅ (bundle 614 KB, a size warning only) |
| winget | present | ✅ allows automatic installs |
| curl | present | ✅ the launcher uses it to wait for the API |
| git | **not on PATH** (the repo has a `.git` folder) | ⚠️ not needed to run. Install with `winget install Git.Git` for version control |
| Dataset | `ml/data/dataset_blood_group`: 6,000 images, all 8 folders | ✅ |
| Trained model | `backend/models/` is empty | ❌ the API runs in DEMO mode (random predictions) |
| Test database | `backend/data/hemoscan.db` with 5 scans | ✅ (demo data) |

`start_hemoscan.bat check` gives the same report at any time without changing anything. Output on this PC:

```
[!] No Python 3.8 - 3.11 found.
    would install Python 3.11 - run without "check" to do it
[OK] Node v24.22.1
[OK] Dataset found in ml\data\dataset_blood_group
[!] No trained model yet - the API will run in DEMO mode
```

**To get this PC running:** double-click `start_hemoscan.bat`. It installs Python 3.11, rebuilds `.venv`,
installs TensorFlow and the other packages (first run ≈ 5-15 min, depending on internet speed), and opens
the dashboard. Then go to **Models & Training → Train all models**.

---

## 3. Project file audit

| Part | Files | Purpose | Assessment |
|---|---|---|---|
| Firmware | `firmware/hemoscan_esp32/hemoscan_esp32.ino` | R307 UART protocol: capture, UpImage, Search, enrol, delete; WiFi heartbeat and command polling | Complete per datasheet. **Untested on hardware**: expect to tune timeouts |
| API | `backend/app/main.py` | REST for patients, scans, devices, commands, training; WebSocket `/ws` | Good structure. Login and roles added (see section 7); still plain HTTP and a default device key |
| Imaging | `backend/app/imaging.py` | 4-bit unpack, quality score, model input | Shared with training (good: no train/serve mismatch) |
| Model wrapper | `backend/app/ml.py` | lazy load, demo mode, `reset()` (new) | OK |
| DB | `backend/app/db.py` | SQLite schema (4 tables) | OK for a prototype. Data is stored unencrypted |
| Simulator | `backend/tools/esp32_simulator.py` | fake ESP32 + R307 | lets the whole system run without hardware |
| Tests | `backend/tests/e2e.py` | 14 end-to-end API checks | needs the API and simulator running |
| Training | `ml/train_model.py` | de-dup → 70/15/15 split → 4 CNNs + 2 baselines → best by validation | Protocol is sound. Now writes live progress |
| Notebooks | `ml/notebooks/01-06` | original reference experiments | the 88 % result in 01 is inflated by leakage |
| Dashboard | `frontend/src/pages/*.jsx` (7 pages) | Dashboard, Live Scan, Patients, Patient detail, Scan history, **Models & Training (new)**, Device & Model | Clean, responsive |
| Launcher | `start_hemoscan.bat`, `stop_hemoscan.bat` | one-click setup and start | rewritten (section 8) |

**Open issues, in priority order**

1. Train and export the model (blocks real predictions).
2. Run the firmware on a real R307 + ESP32 and tune timeouts.
3. Collect R307 images with lab-confirmed groups (section 6): the Kaggle images come from a different scanner.
4. Security before any real patient data: HTTPS, an encrypted DB, a per-device secret. (Login and roles are done.)
5. Replace the home-made quality score with **NFIQ 2** (NIST, open source).

---

## 4. Can blood information be obtained from a fingerprint?

| Question | Answer |
|---|---|
| **Blood group (ABO/Rh)** from a fingerprint image | **Unproven.** Fingerprints form at about weeks 10-16 of pregnancy from genes plus conditions in the womb. ABO is set by one gene (chromosome 9) and RhD by the *RHD* gene. Many small studies in dermatoglyphics report *statistical* links (for example, loop frequency differing between groups), but the results are inconsistent between populations and no biological mechanism is known. Kaggle-style CNN results of 80-95 % usually come from datasets with no person IDs, where the same person's fingers can sit in both train and test sets. |
| **Haemoglobin, SpO₂, glucose** from a fingerprint image | **No.** A ridge image only records skin surface shape. Blood values need light passing *through* tissue (PPG or spectroscopy). Example: pulse oximeters use red + infrared LEDs, and multi-wavelength devices estimate haemoglobin non-invasively. |
| What can a fingerprint do reliably here? | **Identify the patient** (the R307 does this on the sensor), so every scan and lab result is linked to the right record automatically. |

**How HemoScan should present this academically:**

1. Report test accuracy next to the **chance level (12.5 %)** and the **majority-class baseline**. The training script already does both.
2. Report the **macro-F1** score and the confusion matrix, not only accuracy (the classes are imbalanced: A+ has 565 images, A− has 1,009).
3. Collect a **person-level split** in your own data (every finger of one person stays in one split).
4. Use the dashboard's *Model vs lab* agreement on real R307 scans as the final, honest metric.

If you want the project to actually measure blood, add a PPG sensor and an LSTM (section 5.4).

---

## 5. Models: which ones, why, and how they work in HemoScan

### 5.1 Models already built into `ml/train_model.py`

| Model | Type | Input | Params (approx.) | Role |
|---|---|---|---|---|
| **VGG-light** | CNN from scratch: 4 blocks × 2 conv (32→256 filters) + BatchNorm, Dense 512→256→8 | 64×64 | ≈ 3.4 M | **Default deployable model.** Fast on CPU |
| **ResNet-small** | CNN from scratch with residual (skip) connections | 64×64 | ≈ 2.8 M | trains deeper networks without vanishing gradients |
| **MobileNetV2 (transfer)** | open-source ImageNet weights, frozen backbone + new head | 96×96 | ≈ 2.6 M (0.3 M trainable) | light, could later run on a phone or edge device |
| **ResNet50 (transfer)** | open-source ImageNet weights, frozen backbone + new head | 96×96 | ≈ 24 M (0.5 M trainable) | strongest generic features; the reference notebook reports ≈ 81 % |
| HOG + SVM | classical baseline | 64×64 | — | shows whether deep learning beats hand-made features |
| Majority class | baseline | — | — | the "always guess the commonest group" score to beat |

The best model by *validation* accuracy is exported automatically as `backend/models/fingerprint_model.h5`.
Its test numbers go to `metrics.json`, which the **Models & Training** tab displays.

### 5.2 How the CNN works on a fingerprint (step by step)

```
R307 image 288×256 grey
  → contrast stretch (1st-99th percentile) → resize 64×64 → copy to 3 channels → divide by 255
  → Conv block 1 (32 filters)   learns ridge edges and ridge direction
  → Conv block 2 (64)           learns ridge endings and bifurcations (minutiae-like)
  → Conv block 3 (128)          learns local ridge flow, cores and deltas
  → Conv block 4 (256)          learns the overall pattern: loop / whorl / arch, ridge density
  → Flatten → Dense 512 → Dense 256 (dropout 0.5 each, against overfitting)
  → Dense 8 + softmax           probabilities for A+ A− AB+ AB− B+ B− O+ O−
```

The diagram is in `docs/architecture/07_cnn_architecture.md`.

**Minimal code example: build, train and predict**

```python
from tensorflow.keras import layers, models

def vgg_light(size=64, n_classes=8):
    x = inp = layers.Input((size, size, 3))
    for f in (32, 64, 128, 256):
        for _ in range(2):
            x = layers.Conv2D(f, 3, padding="same", use_bias=False)(x)
            x = layers.ReLU()(layers.BatchNormalization()(x))
        x = layers.MaxPooling2D(2)(x)
    x = layers.Dropout(0.5)(layers.Dense(512, activation="relu")(layers.Flatten()(x)))
    x = layers.Dropout(0.5)(layers.Dense(256, activation="relu")(x))
    return models.Model(inp, layers.Dense(n_classes, activation="softmax")(x))

model = vgg_light()
model.compile(optimizer="adam", loss="categorical_crossentropy", metrics=["accuracy"])
model.fit(X_train, y_train_onehot, validation_data=(X_val, y_val_onehot), epochs=25, batch_size=32)

# prediction for one sensor image (exactly what the API does)
from app.imaging import to_model_input
p = model.predict(to_model_input(gray_image))[0]          # 8 probabilities
CLASSES = ["A+", "A-", "AB+", "AB-", "B+", "B-", "O+", "O-"]
print(CLASSES[p.argmax()], f"{p.max():.0%}")
```

**Using the deployed model through the API (no code changes needed)**

```bash
curl -F "file=@ml/data/dataset_blood_group/O+/cluster_6_1004.BMP" http://localhost:8000/api/scans/upload
# illustrative response shape → {"predicted": "O+", "confidence": 0.71, "probs": {...}, "quality": 64.2, "status": "pending", ...}
```

### 5.3 Use-case example (end to end)

> **Scenario: blood-donation camp pre-screening.**
> 1. The operator registers a donor (*Patients → Add*) and enrols the right index finger (*Enrol fingerprint*: two presses, stored in R307 slot 12).
> 2. *Live Scan → Start capture*. The donor places the finger. About 10 s later the dashboard shows **predicted B+ · 63 % · quality 71 · top-4 B+, O+, A+, AB+**, linked to the donor automatically by the R307 match.
> 3. The lab runs the standard tile test: **B+**. The operator presses *Confirm → B+*. The donor record is filled in and the *Model vs lab* KPI updates.
> 4. Next visit: the finger alone identifies the donor, and the record with the lab-confirmed group opens. No re-typing, no mix-ups.
>
> The value delivered is **fast identification plus a provisional estimate**, with the lab result always the final word.

### 5.4 LSTM: where it fits and where it doesn't

| Option | Verdict |
|---|---|
| LSTM on a fingerprint image | **Not recommended.** An image has no time order. Treating rows as a "sequence" (CNN-LSTM) has been tried in papers, but gives no clear gain over a plain CNN and is slower. |
| LSTM on the **training curve** | Not needed: early stopping already handles this. |
| **1-D CNN + LSTM on a PPG signal**, for haemoglobin, SpO₂ and heart rate | **This is the right use.** Add a MAX30102 sensor (≈ ₹250) to the ESP32 over I²C. A PPG signal is a time series, which is exactly what LSTMs are for. It would give the project a *real* blood measurement next to the blood-group screening. |

Extension design: `docs/architecture/10_future_extensions.md`.

**CNN-LSTM for a PPG signal (haemoglobin regression)**

```python
from tensorflow.keras import layers, models
# input: 10 s at 100 Hz, 2 channels (red, infrared) → shape (1000, 2)
inp = layers.Input((1000, 2))
x = layers.Conv1D(32, 7, activation="relu", padding="same")(inp)   # pulse-shape features
x = layers.MaxPooling1D(2)(x)
x = layers.Conv1D(64, 5, activation="relu", padding="same")(x)
x = layers.MaxPooling1D(2)(x)                                      # → (250, 64)
x = layers.Bidirectional(layers.LSTM(64))(x)                       # beat-to-beat dynamics
x = layers.Dense(32, activation="relu")(x)
hb = layers.Dense(1, name="hb_g_dl")(x)                            # haemoglobin in g/dL
model = models.Model(inp, hb)
model.compile(optimizer="adam", loss="mae")                       # report MAE in g/dL against lab Hb
```

Labels must come from lab haemoglobin taken at the same visit. That needs your own data collection with
ethics approval. A typical published target is an MAE below about 1 g/dL.

### 5.5 Open-source models and tools you can use

| Name | Licence | Use in HemoScan |
|---|---|---|
| **Keras Applications**: MobileNetV2/V3, EfficientNet B0-B7 / V2, ResNet50, DenseNet121, ConvNeXt-Tiny | Apache 2.0, ImageNet weights | more transfer-learning candidates. Add one line to `CANDIDATES`. EfficientNetB0 is the best next one to try |
| **NIST NFIQ 2** | open source (NIST) | standard fingerprint quality score 0-100. Replace `imaging.quality()` with it |
| **NIST NBIS** (MINDTCT, PCASYS) | public domain | minutiae extraction; pattern-class (arch / loop / whorl) labels as an extra feature |
| **SourceAFIS** | Apache 2.0 | software matcher, if you ever drop on-sensor matching |
| **FingerNet** | research code (GitHub) | CNN minutiae extraction |
| `fingerprint-enhancer` (PyPI) | open source | Gabor ridge enhancement before the CNN. Worth an ablation test |
| PyTorch `timm` (ViT, Swin) | Apache 2.0 | only if you move to PyTorch. Overkill for 6,000 images |

**Recommendation:** keep the CNN as the main model. Add **EfficientNetB0** as a fifth candidate. Add NFIQ 2
for quality. Add the PPG + CNN-LSTM path only if you want a real blood-measurement feature.

---

## 6. Datasets

| Dataset | Content | Blood-group labels? | Use |
|---|---|---|---|
| **Finger Print Based Blood Group Dataset** (Kaggle), **in use** | 6,000 BMP, 8 groups. A+ 565 · A− 1,009 · AB+ 708 · AB− 761 · B+ 652 · B− 741 · O+ 852 · O− 712. 5,956 images at 103×96 and 44 at 298×241. 11 duplicate groups | ✅ | main training data. Origin and scanner undocumented, no person IDs |
| **SOCOFing** (Sokoto Coventry, Kaggle) | 6,000 prints from 600 people, 10 fingers each, labelled gender / hand / finger, plus altered versions | ❌ | pre-train the CNN on fingerprints (e.g. a finger-type task) before fine-tuning on blood group; robustness tests |
| **FVC2000 / 2002 / 2004** | verification databases, several sensors, 8 impressions per finger | ❌ | sensor variety, quality and matching experiments |
| **NIST SD302** | multi-sensor fingerprints | ❌ | cross-sensor robustness. Check NIST's licence terms |
| **NIST SD4** | 4,000 rolled prints labelled with 5 pattern classes (A, L, R, T, W) | ❌ | pattern-type classifier. NIST has withdrawn several older special databases from public download, so check availability |
| **MIMIC-III Waveform (matched subset)**, PhysioNet | ICU PPG waveforms + lab values including haemoglobin | Hb ✅ | only for the PPG/LSTM extension. Needs credentialed access and a training course |
| **Your own R307 dataset** (most important) | R307 captures + lab-confirmed group, collected with the dashboard's confirm workflow | ✅ | the only data that matches your real sensor. Target ≥ 100 people per group, 2+ fingers each, person-level split, consent form and ethics approval |

Getting the Kaggle dataset onto a new PC: download *Finger Print Based Blood Group Dataset* and extract the 8
folders into `ml/data/dataset_blood_group/`.

---

## 7. Dashboard

**Stack.** The dashboard is **React 18 + Vite, built and served in development with Node.js**. The backend stays
in **Python (FastAPI)**, because TensorFlow, OpenCV and the training script are Python. A Node.js backend
would have to call Python for every prediction anyway, adding a second server with no benefit. If your
syllabus requires a Node.js server, the clean option is a thin Express gateway (login and sessions) in front
of FastAPI. That is a decision for you (section 10).

**Pages**

| Tab | Shows |
|---|---|
| Dashboard | patients, scans, pending reviews, *Model vs lab* agreement, scans per day, patients by group |
| Live Scan | start capture on the ESP32 → live progress → result with probabilities. **This is the tab for checking the project's objective on a real finger** |
| Patients / Patient detail | records, enrolment, scan history, ABO/Rh compatibility chart |
| Scan History | review queue: confirm or reject against the lab result |
| **Models & Training (new)** | selected model, test accuracy, macro-F1, chance level · **live graph of validation accuracy per epoch for every model** · progress bar and log · model comparison (validation vs test) · per-class precision / recall / F1 · confusion matrix · *Train all models* / *Stop* |
| Device & Model | ESP32 online state, sensor OK, firmware settings, recent commands |

**Users and roles (added).** The first visit shows *Create admin account*; the admin then adds users in the **Users** tab.
Passwords are stored as PBKDF2-SHA256 hashes and sessions are signed tokens valid for 12 hours (standard library only).
Each role sees only its own tabs and buttons, and the API refuses anything else (HTTP 403):

| Role | Can do |
|---|---|
| admin | everything: users, training, devices, deletes |
| doctor | patients (create/edit), live scan, confirm results, assign scans |
| lab_tech | view everything; confirm or reject predictions against the lab report |
| operator | register patients, enrol fingerprints, run scans; cannot confirm results |

Full matrix and login flow: `docs/architecture/11_auth_and_roles.md`. Still **not** done: HTTPS and encrypted storage.

**How the live graph works:** `train_model.py` writes `backend/models/training_progress.json` after every
epoch (Keras callback). The API serves it at `GET /api/training`, and the page polls it every 2 s while
training runs. When training finishes, the API reloads the new model without a restart. Until the first
training run, the comparison chart shows the original notebooks' reported numbers, clearly labelled
*reference*.

---

## 8. One-click setup (`start_hemoscan.bat`)

| Step | Behaviour |
|---|---|
| Python | finds 3.11 → 3.10 → 3.9 → 3.8 via the `py` launcher, the usual install folders, then PATH. If none: `winget install Python.Python.3.11` |
| Node | needs v18+. If missing or older: `winget install OpenJS.NodeJS.LTS` |
| `.venv` | rebuilt automatically if broken (as on this PC) |
| Packages | re-installed if any of TensorFlow / FastAPI / OpenCV / scikit-learn fails to import |
| Dashboard | `npm install` once; `npm run build` whenever the source is newer than the build |
| Model | uses `fingerprint_model.h5` if present, otherwise DEMO mode |
| Start | API window, optional ESP32 simulator, waits for `/api/health`, opens the browser |
| Arguments | `check` (report only) · `nosim` (real ESP32) · `train` (train before starting) |

Flow diagram: `docs/architecture/09_setup_launcher.md`.
Not automated: the dataset download (Kaggle needs a login), the firmware flashing (Arduino IDE), and the Windows Firewall rule for port 8000.

---

## 9. Architecture diagrams (`docs/architecture/`)

1. System overview · 2. Hardware wiring + firmware states · 3. Live capture sequence · 4. Enrolment and
identification · 5. ML training pipeline · 6. Inference pipeline · 7. CNN layers · 8. Database ER diagram ·
9. Setup launcher flow · 10. Future: PPG + CNN-LSTM · 11. Login and user roles.

---

## 10. Next steps and decisions needed

| # | Step | Owner |
|---|---|---|
| 1 | Run `start_hemoscan.bat` (installs Python 3.11, rebuilds the environment) | you, about 15 min |
| 2 | *Models & Training → Train all models* (CPU; estimated 1-3 h for all four models, not measured) | automatic |
| 3 | Flash the firmware, test with the real R307, tune timeouts | you + hardware |
| 4 | Begin collecting R307 + lab-confirmed data | you |

**Decisions for you**

1. ~~User sections~~ — done: admin / doctor / lab technician / operator, FastAPI-enforced (section 7). Tell me if you want different roles.
2. ~~Node.js backend~~ — kept FastAPI only; the dashboard is React on Node (Vite).
3. **PPG extension:** add a MAX30102 + CNN-LSTM for haemoglobin / SpO₂, or keep the scope to blood-group screening?
4. **GPU training:** set up WSL2 + CUDA to use the RTX 3050, or stay on CPU?

---

*Disclaimer: HemoScan is an experimental screening aid. Predicting blood group from a fingerprint is not an
established medical method. Always confirm with a laboratory test before any clinical decision or transfusion.*
