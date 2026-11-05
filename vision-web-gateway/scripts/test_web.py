"""End-to-end self-check of the gateway on a temp folder: login and roles, zip checks, queue, a real 1-epoch CPU training,
cancel, download and an email through a fake SMTP server. Needs fastapi, httpx. Usage: python test_web.py (takes a few minutes)"""
import io
import json
import os
import socket
import tempfile
import threading
import time
import zipfile
from pathlib import Path

import numpy as np
import yaml
from PIL import Image

tmp = Path(tempfile.mkdtemp())
os.environ["GATEWAY_HOME"] = str(tmp / "home")
import core  # noqa: E402  (after the env var is not needed, but the config below must exist before web is imported)

cfg = yaml.safe_load(core.CONFIG.read_text(encoding="utf-8"))
cfg["train"].update(imgsz=64, batch=4, workers=0, device="cpu", cache=False, amp=False, plots=False)
(tmp / "config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
os.environ["YOLO_CONFIG"] = str(tmp / "config.yaml")
core.CONFIG = tmp / "config.yaml"

import web  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def fake_smtp(box):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)

    def serve():
        while True:
            conn, _ = srv.accept()
            f = conn.makefile("rwb")
            w = lambda s: (f.write((s + "\r\n").encode()), f.flush())
            w("220 fake")
            data, buf = False, []
            while line := f.readline():
                t = line.decode(errors="replace").rstrip("\r\n")
                if data:
                    if t == ".":
                        data = False
                        box.append("\n".join(buf))
                        buf = []
                        w("250 ok")
                    else:
                        buf.append(t)
                elif t.upper().startswith("DATA"):
                    data = True
                    w("354 go")
                elif t.upper().startswith("QUIT"):
                    w("221 bye")
                    break
                else:
                    w("250 ok")
            conn.close()

    threading.Thread(target=serve, daemon=True).start()
    return srv.getsockname()[1]


def make_zip(n=12, classes="a\nb\n", bad_label=None, extra=None):
    rng, buf = np.random.default_rng(0), io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        if classes is not None:
            z.writestr("data/classes.txt", classes)
        for i in range(n):
            im = io.BytesIO()
            Image.fromarray(rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)).save(im, "JPEG")
            z.writestr(f"images/img{i}.jpg", im.getvalue())
            if i < n - 2:  # last two stay background images
                z.writestr(f"labels/img{i}.txt", bad_label or f"{i % 2} 0.5 0.5 0.4 0.4\n")
        for name, body in (extra or {}).items():
            z.writestr(name, body)
    return buf.getvalue()


def post_job(c, data, epochs=1):
    return c.post("/api/jobs", files={"file": ("d.zip", data, "application/zip")},
                  data={"model": "yolo26n.pt", "epochs": str(epochs), "note": "test"})


def wait(c, jid, states, timeout=600):
    end = time.time() + timeout
    while time.time() < end:
        j = c.get(f"/api/jobs/{jid}").json()
        if j["state"] in states:
            return j
        time.sleep(2)
    raise AssertionError(f"job {jid} never reached {states}: {j}")


mails = []
port = fake_smtp(mails)

with TestClient(web.app) as admin:
    assert admin.get("/api/jobs").status_code == 401
    pw = (tmp / "home/data/FIRST_ADMIN_PASSWORD.txt").read_text().split("password: ")[1].split()[0]
    assert admin.post("/api/login", json={"name": "admin", "password": "nope"}).status_code == 401
    assert admin.post("/api/login", json={"name": "admin", "password": pw}).json()["role"] == "admin"

    for n in ("bob", "eve"):
        assert admin.post("/api/users", json={"name": n, "password": n + "-password", "email": f"{n}@x.com"}).status_code == 200
    assert admin.post("/api/users", json={"name": "bob", "password": "12345678"}).status_code == 409
    assert admin.post("/api/users", json={"name": "x", "password": "12345678"}).status_code == 400  # name too short
    assert admin.patch("/api/users/admin", json={"role": "user"}).status_code == 409  # last admin

    bob, eve = TestClient(web.app), TestClient(web.app)
    for c, n in ((bob, "bob"), (eve, "eve")):
        assert c.post("/api/login", json={"name": n, "password": n + "-password"}).status_code == 200
    assert bob.get("/api/users").status_code == 403 and bob.get("/api/settings").status_code == 403
    assert bob.post("/api/settings/test", json={"channel": "teams"}).status_code == 403

    # zip checks: every message must say what to fix
    assert "classes.txt" in post_job(bob, make_zip(classes=None)).json()["detail"]
    assert "not in classes.txt" in post_job(bob, make_zip(bad_label="7 0.5 0.5 0.4 0.4")).json()["detail"]
    assert "at least" in post_job(bob, make_zip(n=3)).json()["detail"]
    assert "valid zip" in post_job(bob, b"not a zip").json()["detail"]
    slip = tmp / "slip"  # a '../../evil.txt' entry is flattened to its name: nothing escapes the job folder
    slip.mkdir()
    (slip / "z.zip").write_bytes(make_zip(extra={"../../evil.txt": "x"}))
    web.extract(slip / "z.zip", slip / "data", web.web_cfg())
    assert (slip / "data/raw/labels/evil.txt").exists() and not (tmp / "evil.txt").exists() and not (slip / "evil.txt").exists()
    assert post_job(bob, make_zip(), epochs=9999).status_code == 400

    # settings and notifications through a fake SMTP server
    assert admin.put("/api/settings", json={"smtp_host": "127.0.0.1", "smtp_port": str(port), "smtp_security": "none",
                                            "smtp_from": "yolo@x.com", "smtp_password": "secret", "teams_url": "http://not-https"}).status_code == 400
    assert admin.put("/api/settings", json={"smtp_host": "127.0.0.1", "smtp_port": str(port), "smtp_security": "none",
                                            "smtp_from": "yolo@x.com", "smtp_password": "secret"}).status_code == 200
    s = admin.get("/api/settings").json()
    assert s["smtp_password"] == "" and s["smtp_password_set"]  # never sent back
    admin.put("/api/settings", json={"smtp_password": ""})
    assert admin.get("/api/settings").json()["smtp_password_set"]  # blank keeps it
    assert admin.post("/api/settings/test", json={"channel": "smtp", "to": "me@x.com"}).json()["ok"]
    assert len(mails) == 1
    assert not admin.post("/api/settings/test", json={"channel": "teams"}).json()["ok"]  # no URL yet

    # queue: A runs, B and C wait. C (admin) cancelled while queued, B (bob) cancelled while running.
    a = post_job(bob, make_zip()).json()
    b = post_job(bob, make_zip()).json()
    assert post_job(bob, make_zip()).status_code == 429  # bob already has 2 waiting or running
    c = post_job(admin, make_zip()).json()
    jobs = eve.get("/api/jobs").json()  # another user sees the whole queue
    assert {j["id"] for j in jobs} >= {a["id"], b["id"], c["id"]}
    pos = {j["id"]: j["position"] for j in jobs}
    assert pos[b["id"]] == 1 and pos[c["id"]] == 2 or pos[b["id"]] == 2 and pos[c["id"]] == 3  # A may not have started yet
    assert eve.get(f"/api/jobs/{a['id']}").json()["can_open"] is False and "log" not in eve.get(f"/api/jobs/{a['id']}").json()
    assert eve.post(f"/api/jobs/{b['id']}/cancel").status_code == 403  # nobody cancels another user's job except an admin
    assert eve.delete(f"/api/jobs/{b['id']}").status_code == 403 and bob.delete(f"/api/jobs/{b['id']}").status_code == 403  # delete is admin only
    assert admin.post(f"/api/jobs/{c['id']}/cancel").status_code == 200
    assert admin.get(f"/api/jobs/{c['id']}").json()["state"] == "cancelled"

    done = wait(bob, a["id"], ("done", "failed", "cancelled"))
    assert done["state"] == "done", done
    assert "best.pt" in " ".join(zipfile.ZipFile(io.BytesIO(bob.get(f"/api/jobs/{a['id']}/download").content)).namelist())
    assert eve.get(f"/api/jobs/{a['id']}/download").status_code == 403

    wait(admin, b["id"], ("running",), timeout=120)
    assert admin.delete(f"/api/jobs/{b['id']}").status_code == 409  # still running: cancel first
    assert bob.post(f"/api/jobs/{b['id']}/cancel").status_code == 200  # the owner cancels his own job
    assert wait(admin, b["id"], ("cancelled", "done", "failed"), timeout=120)["state"] == "cancelled"
    assert "bob" in admin.get(f"/api/jobs/{b['id']}").json()["detail"]
    # charts data and predict on the finished job
    m = bob.get(f"/api/jobs/{a['id']}/metrics").json()["epochs"]
    assert len(m) == 1 and {"epoch", "precision", "recall", "map50", "map5095"} <= m[0].keys(), m
    assert eve.get(f"/api/jobs/{a['id']}/metrics").status_code == 403

    def predict(c, name, data, jid=a["id"]):
        return c.post(f"/api/jobs/{jid}/predict", files={"file": (name, data)}, data={"conf": "0.05"})

    def wait_pred(c, pid):
        end = time.time() + 180
        while time.time() < end:
            p = c.get(f"/api/predict/{pid}").json()
            if p["state"] in ("done", "failed"):
                return p
            time.sleep(1)
        raise AssertionError(p)

    rng = np.random.default_rng(1)
    jpg = io.BytesIO()
    Image.fromarray(rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)).save(jpg, "JPEG")
    assert predict(bob, "x.txt", b"x").status_code == 400  # neither image nor video
    assert predict(eve, "x.jpg", jpg.getvalue()).status_code == 403  # not eve's job
    p = wait_pred(bob, predict(bob, "x.jpg", jpg.getvalue()).json()["id"])
    assert p["state"] == "done" and p["kind"] == "image" and isinstance(p["result"]["detections"], list), p
    assert bob.get(p["file"]).headers["content-type"] == "image/jpeg" and eve.get(p["file"]).status_code == 403
    import cv2
    vpath = tmp / "v.avi"
    vw = cv2.VideoWriter(str(vpath), cv2.VideoWriter_fourcc(*"MJPG"), 5, (64, 64))
    for _ in range(8):
        vw.write(rng.integers(0, 255, (64, 64, 3), dtype=np.uint8))
    vw.release()
    p = wait_pred(bob, predict(bob, "v.avi", vpath.read_bytes()).json()["id"])
    assert p["state"] == "done" and p["result"]["frames"] == 8 and p["file"], p
    assert len(bob.get(p["file"]).content) > 100 and bob.get(p["file"]).headers["content-type"] == "video/mp4"
    assert wait_pred(bob, predict(bob, "bad.mp4", b"not a video").json()["id"])["state"] == "failed"

    assert predict(bob, "x.jpg", jpg.getvalue(), jid=b["id"]).status_code == 409  # a cancelled job has no model

    end = time.time() + 20
    while len(mails) < 3 and time.time() < end:  # test mail + A done + B cancelled
        time.sleep(1)
    assert len(mails) >= 3 and any(a["id"] in m for m in mails), mails

    # delete a finished job with its files (admin only)
    assert (web.JOBS / b["id"]).exists()
    assert admin.delete(f"/api/jobs/{b['id']}").status_code == 200
    assert not (web.JOBS / b["id"]).exists() and admin.get(f"/api/jobs/{b['id']}").status_code == 404

    # datasets: save once, train on it, list per owner, delete
    before = {d["id"] for d in bob.get("/api/datasets").json()}  # every zip sent with a training was saved as a dataset too
    assert len(before) == 2  # jobs a and b
    ds =bob.post("/api/datasets", files={"file": ("my set.zip", make_zip(), "application/zip")}, data={"name": "Set A"}).json()
    assert ds["name"] == "Set A" and ds["images"] == 12 and ds["classes"] == {"a": 5, "b": 5}, ds
    assert bob.post("/api/datasets", files={"file": ("x.zip", make_zip(classes=None))}).status_code == 400
    assert {d["id"] for d in bob.get("/api/datasets").json()} == before | {ds["id"]} and eve.get("/api/datasets").json() == []
    assert [d["id"] for d in admin.get("/api/datasets").json()].count(ds["id"]) == 1
    assert eve.delete(f"/api/datasets/{ds['id']}").status_code == 403
    assert bob.post("/api/jobs", data={"dataset": ds["id"], "model": "yolo26n.pt", "epochs": "1"},
                    files={"file": ("d.zip", make_zip())}).status_code == 400  # a zip and a dataset together
    assert eve.post("/api/jobs", data={"dataset": ds["id"], "model": "yolo26n.pt", "epochs": "1"}).status_code == 403
    j = bob.post("/api/jobs", data={"dataset": ds["id"], "model": "yolo26n.pt", "epochs": "1"})
    assert j.status_code == 200, j.text
    jd = bob.get(f"/api/jobs/{j.json()['id']}").json()
    assert jd["dataset_name"] == "Set A" and len(list((web.JOBS / jd["id"] / "data/raw/images").iterdir())) == 12
    assert bob.delete(f"/api/datasets/{ds['id']}").status_code == 409  # a job waiting or running uses it
    assert admin.post(f"/api/jobs/{jd['id']}/cancel").status_code == 200  # an admin can cancel any job
    wait(admin, jd["id"], ("cancelled", "done", "failed"), timeout=120)
    assert bob.delete(f"/api/datasets/{ds['id']}").status_code == 200 and not (web.DATASETS / ds["id"]).exists()
    assert (web.JOBS / jd["id"] / "data/raw/images").exists()  # the job keeps its own copy

    # admin model list: only admin sees it, bad names are refused, the saved list is what users may pick
    ml = {m["name"]: m for m in admin.get("/api/models").json()}
    assert "yolo26n.pt" in ml and ml["yolo26n.pt"]["allowed"] and bob.get("/api/models").status_code == 403
    assert admin.put("/api/models", json={"allowed": ["nope.pt"]}).status_code == 400 and admin.put("/api/models", json={"allowed": []}).status_code == 400
    assert admin.post("/api/models/download", json={"name": "../x.pt"}).status_code == 400
    assert bob.put("/api/models", json={"allowed": ["yolo26n.pt"]}).status_code == 403
    assert admin.put("/api/models", json={"allowed": ["yolo26n.pt", "yolo26s.pt"]}).status_code == 200
    assert bob.get("/api/me").json()["options"]["models"] == ["yolo26s.pt", "yolo26n.pt"]  # newest and biggest first
    assert web.newest_first(["yolov8n.pt", "yolo11n.pt", "yolo26n.pt", "yolo26x.pt", "yolo11m.pt", "my.pt"]) == \
        ["yolo26x.pt", "yolo26n.pt", "yolo11m.pt", "yolo11n.pt", "yolov8n.pt", "my.pt"]
    assert bob.post("/api/jobs", data={"dataset": ds["id"], "model": "yolov8n.pt", "epochs": "1"}).status_code in (400, 404)  # not on the list
    assert admin.put("/api/models", json={"allowed": ["yolo26n.pt"]}).status_code == 200

    # training settings from the form: listed in /api/me, checked, written into the job's own config.yaml
    opts = {f"{s['section']}.{s['key']}": s for s in admin.get("/api/me").json()["options"]["settings"]}
    assert opts["train.imgsz"]["default"] == 64 and "paths.data_dir" not in opts and "train.device" not in opts
    nds = len(admin.get("/api/datasets").json())
    for bad in ({"train.imgsz": 650}, {"train.mosaic": 3}, {"train.device": "cpu"}, {"split.group_regex": "("}, {"train.cache": "tape"},
                {"train.amp": "yes"}, {"split.val": 0.4, "split.test": 0.3}):
        r = admin.post("/api/jobs", files={"file": ("d.zip", make_zip())}, data={"model": "yolo26n.pt", "epochs": "1", "settings": json.dumps(bad)})
        assert r.status_code == 400, (bad, r.text)
    assert len(admin.get("/api/datasets").json()) == nds  # a bad setting leaves no dataset behind
    good = {"train.imgsz": 320, "train.batch": "auto", "train.workers": 0, "train.cache": "false", "train.amp": False, "train.optimizer": "AdamW",
            "train.cos_lr": True, "train.mosaic": 0.5, "split.val": 0.2, "split.group_regex": "^(.*)_"}
    r = admin.post("/api/jobs", files={"file": ("d.zip", make_zip())}, data={"model": "yolo26n.pt", "epochs": "1", "settings": json.dumps(good)})
    assert r.status_code == 200, r.text
    assert r.json()["target"] is None  # no target set
    gid = r.json()["id"]
    cfg = yaml.safe_load((web.JOBS / gid / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["train"]["imgsz"] == 320 and cfg["train"]["batch"] == "auto" and cfg["train"]["cache"] is False and cfg["train"]["amp"] is False
    assert cfg["train"]["optimizer"] == "AdamW" and cfg["split"]["val"] == 0.2 and cfg["train"]["epochs"] == 1
    admin.post(f"/api/jobs/{gid}/cancel")
    wait(admin, gid, ("cancelled", "done", "failed"), timeout=120)
    for bad in ("101", "-1"):  # target mAP50 in percent
        assert admin.post("/api/jobs", files={"file": ("d.zip", make_zip())}, data={"model": "yolo26n.pt", "epochs": "1", "target": bad}).status_code == 400
    r = admin.post("/api/jobs", files={"file": ("d.zip", make_zip())}, data={"model": "yolo26n.pt", "epochs": "1", "target": "95"})
    assert r.status_code == 200 and abs(r.json()["target"] - 0.95) < 1e-9, r.text
    admin.post(f"/api/jobs/{r.json()['id']}/cancel")
    wait(admin, r.json()["id"], ("cancelled", "done", "failed"), timeout=120)

    # server load: 50% per job means two jobs run side by side and the third waits
    assert admin.put("/api/settings", json={"job_share": "5"}).status_code == 400
    assert bob.put("/api/settings", json={"job_share": "50"}).status_code == 403
    assert admin.put("/api/settings", json={"job_share": "50"}).status_code == 200
    ids = [post_job(admin, make_zip(), epochs=3).json()["id"] for _ in range(3)]
    end = time.time() + 120
    while time.time() < end:
        st = [admin.get(f"/api/jobs/{i}").json() for i in ids]
        if [s["state"] for s in st[:2]] == ["running", "running"]:
            break
        time.sleep(0.5)
    assert [s["state"] for s in st] == ["running", "running", "queued"] and st[0]["share"] == 50, st
    for i in ids:
        assert admin.post(f"/api/jobs/{i}/cancel").status_code == 200
    for i in ids:
        assert wait(admin, i, ("cancelled", "done", "failed"), timeout=120)["state"] == "cancelled"

    # sessions end with the account
    assert admin.patch("/api/users/eve", json={"active": False}).status_code == 200
    assert eve.get("/api/jobs").status_code == 401
    assert bob.post("/api/logout").status_code == 200 and bob.get("/api/jobs").status_code == 401

print("ok")
