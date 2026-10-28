# 11. Login and user roles

```mermaid
sequenceDiagram
    participant U as User (browser)
    participant UI as React dashboard
    participant API as FastAPI
    participant DB as SQLite (users)
    U->>UI: open dashboard
    UI->>API: GET /api/auth/status
    API-->>UI: needs_setup (true only while there are no users)
    alt first start
        U->>UI: choose admin username + password
        UI->>API: POST /api/auth/setup
        API->>DB: store PBKDF2 hash, role = admin
    else normal start
        U->>UI: username + password
        UI->>API: POST /api/auth/login
        API->>DB: verify hash, active = 1
    end
    API-->>UI: signed token (12 h) + user
    UI->>API: every call with "Authorization: Bearer token"
    API->>API: check signature, expiry, active, role
    API-->>UI: 200, or 401 (sign in again) / 403 (role not allowed)
    UI->>API: WS /ws?token=...  and  img src ?token=...
```

```mermaid
flowchart LR
    subgraph roles[Roles]
        A[admin]
        D[doctor]
        L[lab_tech]
        O[operator]
    end
    A --> everything[All tabs + Users + training + Device]
    D --> clinical[Patients, Live Scan, confirm results, assign scans]
    L --> review[View data, confirm / reject against lab report]
    O --> intake[Register patients, enrol fingerprints, run scans]
    ESP[ESP32 / simulator] -. "X-Device-Key, no login" .-> device[/api/device/*/]
```

| Capability | admin | doctor | lab_tech | operator |
|---|:-:|:-:|:-:|:-:|
| Dashboard, Patients, Scan History, Models (view) | ✔ | ✔ | ✔ | ✔ |
| Live Scan, enrol fingerprint, upload image | ✔ | ✔ | | ✔ |
| Create patient | ✔ | ✔ | | ✔ |
| Edit patient | ✔ | ✔ | | |
| Delete patient / scan | ✔ | | | |
| Confirm / reject against lab result | ✔ | ✔ | ✔ | |
| Assign a scan to a patient | ✔ | ✔ | | |
| Start / stop training | ✔ | | | |
| Device & Model tab, Users tab | ✔ | | | |

The dashboard hides what a role cannot use, but the **API enforces it** (`backend/app/main.py`, `require(...)`).
