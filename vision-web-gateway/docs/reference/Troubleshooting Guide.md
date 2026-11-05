---
tags: [yolo-gateway, troubleshooting]
---
# Troubleshooting guide

## 1. Where are the errors?

| What | Where |
|---|---|
| Why a job failed | Open the job in Queue and jobs: the **Result** line has the last log lines, the log box the last 40. The full log is `jobs/<id>/log.txt`. |
| Server errors (Python exceptions, uvicorn) | The console window where `app.py` runs (or the Task Scheduler output). |
| Notification errors | Admin > Notifications, line under the form (`last_notify_error`). |
| Browser | F12 > Network (the failing `/api/...` request and its JSON `detail`), Console for JavaScript errors. |
| Config | `configuration/web.yaml` (read on every use, no restart needed except host/port), `configuration/config.yaml`. |
| Database | `data/gateway.db` (SQLite). Stop the server before editing it by hand. |
| Reachability | `http://<server>:8000/` from another PC; if blocked, the Windows firewall rule for TCP 8000 (see `docs/README.md`). |

## 2. Symptom -> first place to look

| Symptom | Likely cause | Look at |
|---|---|---|
| Cannot sign in | wrong password, user inactive, 5-failure lock | [[0.1 Sign in and sign out]], [[4.1 Users]] |
| Page returns to the login form | cookie expired (12 h) or user deactivated | [[0.1 Sign in and sign out]] |
| 403 `admin only` | normal user on an admin route | [[4.1 Users]] |
| Upload refused (413 / 507 / 429) | zip too big, disk low, too many datasets | [[2.1 Datasets]], `web.yaml` |
| Upload refused with a label message | bad `classes.txt` or label lines | [[2.1 Datasets]] |
| Job stays queued | another job runs (share 100), or `app.py` is not running | [[0.2 Background workers]], [[4.3 Server load]] |
| Job failed within a minute with `Download failure` / `SSLCertVerificationError` | model `.pt` missing and the proxy re-signs HTTPS | section 3 below, [[4.2 Models]] |
| Job failed: `the server restarted while this job was running` | `app.py` stopped or PC rebooted | [[0.2 Background workers]] |
| Job failed: `CUDA out of memory` | batch too big for the share | lower Batch, smaller model, lower share ([[4.3 Server load]]) |
| Job failed: `training ended without a best.pt` | no epoch completed | `jobs/<id>/log.txt` |
| Job failed right at the start with a settings or config error | a hand-edited `config.yaml` or a bad setting | [[3.1 New training]] |
| Progress bar stuck | long first epoch, dataset caching to RAM/disk | the log box (it moves while training runs) |
| Charts empty | no epoch finished yet | [[1.3 Results charts and advice]] |
| Predict fails or is slow | CPU inference, ffmpeg missing, file too big | [[1.4 Predict]] |
| No email / Teams message | SMTP or webhook wrong, user without email | [[4.4 Notifications]] |
| Models table: every Download shows an error | server cannot reach GitHub | section 3 below |
| Result Download answers `this job has no result` | job is not `done` | [[1.2 Job detail]] |

## 3. Model download blocked (GitHub / company proxy)

The server downloads `.pt` weights from `github.com` and `release-assets.githubusercontent.com`.

- **Quick workaround:** copy the `.pt` (for example `yolo26m.pt`) from a PC that can download it into `<install folder>\models\`. Admin > Models then shows it as downloaded.
- **Certificate error** (`self-signed certificate in certificate chain`): the company network re-signs HTTPS. Python does not trust the company root. Run `.venv\Scripts\pip install pip-system-certs` (Python then uses the Windows certificate store), or set the environment variables `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE` to the company root `.pem` before starting `app.py`. Do not disable verification.
- **Plain block** (timeouts): ask IT to allow `github.com` and `*.githubusercontent.com` on 443, or set `HTTPS_PROXY`.
- Admin > Models only shows the first 150 characters of the error; the job log shows the full one.

## 4. Useful read-only checks

Run on the server with the gateway stopped or not (read-only open). Replace the path if needed.

```powershell
# jobs and their state
.venv\Scripts\python -c "import sqlite3;c=sqlite3.connect('file:data/gateway.db?mode=ro',uri=True);[print(r) for r in c.execute('select id,owner,state,model,epochs,target,detail from jobs order by created desc limit 20')]"

# users (no password hashes)
.venv\Scripts\python -c "import sqlite3;c=sqlite3.connect('file:data/gateway.db?mode=ro',uri=True);[print(r) for r in c.execute('select name,role,email,active from users')]"

# saved settings (the SMTP password is in here: do not paste the output anywhere)
.venv\Scripts\python -c "import sqlite3;c=sqlite3.connect('file:data/gateway.db?mode=ro',uri=True);[print(r[0]) for r in c.execute('select key from settings')]"

# hardware and what auto would pick
.venv\Scripts\python scripts\core.py

# self-check of the whole API (runs a real 1-epoch CPU training in a temp folder)
.venv\Scripts\python scripts\test_web.py
```

Use only SELECT while investigating. Deleting a job or dataset is done from the page (admin), not by deleting folders, so the database and the disk stay in step.
