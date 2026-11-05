# Annotation tool (X-AnyLabeling)

> **Credit:** the labeling application is **[X-AnyLabeling](https://github.com/CVHub520/X-AnyLabeling)** by CVHub520 and contributors, licensed under GPL-3.0. This folder contains **none of its code**. It only holds a one-click setup script (`00.Setup_env.ps1`) that installs the official `x-anylabeling-cvhub` package from PyPI into a local `.venv`, and a small launcher (`app.py`). All features, bugs and docs of the tool itself belong to the X-AnyLabeling project; please star and support it there.

Draw boxes on images and export them as YOLO labels for `vision-desktop`.

## Open it (two clicks)
1. First time on a PC: right-click `00.Setup_env.ps1` -> **Run with PowerShell**. It installs everything, then opens the tool.
2. Later: double-click `app.py`.

Copying this folder to another PC works the same way: run step 1 there.

## Label images
1. Put photos in `vision-desktop\data\raw\images`.
2. In the tool: **Open Dir** -> that images folder.
3. **Upload -> Upload Label Classes File** -> `vision-desktop\data\classes.txt` (one class per line, ids start at 0).
4. Press `R`, click two opposite corners of the object, pick the class. Repeat.
   To keep drawing without re-pressing `R`: Settings -> General -> Behavior -> turn off *Auto Switch To Edit Mode*.

## Export to YOLO
1. **Export Annotations -> Export YOLO Annotations**, task = detection, classes file = the same `classes.txt`.
2. The `.txt` files may land in a `labels` folder inside the images folder. Move them to
   `vision-desktop\data\raw\labels` (each file named like its image: `a.jpg` -> `a.txt`).
3. In `vision-desktop`, double-click `app.py`: **1. Prepare dataset**, **2. Train**, **3. Predict**.

The tool also saves a `.json` next to each image. Leave them; the dataset step ignores them.

## Notes
- Installs the CPU build (enough for drawing). For GPU auto-labeling run `.venv\Scripts\python -m uv pip install "x-anylabeling-cvhub[gpu]"` after removing the cpu one.
- Project: https://github.com/CVHub520/X-AnyLabeling
