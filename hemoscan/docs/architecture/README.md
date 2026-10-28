# HemoScan — system architecture (Mermaid)

Each file holds one diagram as a ` ```mermaid ` block. They render on GitHub, in VS Code
(extension *Markdown Preview Mermaid Support*), and at <https://mermaid.live> (paste the block).

| # | File | Shows |
|---|---|---|
| 1 | [01_system_overview.md](01_system_overview.md) | All components and how they talk |
| 2 | [02_hardware.md](02_hardware.md) | R307 ↔ ESP32 wiring and firmware states |
| 3 | [03_capture_sequence.md](03_capture_sequence.md) | One live scan, button press → result on screen |
| 4 | [04_enrolment_identification.md](04_enrolment_identification.md) | Enrolling a patient's finger and recognising it later |
| 5 | [05_ml_training_pipeline.md](05_ml_training_pipeline.md) | Dataset → leak-free split → 4 CNNs → selected model |
| 6 | [06_inference_pipeline.md](06_inference_pipeline.md) | Raw sensor bytes → blood-group probabilities |
| 7 | [07_cnn_architecture.md](07_cnn_architecture.md) | Layers of the VGG-light CNN |
| 8 | [08_database_er.md](08_database_er.md) | SQLite tables and relations |
| 9 | [09_setup_launcher.md](09_setup_launcher.md) | What `start_hemoscan.bat` does on a new PC |
| 10 | [10_future_extensions.md](10_future_extensions.md) | Optional PPG sensor + LSTM for haemoglobin |
| 11 | [11_auth_and_roles.md](11_auth_and_roles.md) | Login flow and what each user role may do |
