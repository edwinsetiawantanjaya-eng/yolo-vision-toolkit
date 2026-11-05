# Start here. Installs Python 3.12 if missing, creates .venv, installs X-AnyLabeling, then opens it.
# Right-click this file -> Run with PowerShell. Later, just double-click app.py.
#   -Force     reinstall X-AnyLabeling even if it is already installed
#   -NoLaunch  do not open the tool afterwards
param([switch]$Force, [switch]$NoLaunch)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

try {

    # Native tools print to stderr on failure; run them without turning that into a script error.
    function Try-Run($block) {
        $ErrorActionPreference = "Continue"
        & $block 2>&1 | Out-Null
        $ok = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = "Stop"
        return $ok
    }

    # X-AnyLabeling supports Python 3.11 to 3.13 (3.12 recommended).
    # A Python installed seconds ago is not on this window's PATH yet: reload it, and also look in the default install folder.
    function New-Venv {
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
        foreach ($v in "3.12", "3.11", "3.13") {
            $exe = "$env:LOCALAPPDATA\Programs\Python\Python$($v -replace '\.')\python.exe"
            if ((Get-Command py -ErrorAction SilentlyContinue) -and (Try-Run { py "-$v" -m venv .venv })) {
                Write-Host "Using Python $v"
                return $true
            }
            if ((Test-Path $exe) -and (Try-Run { & $exe -m venv .venv })) {
                Write-Host "Using Python $v"
                return $true
            }
        }
        return $false
    }

    # A .venv copied from another PC points at that PC's Python and cannot run: rebuild it.
    if ((Test-Path .venv) -and -not (Try-Run { & .\.venv\Scripts\python.exe --version })) {
        Write-Host "Existing .venv does not work on this PC, rebuilding it ..."
        Remove-Item .venv -Recurse -Force
    }

    if (-not (Test-Path .venv)) {
        if (-not (New-Venv)) {
            Write-Host "No suitable Python found. Installing Python 3.12 ..."
            if (Get-Command py -ErrorAction SilentlyContinue) { Try-Run { py install 3.12 } | Out-Null }
            if (-not (New-Venv)) {
                if (Get-Command winget -ErrorAction SilentlyContinue) {
                    Try-Run { winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements } | Out-Null
                }
                if (-not (New-Venv)) {
                    Write-Host "winget not available or failed. Downloading Python 3.12 from python.org ..."
                    $installer = "$env:TEMP\python-3.12.10-amd64.exe"
                    $ProgressPreference = "SilentlyContinue"
                    Invoke-WebRequest "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe" -OutFile $installer
                    Start-Process $installer -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1" -Wait
                }
                if (-not (New-Venv)) {
                    throw "Could not install Python 3.12 automatically. Install it from python.org, close and reopen PowerShell, then rerun this script."
                }
            }
        }
    }
    $py = ".\.venv\Scripts\python.exe"

    if ($Force -or -not (Try-Run { & $py -m pip show x-anylabeling-cvhub })) {
        & $py -m pip install --upgrade pip uv
        & $py -m uv pip install --python $py "x-anylabeling-cvhub[cpu]"   # [cpu] is enough for drawing boxes
        if (-not (Try-Run { & $py -m pip show x-anylabeling-cvhub })) {
            throw "Install failed. Check the internet connection and run this script again."
        }
    }

    if (-not $NoLaunch) { & $py app.py }
} catch {
    Write-Host "`nSETUP FAILED: $_" -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}
