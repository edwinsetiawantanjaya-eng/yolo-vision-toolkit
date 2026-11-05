"""Self-check for the pure logic in core.py. Usage: python test_core.py"""
import core

stems = [f"{uid}_{i}" for uid in range(40) for i in range(3)]  # 40 units x 3 images
parts = core.split_groups(stems, 0.15, 0.10, r"^(\d+)_", seed=0)
assert sorted(sum(parts.values(), [])) == sorted(stems)
ids = {p: {s.split("_")[0] for s in v} for p, v in parts.items()}
assert not (ids["train"] & ids["val"] or ids["train"] & ids["test"] or ids["val"] & ids["test"]), "leakage"
assert len(parts["val"]) >= 18 and len(parts["test"]) >= 12

assert [core.model_size(n) for n in ("yolo26n.pt", "yolov9c.pt", "yolov9e.pt", "yolo11x.pt", "weird.pt")] == list("nmxxs")

cfg = {"model": "yolov8n.pt", "train": {"imgsz": 1152, "batch": "auto", "epochs": 5,
                                        "device": "auto", "amp": "auto", "cache": "auto", "workers": "auto"}}
gpu6 = {"device": "0", "vram_free_gb": 6.0, "ram_free_gb": 16, "cpu_threads": 16}
assert core.resolve_train_args(cfg, gpu6, 1266)["batch"] == 8  # matches the 6 GB result in project 004
assert core.resolve_train_args(cfg, gpu6, 1266)["epochs"] == 5  # explicit values are kept
cpu = {"device": "cpu", "vram_free_gb": 0, "ram_free_gb": 0.1, "cpu_threads": 8}
a = core.resolve_train_args(cfg, cpu, 1266)
assert (a["device"], a["amp"], a["cache"]) == ("cpu", False, "disk")

import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as t:  # a dataset copied from another PC: stale yaml must follow the new location
    t = Path(t)
    (t / "dataset/train/images").mkdir(parents=True)
    (t / "dataset/dataset.yaml").write_text("path: D:/old/place\n")
    (t / "classes.txt").write_text("a\nb\n")
    y = core.write_dataset_yaml({"paths": {"data_dir": str(t)}})
    assert f"path: {(t / 'dataset').as_posix()}" in y.read_text() and "1: b" in y.read_text()
print("ok")
