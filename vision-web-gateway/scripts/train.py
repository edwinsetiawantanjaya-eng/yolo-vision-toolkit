"""Step 3: train. Everything comes from config.yaml. Usage: python train.py"""
import os

import ultralytics.utils.torch_utils as tu
from ultralytics import YOLO

import core


def main():
    cfg, hw = core.load_config(), core.detect_hardware()
    if os.environ.get("YOLO_SHARE"):  # CPU training: Ultralytics takes min(8, cores - 1) threads however busy the server is
        tu.NUM_THREADS = max(1, min(tu.NUM_THREADS, hw["cpu_threads"]))
    data = core.write_dataset_yaml(cfg)  # always fresh: paths follow wherever this folder lives now
    args = core.resolve_train_args(cfg, hw, core.count_train_images(cfg))
    print(f"model={cfg['model']}  gpu={hw['gpu']}  free VRAM={hw['vram_free_gb']:.1f} GB  free RAM={hw['ram_free_gb']:.1f} GB")
    print("train args:", args)
    YOLO(core.resolve_model(cfg["model"])).train(
        data=str(data), project=str(core.path(cfg, "runs_dir")), name=cfg["run_name"], **args)


if __name__ == "__main__":  # guard is required on Windows when workers > 0
    main()
