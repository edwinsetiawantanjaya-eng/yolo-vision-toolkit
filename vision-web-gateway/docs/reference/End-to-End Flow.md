---
tags: [yolo-gateway, flow]
---
# End-to-End Flow

The life of one training, from the upload to the cleanup. Numbers in brackets point to the menu notes.

```mermaid
flowchart TD
    U(["User opens New training [3.1]"]):::user
    Z["Zip or saved dataset<br/>[2.1] make_dataset"]:::php
    S1[("datasets folder<br/>+ datasets row")]:::wr
    SUB["POST /api/jobs [3.1]<br/>submit()"]:::route
    CFG[("jobs/id/config.yaml<br/>+ data hard links")]:::wr
    Q[("jobs row<br/>state queued")]:::wr
    DSP{{"dispatcher [0.2]<br/>share fits?"}}:::sp
    RUN[("jobs row<br/>state running")]:::wr
    P1{{"prepare_dataset.py<br/>split train/val/test"}}:::sp
    P2{{"train.py<br/>Ultralytics"}}:::sp
    LOG[("log.txt + runs/results.csv<br/>live progress")]:::wr
    OK{{"best.pt exists?"}}:::sp
    JOB_DONE[("jobs row done<br/>detail = mAP50")]:::wr
    JOB_FAIL[("jobs row failed<br/>detail = last log lines")]:::wr
    JOB_CANCEL[("jobs row cancelled")]:::wr
    NOT{{"notify [4.4]<br/>email + Teams"}}:::sp
    VIEW["Charts and advice [1.3]<br/>Download [1.2]<br/>Predict [1.4]"]:::php
    CLN{{"cleanup after keep_days<br/>or admin Delete [1.2]"}}:::sp
    U --> Z --> S1 --> SUB --> CFG --> Q --> DSP --> RUN --> P1 --> P2 --> LOG --> OK
    OK -->|yes| JOB_DONE
    OK -->|no or error| JOB_FAIL
    RUN -.->|"Cancel 1.2"| JOB_CANCEL
    JOB_DONE --> NOT
    JOB_FAIL --> NOT
    JOB_CANCEL --> NOT
    JOB_DONE --> VIEW
    JOB_DONE --> CLN
    JOB_FAIL --> CLN
    JOB_CANCEL --> CLN

    classDef user fill:#eeeeee,stroke:#888888,color:#000000
    classDef route fill:#efe4fa,stroke:#8855cc,color:#000000
    classDef php fill:#e3f4e8,stroke:#33aa55,color:#000000
    classDef sp fill:#fff1c2,stroke:#cc9900,color:#000000
    classDef wr fill:#fbdcdc,stroke:#dd3333,color:#000000
    classDef rd fill:#dce9fb,stroke:#3377cc,color:#000000
    classDef note fill:#ffffff,stroke:#999999,color:#333333,stroke-dasharray: 4 3
```

## What hands data to the next step

| From | To | Through |
|---|---|---|
| Upload ([[2.1 Datasets]]) | Training ([[3.1 New training]]) | `datasets/<id>/` hard-linked into `jobs/<id>/data/` |
| Form values ([[3.1 New training]]) | `prepare_dataset.py`, `train.py` | `jobs/<id>/config.yaml` (env `YOLO_CONFIG`) |
| `prepare_dataset.py` | `train.py` | `data/dataset/{train,val,test}` and `dataset.yaml` |
| `train.py` | Charts ([[1.3 Results charts and advice]]) | `runs/<run>/results.csv` |
| `train.py` | Predict ([[1.4 Predict]]), Download ([[1.2 Job detail]]) | `runs/<run>/weights/best.pt` |
| Job end | Notifications ([[4.4 Notifications]]) | `jobs` row (state, detail) read by `notify()` |
| Server load ([[4.3 Server load]]) | Dispatcher | `settings.job_share`, read when the next job starts |
| Models ([[4.2 Models]]) | New training | `settings.models` list and `models/*.pt` files |

## States of a job

| State | Set by | Next |
|---|---|---|
| queued | `submit()` | running (dispatcher) or cancelled |
| running | `run_job()` | done, failed or cancelled; failed by `startup()` if the server restarts |
| done | `finish()` when `best.pt` exists | deleted after `keep_days` or by admin |
| failed | `finish()` on a non-zero exit, missing best.pt, gateway error or restart | same |
| cancelled | `cancel()` (queued) or `run_job()` after the kill (running) | same |
