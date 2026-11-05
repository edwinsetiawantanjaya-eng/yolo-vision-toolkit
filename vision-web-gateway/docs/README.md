# Yolo Web Gateway

Users open a web page, upload a dataset zip, and the server trains a YOLO model for them. Everybody sees the queue, the admin can cancel, and the result is downloaded from the page. The training engine is the same as `vision-desktop` (`scripts/prepare_dataset.py` + `scripts/train.py`, settings in `configuration/config.yaml`).

Documentation vault for Obsidian (menu -> route -> function -> store, with flow charts): the folder `reference/` next to this file (open it with "Open folder as vault", start at `00 START HERE`).

## Start (on the server)

1. Right-click `00.Setup_env.ps1`, **Run with PowerShell**. It installs Python and the packages (first time only) and starts the gateway.
2. Next times: double-click `app.py`.
3. First start prints the admin password and saves it in `data/FIRST_ADMIN_PASSWORD.txt`. Open `http://localhost:8000`, sign in as `admin`, change the password in **Account** (that deletes the file).
4. Other PCs open `http://<server name>:8000`. If Windows blocks it, run once in an admin PowerShell:

```powershell
New-NetFirewallRule -DisplayName "YOLO Gateway" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
```

Keep it running after a reboot or logoff with Task Scheduler (run once in an admin PowerShell, adjust the path; not tested on your server):

```powershell
schtasks /Create /TN "YOLO Gateway" /SC ONSTART /RU SYSTEM /TR "'C:\path\to\vision-web-gateway\.venv\Scripts\python.exe' 'C:\path\to\vision-web-gateway\app.py'"
```

## Roles

| | user | admin |
|---|---|---|
| See the whole queue (who, model, state, progress, ETA) | yes | yes |
| Start a training (upload zip) | yes, max 2 waiting or running | yes, unlimited |
| Open the log, charts, Predict and download the result | own jobs only | all jobs |
| Cancel a job | own jobs only | all jobs |
| Delete a finished job (log, training files, result) | no | yes |
| Datasets (save, reuse, delete) | own datasets | all datasets |
| Users, SMTP, Teams settings | no | yes |

Admin creates users in **Admin > Users** (name, password, role, email). The email is where "your job finished / failed / was cancelled" goes.

## Datasets

The **Datasets** tab keeps uploaded zips so a dataset is uploaded once and reused by any number of trainings (pick it in **New training**, or press **Train with this**). A zip sent directly in New training is saved as a dataset too. Each training gets its own copy of the files (hard links on the same disk, so it takes no extra space), so deleting a dataset never breaks a training that already used it. A dataset used by a waiting or running job cannot be deleted. Users see their own datasets, admins see all with the size of each. Datasets are not deleted automatically (limit per user: `max_datasets_per_user` in `web.yaml`, admins unlimited); finished jobs still are after `keep_days`.

## Models (Admin > Models)

Lists the presets of `config.yaml` plus every `.pt` in the `models` folder. Tick which ones users can pick in New training and press **Save list** (saved in the database; `models` in `web.yaml` is only the starting list). **Download** fetches the weights into `models/` in the background (the server needs internet); the box below it downloads any other official name, e.g. `yolo11m.pt`. An undownloaded model is still fetched by the first training that uses it.

## Training settings (New training > Training settings)

Like the tabs of the desktop app, the form lists the settings of `configuration/config.yaml` that a user may change per training, filled with the server's values: `train.imgsz`, `patience`, `batch`, `workers`, `cache`, `amp`, `optimizer`, `cos_lr`, `single_cls`, `mosaic`, `close_mosaic`, `scale`, `fliplr`, `flipud`, `seed` and `split.val`, `test`, `seed`, `group_regex` (hover a name for what it does; `auto` is accepted where the desktop app accepts it). The server checks every value (range, type, regex) and refuses a bad one with a message before anything is saved. Paths and `device` are not shown: they belong to the server. Each job keeps its own copy in `jobs/<id>/config.yaml`, so changing `config.yaml` later never changes a queued job. Editing the list of options = `SETTINGS` in `scripts/web.py`.

## Cancel and delete

A user can cancel their own queued or running job; an admin can cancel any job. After a job is cancelled, failed or done, an admin can press **Delete** (or **Delete log and files** in the job detail) to remove the job, its log, the training files and the result from the server for good.

## Server load (Admin > Server load)

"Share of the server per job" decides how much of the machine one training may use and so how many run at once: 100 = one job at a time (default), 50 = two at a time, 33 = three, 25 = four. Jobs start in queue order while the shares of the running jobs plus the next one add up to 100 or less; the rest wait. The share limits CPU threads, RAM and GPU memory (so the batch size) of that job. The GPU compute itself is time-shared by Windows and the driver, not capped. A running job keeps the share it started with; the new value applies to the jobs that start after it. Pick values that divide 100 (60 would still run one at a time). With two jobs on one GPU each is slower than alone: the share only decides who runs together.

The ETA is counted from the first training progress line, not from when the job was picked up, so dataset preparation and model loading no longer inflate it.

## Results page: charts and Predict

Open a running or finished job (your own, or any job as admin):

- **Charts per epoch** (while it runs they grow every epoch): precision, recall, mAP50, mAP50-95, miss ratio (1 - recall) and false-alarm ratio (1 - precision), plus the values of the latest epoch. They are measured on the validation images. Under the charts, **What this means** reads those numbers in plain words and suggests what to try (more epochs, more or cleaner data, background images, larger image size, bigger model, ...). If **Target mAP50 %** was filled in New training, the advice appears only when the finished training stays below that target (best epoch is compared); a reached target just says so, and a running job only shows progress. With no target the advice is always shown. It is a set of rules of thumb in `readout()` in `scripts/index.html`, not a guarantee.
- **Predict** (finished jobs only): send an image or a video, get it back with the boxes drawn and a table of what was found. The confidence box sets how sure the model must be (lower = more boxes). It runs on the server CPU (`predict_device` in `web.yaml`), not in the training queue, so it never takes the GPU from a training. Max 2 waiting predictions per user, files up to `max_predict_mb`, videos up to `max_video_frames` (about 2 minutes). Results are kept for 1 day. Videos are encoded with the ffmpeg that comes with the `imageio-ffmpeg` package.

## Notifications (Admin > Notifications)

- **Email:** fill SMTP server, port, security, login and From address. The job owner gets a message when the job ends. Press **Save**, then **Test email**.
- **Teams:** paste an incoming webhook URL (https). Every job result is posted to that channel. Press **Save**, then **Test Teams**. The message is an Adaptive Card; it was not tested against a real Teams tenant, so use the test button first.
- "This site's address" is only put in the messages as a link.
- A failed notification never stops a job; the last problem is shown under the form.

## What users upload

```
my-dataset.zip
  classes.txt        one class name per line (line 1 = class 0)
  images/            .jpg .png ...
  labels/            YOLO .txt, same name as the image: class x y w h (0 to 1)
```

The server refuses the zip with a clear message when `classes.txt` is missing, there are too few images, a label has a class not in `classes.txt`, a label line is malformed, or names collide. Folders inside the zip are ignored (names only are used). An image without a label counts as background.

## Settings files

- `configuration/web.yaml`: port, upload limits, allowed models, max epochs, jobs per user, how long to keep finished jobs.
- `configuration/config.yaml`: the training settings every job copies (image size, augmentation, `split.group_regex`, ...). Same keys as in `vision-desktop`. `auto` picks batch, workers and so on from this server's GPU.
- `data/gateway.db`: users, notification settings (SMTP password included, keep the folder private) and the job list. `jobs/<id>/`: one folder per job (data, runs, log, result).

## Good to know

- One job runs at a time (one GPU). Jobs wait in order. If the server restarts, a running job is marked failed and waiting jobs continue.
- Cancelling a running job kills the training; its result is lost.
- Sign-in uses a cookie, 12 hours. Five wrong passwords lock that name for 5 minutes. The page is plain HTTP: for use beyond a trusted office network put an HTTPS reverse proxy in front.
- Self-check: `.venv\Scripts\python scripts\test_web.py` (needs `pip install httpx`; runs a real 1-epoch CPU training, a few minutes).
