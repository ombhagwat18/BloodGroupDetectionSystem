# 7. VGG-light CNN (default model)

```mermaid
flowchart TD
    I["Input 64×64×3"] --> B1
    subgraph B1["Block 1 — 32 filters"]
        c11[Conv 3×3 → BN → ReLU] --> c12[Conv 3×3 → BN → ReLU] --> p1[MaxPool 2×2 → 32×32]
    end
    B1 --> B2
    subgraph B2["Block 2 — 64 filters"]
        c21[Conv → BN → ReLU] --> c22[Conv → BN → ReLU] --> p2[MaxPool → 16×16]
    end
    B2 --> B3
    subgraph B3["Block 3 — 128 filters"]
        c31[Conv → BN → ReLU] --> c32[Conv → BN → ReLU] --> p3[MaxPool → 8×8]
    end
    B3 --> B4
    subgraph B4["Block 4 — 256 filters"]
        c41[Conv → BN → ReLU] --> c42[Conv → BN → ReLU] --> p4[MaxPool → 4×4]
    end
    B4 --> FL["Flatten 4×4×256 = 4,096"]
    FL --> D1["Dense 512 · ReLU · Dropout 0.5"]
    D1 --> D2["Dense 256 · ReLU · Dropout 0.5"]
    D2 --> OUT["Dense 8 · softmax"]
```

What each part learns on a fingerprint: block 1 → ridge edges and orientation; block 2 → ridge
endings and bifurcations (minutiae-like shapes); blocks 3-4 → larger structures such as cores,
deltas and the loop / whorl / arch pattern; dense layers → map those features to the 8 groups.
Optimiser Adam (lr 5e-4), loss categorical cross-entropy, batch 32.
