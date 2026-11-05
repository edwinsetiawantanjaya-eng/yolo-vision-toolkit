"""Shared helpers for every script: config, paths, hardware auto-detect, dataset prep.

Run `python core.py` for a hardware report and the values "auto" will pick.
"""
import math
import os
import random
import re
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent  # project folder (scripts/ lives inside it)
CONFIG = ROOT / "configuration" / "config.yaml"
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}

# Train memory in GB per image at imgsz 640 with AMP, by model size letter.
# Scaled from a measured sizing table (matches an RTX A3000 6 GB laptop GPU).
GB_PER_IMG = {"n": 0.12, "s": 0.19, "m": 0.31, "l": 0.46, "x": 0.62}
# Letter at the end of a model name -> size class (v9: t/s/m/c/e, v8+: n/s/m/l/x)
SIZE_ALIAS = {"t": "n", "n": "n", "s": "s", "m": "m", "c": "m", "l": "l", "e": "x", "x": "x"}


# ---------- config and paths ----------

def load_config():
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def save_config(cfg):
    CONFIG.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")


def path(cfg, key):
    """Folder from config `paths`. Relative = inside the project, absolute is kept as is."""
    return (ROOT / cfg["paths"][key]).resolve()


def resolve_model(name):
    """`yolo26n.pt` -> models/yolo26n.pt (Ultralytics downloads it there on first use).
    A .yaml (train from scratch) or any path with a folder is passed through."""
    if Path(name).suffix == ".pt" and Path(name).name == name:
        (ROOT / "models").mkdir(exist_ok=True)
        return str(ROOT / "models" / name)
    return name


def count_train_images(cfg):
    d = path(cfg, "data_dir") / "dataset" / "train" / "images"
    return sum(1 for p in d.glob("*") if p.suffix.lower() in IMG_EXT) if d.is_dir() else 0


# ---------- hardware ----------

def detect_hardware():
    """What this machine can give right now (free memory, not installed memory)."""
    import psutil

    vm = psutil.virtual_memory()
    hw = {"cpu_threads": os.cpu_count() or 4, "ram_free_gb": vm.available / 2**30,
          "ram_total_gb": vm.total / 2**30, "gpu": None, "vram_free_gb": 0.0,
          "vram_total_gb": 0.0, "device": "cpu"}
    try:
        import torch
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info(0)
            hw.update(gpu=torch.cuda.get_device_name(0), device="0",
                      vram_free_gb=free / 2**30, vram_total_gb=total / 2**30,
                      gpu_count=torch.cuda.device_count())
        elif torch.backends.mps.is_available():
            hw.update(gpu="Apple MPS", device="mps")
    except ImportError:
        hw["note"] = "torch not installed yet, assuming CPU (run 00.Setup_env.ps1)"
    return hw


def model_size(model_name):
    return SIZE_ALIAS.get(Path(model_name).stem[-1:], "s")  # unknown name -> assume s


def auto_settings(cfg, hw, n_train):
    """Values for every `auto` in config.train."""
    imgsz = cfg["train"].get("imgsz", 640)
    cuda = hw["device"] not in ("cpu", "mps")
    if cuda:
        per_img = GB_PER_IMG[model_size(cfg["model"])] * (imgsz / 640) ** 2
        fit = (hw["vram_free_gb"] * 0.8 - 1.5) / per_img  # 20% headroom + ~1.5 GB fixed
    else:
        fit = 8
    batch = 2 ** int(math.log2(max(2, min(fit, 64))))  # power of 2 in [2, 64]
    cores = max(1, hw["cpu_threads"] // 2)
    cache_gb = n_train * imgsz * imgsz * 3 / 2**30
    return {
        "device": hw["device"],
        "batch": batch,
        "workers": min(cores, 8 if cuda else 4),
        "cache": "ram" if cache_gb < 0.4 * hw["ram_free_gb"] else "disk",
        "amp": cuda,
    }


def resolve_train_args(cfg, hw, n_train):
    auto = auto_settings(cfg, hw, n_train)
    return {k: auto[k] if v == "auto" and k in auto else v for k, v in cfg["train"].items()}


# ---------- dataset ----------

def split_groups(stems, val, test, group_regex, seed):
    """Assign file stems to train/val/test. Stems sharing a group (regex group 1) stay together,
    which stops the same physical unit leaking into both train and val."""
    groups = {}
    for s in stems:
        m = re.search(group_regex, s) if group_regex else None
        groups.setdefault(m.group(1) if m else s, []).append(s)
    keys = sorted(groups)
    random.Random(seed).shuffle(keys)
    want = {"val": len(stems) * val, "test": len(stems) * test}
    out = {"train": [], "val": [], "test": []}
    for k in keys:
        for part in ("val", "test"):
            if len(out[part]) < want[part]:
                out[part] += groups[k]
                break
        else:
            out["train"] += groups[k]
    return out


def read_classes(data):
    classes = data / "classes.txt"
    if not classes.is_file():
        sys.exit(f"missing {classes} (one class name per line)")
    return [n.strip() for n in classes.read_text(encoding="utf-8").splitlines() if n.strip()]


def write_dataset_yaml(cfg):
    """(Re)write dataset.yaml with this machine's absolute path, so a dataset folder copied from another PC just works."""
    data = path(cfg, "data_dir")
    out = data / "dataset"
    names = read_classes(data)
    if not (out / "train" / "images").is_dir():
        sys.exit(f"no dataset in {out}: copy train/val/test there, or put images in {data / 'raw'} and run prepare_dataset")
    for c in out.glob("*/*.cache"):  # stale caches hold old absolute paths
        c.unlink()
    lines = [f"path: {out.as_posix()}", "train: train/images", "val: val/images"]
    if (out / "test" / "images").is_dir() and any((out / "test" / "images").iterdir()):
        lines.append("test: test/images")
    lines += ["names:"] + [f"  {i}: {n}" for i, n in enumerate(names)]
    y = out / "dataset.yaml"
    y.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return y


def prepare_dataset(cfg):
    data = path(cfg, "data_dir")
    raw, out = data / "raw", data / "dataset"
    read_classes(data)  # fail before touching anything

    imgs = {p.stem: p for p in sorted((raw / "images").glob("*")) if p.suffix.lower() in IMG_EXT}
    if imgs:
        sp = cfg["split"]
        parts = split_groups(list(imgs), sp["val"], sp["test"], sp.get("group_regex", ""), sp["seed"])
        if out.exists():
            shutil.rmtree(out)  # generated folder only; raw/ is never touched
        for part, stems in parts.items():
            for sub in ("images", "labels"):
                (out / part / sub).mkdir(parents=True)
            for s in stems:
                shutil.copy2(imgs[s], out / part / "images" / imgs[s].name)
                lbl = raw / "labels" / f"{s}.txt"
                if lbl.is_file():  # no label file = background image, valid for YOLO
                    shutil.copy2(lbl, out / part / "labels" / lbl.name)
            print(f"{part}: {len(stems)} images")
    elif not (out / "train" / "images").is_dir():
        sys.exit(f"no images in {raw / 'images'} and no ready dataset in {out}")
    else:
        print(f"{raw / 'images'} is empty, using the existing split in {out}")

    y = write_dataset_yaml(cfg)
    print(f"wrote {y}")
    return y


if __name__ == "__main__":
    c, h = load_config(), detect_hardware()
    print("hardware:", {k: (round(v, 1) if isinstance(v, float) else v) for k, v in h.items()})
    print("auto picks:", auto_settings(c, h, count_train_images(c)))
