"""Double-click to open X-AnyLabeling. Runs the setup first if .venv is missing or broken."""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = HERE / ".venv" / "Scripts" / "python.exe"
TOOL = HERE / ".venv" / "Scripts" / "xanylabeling.exe"

if PY.is_file() and TOOL.is_file() and subprocess.run([str(PY), "--version"], capture_output=True).returncode == 0:
    subprocess.Popen([str(TOOL)], cwd=HERE)  # this console closes, the tool keeps running
else:
    print("Not installed yet: running the setup (it opens the tool when done) ...")
    sys.exit(subprocess.call(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "00.Setup_env.ps1")]))
