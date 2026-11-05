---
tags: [yolo-gateway, catalog]
---
# Table Catalog

Every place the app keeps state: SQLite tables in `data/gateway.db`, folders on disk, config files and RAM structures. One heading per store. Row counts are not listed here because the live database is on the server; see the read-only queries in [[Troubleshooting Guide]].

## SQLite tables (`data/gateway.db`)

### users

- **What it holds:** Accounts: `name` (PK), `pw` (scrypt salt:hash), `role` (admin or user), `email`, `active` (1/0).
- **Good to know:** SQLite `data/gateway.db`. Created at start-up; the first admin is added when the table is empty.
- **Written from menus:** [[0.2 Background workers|0.2 Background workers]], [[4.1 Users|4.1 Users]], [[5.1 Account|5.1 Account]]
- **Read from menus:** [[0.1 Sign in and sign out|0.1 Sign in and sign out]], [[0.2 Background workers|0.2 Background workers]], [[4.1 Users|4.1 Users]], [[4.4 Notifications|4.4 Notifications]]
- **Functions that write it:** [[Function Catalog#startup|startup]]

### sessions

- **What it holds:** Sign-in cookies: `token` (sha256 of the cookie value), `name`, `expires` (epoch, 12 h after login).
- **Good to know:** SQLite. Expired rows are deleted by cleanup(); deactivating or deleting a user deletes that user's rows.
- **Written from menus:** [[0.1 Sign in and sign out|0.1 Sign in and sign out]], [[0.2 Background workers|0.2 Background workers]], [[4.1 Users|4.1 Users]]
- **Read from menus:** -
- **Functions that write it:** [[Function Catalog#cleanup|cleanup]]

### settings

- **What it holds:** Key/value: `smtp_host/port/security/user/password/from`, `teams_url`, `public_url`, `notify_email`, `notify_teams`, `job_share`, `models` (comma list of what users may pick), `last_notify_error`.
- **Good to know:** SQLite. The SMTP password is stored here as plain text: keep `data/` private. A missing key falls back to `SETTING_DEFAULTS` in web.py (and `models` to web.yaml).
- **Written from menus:** [[0.2 Background workers|0.2 Background workers]], [[4.2 Models|4.2 Models]], [[4.3 Server load|4.3 Server load]], [[4.4 Notifications|4.4 Notifications]]
- **Read from menus:** [[0.1 Sign in and sign out|0.1 Sign in and sign out]], [[0.2 Background workers|0.2 Background workers]], [[3.1 New training|3.1 New training]], [[4.2 Models|4.2 Models]], [[4.3 Server load|4.3 Server load]], [[4.4 Notifications|4.4 Notifications]]
- **Functions that write it:** [[Function Catalog#notify|notify]]

### jobs

- **What it holds:** One row per training: `id`, `owner`, `state` (queued, running, done, failed, cancelled), `model`, `epochs`, `note`, `created`, `started`, `finished`, `images`, `info` (dataset summary JSON), `detail` (result line or error), `frac` (progress 0 to 1), `dataset` (dataset id), `target` (mAP50 goal 0 to 1, NULL = none).
- **Good to know:** SQLite. `target` and `dataset` are added by an ALTER TABLE at start-up when an older database lacks them.
- **Written from menus:** [[0.2 Background workers|0.2 Background workers]], [[1.2 Job detail|1.2 Job detail]], [[3.1 New training|3.1 New training]]
- **Read from menus:** [[0.2 Background workers|0.2 Background workers]], [[1.1 Queue and jobs|1.1 Queue and jobs]], [[1.2 Job detail|1.2 Job detail]], [[1.3 Results charts and advice|1.3 Results charts and advice]], [[1.4 Predict|1.4 Predict]], [[2.1 Datasets|2.1 Datasets]], [[4.4 Notifications|4.4 Notifications]]
- **Functions that write it:** [[Function Catalog#finish|finish]], [[Function Catalog#run_job|run_job]], [[Function Catalog#cleanup|cleanup]], [[Function Catalog#startup|startup]]

### datasets

- **What it holds:** One row per saved dataset: `id` (d + date + random), `owner`, `name`, `created`, `images`, `info` (JSON: images, labeled, background, orphan_labels, classes with box counts), `bytes`.
- **Good to know:** SQLite. The files live in the datasets folder.
- **Written from menus:** [[2.1 Datasets|2.1 Datasets]], [[3.1 New training|3.1 New training]]
- **Read from menus:** [[1.2 Job detail|1.2 Job detail]], [[2.1 Datasets|2.1 Datasets]], [[3.1 New training|3.1 New training]]
- **Functions that write it:** [[Function Catalog#make_dataset|make_dataset]]

## Folders and files on disk

### jobs folder

- **What it holds:** `jobs/<id>/`: `config.yaml` (this job's own copy of the settings), `data/` (hard links of the dataset: `raw/`, later `dataset/` split, `classes.txt`), `runs/<run>/` (Ultralytics: `results.csv`, `weights/best.pt`, `args.yaml`, charts `*.png`), `log.txt`, `result.zip` (built on first download), `predict/<pid>/` (uploaded file and the drawn result).
- **Good to know:** Deleted with the job (admin Delete, or cleanup() after `keep_days`). `GATEWAY_HOME` env var moves it.
- **Written from menus:** [[0.2 Background workers|0.2 Background workers]], [[1.2 Job detail|1.2 Job detail]], [[1.4 Predict|1.4 Predict]], [[3.1 New training|3.1 New training]]
- **Read from menus:** [[1.2 Job detail|1.2 Job detail]], [[1.3 Results charts and advice|1.3 Results charts and advice]], [[1.4 Predict|1.4 Predict]]
- **Functions that write it:** [[Function Catalog#run_job|run_job]], [[Function Catalog#cleanup|cleanup]], [[Function Catalog#run_predict|run_predict]], [[Function Catalog#predict_worker|predict_worker]], [[Function Catalog#core.write_dataset_yaml|core.write_dataset_yaml]], [[Function Catalog#core.prepare_dataset|core.prepare_dataset]], [[Function Catalog#prepare_dataset.py|prepare_dataset.py]], [[Function Catalog#train.py|train.py]]

### datasets folder

- **What it holds:** `datasets/<id>/`: `raw/images`, `raw/labels`, `classes.txt` (the zip, flattened; the zip itself is deleted after unpacking).
- **Good to know:** Never deleted automatically; deleting a dataset removes the folder. Jobs hold hard links, so they survive it.
- **Written from menus:** [[2.1 Datasets|2.1 Datasets]], [[3.1 New training|3.1 New training]]
- **Read from menus:** -
- **Functions that write it:** [[Function Catalog#make_dataset|make_dataset]]

### models folder

- **What it holds:** `models/*.pt`: the weights Ultralytics starts from (e.g. `yolo26n.pt`).
- **Good to know:** Filled by Admin > Models > Download, by the first training that needs a missing file, or by copying a `.pt` in by hand.
- **Written from menus:** [[4.2 Models|4.2 Models]]
- **Read from menus:** [[0.2 Background workers|0.2 Background workers]], [[4.2 Models|4.2 Models]]
- **Functions that write it:** [[Function Catalog#fetch_model|fetch_model]]

### first admin file

- **What it holds:** `data/FIRST_ADMIN_PASSWORD.txt`: the first admin's password.
- **Good to know:** Written at the very first start, deleted when any user changes a password.
- **Written from menus:** [[0.2 Background workers|0.2 Background workers]], [[5.1 Account|5.1 Account]]
- **Read from menus:** -
- **Functions that write it:** [[Function Catalog#startup|startup]]

## Config files

### web.yaml

- **What it holds:** `configuration/web.yaml`: host, port, upload limits, min_images, max_epochs, max_active_per_user, keep_days, max_datasets_per_user, predict settings, starting list of models.
- **Good to know:** Read on every use (web_cfg()), so an edit applies without a restart, except host and port.
- **Written from menus:** -
- **Read from menus:** [[0.1 Sign in and sign out|0.1 Sign in and sign out]], [[0.2 Background workers|0.2 Background workers]], [[1.4 Predict|1.4 Predict]], [[2.1 Datasets|2.1 Datasets]], [[3.1 New training|3.1 New training]], [[4.2 Models|4.2 Models]]
- **Functions that write it:** -

### config.yaml

- **What it holds:** `configuration/config.yaml`: the training settings every job copies (model presets, split, train, predict).
- **Good to know:** Each job copies it to `jobs/<id>/config.yaml` at submit time; later edits never change a queued job.
- **Written from menus:** -
- **Read from menus:** [[0.1 Sign in and sign out|0.1 Sign in and sign out]], [[3.1 New training|3.1 New training]], [[4.2 Models|4.2 Models]]
- **Functions that write it:** -

## RAM (lost on restart)

### RAM running jobs

- **What it holds:** `LIVE` (progress, epoch, ETA start), `PROCS` (running subprocess), `CANCEL` (who asked to stop), `ACTIVE` (running jobs and their share).
- **Good to know:** Lost on restart; a job that was running is then marked failed by startup().
- **Written from menus:** [[0.2 Background workers|0.2 Background workers]], [[1.2 Job detail|1.2 Job detail]]
- **Read from menus:** [[1.1 Queue and jobs|1.1 Queue and jobs]], [[1.2 Job detail|1.2 Job detail]]
- **Functions that write it:** [[Function Catalog#finish|finish]], [[Function Catalog#run_job|run_job]], [[Function Catalog#job_thread|job_thread]], [[Function Catalog#dispatcher|dispatcher]]

### RAM predictions

- **What it holds:** `PRED`: state, progress, result and folder of every prediction, plus the queue `PQUEUE`.
- **Good to know:** Lost on restart (the files stay in `jobs/<id>/predict/`). Entries older than 1 day are dropped on the next predict upload.
- **Written from menus:** [[0.2 Background workers|0.2 Background workers]], [[1.2 Job detail|1.2 Job detail]], [[1.4 Predict|1.4 Predict]]
- **Read from menus:** [[1.4 Predict|1.4 Predict]]
- **Functions that write it:** [[Function Catalog#run_predict|run_predict]], [[Function Catalog#predict_worker|predict_worker]]

### RAM downloads

- **What it holds:** `DL`: model name to `downloading` or `error: ...` (first 150 characters).
- **Good to know:** Lost on restart; the entry disappears when the download works.
- **Written from menus:** [[4.2 Models|4.2 Models]]
- **Read from menus:** -
- **Functions that write it:** [[Function Catalog#fetch_model|fetch_model]]

### RAM login fails

- **What it holds:** `FAILS`: user name to the times of wrong passwords in the last 5 minutes.
- **Good to know:** Lost on restart (which also clears a lock).
- **Written from menus:** [[0.1 Sign in and sign out|0.1 Sign in and sign out]]
- **Read from menus:** -
- **Functions that write it:** -

### RAM model cache

- **What it holds:** `MODELS`: the YOLO model of the last job that was used for Predict.
- **Good to know:** One entry only; cleared when another job is used or the job is deleted.
- **Written from menus:** [[0.2 Background workers|0.2 Background workers]], [[1.2 Job detail|1.2 Job detail]], [[1.4 Predict|1.4 Predict]]
- **Read from menus:** -
- **Functions that write it:** [[Function Catalog#load_model|load_model]]
