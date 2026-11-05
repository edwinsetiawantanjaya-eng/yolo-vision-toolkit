"""Start the web gateway. Double-click it, or: python app.py

First start prints (and saves in data/FIRST_ADMIN_PASSWORD.txt) the admin password. Open http://localhost:<port>.
"""
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV = HERE / ".venv"


def bootstrap():
    """Double-click friendly: always run inside .venv, and run the setup first if .venv is missing or broken."""
    py = VENV / "Scripts" / "python.exe"
    works = py.is_file() and subprocess.run([str(py), "--version"], capture_output=True).returncode == 0
    if not works:
        print("Environment not ready: running the setup (it starts the gateway when done) ...")
        subprocess.call(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "00.Setup_env.ps1")])
    else:
        subprocess.call([str(py), str(HERE / "app.py")])
    sys.exit()


if __name__ == "__main__" and Path(sys.prefix).resolve() != VENV.resolve():
    bootstrap()  # never returns; the .venv copy of this script continues below

if __name__ == "__main__":
    sys.path.insert(0, str(HERE / "scripts"))
    import web

    url = f"http://localhost:{web.web_cfg()['port']}"
    print(f"Web gateway at {url}  (Ctrl+C to stop)")
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    web.main()
