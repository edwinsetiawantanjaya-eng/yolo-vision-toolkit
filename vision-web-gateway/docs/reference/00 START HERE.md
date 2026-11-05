---
tags: [yolo-gateway, index]
---
# Yolo Web Gateway documentation: start here

Yolo Web Gateway = a FastAPI web page where users upload a dataset zip (or reuse a saved one), the server trains a YOLO model in a queue, everybody sees the queue, and the result, charts and Predict are on the same page. This vault explains **which screen uses which handler, which function or step, and which table or folder**, so you can go straight to the right place when something breaks.

> [!tip] Fast path when a problem happens
> 1. Find the screen in [[Menu Map]] (same numbering as the tabs).
> 2. Open the menu note. The table **"Action map"** shows for each button: route -> handler -> helpers -> **function or step** -> **stores**.
> 3. Click the function in [[Function Catalog]] to see its purpose, parameters, the stores it reads/writes and the file and line where it is defined.
> 4. Check the data in the stores ([[Table Catalog]]), or the job's own log `jobs/<id>/log.txt`.
> 4b. Prefer a picture? Every menu note has a **Flow chart** section (overview plus one chart per button).
> 5. Still unclear? Follow [[Troubleshooting Guide]].

## Notes in this vault

| Note | Use it for |
|---|---|
| [[Menu Map]] | One-page overview: menu -> routes -> functions -> stores |
| [[Architecture]] | How a click travels: browser -> guard -> route -> handler -> function -> store; threads, subprocesses, roles, config |
| [[End-to-End Flow]] | The life of a training: upload -> queue -> split -> train -> result -> notify -> predict -> cleanup |
| [[Function Catalog]] | All functions, subprocess steps, browser functions and external systems the menus use |
| [[Table Catalog]] | SQLite tables, folders, config files and RAM state, and who writes them |
| [[Troubleshooting Guide]] | Symptom -> where to look; log files; read-only queries |

## Menus

### System (0.x)
- [[0.1 Sign in and sign out|0.1 Sign in and sign out]]
- [[0.2 Background workers|0.2 Background workers]]

### Queue and jobs tab (1.x)
- [[1.1 Queue and jobs|1.1 Queue and jobs]]
- [[1.2 Job detail|1.2 Job detail]]
- [[1.3 Results charts and advice|1.3 Results charts and advice]]
- [[1.4 Predict|1.4 Predict]]

### Datasets tab (2.x)
- [[2.1 Datasets|2.1 Datasets]]

### New training tab (3.x)
- [[3.1 New training|3.1 New training]]

### Admin tab (4.x, admin only)
- [[4.1 Users|4.1 Users]]
- [[4.2 Models|4.2 Models]]
- [[4.3 Server load|4.3 Server load]]
- [[4.4 Notifications|4.4 Notifications]]

### Account tab (5.x)
- [[5.1 Account|5.1 Account]]

## Conventions used in the notes

- **Handler** = the FastAPI route function in `scripts/web.py` (green box). **Function / step** = a catalog object a handler calls (yellow hexagon). The training itself is two subprocess steps: `prepare_dataset.py` and `train.py` (same engine as `vision-desktop`).
- **W / R** in store columns: **W** = the function writes (insert, update, delete, file write) the store, R = only reads.
- **Inline SQL / files in handler** is flagged in bold in the action map: there the logic sits in the route function itself, not in a catalog function.
- **Roles:** `user` sees the whole queue but opens, cancels, downloads and predicts only their own jobs and sees only their own datasets; `admin` can do everything and also has the Admin tab.
- **RAM** stores (`LIVE`, `PRED`, `DL`, ...) are lost when `app.py` restarts.
- Code root: `vision-web-gateway/` in this repo. Deployed copy: any folder on the server, reached at `http://<server>:8000`. Desktop version: `vision-desktop/` (separate on purpose, not part of this vault).

## Scope and honesty notes

- Written by reading the source (`web.py`, `core.py`, `index.html`, `train.py`, `prepare_dataset.py`, the YAML files). No code or data was changed for this documentation. Line numbers in the Function Catalog come from the real files on the day of writing and move when the code changes.
- The self-check `scripts/test_web.py` exercises the API (users, datasets, models, settings, jobs, predict) with a real 1-epoch CPU training. Run it locally before deploying.
- Not verified: Teams delivery against a real tenant. Behind a corporate proxy, model downloads may need the steps in [[Troubleshooting Guide]].
