"""Config GUI. Double-click it, or: python app.py

The form is built from configuration/config.yaml, so a new key in the file shows up here with no code change.
Saving rewrites config.yaml (comments are lost; docs/README.md documents every key).
"""
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import timedelta
from pathlib import Path
from tkinter import messagebox, ttk

HERE = Path(__file__).resolve().parent
VENV = HERE / ".venv"


def bootstrap():
    """Double-click friendly: always run inside .venv, and run the setup first if .venv is missing or broken."""
    py = VENV / "Scripts" / "python.exe"
    works = py.is_file() and subprocess.run([str(py), "--version"], capture_output=True).returncode == 0
    if not works:
        print("Environment not ready: running the setup (it opens this GUI when done) ...")
        subprocess.call(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "00.Setup_env.ps1")])
    else:
        subprocess.call([str(py), str(HERE / "app.py")])
    sys.exit()


if __name__ == "__main__" and Path(sys.prefix).resolve() != VENV.resolve():
    bootstrap()  # never returns; the .venv copy of this script continues below

import yaml  # noqa: E402

sys.path.insert(0, str(HERE / "scripts"))
import core  # noqa: E402

ROWS_PER_COLUMN = 12
HIDDEN = {"model_presets"}  # lists edited by hand in the file


def hms(seconds):
    return str(timedelta(seconds=int(seconds)))


def to_text(v):
    return yaml.safe_dump(v, default_flow_style=True, width=10**6).strip().removesuffix("\n...")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("YOLO Easy Config")
        self.geometry("1050x720")
        self.cfg = core.load_config()
        self.vars = {}  # ("train", "imgsz") -> StringVar
        self.proc = None
        self.t0 = None  # start time of the running job; None when idle
        self.frac = None  # 0..1 done, None until the output shows progress
        self.epoch = self.epochs = 0
        self.auto_text = ""

        tabs = ttk.Notebook(self)
        tabs.pack(fill="x", padx=8, pady=6)
        general = {k: v for k, v in self.cfg.items() if not isinstance(v, dict) and k not in HIDDEN}
        sections = {"general": general, **{k: v for k, v in self.cfg.items() if isinstance(v, dict)}}
        for name, items in sections.items():
            self.build_tab(tabs, name, items)

        prog = ttk.Frame(self)
        prog.pack(fill="x", padx=10, pady=(4, 0))
        self.bar = ttk.Progressbar(prog, maximum=100)
        self.bar.pack(fill="x")
        self.prog_label = ttk.Label(prog, text="idle")
        self.prog_label.pack(anchor="w")

        self.hw_label = ttk.Label(self, justify="left", font=("Consolas", 10))
        self.hw_label.pack(fill="x", padx=10)

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=6)
        self.buttons = []
        for text, cmd in [("Save Configuration", self.save),
                          ("1. Prepare dataset", lambda: self.run("prepare_dataset.py")),
                          ("2. Run Train", lambda: self.run("train.py")),
                          ("3. Predict", lambda: self.run("predict.py"))]:
            b = ttk.Button(bar, text=text, command=cmd)
            b.pack(side="left", padx=3)
            self.buttons.append(b)
        for text, cmd in [("Open results", lambda: os.startfile(core.path(self.cfg, "runs_dir"))),
                          ("Clear train", self.clear_train), ("Clear dataset", self.clear_dataset),
                          ("Stop", self.stop)]:  # packed from the right edge inwards
            ttk.Button(bar, text=text, command=cmd).pack(side="right", padx=3)

        self.log = tk.Text(self, height=18, bg="#111", fg="#ddd", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.tick()

    def build_tab(self, tabs, name, items):
        frame = ttk.Frame(tabs, padding=8)
        tabs.add(frame, text=name)
        for i, (key, val) in enumerate(items.items()):
            row, col = i % ROWS_PER_COLUMN, (i // ROWS_PER_COLUMN) * 2
            ttk.Label(frame, text=key).grid(row=row, column=col, sticky="w", padx=(0, 6), pady=2)
            var = tk.StringVar(value=to_text(val))
            self.vars[(name, key)] = var
            if key == "model":  # dropdown of presets, still free-typing
                w = ttk.Combobox(frame, textvariable=var, values=self.cfg.get("model_presets", []), width=28)
            else:
                w = ttk.Entry(frame, textvariable=var, width=30)
            w.grid(row=row, column=col + 1, sticky="w", padx=(0, 24), pady=2)

    def collect(self):
        """Form -> config dict. Each field is parsed as YAML: 8 -> int, auto -> str, true -> bool."""
        for (section, key), var in self.vars.items():
            value = yaml.safe_load(var.get())
            if section == "general":
                self.cfg[key] = value
            else:
                self.cfg[section][key] = value
        return self.cfg

    def save(self):
        core.save_config(self.collect())
        self.say("saved config.yaml")

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def tick(self):
        """Every second: hardware text and the progress/ETA label."""
        try:
            self.refresh_hw()
        except Exception:  # form half-typed (invalid YAML, empty number): keep the last text
            pass
        self.show_progress()
        self.after(1000, self.tick)

    def refresh_hw(self):
        hw = core.detect_hardware()
        if not self.running():  # while a job runs it holds the VRAM, so fresh auto picks would mislead
            cfg = self.collect()
            auto = core.auto_settings(cfg, hw, core.count_train_images(cfg))
            self.auto_text = f"auto picks for {cfg['model']} @ {cfg['train'].get('imgsz')}px: {auto}"
        self.hw_label.config(text=(
            f"GPU: {hw['gpu'] or 'none (CPU mode)'}   free VRAM: {hw['vram_free_gb']:.1f}/{hw['vram_total_gb']:.1f} GB\n"
            f"CPU threads: {hw['cpu_threads']}   free RAM: {hw['ram_free_gb']:.1f}/{hw['ram_total_gb']:.1f} GB   {hw.get('note', '')}\n"
            f"{self.auto_text}"))

    def parse_progress(self, line):
        """0..1 done from Ultralytics output. Train: '3/100 4.1G ...' (epoch) and '17/80 2.2s/it' (batch). Predict: 'image 5/50'."""
        if m := re.match(r"\s*(\d+)/(\d+)\s+[\d.]+G", line):
            self.epoch, self.epochs = int(m[1]), int(m[2])
        if m := re.search(r"image (\d+)/(\d+)", line):
            return int(m[1]) / int(m[2])
        b = re.findall(r"\b(\d+)/(\d+)\s+[\d.]+(?:it/s|s)\b", line)
        if self.epochs and b:
            return (self.epoch - 1 + int(b[-1][0]) / int(b[-1][1])) / self.epochs

    def show_progress(self):
        if self.t0 is None:
            return
        el = time.monotonic() - self.t0
        if self.frac is None:
            return self.prog_label.config(text=f"running ...   elapsed {hms(el)}")
        eta = hms(el * (1 - self.frac) / self.frac) if self.frac > 0.005 else "--"
        ep = f"epoch {self.epoch}/{self.epochs}   " if self.epochs else ""
        self.bar["value"] = self.frac * 100
        self.prog_label.config(text=f"{ep}{self.frac * 100:.1f}%   elapsed {hms(el)}   ETA {eta}")

    def on_line(self, line):
        line = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line)  # Ultralytics colour/erase codes
        self.say(line)
        f = self.parse_progress(line)
        if f is not None:
            if self.frac is None:
                self.bar.stop()
                self.bar.config(mode="determinate")
            self.frac = max(self.frac or 0, f)  # val bars restart at 0; never go backwards
            self.show_progress()

    def finish(self, code):
        self.say(f"[finished, exit code {code}]")
        self.bar.stop()
        self.bar.config(mode="determinate")
        if code == 0:
            self.bar["value"] = 100
        state = "done" if code == 0 else f"stopped (exit code {code})"
        self.prog_label.config(text=f"{state}   elapsed {hms(time.monotonic() - self.t0)}")
        self.t0 = None

    def say(self, text):
        self.log.insert("end", text.rstrip("\n") + "\n")
        self.log.see("end")

    def clear_train(self):
        """Delete every training run (weights, plots, results) inside the runs folder; the folder itself stays."""
        if self.running():
            return self.say("something is already running; press Stop first")
        d = core.path(self.cfg, "runs_dir")
        runs = [p for p in d.iterdir()] if d.is_dir() else []
        if not runs:
            return self.say("no training runs, nothing to clear")
        if not messagebox.askyesno("Clear train", f"Delete {len(runs)} item(s) in {d}?\n\n"
                                   "This removes the trained weights (best.pt / last.pt) and results of every run."):
            return
        for p in runs:
            shutil.rmtree(p) if p.is_dir() else p.unlink()
        self.say(f"deleted {len(runs)} item(s) in {d}")

    def clear_dataset(self):
        """Delete the generated data/dataset folder (train/val/test + dataset.yaml). data/raw is never touched."""
        if self.proc and self.proc.poll() is None:
            return self.say("something is already running; press Stop first")
        d = core.path(self.cfg, "data_dir") / "dataset"
        n = core.count_train_images(self.cfg)
        if not d.is_dir():
            return self.say("no dataset folder, nothing to clear")
        if not messagebox.askyesno("Clear dataset", f"Delete {d}\n({n} training images and its val/test sets)?\n\n"
                                   "data/raw is kept. If this dataset was copied in by hand and not made from data/raw, "
                                   "it is gone unless you still have the original."):
            return
        shutil.rmtree(d)
        self.say(f"deleted {d}")

    def run(self, script, cmd=None):
        """Run scripts/<script> with this Python, or an explicit command, and stream its output."""
        if self.proc and self.proc.poll() is None:
            return self.say("something is already running; press Stop first")
        self.save()
        cmd = cmd or [sys.executable, "-u", str(core.ROOT / "scripts" / script)]
        self.proc = subprocess.Popen(
            cmd, cwd=core.ROOT, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        self.say(f"> {script or cmd[-1]}")
        self.t0, self.frac, self.epoch, self.epochs = time.monotonic(), None, 0, 0
        self.bar.config(mode="indeterminate", value=0)
        self.bar.start(15)
        threading.Thread(target=self.pump, args=(self.proc,), daemon=True).start()

    def pump(self, proc):
        for line in proc.stdout:
            self.after(0, self.on_line, line)
        self.after(0, self.finish, proc.wait())

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


if __name__ == "__main__":
    App().mainloop()
