# 10. Proposed extensions (not built yet)

## A. Haemoglobin / SpO₂ estimate with a PPG sensor + CNN-LSTM

A fingerprint *image* holds no information about the blood itself. Measuring something about the
blood (haemoglobin, SpO₂, heart rate) needs light passing *through* the fingertip. That is
photoplethysmography (PPG), from a sensor such as the MAX30102. A PPG signal is a **time series**,
and that is where an LSTM belongs.

```mermaid
flowchart LR
    FG([Fingertip]) --> MAX["MAX30102<br/>red + IR LEDs, 100 Hz"]
    MAX -- I²C --> ESP[ESP32]
    ESP -- "10 s window<br/>2 × 1,000 samples" --> API[FastAPI]
    API --> PRE["band-pass 0.5-5 Hz<br/>normalise · segment"]
    PRE --> CNN1D["1-D CNN<br/>pulse shape features"]
    CNN1D --> LSTM["LSTM / BiLSTM<br/>beat-to-beat dynamics"]
    LSTM --> HB["Hb g/dL (regression)<br/>+ anaemia flag"]
    HB --> UI[Dashboard]
    LAB[(lab Hb values)] -. training labels .-> LSTM
```

## B. Role-based user sections

```mermaid
flowchart LR
    L[Login] --> R{role}
    R -- admin --> A["Users · devices · model training"]
    R -- doctor --> D["Patients · scans · confirm results"]
    R -- lab_tech --> T["Enter lab results · review queue"]
    R -- operator --> O["Live scan only"]
```
