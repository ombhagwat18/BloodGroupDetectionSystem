# 4. Enrolment and identification

The R307 does the *identity* matching itself (minutiae templates stored on the sensor);
the CNN only does the *blood-group* estimate. These are two separate jobs.

```mermaid
flowchart TD
    A[Patient page → Enrol fingerprint] --> B{Patient already has a slot?}
    B -- yes --> C[reuse slot]
    B -- no --> D[pick first free slot 1-200]
    C --> E[queue command enroll + slot]
    D --> E
    E --> F[ESP32: two presses of the same finger]
    F --> G[R307 RegModel → StoreChar slot]
    G --> H[POST /api/device/enroll_result]
    H --> I[(patients.sensor_slot = slot)]

    J[Any later capture] --> K[R307 Search]
    K -- match --> L[slot N + score]
    K -- no match --> M[slot 0 → scan is Unassigned]
    L --> N[(look up patient with sensor_slot = N)]
    N --> O[scan linked to patient automatically]
```
