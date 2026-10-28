# 6. Inference — sensor bytes to prediction

```mermaid
flowchart LR
    RAW["36,864 bytes<br/>2 pixels / byte"] --> U["unpack_r307()<br/>high nibble first · ×17"]
    UP["Manual upload<br/>PNG / JPG / BMP"] --> DEC["decode_image()"]
    U --> G["uint8 grey 288×256"]
    DEC --> G
    G --> Q["quality()<br/>contrast + ridge coverage → 0-100"]
    G --> PRE["to_model_input()<br/>1-99 % stretch → 64×64 → RGB → /255"]
    PRE --> CNN["Keras CNN"]
    CNN --> SM["softmax over<br/>A+ A- AB+ AB- B+ B- O+ O-"]
    SM --> R["predicted = argmax<br/>confidence = max prob<br/>top-4 bars"]
    Q --> FLAG{"quality ≥ 35?"}
    FLAG -- no --> W["flag: re-scan advised"]
    R --> STORE[("scan row · status pending")]
    W --> STORE
```

Modes (`backend/app/ml.py`): **model** = real file loaded · **demo** = random Dirichlet output, clearly labelled · **none** = scan stored without prediction.
