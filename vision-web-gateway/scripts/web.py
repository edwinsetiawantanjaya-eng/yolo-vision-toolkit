"""YOLO web gateway: users upload a dataset zip, jobs train one at a time on this server, everyone sees the queue.

Run: python app.py (or python scripts/web.py). State: data/gateway.db (users, settings, jobs), jobs/<id>/ (one folder per job).
Roles: admin = everything (cancel, users, notification settings); user = start a training, see the queue,
download their own result. Training itself is scripts/prepare_dataset.py + scripts/train.py, the same as the desktop GUI.
"""
import contextlib
import csv
import hashlib
import hmac
import json
import os
import queue
import re
import secrets
import shutil
import smtplib
import sqlite3
import ssl
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from email.message import EmailMessage
from pathlib import Path

import uvicorn
import yaml
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse

import core

HOME = Path(os.environ.get("GATEWAY_HOME") or core.ROOT)  # where data/ and jobs/ live
JOBS = HOME / "jobs"
DATASETS = HOME / "datasets"
DS_ID = re.compile(r"^d\d{6}-\d{6}-[0-9a-f]{4}$")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
JOB_ID = re.compile(r"^\d{6}-\d{6}-[0-9a-f]{4}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
NAME = re.compile(r"^[A-Za-z0-9_.-]{2,32}$")
WEB_DEFAULTS = {"host": "0.0.0.0", "port": 8000, "max_upload_mb": 2048, "max_unzipped_mb": 6144, "min_images": 10,
                "max_epochs": 100, "max_active_per_user": 2, "keep_days": 30, "models": ["yolo26n.pt"],
                "predict_device": "cpu", "max_predict_mb": 200, "max_video_frames": 3000, "max_datasets_per_user": 10}
SETTING_DEFAULTS = {"smtp_host": "", "smtp_port": "587", "smtp_security": "starttls", "smtp_user": "", "smtp_password": "",
                    "smtp_from": "", "teams_url": "", "public_url": "", "notify_email": "1", "notify_teams": "1", "job_share": "100"}
STATE_WORD = {"done": "finished", "failed": "FAILED", "cancelled": "was cancelled"}
VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}

(HOME / "data").mkdir(parents=True, exist_ok=True)
JOBS.mkdir(exist_ok=True)
DATASETS.mkdir(exist_ok=True)
db = sqlite3.connect(HOME / "data" / "gateway.db", check_same_thread=False, isolation_level=None)  # autocommit
db.row_factory = sqlite3.Row
lock = threading.RLock()
db.executescript("""
create table if not exists users(name text primary key, pw text not null, role text not null, email text default '', active int default 1);
create table if not exists sessions(token text primary key, name text not null, expires real not null);
create table if not exists settings(key text primary key, value text not null);
create table if not exists jobs(id text primary key, owner text, state text, model text, epochs int, note text,
  created real, started real, finished real, images int, info text, detail text, frac real, dataset text);
create table if not exists datasets(id text primary key, owner text, name text, created real, images int, info text, bytes int);
""")
for _col, _typ in (("dataset", "text"), ("target", "real")):  # a database made before this column existed
    if _col not in [r["name"] for r in db.execute("pragma table_info(jobs)")]:
        db.execute(f"alter table jobs add column {_col} {_typ}")

LIVE = {}  # job id -> {"frac", "epoch", "epochs"} of the running job
PROCS = {}  # job id -> Popen of the running step
CANCEL = {}  # job id -> name of who asked to stop it
ACTIVE = {}  # running job id -> its share of the server in percent; jobs start while the shares add up to 100 or less
WAKE = threading.Event()  # tells the dispatcher that a job arrived or ended
PRED = {}  # prediction id -> its state (in memory; the files live in jobs/<id>/predict/<pid>/)
PQUEUE = queue.Queue()
MODELS = {}  # job id -> loaded model (only the last one is kept)
FAILS = {}  # user name -> times of recent wrong passwords
started = False


class Bad(Exception):
    """A problem the user can fix (shown as is in the web page)."""

    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.code = code


def sql(query, *args):
    with lock:
        return db.execute(query, args).fetchall()


def sql_n(query, *args):
    """Run a write and return how many rows it changed (used for atomic state changes)."""
    with lock:
        return db.execute(query, args).rowcount


def web_cfg():
    f = core.ROOT / "configuration" / "web.yaml"
    return {**WEB_DEFAULTS, **((yaml.safe_load(f.read_text(encoding="utf-8-sig")) or {}) if f.is_file() else {})}


def get_settings():
    return {**SETTING_DEFAULTS, **{r["key"]: r["value"] for r in sql("select * from settings")}}


def hash_pw(pw, salt=None):
    salt = salt or secrets.token_bytes(16)
    return salt.hex() + ":" + hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1).hex()


def check_pw(pw, stored):
    salt, h = stored.split(":")
    return hmac.compare_digest(hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1).hex(), h)


# ---------- users and sessions ----------

def user_from_cookie(request):
    tok = request.cookies.get("gw_session")
    if not tok:
        return None
    r = sql("select u.* from sessions s join users u on u.name = s.name where s.token = ? and s.expires > ? and u.active = 1",
            hashlib.sha256(tok.encode()).hexdigest(), time.time())
    return dict(r[0]) if r else None


def current_user(request: Request):
    u = user_from_cookie(request)
    if not u:
        raise HTTPException(401, "sign in first")
    return u


def admin_user(u=Depends(current_user)):
    if u["role"] != "admin":
        raise HTTPException(403, "admin only")
    return u


def public_user(u):
    return {"name": u["name"], "role": u["role"], "email": u["email"]}


def check_new_password(pw):
    if not isinstance(pw, str) or len(pw) < 8:
        raise HTTPException(400, "password needs at least 8 characters")


def check_email(email):
    if email and not EMAIL.match(email):
        raise HTTPException(400, "that email address does not look right")


def other_admins(name):
    return sql("select count(*) c from users where role = 'admin' and active = 1 and name != ?", name)[0]["c"]


# ---------- notifications ----------

def send_mail(s, to, subject, body):
    if not s["smtp_host"] or not s["smtp_from"]:
        raise ValueError("fill in the SMTP server and the From address first")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s["smtp_from"], to, subject
    msg.set_content(body)
    ctx, mode = ssl.create_default_context(), s["smtp_security"]
    cls = smtplib.SMTP_SSL if mode == "ssl" else smtplib.SMTP
    with cls(s["smtp_host"], int(s["smtp_port"]), timeout=15, **({"context": ctx} if mode == "ssl" else {})) as c:
        if mode == "starttls":
            c.starttls(context=ctx)
        if s["smtp_user"]:
            c.login(s["smtp_user"], s["smtp_password"])
        c.send_message(msg)


def send_teams(url, text):
    if not url.startswith("https://"):
        raise ValueError("fill in the Teams webhook URL first (it starts with https://)")
    card = {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.4",
        "body": [{"type": "TextBlock", "text": text, "wrap": True}]}}]}
    req = urllib.request.Request(url, json.dumps(card).encode(), {"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=15).read()


def notify(jid):
    """Tell the owner (email) and the team channel (Teams) how the job ended. Never raises."""
    errors = []
    try:
        r, s = find_job(jid), get_settings()
        text = f"YOLO job {jid} {STATE_WORD.get(r['state'], r['state'])}\nOwner: {r['owner']}   Model: {r['model']}   Epochs: {r['epochs']}"
        if r["detail"]:
            text += f"\n{r['detail']}"
        if s["public_url"]:
            text += f"\nOpen: {s['public_url']}"
        owner = sql("select email from users where name = ?", r["owner"])
        if s["notify_email"] == "1" and s["smtp_host"] and owner and owner[0]["email"]:
            try:
                send_mail(s, owner[0]["email"], f"YOLO job {jid} {STATE_WORD.get(r['state'], r['state'])}", text)
            except Exception as e:
                errors.append(f"email: {e}")
        if s["notify_teams"] == "1" and s["teams_url"]:
            try:
                send_teams(s["teams_url"], text)
            except Exception as e:
                errors.append(f"Teams: {e}")
    except Exception as e:
        errors.append(str(e))
    sql("insert or replace into settings values('last_notify_error', ?)", f"{time.strftime('%Y-%m-%d %H:%M')} {'; '.join(errors)}" if errors else "")


def notify_later(jid):
    threading.Thread(target=notify, args=(jid,), daemon=True).start()  # SMTP can take seconds: never block the queue


# ---------- zip -> dataset ----------

def save_upload(f, dest, cap):
    n = 0
    with open(dest, "wb") as out:
        while chunk := f.file.read(1 << 20):
            n += len(chunk)
            if n > cap:
                raise Bad(f"the zip is bigger than {cap // 2**20} MB", 413)
            out.write(chunk)


def extract(zpath, data_dir, cfgw):
    """Flatten the zip into data/raw/images, data/raw/labels, data/classes.txt. Names only: no path from the zip is ever used."""
    raw = data_dir / "raw"
    (raw / "images").mkdir(parents=True)
    (raw / "labels").mkdir()
    classes, seen = None, set()
    try:
        z = zipfile.ZipFile(zpath)
    except zipfile.BadZipFile:
        raise Bad("this is not a valid zip file")
    with z:
        files = [i for i in z.infolist() if not i.is_dir()]
        if sum(i.file_size for i in files) > cfgw["max_unzipped_mb"] * 2**20:
            raise Bad("the zip is too big once unpacked")
        if shutil.disk_usage(JOBS).free < 3 * sum(i.file_size for i in files):
            raise Bad("the server is low on disk space, tell the admin", 507)
        for i in files:
            name = Path(i.filename.replace("\\", "/")).name
            ext = Path(name).suffix.lower()
            if name.startswith(".") or "__MACOSX" in i.filename:
                continue
            if name.lower() == "classes.txt":
                if i.file_size > 1 << 20:
                    raise Bad("classes.txt is too big")
                classes = z.read(i).decode("utf-8-sig", "replace")
            elif ext in core.IMG_EXT or ext == ".txt":
                if name.lower() in seen:
                    raise Bad(f"two files are called {name} (folders inside the zip are ignored, names must be unique)")
                seen.add(name.lower())
                with z.open(i) as src, open(raw / ("images" if ext != ".txt" else "labels") / name, "wb") as out:
                    shutil.copyfileobj(src, out)
    if classes is None:
        raise Bad("classes.txt is missing in the zip (one class name per line)")
    names = [n.strip() for n in classes.splitlines() if n.strip()]
    if not names or len(names) > 1000:
        raise Bad("classes.txt must list between 1 and 1000 class names")
    (data_dir / "classes.txt").write_text("\n".join(names) + "\n", encoding="utf-8")
    return raw, names


def validate(raw, names, min_images):
    """Check pairs and label lines. Returns the summary shown on the job page."""
    imgs = {}
    for p in (raw / "images").iterdir():
        if p.stem in imgs:
            raise Bad(f"images {imgs[p.stem].name} and {p.name} share a name; rename one")
        imgs[p.stem] = p
    if len(imgs) < min_images:
        raise Bad(f"found {len(imgs)} images, at least {min_images} are needed")
    counts, labeled, orphans, problems = [0] * len(names), 0, 0, []
    for p in sorted((raw / "labels").iterdir()):
        if p.stem not in imgs:
            orphans += 1
            p.unlink()  # label without image: ignore it
            continue
        if p.stat().st_size > 5 << 20:
            raise Bad(f"{p.name} is too big for a label file")
        boxes = 0
        for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            parts = line.split()
            if not parts:
                continue
            try:
                if len(parts) != 5:
                    raise ValueError(f"expected 5 numbers (class x y w h), got {len(parts)}")
                c, vals = int(parts[0]), [float(x) for x in parts[1:]]
                if not 0 <= c < len(names):
                    raise ValueError(f"class {c} is not in classes.txt (it has {len(names)})")
                if any(not 0 <= v <= 1 for v in vals):
                    raise ValueError("box values must be between 0 and 1")
            except ValueError as e:
                problems.append(f"{p.name} line {n}: {e}")
                break
            counts[c] += 1
            boxes += 1
        labeled += boxes > 0
    if problems:
        raise Bad("label problems: " + " | ".join(problems[:5]) + (f" (+{len(problems) - 5} more)" if len(problems) > 5 else ""))
    if not sum(counts):
        raise Bad("no boxes found: the labels folder is empty or does not match the image names")
    return {"images": len(imgs), "labeled": labeled, "background": len(imgs) - labeled, "orphan_labels": orphans,
            "classes": dict(zip(names, counts))}


# ---------- jobs ----------

def find_job(jid):
    r = sql("select * from jobs where id = ?", jid) if JOB_ID.match(jid or "") else []
    if not r:
        raise HTTPException(404, "no such job")
    return r[0]


def job_view(r, me, position=None):
    live = LIVE.get(r["id"], {})
    frac = live.get("frac") if r["state"] == "running" else r["frac"]
    eta, t0 = None, live.get("t0")  # counted from the first progress line: dataset prep and model loading are not training speed
    if r["state"] == "running" and t0 and frac and frac - t0[1] > 0.005:
        eta = (time.time() - t0[0]) * (1 - frac) / (frac - t0[1])
    can_open = me["role"] == "admin" or r["owner"] == me["name"]
    return {"id": r["id"], "owner": r["owner"], "state": r["state"], "model": r["model"], "epochs": r["epochs"],
            "note": r["note"], "created": r["created"], "started": r["started"], "finished": r["finished"],
            "images": r["images"], "target": r["target"], "frac": frac, "epoch": live.get("epoch"), "epoch_total": live.get("epochs"), "eta": eta,
            "share": ACTIVE.get(r["id"]), "position": position, "detail": r["detail"] if can_open else "", "can_open": can_open,
            "can_cancel": can_open and r["state"] in ("queued", "running"),
            "can_delete": me["role"] == "admin" and r["state"] in ("done", "failed", "cancelled")}


def queued_ids():
    return [r["id"] for r in sql("select id from jobs where state = 'queued' order by created")]


def tail(p, n=40):
    if not p.is_file():
        return ""
    with open(p, "rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 16384))
        return "\n".join(f.read().decode("utf-8", "replace").splitlines()[-n:])


def kill_tree(p):
    if os.name == "nt":  # data loader workers are children: terminate() alone would leave them running
        subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
    else:
        p.terminate()


def read_metrics(jdir):
    """One dict per finished epoch from Ultralytics' results.csv (also works while the job runs)."""
    out = []
    for f in jdir.glob("runs/*/results.csv"):
        try:
            with open(f, encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
        except OSError:
            continue
        for row in rows:
            try:  # the last line may be half written
                r = {k.strip(): v.strip() for k, v in row.items()}
                out.append({"epoch": int(float(r["epoch"])), "precision": float(r["metrics/precision(B)"]),
                            "recall": float(r["metrics/recall(B)"]), "map50": float(r["metrics/mAP50(B)"]),
                            "map5095": float(r["metrics/mAP50-95(B)"])})
            except (KeyError, ValueError, AttributeError):
                pass
        break
    return out


def last_metrics(jdir):
    m = read_metrics(jdir)
    return f"mAP50 {m[-1]['map50']:.3f}   mAP50-95 {m[-1]['map5095']:.3f}" if m else ""


def finish(jid, state, detail=""):
    frac = 1.0 if state == "done" else (LIVE.get(jid, {}).get("frac") or 0)
    sql("update jobs set state = ?, finished = ?, detail = ?, frac = ? where id = ?", state, time.time(), detail, frac, jid)
    LIVE.pop(jid, None)
    PROCS.pop(jid, None)
    CANCEL.pop(jid, None)
    notify_later(jid)


def run_job(jid, share):
    jdir = JOBS / jid
    if not sql_n("update jobs set state = 'running', started = ? where id = ? and state = 'queued'", time.time(), jid):
        return  # cancelled while waiting
    LIVE[jid] = {"frac": None, "epoch": 0, "epochs": 0}
    env = {**os.environ, "YOLO_CONFIG": str(jdir / "config.yaml"), "PYTHONIOENCODING": "utf-8", "YOLO_SHARE": str(share)}
    code = 0
    with open(jdir / "log.txt", "a", encoding="utf-8") as log:
        for script in ("prepare_dataset.py", "train.py"):
            if jid in CANCEL:
                break
            p = PROCS[jid] = subprocess.Popen(
                [sys.executable, "-u", str(core.ROOT / "scripts" / script)], cwd=core.ROOT, env=env, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            if jid in CANCEL:
                kill_tree(p)
            for line in p.stdout:
                line = ANSI.sub("", line).rstrip()
                log.write(line + "\n")
                log.flush()
                f = core.parse_progress(line, st := LIVE[jid])
                if f is not None:
                    st["frac"] = max(st["frac"] or 0, f)  # val bars restart at 0; never go backwards
                    st.setdefault("t0", (time.time(), st["frac"]))
            code = p.wait()
            if code:
                break
    if jid in CANCEL:
        return finish(jid, "cancelled", f"stopped by {CANCEL[jid]}")
    if code:
        return finish(jid, "failed", " | ".join(tail(jdir / "log.txt", 3).splitlines()) or f"exit code {code}")
    if not list(jdir.glob("runs/*/weights/best.pt")):
        return finish(jid, "failed", "training ended without a best.pt")
    finish(jid, "done", last_metrics(jdir))


def job_thread(jid, share):
    try:
        run_job(jid, share)
    except Exception as e:  # keep the queue alive whatever happens to one job
        finish(jid, "failed", f"gateway error: {e}")
    finally:
        ACTIVE.pop(jid, None)
        WAKE.set()
    with contextlib.suppress(Exception):
        cleanup()


def dispatcher():
    """Start the oldest waiting jobs while the shares of the running jobs plus the next one fit in 100%.
    The share is read when the job starts, so changing it never touches a job that already runs."""
    while True:
        WAKE.wait(3)
        WAKE.clear()
        try:
            share = int(get_settings()["job_share"])
            for jid in queued_ids():
                if jid in ACTIVE:
                    continue
                if sum(ACTIVE.values()) + share > 100:
                    break  # strict order: a later job never jumps ahead of an older one
                ACTIVE[jid] = share
                threading.Thread(target=job_thread, args=(jid, share), daemon=True).start()
        except Exception as e:
            print("dispatcher:", e)


# ---------- predict: run a finished job's best.pt on an image or a video ----------

def load_model(jid):
    if jid not in MODELS:
        from ultralytics import YOLO  # heavy import: only when someone predicts
        MODELS.clear()
        MODELS[jid] = YOLO(str(next((JOBS / jid).glob("runs/*/weights/best.pt"))))
    return MODELS[jid]


def infer(model, frame, conf):
    dev = web_cfg()["predict_device"]  # cpu by default so a prediction never fights the training for the GPU
    r = model.predict(frame, conf=conf, verbose=False, **({} if dev == "auto" else {"device": dev}))[0]
    dets = [{"name": r.names[int(c)], "conf": round(float(p), 3), "box": [round(float(v)) for v in b]}
            for c, p, b in zip(r.boxes.cls, r.boxes.conf, r.boxes.xyxy)]
    return r.plot(), dets


def open_writer(d, fps, size):
    """ffmpeg process fed with raw BGR frames: OpenCV alone cannot write H.264, which is what browsers play."""
    import imageio_ffmpeg
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{size[0]}x{size[1]}",
           "-r", str(fps), "-i", "-", "-an", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", str(d / "out.mp4")]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)


def close_writer(w):
    with contextlib.suppress(OSError):
        w.stdin.close()
    err = w.stderr.read()
    if w.wait():
        raise Bad("could not write the result video: " + err.decode(errors="replace")[-300:])


def run_predict(pid):
    import cv2
    p, cfgw = PRED[pid], web_cfg()
    d, src, model = p["dir"], p["dir"] / p["src"], load_model(p["job"])
    if p["kind"] == "image":
        img = cv2.imread(str(src))
        if img is None:
            raise Bad("this image cannot be read")
        plotted, dets = infer(model, img, p["conf"])
        cv2.imwrite(str(d / "out.jpg"), plotted)
        p.update(file="out.jpg", mime="image/jpeg", result={"detections": dets})
        return
    cap = cv2.VideoCapture(str(src))
    n, fps = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), cap.get(cv2.CAP_PROP_FPS) or 25
    size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    if n <= 0 or not size[0]:
        raise Bad("this video cannot be read")
    if n > cfgw["max_video_frames"]:
        raise Bad(f"the video has {n} frames (about {n / fps:.0f} s); the limit is {cfgw['max_video_frames']} frames")
    writer = open_writer(d, fps, size)
    stats, i = {}, 0
    while i < cfgw["max_video_frames"]:
        ok, frame = cap.read()
        if not ok:
            break
        plotted, dets = infer(model, frame, p["conf"])
        try:
            writer.stdin.write(plotted.tobytes())
        except OSError:  # ffmpeg stopped: close_writer reports why
            break
        seen = {}
        for x in dets:
            seen[x["name"]] = seen.get(x["name"], 0) + 1
        for k, v in seen.items():
            s = stats.setdefault(k, {"frames": 0, "max_in_frame": 0})
            s["frames"], s["max_in_frame"] = s["frames"] + 1, max(s["max_in_frame"], v)
        i += 1
        p["frac"] = min(i / n, 1)
    cap.release()
    close_writer(writer)
    p.update(file="out.mp4", mime="video/mp4", result={"frames": i, "seconds": round(i / fps, 1), "classes": stats})


def predict_worker():
    while True:
        pid = PQUEUE.get()
        p = PRED.get(pid)
        if not p:
            continue
        p["state"] = "running"
        try:
            run_predict(pid)
            p["state"] = "done"
        except Bad as e:
            p.update(state="failed", error=str(e))
        except Exception as e:
            p.update(state="failed", error=f"prediction failed: {e}")
        (p["dir"] / p["src"]).unlink(missing_ok=True)  # the upload is not needed once the result exists


def pred_view(pid):
    p = PRED[pid]
    return {"id": pid, "state": p["state"], "kind": p["kind"], "frac": p["frac"], "error": p.get("error", ""),
            "result": p.get("result"), "file": f"/api/predict/{pid}/file" if p["state"] == "done" else None}


def cleanup():
    cut = time.time() - web_cfg()["keep_days"] * 86400
    for r in sql("select id from jobs where state in ('done', 'failed', 'cancelled') and finished < ?", cut):
        shutil.rmtree(JOBS / r["id"], ignore_errors=True)
        sql("delete from jobs where id = ?", r["id"])
    sql("delete from sessions where expires < ?", time.time())


def startup():
    global started
    if started:
        return
    started = True
    if not sql("select 1 from users"):
        pw = secrets.token_urlsafe(9)
        sql("insert into users(name, pw, role) values('admin', ?, 'admin')", hash_pw(pw))
        note = HOME / "data" / "FIRST_ADMIN_PASSWORD.txt"
        note.write_text(f"user: admin\npassword: {pw}\n(deleted when the admin changes the password)\n")
        print(f"\nFirst start: sign in as admin with password {pw}  (also saved in {note})\n")
    sql("update jobs set state = 'failed', finished = ?, detail = 'the server restarted while this job was running' where state = 'running'",
        time.time())
    cleanup()
    threading.Thread(target=dispatcher, daemon=True).start()
    threading.Thread(target=predict_worker, daemon=True).start()


@contextlib.asynccontextmanager
async def lifespan(_app):
    startup()
    yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path
    if request.method == "POST" and (path in ("/api/jobs", "/api/datasets") or path.endswith("/predict")):  # refuse big anonymous uploads before they are read
        if not user_from_cookie(request):
            return JSONResponse({"detail": "sign in first"}, 401)
        key = "max_predict_mb" if path.endswith("/predict") else "max_upload_mb"
        length = request.headers.get("content-length", "0")
        if length.isdigit() and int(length) > (web_cfg()[key] + 1) * 2**20:
            return JSONResponse({"detail": f"the file is bigger than {web_cfg()[key]} MB"}, 413)
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    return resp


@app.get("/")
def index():
    return FileResponse(Path(__file__).with_name("index.html"))


# ---------- account ----------

@app.post("/api/login")
def login(body: dict, response: Response):
    name, pw = str(body.get("name", "")), str(body.get("password", ""))
    FAILS[name] = [t for t in FAILS.get(name, []) if t > time.time() - 300]
    if len(FAILS[name]) >= 5:
        raise HTTPException(429, "too many wrong passwords, wait 5 minutes")
    rows = sql("select * from users where name = ? and active = 1", name)
    if not rows or not check_pw(pw, rows[0]["pw"]):
        FAILS[name].append(time.time())
        raise HTTPException(401, "wrong name or password")
    tok = secrets.token_urlsafe(32)
    sql("insert into sessions values(?, ?, ?)", hashlib.sha256(tok.encode()).hexdigest(), name, time.time() + 12 * 3600)
    response.set_cookie("gw_session", tok, httponly=True, samesite="lax", max_age=12 * 3600)
    return public_user(dict(rows[0]))


@app.post("/api/logout")
def logout(request: Request, response: Response):
    tok = request.cookies.get("gw_session")
    if tok:
        sql("delete from sessions where token = ?", hashlib.sha256(tok.encode()).hexdigest())
    response.delete_cookie("gw_session")
    return {"ok": True}


# What a user may change per training (the desktop app shows every key; paths and device stay with the server).
# (section, key, kind, low/choices, high, help). kind: int, float, bool, text, choice, "auto" + one of those = also accepts `auto`.
SETTINGS = [
    ("train", "imgsz", "int", 32, 1280, "Image size in pixels (multiple of 32). Bigger = finer detail, slower."),
    ("train", "patience", "int", 0, 500, "Stop early after this many epochs without improvement (0 = never)."),
    ("train", "batch", "auto int", 1, 256, "Images per step. auto = fits the free GPU memory."),
    ("train", "workers", "auto int", 0, 16, "Data loading threads. auto = from the CPU cores."),
    ("train", "cache", "auto choice", ["ram", "disk", "false"], None, "Keep decoded images in RAM or on disk to speed up epochs."),
    ("train", "amp", "auto bool", None, None, "Mixed precision (GPU only). auto = on when a GPU is used."),
    ("train", "optimizer", "auto choice", ["SGD", "Adam", "AdamW", "NAdam", "RAdam", "RMSProp"], None, "auto lets YOLO pick from the epoch count."),
    ("train", "cos_lr", "bool", None, None, "Cosine learning-rate schedule."),
    ("train", "single_cls", "bool", None, None, "Treat all classes as one."),
    ("train", "mosaic", "float", 0, 1, "Augmentation: mosaic probability."),
    ("train", "close_mosaic", "int", 0, 100, "Switch mosaic off for the last N epochs."),
    ("train", "scale", "float", 0, 1, "Augmentation: random zoom range."),
    ("train", "fliplr", "float", 0, 1, "Augmentation: horizontal flip probability."),
    ("train", "flipud", "float", 0, 1, "Augmentation: vertical flip probability."),
    ("train", "seed", "int", 0, 99999, "Random seed."),
    ("split", "val", "float", 0.05, 0.4, "Share of the images used for validation (the charts)."),
    ("split", "test", "float", 0, 0.3, "Share kept aside for testing."),
    ("split", "seed", "int", 0, 99999, "Seed of the train/val/test split."),
    ("split", "group_regex", "text", None, None, "Regex whose group 1 keeps images of the same unit in one split (empty = off)."),
]


def settings_form():
    cfg = core.load_config()
    return [{"section": s, "key": k, "kind": kind, "low": lo, "high": hi, "help": hp, "default": cfg[s].get(k)}
            for s, k, kind, lo, hi, hp in SETTINGS]


def apply_settings(cfg, raw):
    """Check what the form sent (JSON {"train.imgsz": 640, ...}) against SETTINGS and put it in the job's config."""
    try:
        sent = json.loads(raw) if raw else {}
        assert isinstance(sent, dict)
    except Exception:
        raise HTTPException(400, "settings must be a JSON object")
    known = {f"{r[0]}.{r[1]}": r for r in SETTINGS}
    for name, v in sent.items():
        if name not in known:
            raise HTTPException(400, f"unknown setting {name}")
        s, k, kind, lo, hi, hint = known[name]
        v = v.strip() if isinstance(v, str) else v
        if "auto" in kind and v == "auto":
            cfg[s][k] = "auto"; continue
        kind = kind.replace("auto ", "")
        try:
            if kind == "bool":
                assert isinstance(v, bool)
            elif kind == "text":
                assert isinstance(v, str) and len(v) <= 200
                re.compile(v)
            elif kind == "choice":
                assert v in lo
                v = False if v == "false" else v
            else:
                v = int(v) if kind == "int" and not isinstance(v, bool) else float(v)
                assert lo <= v <= hi
            if k == "imgsz":
                assert v % 32 == 0
        except Exception:
            raise HTTPException(400, f"{name} is not valid. {hint}")
        cfg[s][k] = v
    if cfg["split"]["val"] + cfg["split"]["test"] > 0.6:
        raise HTTPException(400, "split.val + split.test must not be more than 0.6")


@app.get("/api/me")
def me(u=Depends(current_user)):
    return {**public_user(u), "options": {**{k: web_cfg()[k] for k in ("max_epochs", "max_upload_mb", "min_images")}, "models": allowed_models(),
                                          "settings": settings_form()}}


@app.post("/api/me/password")
def change_password(body: dict, u=Depends(current_user)):
    if not check_pw(str(body.get("old", "")), u["pw"]):
        raise HTTPException(400, "the current password is wrong")
    check_new_password(body.get("new"))
    sql("update users set pw = ? where name = ?", hash_pw(body["new"]), u["name"])
    (HOME / "data" / "FIRST_ADMIN_PASSWORD.txt").unlink(missing_ok=True)
    return {"ok": True}


@app.post("/api/me/email")
def change_email(body: dict, u=Depends(current_user)):
    email = str(body.get("email", "")).strip()
    check_email(email)
    sql("update users set email = ? where name = ?", email, u["name"])
    return {"ok": True}


# ---------- jobs ----------

@app.get("/api/jobs")
def list_jobs(u=Depends(current_user)):
    rows = sql("select * from jobs order by (state = 'running') desc, (state = 'queued') desc, "
               "case when state = 'queued' then created end asc, created desc limit 200")
    waiting = queued_ids()
    return [job_view(r, u, waiting.index(r["id"]) + 1 if r["id"] in waiting else None) for r in rows]


@app.post("/api/jobs")
def submit(file: UploadFile | None = File(None), dataset: str = Form(""), model: str = Form(...), epochs: int = Form(...),
           note: str = Form(""), settings: str = Form(""), target: float = Form(0), u=Depends(current_user)):
    """Train on a saved dataset (`dataset` = its id) or on a zip sent now (which is saved as a dataset first)."""
    cfgw = web_cfg()
    if model not in allowed_models():
        raise HTTPException(400, "that model is not allowed")
    if not 1 <= epochs <= cfgw["max_epochs"]:
        raise HTTPException(400, f"epochs must be between 1 and {cfgw['max_epochs']}")
    if not 0 <= target <= 100:
        raise HTTPException(400, "target mAP50 must be between 0 and 100 (percent, 0 = no target)")
    if bool(file) == bool(dataset):
        raise HTTPException(400, "send a zip or pick a saved dataset, not both and not neither")
    cfg = core.load_config()
    apply_settings(cfg, settings)  # before the zip is read: a bad value must not leave a dataset behind
    if u["role"] != "admin" and sql("select count(*) c from jobs where owner = ? and state in ('queued', 'running')",
                                    u["name"])[0]["c"] >= cfgw["max_active_per_user"]:
        raise HTTPException(429, f"you already have {cfgw['max_active_per_user']} jobs waiting or running")
    try:
        ds = make_dataset(file, file.filename, u, cfgw) if file else own_dataset(dataset, u)
    except Bad as e:
        raise HTTPException(e.code, str(e))
    jid = time.strftime("%y%m%d-%H%M%S-") + secrets.token_hex(2)
    jdir = JOBS / jid
    try:
        jdir.mkdir()
        shutil.copytree(DATASETS / ds["id"], jdir / "data", copy_function=link_or_copy)  # the job never touches the saved dataset
        cfg["model"], cfg["train"]["epochs"] = model, epochs
        cfg["paths"] = {"data_dir": str(jdir / "data"), "runs_dir": str(jdir / "runs"), "output_dir": str(jdir / "outputs")}
        (jdir / "config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    except Exception:
        shutil.rmtree(jdir, ignore_errors=True)
        raise
    sql("insert into jobs(id, owner, state, model, epochs, note, created, images, info, detail, dataset, target) values(?, ?, 'queued', ?, ?, ?, ?, ?, ?, '', ?, ?)",
        jid, u["name"], model, epochs, note.strip()[:200], time.time(), ds["images"], ds["info"], ds["id"], target / 100 or None)
    WAKE.set()
    return job_view(find_job(jid), u, len(queued_ids()))


# ---------- datasets: saved zips that jobs can reuse ----------

def link_or_copy(src, dst):
    try:
        os.link(src, dst)  # same disk: no second copy of the images
    except OSError:
        shutil.copy2(src, dst)


def make_dataset(file, name, u, cfgw):
    if u["role"] != "admin" and sql("select count(*) c from datasets where owner = ?", u["name"])[0]["c"] >= cfgw["max_datasets_per_user"]:
        raise Bad(f"you already have {cfgw['max_datasets_per_user']} datasets; delete one you no longer need first", 429)
    did = "d" + time.strftime("%y%m%d-%H%M%S-") + secrets.token_hex(2)
    d = DATASETS / did
    d.mkdir(parents=True)
    try:
        save_upload(file, d / "upload.zip", cfgw["max_upload_mb"] * 2**20)
        raw, names = extract(d / "upload.zip", d, cfgw)
        info = validate(raw, names, cfgw["min_images"])
        (d / "upload.zip").unlink()
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise
    size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
    row = {"id": did, "owner": u["name"], "name": (Path(name or "").stem or did)[:80], "created": time.time(),
           "images": info["images"], "info": json.dumps(info), "bytes": size}
    sql("insert into datasets values(?, ?, ?, ?, ?, ?, ?)", *row.values())
    return row


def own_dataset(did, u):
    r = sql("select * from datasets where id = ?", did) if DS_ID.match(did or "") else []
    if not r:
        raise Bad("no such dataset", 404)
    if u["role"] != "admin" and r[0]["owner"] != u["name"]:
        raise Bad("this is not your dataset", 403)
    return dict(r[0])


def dataset_view(r):
    info = json.loads(r["info"])
    return {"id": r["id"], "owner": r["owner"], "name": r["name"], "created": r["created"], "images": r["images"],
            "labeled": info["labeled"], "background": info["background"], "classes": info["classes"],
            "size_mb": round(r["bytes"] / 2**20, 1), "jobs": sql("select count(*) c from jobs where dataset = ?", r["id"])[0]["c"]}


@app.get("/api/datasets")
def list_datasets(u=Depends(current_user)):
    rows = sql("select * from datasets order by created desc") if u["role"] == "admin" else \
        sql("select * from datasets where owner = ? order by created desc", u["name"])
    return [dataset_view(r) for r in rows]


@app.post("/api/datasets")
def add_dataset(file: UploadFile = File(...), name: str = Form(""), u=Depends(current_user)):
    try:
        row = make_dataset(file, name.strip() or file.filename, u, web_cfg())
    except Bad as e:
        raise HTTPException(e.code, str(e))
    return dataset_view(row)


@app.delete("/api/datasets/{did}")
def delete_dataset(did: str, u=Depends(current_user)):
    try:
        own_dataset(did, u)
    except Bad as e:
        raise HTTPException(e.code, str(e))
    if sql("select 1 from jobs where dataset = ? and state in ('queued', 'running')", did):
        raise HTTPException(409, "a job waiting or running uses this dataset")
    shutil.rmtree(DATASETS / did, ignore_errors=True)
    if (DATASETS / did).exists():
        raise HTTPException(409, "some files are still in use, try again in a moment")
    sql("delete from datasets where id = ?", did)
    return {"ok": True}


@app.get("/api/jobs/{jid}")
def job_detail(jid: str, u=Depends(current_user)):
    r = find_job(jid)
    waiting = queued_ids()
    v = job_view(r, u, waiting.index(jid) + 1 if jid in waiting else None)
    if v["can_open"]:
        v["log"], v["summary"] = tail(JOBS / jid / "log.txt"), json.loads(r["info"] or "{}")
        ds = sql("select name from datasets where id = ?", r["dataset"] or "")
        v["dataset_name"] = ds[0]["name"] if ds else ""
    return v


@app.post("/api/jobs/{jid}/cancel")
def cancel(jid: str, u=Depends(current_user)):
    r = find_job(jid)
    if u["role"] != "admin" and r["owner"] != u["name"]:
        raise HTTPException(403, "you can only cancel your own jobs")
    if sql_n("update jobs set state = 'cancelled', finished = ?, detail = ? where id = ? and state = 'queued'",
             time.time(), f"cancelled by {u['name']} before it started", jid):
        notify_later(jid)
    elif r["state"] == "running":
        CANCEL[jid] = u["name"]
        if jid in PROCS:
            kill_tree(PROCS[jid])
    else:
        raise HTTPException(409, "this job is already finished")
    return {"ok": True}


@app.delete("/api/jobs/{jid}")
def delete_job(jid: str, _=Depends(admin_user)):
    """Remove a finished job with its log, training files and result."""
    if find_job(jid)["state"] not in ("done", "failed", "cancelled"):
        raise HTTPException(409, "cancel the job first; only finished jobs can be deleted")
    for k in [k for k, v in PRED.items() if v["job"] == jid]:
        PRED.pop(k)
    MODELS.pop(jid, None)
    shutil.rmtree(JOBS / jid, ignore_errors=True)
    if (JOBS / jid).exists():
        raise HTTPException(409, "some files are still in use (the training is stopping), try again in a moment")
    sql("delete from jobs where id = ?", jid)
    return {"ok": True}


@app.get("/api/jobs/{jid}/download")
def download(jid: str, u=Depends(current_user)):
    r = find_job(jid)
    if u["role"] != "admin" and r["owner"] != u["name"]:
        raise HTTPException(403, "you can only download your own results")
    if r["state"] != "done":
        raise HTTPException(409, "this job has no result")
    jdir, zp = JOBS / jid, JOBS / jid / "result.zip"
    if not zp.is_file():
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            for run in jdir.glob("runs/*"):
                for f in [run / "weights" / "best.pt", run / "results.csv", run / "args.yaml", *run.glob("*.png")]:
                    if f.is_file():
                        z.write(f, f.relative_to(run).as_posix())
            z.write(jdir / "data" / "classes.txt", "classes.txt")
    return FileResponse(zp, filename=f"yolo-{jid}.zip")


def own_job(jid, u):
    r = find_job(jid)
    if u["role"] != "admin" and r["owner"] != u["name"]:
        raise HTTPException(403, "you can only use your own jobs")
    return r


@app.get("/api/jobs/{jid}/metrics")
def metrics(jid: str, u=Depends(current_user)):
    own_job(jid, u)
    return {"epochs": read_metrics(JOBS / jid)}


@app.post("/api/jobs/{jid}/predict")
def predict(jid: str, file: UploadFile = File(...), conf: float = Form(0.25), u=Depends(current_user)):
    cfgw = web_cfg()
    if own_job(jid, u)["state"] != "done":
        raise HTTPException(409, "this job has no trained model (yet)")
    if not 0.01 <= conf <= 0.99:
        raise HTTPException(400, "confidence must be between 0.01 and 0.99")
    ext = Path(file.filename or "").suffix.lower()
    kind = "image" if ext in core.IMG_EXT else "video" if ext in VIDEO_EXT else None
    if not kind:
        raise HTTPException(400, "send an image (" + " ".join(sorted(core.IMG_EXT)) + ") or a video (" + " ".join(sorted(VIDEO_EXT)) + ")")
    for k in [k for k, v in PRED.items() if v["created"] < time.time() - 86400]:  # results are kept for a day
        shutil.rmtree(PRED.pop(k)["dir"], ignore_errors=True)
    if sum(v["owner"] == u["name"] and v["state"] in ("queued", "running") for v in PRED.values()) >= 2:
        raise HTTPException(429, "you already have 2 predictions waiting or running")
    pid = secrets.token_hex(8)
    d = JOBS / jid / "predict" / pid
    d.mkdir(parents=True)
    try:
        save_upload(file, d / ("in" + ext), cfgw["max_predict_mb"] * 2**20)
    except Bad as e:
        shutil.rmtree(d, ignore_errors=True)
        raise HTTPException(e.code, str(e))
    PRED[pid] = {"job": jid, "owner": u["name"], "dir": d, "src": "in" + ext, "kind": kind, "conf": conf, "state": "queued",
                 "frac": 0, "created": time.time()}
    PQUEUE.put(pid)
    return pred_view(pid)


def own_pred(pid, u):
    p = PRED.get(pid)
    if not p:
        raise HTTPException(404, "no such prediction (results are kept for a day)")
    if u["role"] != "admin" and p["owner"] != u["name"]:
        raise HTTPException(403, "this is not your prediction")
    return p


@app.get("/api/predict/{pid}")
def predict_status(pid: str, u=Depends(current_user)):
    own_pred(pid, u)
    return pred_view(pid)


@app.get("/api/predict/{pid}/file")
def predict_file(pid: str, u=Depends(current_user)):
    p = own_pred(pid, u)
    if p["state"] != "done":
        raise HTTPException(409, "the result is not ready")
    return FileResponse(p["dir"] / p["file"], media_type=p["mime"])


# ---------- admin: users and notification settings ----------

@app.get("/api/users")
def list_users(_=Depends(admin_user)):
    return [{"name": r["name"], "role": r["role"], "email": r["email"], "active": bool(r["active"])}
            for r in sql("select * from users order by name")]


@app.post("/api/users")
def add_user(body: dict, _=Depends(admin_user)):
    name, role, email = str(body.get("name", "")), body.get("role", "user"), str(body.get("email", "")).strip()
    if not NAME.match(name):
        raise HTTPException(400, "name: 2 to 32 letters, digits, dot, dash or underscore")
    if role not in ("admin", "user"):
        raise HTTPException(400, "role must be admin or user")
    check_new_password(body.get("password"))
    check_email(email)
    if sql("select 1 from users where name = ?", name):
        raise HTTPException(409, "that name is taken")
    sql("insert into users(name, pw, role, email) values(?, ?, ?, ?)", name, hash_pw(body["password"]), role, email)
    return {"ok": True}


@app.patch("/api/users/{name}")
def edit_user(name: str, body: dict, me=Depends(admin_user)):
    r = sql("select * from users where name = ?", name)
    if not r:
        raise HTTPException(404, "no such user")
    role, active = body.get("role", r[0]["role"]), int(bool(body.get("active", r[0]["active"])))
    if role not in ("admin", "user"):
        raise HTTPException(400, "role must be admin or user")
    if r[0]["role"] == "admin" and (role != "admin" or not active) and not other_admins(name):
        raise HTTPException(409, "keep at least one active admin")
    if "email" in body:
        check_email(str(body["email"]).strip())
        sql("update users set email = ? where name = ?", str(body["email"]).strip(), name)
    if body.get("password"):
        check_new_password(body["password"])
        sql("update users set pw = ? where name = ?", hash_pw(body["password"]), name)
    sql("update users set role = ?, active = ? where name = ?", role, active, name)
    if not active:
        sql("delete from sessions where name = ?", name)
    return {"ok": True}


@app.delete("/api/users/{name}")
def delete_user(name: str, me=Depends(admin_user)):
    r = sql("select * from users where name = ?", name)
    if not r:
        raise HTTPException(404, "no such user")
    if name == me["name"] or (r[0]["role"] == "admin" and not other_admins(name)):
        raise HTTPException(409, "you cannot delete yourself or the last admin")
    sql("delete from users where name = ?", name)
    sql("delete from sessions where name = ?", name)
    return {"ok": True}


MODEL_NAME = re.compile(r"^[A-Za-z0-9._-]+\.pt$")
DL = {}  # model name -> "downloading" | "error: ..." (gone again when it finished)


def newest_first(names):
    """Newest generation first, inside a generation the biggest (x, l, m, s, n); names that do not fit the pattern go last."""
    def key(n):
        m = re.match(r"yolo(?:v)?(\d+)([nsmlx])?", n)
        return (-int(m[1]), -"nsmlx".index(m[2] or "n"), n) if m else (0, 0, n)
    return sorted(set(names), key=key)


def allowed_models():
    """What users may pick: the admin's list (saved in the database) or, until he saves one, `models` of web.yaml."""
    r = sql("select value from settings where key = 'models'")
    return newest_first(m for m in r[0]["value"].split(",") if m) if r else newest_first(web_cfg()["models"])


def known_models():
    have = {p.name for p in (core.ROOT / "models").glob("*.pt")}
    return newest_first(set(core.load_config().get("model_presets", [])) | have | set(allowed_models()))


def fetch_model(name):
    from ultralytics.utils.downloads import attempt_download_asset
    try:
        target = core.resolve_model(name)
        attempt_download_asset(target)
        if not Path(target).is_file():
            raise RuntimeError("Ultralytics has no download for this name")
        DL.pop(name, None)
    except Exception as e:
        DL[name] = f"error: {str(e)[:150]}"


@app.get("/api/models")
def list_models(_=Depends(admin_user)):
    ok = set(allowed_models())
    out = []
    for m in known_models():
        f = core.ROOT / "models" / m
        out.append({"name": m, "allowed": m in ok, "downloaded": f.is_file(), "mb": round(f.stat().st_size / 2**20, 1) if f.is_file() else None,
                    "download": DL.get(m)})
    return out


@app.put("/api/models")
def set_models(body: dict, _=Depends(admin_user)):
    names = body.get("allowed")
    if not isinstance(names, list) or not names or not all(isinstance(n, str) and n in known_models() for n in names):
        raise HTTPException(400, "pick at least one model from the list")
    sql("insert or replace into settings values('models', ?)", ",".join(names))
    return {"ok": True}


@app.post("/api/models/download")
def download_model(body: dict, _=Depends(admin_user)):
    name = str(body.get("name", "")).strip()
    if not MODEL_NAME.match(name):
        raise HTTPException(400, "a model name looks like yolo26n.pt")
    if DL.get(name) == "downloading":
        raise HTTPException(409, "already downloading")
    DL[name] = "downloading"
    threading.Thread(target=fetch_model, args=(name,), daemon=True).start()
    return {"ok": True}


@app.get("/api/settings")
def read_settings(_=Depends(admin_user)):
    s = get_settings()
    last = sql("select value from settings where key = 'last_notify_error'")
    return {**s, "smtp_password": "", "smtp_password_set": bool(s["smtp_password"]), "last_notify_error": last[0]["value"] if last else ""}


@app.put("/api/settings")
def write_settings(body: dict, _=Depends(admin_user)):
    new = {k: str(body[k]).strip() for k in SETTING_DEFAULTS if k in body}
    if new.get("smtp_password") == "":
        new.pop("smtp_password")  # blank = keep the saved one
    if "job_share" in new and not (new["job_share"].isdigit() and 10 <= int(new["job_share"]) <= 100):
        raise HTTPException(400, "the share per job must be a whole number from 10 to 100")
    if "smtp_port" in new and not new["smtp_port"].isdigit():
        raise HTTPException(400, "SMTP port must be a number")
    if new.get("smtp_security", "starttls") not in ("starttls", "ssl", "none"):
        raise HTTPException(400, "security must be starttls, ssl or none")
    if new.get("teams_url") and not new["teams_url"].startswith("https://"):
        raise HTTPException(400, "the Teams webhook URL must start with https://")
    if new.get("public_url") and not new["public_url"].startswith(("http://", "https://")):
        raise HTTPException(400, "the public URL must start with http:// or https://")
    if new.get("smtp_from") and not EMAIL.match(new["smtp_from"]):
        raise HTTPException(400, "the From address does not look right")
    for k, v in new.items():
        sql("insert or replace into settings values(?, ?)", k, v)
    return {"ok": True}


@app.post("/api/settings/test")
def test_notification(body: dict, me=Depends(admin_user)):
    s = get_settings()
    try:
        if body.get("channel") == "smtp":
            to = str(body.get("to") or me["email"]).strip()
            if not EMAIL.match(to):
                raise ValueError("type the address to send the test to")
            send_mail(s, to, "YOLO gateway test", "If you read this, email notifications work.")
        elif body.get("channel") == "teams":
            send_teams(s["teams_url"], "YOLO gateway test: Teams notifications work.")
        else:
            raise ValueError("unknown channel")
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True}


def main():
    cfg = web_cfg()
    uvicorn.run(app, host=cfg["host"], port=int(cfg["port"]))


if __name__ == "__main__":
    main()
