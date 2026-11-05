"""Step 4: run the trained model. Usage: python predict.py [--source PATH] [--weights best.pt]"""
import argparse
import sys
from pathlib import Path

from ultralytics import YOLO

import core


def newest_weights(runs_dir):
    found = list(runs_dir.glob("*/weights/best.pt"))
    if not found:
        sys.exit(f"no trained model in {runs_dir}; run train.py first or pass --weights")
    return max(found, key=lambda p: p.stat().st_mtime)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source")
    ap.add_argument("--weights")
    cli = ap.parse_args()

    cfg, hw = core.load_config(), core.detect_hardware()
    opts = dict(cfg["predict"])
    weights = cli.weights or opts.pop("weights")
    source = cli.source or opts.pop("source")
    opts.pop("weights", None), opts.pop("source", None)
    if weights == "auto":
        weights = newest_weights(core.path(cfg, "runs_dir"))
    if opts.get("imgsz") == "auto":
        opts["imgsz"] = cfg["train"]["imgsz"]
    source = core.ROOT / source  # absolute stays absolute
    if not source.exists():
        sys.exit(f"source not found: {source}")
    print(f"weights={weights}  source={source}")
    YOLO(str(weights)).predict(source=str(source), device=hw["device"], save=True,
                               project=str(core.path(cfg, "output_dir")), name="predict", **opts)


if __name__ == "__main__":
    main()
