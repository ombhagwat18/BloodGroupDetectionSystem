# 5. ML training pipeline (`ml/train_model.py`)

```mermaid
flowchart TD
    D[("ml/data/dataset_blood_group<br/>8 folders · 6,000 BMP")] --> H["MD5 hash every file<br/>drop exact duplicates"]
    H --> S["Stratified split on ORIGINAL images<br/>70% train · 15% val · 15% test · seed 42"]
    S --> TR[Train set]
    S --> VA[Validation set]
    S --> TE[Test set — locked]
    TR --> AUG["Augment (train only)<br/>rotate ±4% · shift 6% · zoom 8%"]
    AUG --> P["to_model_input()<br/>contrast stretch · resize · 3 channels · [0,1]"]
    VA --> P
    P --> B1[Baselines:<br/>majority class · HOG + SVM]
    P --> M1[VGG-light CNN · 64px]
    P --> M2[ResNet-small CNN · 64px]
    P --> M3[MobileNetV2 transfer · 96px]
    P --> M4[ResNet50 transfer · 96px]
    M1 & M2 & M3 & M4 --> CB["Callbacks: EarlyStopping(val_acc)<br/>ReduceLROnPlateau · ProgressLogger"]
    CB -- every epoch --> LIVE[("training_progress.json<br/>→ Models page live graph")]
    CB --> SEL{"Highest VALIDATION<br/>accuracy"}
    SEL --> EX["Evaluate once on TEST set"]
    TE --> EX
    EX --> O1[("backend/models/fingerprint_model.h5")]
    EX --> O2[("metrics.json<br/>per-class · confusion matrix")]
    EX --> O3[("docs/model_comparison.png")]
```

Why the test set is touched only once: choosing a model by test accuracy would make the
test number optimistic. The reference notebook's 88 % has this kind of leak (augmented
copies of the same image ended up in both train and test).
