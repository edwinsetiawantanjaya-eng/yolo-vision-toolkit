---
tags: [yolo-gateway, catalog]
---
# Function Catalog

The Python functions, subprocess steps, browser functions and external systems that the menus use (the equivalent of a stored-procedure catalog). One heading per object. The yellow hexagons in the flow charts are these objects. Route handlers (the green boxes) are listed in each menu note's Action map.

## Access

### guard

- **Purpose:** HTTP middleware. Refuses a big anonymous upload (401) or a file over `max_upload_mb` / `max_predict_mb` (413) before it is read, and adds `X-Content-Type-Options` and `X-Frame-Options` to every answer.
- **Parameters:** request
- **Used from menus:** none directly (called by another function)
- **Stores read:** [[Table Catalog#sessions|sessions]], [[Table Catalog#users|users]], [[Table Catalog#web.yaml|web.yaml]]
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 599 (file has 1168 lines)

### user_from_cookie

- **Purpose:** Finds the signed-in user from the `gw_session` cookie (sha256 lookup in sessions joined with users, not expired, active).
- **Parameters:** request
- **Used from menus:** none directly (called by another function)
- **Stores read:** [[Table Catalog#sessions|sessions]], [[Table Catalog#users|users]]
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 122 (file has 1168 lines)

### current_user

- **Purpose:** FastAPI dependency of every API route: the user, or 401 `sign in first`.
- **Parameters:** request
- **Used from menus:** none directly (called by another function)
- **Stores read:** [[Table Catalog#sessions|sessions]], [[Table Catalog#users|users]]
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 131 (file has 1168 lines)

### admin_user

- **Purpose:** FastAPI dependency of admin routes: the user, or 403 `admin only`.
- **Parameters:** current_user
- **Used from menus:** none directly (called by another function)
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 138 (file has 1168 lines)

### hash_pw

- **Purpose:** scrypt hash (n=2^14, r=8, p=1) with a random 16-byte salt, stored as `salt:hash`.
- **Parameters:** pw, salt
- **Used from menus:** [[4.1 Users|4.1 Users]], [[5.1 Account|5.1 Account]]
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 110 (file has 1168 lines)

### check_pw

- **Purpose:** Constant-time password check against the stored `salt:hash`.
- **Parameters:** pw, stored
- **Used from menus:** [[0.1 Sign in and sign out|0.1 Sign in and sign out]], [[5.1 Account|5.1 Account]]
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 115 (file has 1168 lines)

### public_user

- **Purpose:** The part of a user row that is safe to send to the browser (name, role, email).
- **Parameters:** u
- **Used from menus:** none directly (called by another function)
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 144 (file has 1168 lines)

### check_new_password

- **Purpose:** Password must be a string of at least 8 characters, else 400.
- **Parameters:** pw
- **Used from menus:** [[4.1 Users|4.1 Users]], [[5.1 Account|5.1 Account]]
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 148 (file has 1168 lines)

### check_email

- **Purpose:** Empty or `x@y.z` shaped, else 400.
- **Parameters:** email
- **Used from menus:** [[4.1 Users|4.1 Users]], [[5.1 Account|5.1 Account]]
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 153 (file has 1168 lines)

### other_admins

- **Purpose:** How many other active admins exist (guards: keep at least one).
- **Parameters:** name
- **Used from menus:** [[4.1 Users|4.1 Users]]
- **Stores read:** [[Table Catalog#users|users]]
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 158 (file has 1168 lines)

### own_job

- **Purpose:** Job of the URL if the user owns it or is admin, else 403/404.
- **Parameters:** jid, u
- **Used from menus:** [[1.3 Results charts and advice|1.3 Results charts and advice]], [[1.4 Predict|1.4 Predict]]
- **Stores read:** [[Table Catalog#jobs|jobs]]
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 926 (file has 1168 lines)

### own_pred

- **Purpose:** Prediction of the URL if the user owns it or is admin, else 403/404.
- **Parameters:** pid, u
- **Used from menus:** [[1.4 Predict|1.4 Predict]]
- **Stores read:** [[Table Catalog#RAM predictions|RAM predictions]]
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 968 (file has 1168 lines)

## Settings

### web_cfg

- **Purpose:** `web.yaml` merged over `WEB_DEFAULTS`.
- **Parameters:** -
- **Used from menus:** none directly (called by another function)
- **Stores read:** [[Table Catalog#web.yaml|web.yaml]]
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 101 (file has 1168 lines)

### get_settings

- **Purpose:** All rows of settings merged over `SETTING_DEFAULTS`.
- **Parameters:** -
- **Used from menus:** [[4.3 Server load|4.3 Server load]], [[4.4 Notifications|4.4 Notifications]]
- **Stores read:** [[Table Catalog#settings|settings]]
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 106 (file has 1168 lines)

### settings_form

- **Purpose:** The list of per-training options for New training (section, key, kind, range, help, default from config.yaml). The list itself is `SETTINGS` in web.py.
- **Parameters:** -
- **Used from menus:** [[0.1 Sign in and sign out|0.1 Sign in and sign out]], [[3.1 New training|3.1 New training]]
- **Stores read:** [[Table Catalog#config.yaml|config.yaml]]
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 671 (file has 1168 lines)

### apply_settings

- **Purpose:** Validates the JSON the form sent (`{"train.imgsz": 640, ...}`) against `SETTINGS` (type, range, imgsz multiple of 32, regex compiles, val + test at most 0.6) and writes it into the job's config copy. Unknown keys and paths/device are refused with 400.
- **Parameters:** cfg, raw
- **Used from menus:** [[3.1 New training|3.1 New training]]
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 677 (file has 1168 lines)

### core.load_config

- **Purpose:** Reads the YAML named by `YOLO_CONFIG` (a job's own copy) or `configuration/config.yaml`.
- **Parameters:** -
- **Used from menus:** none directly (called by another function)
- **Stores read:** [[Table Catalog#config.yaml|config.yaml]]
- **Stores written:** -
- **Defined in:** `scripts/core.py` line 28 (file has 206 lines)

## Notifications

### send_mail

- **Purpose:** Sends one email through the configured SMTP server (starttls, ssl or none, optional login). Raises when host or From is empty.
- **Parameters:** s (settings), to, subject, body
- **Used from menus:** [[0.2 Background workers|0.2 Background workers]], [[4.4 Notifications|4.4 Notifications]]
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 164 (file has 1168 lines)

### send_teams

- **Purpose:** Posts an Adaptive Card to the Teams incoming webhook (https only).
- **Parameters:** url, text
- **Used from menus:** [[0.2 Background workers|0.2 Background workers]], [[4.4 Notifications|4.4 Notifications]]
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 180 (file has 1168 lines)

### notify

- **Purpose:** Builds the message for a finished job, emails the owner and posts to Teams (each only when enabled and configured). Never raises; the last problem is saved for Admin > Notifications.
- **Parameters:** jid
- **Used from menus:** [[0.2 Background workers|0.2 Background workers]], [[4.4 Notifications|4.4 Notifications]]
- **Stores read:** [[Table Catalog#jobs|jobs]], [[Table Catalog#settings|settings]], [[Table Catalog#users|users]]
- **Stores written:** [[Table Catalog#settings|settings]]
- **Defined in:** `scripts/web.py` line 190 (file has 1168 lines)

### notify_later

- **Purpose:** Runs notify() in a daemon thread so SMTP can never block the queue.
- **Parameters:** jid
- **Used from menus:** [[1.2 Job detail|1.2 Job detail]]
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 216 (file has 1168 lines)

## Datasets

### save_upload

- **Purpose:** Streams an upload to disk in 1 MB chunks and stops with 413 when it passes the cap.
- **Parameters:** file, dest, cap
- **Used from menus:** [[1.4 Predict|1.4 Predict]], [[2.1 Datasets|2.1 Datasets]]
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 222 (file has 1168 lines)

### extract

- **Purpose:** Flattens the zip into `raw/images`, `raw/labels`, `classes.txt` using file names only (no path from the zip is used). Refuses bad zip, too big when unpacked, low disk (needs 3x), duplicate names, missing or oversize `classes.txt`.
- **Parameters:** zpath, data_dir, cfgw
- **Used from menus:** [[2.1 Datasets|2.1 Datasets]]
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 232 (file has 1168 lines)

### validate

- **Purpose:** Checks image/label pairs and every label line (5 numbers, class in classes.txt, values 0 to 1), drops labels without an image, needs `min_images`. Returns the summary stored in datasets.info.
- **Parameters:** raw, names, min_images
- **Used from menus:** [[2.1 Datasets|2.1 Datasets]]
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 272 (file has 1168 lines)

### make_dataset

- **Purpose:** Whole upload pipeline: per-user dataset limit, new id, save_upload, extract, validate, delete the zip, insert the row. On any error the folder is removed.
- **Parameters:** file, name, u, cfgw
- **Used from menus:** [[2.1 Datasets|2.1 Datasets]], [[3.1 New training|3.1 New training]]
- **Stores read:** [[Table Catalog#datasets|datasets]], [[Table Catalog#web.yaml|web.yaml]]
- **Stores written:** [[Table Catalog#datasets folder|datasets folder]], [[Table Catalog#datasets|datasets]]
- **Defined in:** `scripts/web.py` line 796 (file has 1168 lines)

### own_dataset

- **Purpose:** Dataset row if it exists and the user owns it (or is admin), else 404/403.
- **Parameters:** did, u
- **Used from menus:** [[2.1 Datasets|2.1 Datasets]], [[3.1 New training|3.1 New training]]
- **Stores read:** [[Table Catalog#datasets|datasets]]
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 817 (file has 1168 lines)

### dataset_view

- **Purpose:** Row to the JSON of the Datasets table (counts, size, how many jobs used it).
- **Parameters:** row
- **Used from menus:** [[2.1 Datasets|2.1 Datasets]]
- **Stores read:** [[Table Catalog#jobs|jobs]]
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 826 (file has 1168 lines)

### link_or_copy

- **Purpose:** Hard link a file (no extra disk); copy when links are not possible.
- **Parameters:** src, dst
- **Used from menus:** [[3.1 New training|3.1 New training]]
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 789 (file has 1168 lines)

## Jobs

### find_job

- **Purpose:** Job row by id (id must match the pattern), else 404.
- **Parameters:** jid
- **Used from menus:** [[1.2 Job detail|1.2 Job detail]]
- **Stores read:** [[Table Catalog#jobs|jobs]]
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 318 (file has 1168 lines)

### job_view

- **Purpose:** Job row to JSON: state, progress, ETA, queue position, share, `target`, and detail only for owner/admin; also `can_cancel` and `can_delete`.
- **Parameters:** r, me, position
- **Used from menus:** [[1.1 Queue and jobs|1.1 Queue and jobs]], [[1.2 Job detail|1.2 Job detail]]
- **Stores read:** [[Table Catalog#RAM running jobs|RAM running jobs]]
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 325 (file has 1168 lines)

### queued_ids

- **Purpose:** Ids of queued jobs, oldest first (queue order).
- **Parameters:** -
- **Used from menus:** [[1.1 Queue and jobs|1.1 Queue and jobs]]
- **Stores read:** [[Table Catalog#jobs|jobs]]
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 340 (file has 1168 lines)

### tail

- **Purpose:** Last lines of a log file (reads only the last 16 KB).
- **Parameters:** path, n=40
- **Used from menus:** [[1.2 Job detail|1.2 Job detail]]
- **Stores read:** [[Table Catalog#jobs folder|jobs folder]]
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 344 (file has 1168 lines)

### kill_tree

- **Purpose:** Stops a subprocess and its children (`taskkill /T /F` on Windows, because data loader workers are children).
- **Parameters:** p
- **Used from menus:** [[1.2 Job detail|1.2 Job detail]]
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 353 (file has 1168 lines)

### read_metrics

- **Purpose:** One dict per finished epoch from `runs/*/results.csv` (precision, recall, mAP50, mAP50-95); works while the job runs, skips a half-written last line.
- **Parameters:** jdir
- **Used from menus:** [[1.3 Results charts and advice|1.3 Results charts and advice]]
- **Stores read:** [[Table Catalog#jobs folder|jobs folder]]
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 360 (file has 1168 lines)

### last_metrics

- **Purpose:** Text `mAP50 x   mAP50-95 y` of the last epoch (the `detail` of a done job).
- **Parameters:** jdir
- **Used from menus:** none directly (called by another function)
- **Stores read:** [[Table Catalog#jobs folder|jobs folder]]
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 381 (file has 1168 lines)

### finish

- **Purpose:** Writes the final state, time, detail and progress of a job, clears its RAM entries and calls notify_later().
- **Parameters:** jid, state, detail
- **Used from menus:** [[0.2 Background workers|0.2 Background workers]]
- **Stores read:** -
- **Stores written:** [[Table Catalog#jobs|jobs]], [[Table Catalog#RAM running jobs|RAM running jobs]]
- **Defined in:** `scripts/web.py` line 386 (file has 1168 lines)

### run_job

- **Purpose:** Runs one job: marks it running (only if still queued), starts `prepare_dataset.py` then `train.py` as subprocesses with `YOLO_CONFIG` and `YOLO_SHARE`, copies the output into `log.txt`, tracks progress, then calls finish() as done, failed or cancelled. Fails when no `best.pt` exists.
- **Parameters:** jid, share
- **Used from menus:** [[0.2 Background workers|0.2 Background workers]]
- **Stores read:** [[Table Catalog#jobs|jobs]], [[Table Catalog#jobs folder|jobs folder]]
- **Stores written:** [[Table Catalog#jobs|jobs]], [[Table Catalog#jobs folder|jobs folder]], [[Table Catalog#RAM running jobs|RAM running jobs]]
- **Defined in:** `scripts/web.py` line 395 (file has 1168 lines)

### job_thread

- **Purpose:** Thread body around run_job(): any exception becomes a failed job; always frees the share, wakes the dispatcher and runs cleanup().
- **Parameters:** jid, share
- **Used from menus:** [[0.2 Background workers|0.2 Background workers]]
- **Stores read:** -
- **Stores written:** [[Table Catalog#RAM running jobs|RAM running jobs]]
- **Defined in:** `scripts/web.py` line 431 (file has 1168 lines)

### dispatcher

- **Purpose:** Loop (wakes every 3 s or when a job arrives/ends): starts the oldest queued jobs while the running shares plus the next one add up to 100 or less. The share is read when the job starts.
- **Parameters:** -
- **Used from menus:** [[0.2 Background workers|0.2 Background workers]]
- **Stores read:** [[Table Catalog#settings|settings]], [[Table Catalog#jobs|jobs]]
- **Stores written:** [[Table Catalog#RAM running jobs|RAM running jobs]]
- **Defined in:** `scripts/web.py` line 443 (file has 1168 lines)

### cleanup

- **Purpose:** Deletes finished jobs older than `keep_days` (row and folder) and expired sessions.
- **Parameters:** -
- **Used from menus:** [[0.2 Background workers|0.2 Background workers]]
- **Stores read:** [[Table Catalog#jobs|jobs]], [[Table Catalog#web.yaml|web.yaml]]
- **Stores written:** [[Table Catalog#jobs|jobs]], [[Table Catalog#jobs folder|jobs folder]], [[Table Catalog#sessions|sessions]]
- **Defined in:** `scripts/web.py` line 563 (file has 1168 lines)

### startup

- **Purpose:** Once at server start: creates the first admin if there are no users (and the password file), marks jobs that were running as failed, runs cleanup(), starts the dispatcher and predict-worker threads.
- **Parameters:** -
- **Used from menus:** [[0.2 Background workers|0.2 Background workers]]
- **Stores read:** [[Table Catalog#users|users]], [[Table Catalog#jobs|jobs]]
- **Stores written:** [[Table Catalog#users|users]], [[Table Catalog#jobs|jobs]], [[Table Catalog#first admin file|first admin file]]
- **Defined in:** `scripts/web.py` line 571 (file has 1168 lines)

## Predict

### load_model

- **Purpose:** Loads `runs/*/weights/best.pt` of a job into the one-entry cache.
- **Parameters:** jid
- **Used from menus:** [[0.2 Background workers|0.2 Background workers]], [[1.4 Predict|1.4 Predict]]
- **Stores read:** [[Table Catalog#jobs folder|jobs folder]]
- **Stores written:** [[Table Catalog#RAM model cache|RAM model cache]]
- **Defined in:** `scripts/web.py` line 464 (file has 1168 lines)

### infer

- **Purpose:** Runs the model on one frame on `predict_device` (cpu by default, so it never fights training for the GPU) and returns the drawn frame and the detections.
- **Parameters:** model, frame, conf
- **Used from menus:** [[0.2 Background workers|0.2 Background workers]], [[1.4 Predict|1.4 Predict]]
- **Stores read:** [[Table Catalog#web.yaml|web.yaml]]
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 472 (file has 1168 lines)

### open_writer

- **Purpose:** Starts ffmpeg (from `imageio-ffmpeg`) fed with raw frames to write an H.264 mp4 that browsers can play.
- **Parameters:** d, fps, size
- **Used from menus:** [[1.4 Predict|1.4 Predict]]
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 480 (file has 1168 lines)

### close_writer

- **Purpose:** Closes ffmpeg and raises with its message when it failed.
- **Parameters:** w
- **Used from menus:** [[1.4 Predict|1.4 Predict]]
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 489 (file has 1168 lines)

### run_predict

- **Purpose:** Image: one inference. Video: frame by frame (up to `max_video_frames`), counting frames and max objects per class. Writes `out.jpg` or `out.mp4`.
- **Parameters:** pid
- **Used from menus:** [[0.2 Background workers|0.2 Background workers]], [[1.4 Predict|1.4 Predict]]
- **Stores read:** [[Table Catalog#jobs folder|jobs folder]], [[Table Catalog#web.yaml|web.yaml]], [[Table Catalog#RAM predictions|RAM predictions]]
- **Stores written:** [[Table Catalog#jobs folder|jobs folder]], [[Table Catalog#RAM predictions|RAM predictions]]
- **Defined in:** `scripts/web.py` line 497 (file has 1168 lines)

### predict_worker

- **Purpose:** Thread: takes predictions from the queue one at a time, marks done or failed, deletes the uploaded input.
- **Parameters:** -
- **Used from menus:** [[0.2 Background workers|0.2 Background workers]], [[1.4 Predict|1.4 Predict]]
- **Stores read:** [[Table Catalog#RAM predictions|RAM predictions]]
- **Stores written:** [[Table Catalog#RAM predictions|RAM predictions]], [[Table Catalog#jobs folder|jobs folder]]
- **Defined in:** `scripts/web.py` line 540 (file has 1168 lines)

### pred_view

- **Purpose:** Prediction state to JSON (state, progress, error, result, file URL).
- **Parameters:** pid
- **Used from menus:** [[1.4 Predict|1.4 Predict]]
- **Stores read:** [[Table Catalog#RAM predictions|RAM predictions]]
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 557 (file has 1168 lines)

## Models

### newest_first

- **Purpose:** Sort: newest generation first, inside a generation x, l, m, s, n; names that do not fit the pattern go last.
- **Parameters:** names
- **Used from menus:** none directly (called by another function)
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 1052 (file has 1168 lines)

### allowed_models

- **Purpose:** What users may pick: the saved list in settings, or web.yaml `models` until an admin saves one.
- **Parameters:** -
- **Used from menus:** [[0.1 Sign in and sign out|0.1 Sign in and sign out]], [[3.1 New training|3.1 New training]], [[4.2 Models|4.2 Models]]
- **Stores read:** [[Table Catalog#settings|settings]], [[Table Catalog#web.yaml|web.yaml]]
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 1060 (file has 1168 lines)

### known_models

- **Purpose:** Every model the admin can tick: presets of config.yaml, `.pt` files in models, and the allowed list.
- **Parameters:** -
- **Used from menus:** [[4.2 Models|4.2 Models]]
- **Stores read:** [[Table Catalog#config.yaml|config.yaml]], [[Table Catalog#models folder|models folder]], [[Table Catalog#settings|settings]], [[Table Catalog#web.yaml|web.yaml]]
- **Stores written:** -
- **Defined in:** `scripts/web.py` line 1066 (file has 1168 lines)

### fetch_model

- **Purpose:** Background download of a model with Ultralytics' `attempt_download_asset`; stores `error: ...` when it fails (for example a certificate or proxy problem).
- **Parameters:** name
- **Used from menus:** [[4.2 Models|4.2 Models]]
- **Stores read:** -
- **Stores written:** [[Table Catalog#models folder|models folder]], [[Table Catalog#RAM downloads|RAM downloads]]
- **Defined in:** `scripts/web.py` line 1071 (file has 1168 lines)

### core.resolve_model

- **Purpose:** `yolo26n.pt` to `models/yolo26n.pt` (creates the folder). A `.yaml` or a path is passed through.
- **Parameters:** name
- **Used from menus:** [[4.2 Models|4.2 Models]]
- **Stores read:** [[Table Catalog#models folder|models folder]]
- **Stores written:** -
- **Defined in:** `scripts/core.py` line 41 (file has 206 lines)

## Training engine

### core.parse_progress

- **Purpose:** Turns an Ultralytics output line into progress 0 to 1 and remembers epoch / total in the state.
- **Parameters:** line, st
- **Used from menus:** none directly (called by another function)
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/core.py` line 55 (file has 206 lines)

### core.detect_hardware

- **Purpose:** CPU threads, free RAM, GPU and free VRAM (via torch), scaled by `YOLO_SHARE` so a job only sees its share.
- **Parameters:** -
- **Used from menus:** none directly (called by another function)
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/core.py` line 69 (file has 206 lines)

### core.auto_settings

- **Purpose:** Values for every `auto` (device, batch from free VRAM and model size, workers, cache, amp).
- **Parameters:** cfg, hw, n_train
- **Used from menus:** none directly (called by another function)
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/core.py` line 99 (file has 206 lines)

### core.resolve_train_args

- **Purpose:** Replaces each `auto` in `train` with the value from auto_settings.
- **Parameters:** cfg, hw, n_train
- **Used from menus:** none directly (called by another function)
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/core.py` line 120 (file has 206 lines)

### core.count_train_images

- **Purpose:** Counts images in the train split (input of auto batch/cache).
- **Parameters:** cfg
- **Used from menus:** none directly (called by another function)
- **Stores read:** [[Table Catalog#jobs folder|jobs folder]]
- **Stores written:** -
- **Defined in:** `scripts/core.py` line 50 (file has 206 lines)

### core.split_groups

- **Purpose:** Splits file stems into train/val/test; stems with the same regex group 1 stay together.
- **Parameters:** stems, val, test, group_regex, seed
- **Used from menus:** none directly (called by another function)
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/core.py` line 127 (file has 206 lines)

### core.read_classes

- **Purpose:** Class names from `classes.txt` (exits when missing).
- **Parameters:** data
- **Used from menus:** none directly (called by another function)
- **Stores read:** [[Table Catalog#jobs folder|jobs folder]]
- **Stores written:** -
- **Defined in:** `scripts/core.py` line 148 (file has 206 lines)

### core.write_dataset_yaml

- **Purpose:** Writes `dataset.yaml` with this machine's absolute paths and drops stale `*.cache`.
- **Parameters:** cfg
- **Used from menus:** none directly (called by another function)
- **Stores read:** [[Table Catalog#jobs folder|jobs folder]]
- **Stores written:** [[Table Catalog#jobs folder|jobs folder]]
- **Defined in:** `scripts/core.py` line 155 (file has 206 lines)

### core.prepare_dataset

- **Purpose:** Copies `raw/` into `dataset/train|val|test` with the split, then writes dataset.yaml. `raw/` is never changed.
- **Parameters:** cfg
- **Used from menus:** none directly (called by another function)
- **Stores read:** [[Table Catalog#jobs folder|jobs folder]]
- **Stores written:** [[Table Catalog#jobs folder|jobs folder]]
- **Defined in:** `scripts/core.py` line 173 (file has 206 lines)

### prepare_dataset.py

- **Purpose:** Subprocess step 1 of a job: calls core.prepare_dataset(core.load_config()).
- **Parameters:** env YOLO_CONFIG
- **Used from menus:** [[0.2 Background workers|0.2 Background workers]]
- **Stores read:** [[Table Catalog#jobs folder|jobs folder]]
- **Stores written:** [[Table Catalog#jobs folder|jobs folder]]
- **Defined in:** `scripts/prepare_dataset.py` line 1 (file has 5 lines)

### train.py

- **Purpose:** Subprocess step 2 of a job: limits threads by `YOLO_SHARE`, writes dataset.yaml, resolves `auto` values and calls Ultralytics `YOLO(model).train(...)`; output goes to `runs/<run>/`.
- **Parameters:** env YOLO_CONFIG, YOLO_SHARE
- **Used from menus:** [[0.2 Background workers|0.2 Background workers]]
- **Stores read:** [[Table Catalog#jobs folder|jobs folder]], [[Table Catalog#models folder|models folder]]
- **Stores written:** [[Table Catalog#jobs folder|jobs folder]]
- **Defined in:** `scripts/train.py` line 10 (file has 23 lines)

## External systems

### SMTP server

- **Purpose:** The company mail server set in Admin > Notifications. Not part of this project.
- **Parameters:** host, port, security, user, password
- **Used from menus:** [[0.2 Background workers|0.2 Background workers]], [[4.4 Notifications|4.4 Notifications]]
- **Stores read:** -
- **Stores written:** -
- **Defined in:** outside this project

### Teams webhook

- **Purpose:** Incoming webhook of a Teams channel (https URL). Not tested against a real tenant.
- **Parameters:** url
- **Used from menus:** [[0.2 Background workers|0.2 Background workers]], [[4.4 Notifications|4.4 Notifications]]
- **Stores read:** -
- **Stores written:** -
- **Defined in:** outside this project

### GitHub model files

- **Purpose:** Where Ultralytics downloads `.pt` weights from (github.com and release-assets.githubusercontent.com). A company proxy that re-signs HTTPS breaks it with `self-signed certificate in certificate chain`.
- **Parameters:** model name
- **Used from menus:** [[4.2 Models|4.2 Models]]
- **Stores read:** -
- **Stores written:** -
- **Defined in:** outside this project

## Browser (index.html)

### loadCharts

- **Purpose:** Fetches `/api/jobs/{id}/metrics` and draws the six tiles and three line charts, then adds readout().
- **Parameters:** id, j
- **Used from menus:** [[1.3 Results charts and advice|1.3 Results charts and advice]]
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/index.html` line 395 (file has 651 lines)

### readout

- **Purpose:** Rules of thumb over the validation numbers: what the metrics imply and what to try. With a target set, advice appears only when a finished job stayed below it.
- **Parameters:** m (epochs), j (job)
- **Used from menus:** [[1.3 Results charts and advice|1.3 Results charts and advice]]
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/index.html` line 365 (file has 651 lines)

### buildSettings

- **Purpose:** Draws the Training settings form from `/api/me` options.
- **Parameters:** -
- **Used from menus:** [[3.1 New training|3.1 New training]]
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/index.html` line 501 (file has 651 lines)

### collectSettings

- **Purpose:** Collects only the values the user changed into the JSON sent as `settings`.
- **Parameters:** -
- **Used from menus:** [[3.1 New training|3.1 New training]]
- **Stores read:** -
- **Stores written:** -
- **Defined in:** `scripts/index.html` line 517 (file has 651 lines)
