# ml/ — model training and reference material

```
ml/
├── train_model.py        trains the VGG-inspired CNN -> ../backend/models/fingerprint_model.h5
├── data/
│   ├── dataset_blood_group/   6,000 fingerprint BMPs, one folder per class (A+, A-, AB+, AB-, B+, B-, O+, O-)
│   └── sample_data.jpg
├── notebooks/            experiments (01 = the notebook HemoScan's model comes from; 02-06 compare other networks)
└── reference/
    ├── pretrained/       third-party ResNet50 .h5 (saved with Keras 3 - does not load in TensorFlow 2.13)
    ├── results/          accuracy/loss graphs and comparison tables from the reference project
    └── README_*.md, LICENSE, requirements_reference.txt
```

Train: `python ml/train_model.py --data ml/data/dataset_blood_group --epochs 10`
