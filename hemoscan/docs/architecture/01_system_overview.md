# 1. System overview

```mermaid
flowchart LR
    subgraph Edge["Hardware (bedside)"]
        F([Finger]) --> R307["R307 optical sensor<br/>256x288 px, 4-bit grey<br/>stores 200 templates"]
        R307 -- "UART 57600 baud" --> ESP["ESP32<br/>hemoscan_esp32.ino"]
    end

    subgraph Server["Laptop / server (Python)"]
        API["FastAPI app<br/>backend/app/main.py"]
        IMG["imaging.py<br/>unpack · quality · resize"]
        ML["ml.py<br/>Keras CNN"]
        DB[("SQLite<br/>hemoscan.db")]
        FS[("scan PNGs<br/>backend/data/scans")]
        TR["ml/train_model.py<br/>trains + compares models"]
        HUB["hub.py<br/>WebSocket broadcast"]
    end

    subgraph Client["Browser (React + Vite, built with Node.js)"]
        UI["Dashboard · Live Scan · Patients<br/>Scan History · Models & Training · Device"]
    end

    ESP -- "HTTPS/HTTP over WiFi<br/>heartbeat · poll · scan upload" --> API
    API --> IMG --> ML
    API <--> DB
    API --> FS
    API -- "spawns" --> TR
    TR -- "fingerprint_model.h5<br/>metrics.json · training_progress.json" --> ML
    API --> HUB -- "WS /ws live events" --> UI
    UI -- "REST /api/*" --> API
    DS[("Kaggle dataset<br/>6,000 BMP, 8 groups")] --> TR
```

**Key design choices**

* The ESP32 only makes *outgoing* requests (it polls for commands every second), so no router or port-forwarding setup is needed.
* All ML runs in Python on the server — the ESP32 has neither the RAM nor the speed for a CNN.
* The same preprocessing function (`imaging.to_model_input`) is used in training and live prediction, so the model sees identical inputs in both.
