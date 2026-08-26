# Divar Marketing console installer
# ASCII-only so Windows PowerShell 5.1 always parses this file.
#requires -Version 3.0
$ErrorActionPreference = "Stop"
$Log = Join-Path $env:TEMP "divar-marketing-install.log"

function L([string]$m) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m
    try { Add-Content -LiteralPath $Log -Value $line -Encoding UTF8 } catch {}
    Write-Host $m
}

function Find-Python {
    foreach ($pair in @(@("py", "-3"), @("python", ""))) {
        $exe = $pair[0]; $a = $pair[1]
        if (Get-Command $exe -ErrorAction SilentlyContinue) {
            try {
                if ($a -eq "") {
                    & $exe -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" | Out-Null
                } else {
                    & $exe $a -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" | Out-Null
                }
                if ($LASTEXITCODE -eq 0) {
                    if ($a -eq "") {
                        $p = & $exe -c "import sys; print(sys.executable)" 2>$null
                    } else {
                        $p = & $exe $a -c "import sys; print(sys.executable)" 2>$null
                    }
                    if ($p) { return ($p | Select-Object -First 1).ToString().Trim() }
                }
            } catch { }
        }
    }
    $cand = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"
    if (Test-Path -LiteralPath $cand) { return $cand }
    return $null
}

function Install-Python {
    $url = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
    $dl = Join-Path $env:TEMP "divar-python-3.11.9.exe"
    L "Downloading Python 3.11.9 ..."
    $wc = New-Object System.Net.WebClient
    $wc.DownloadFile($url, $dl)
    if (-not (Test-Path -LiteralPath $dl) -or (Get-Item -LiteralPath $dl).Length -lt 5MB) {
        throw "Python download failed"
    }
    try { Unblock-File -LiteralPath $dl } catch { }
    L "Installing Python (quiet, 1-3 min) ..."
    $p = Start-Process -FilePath $dl -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1 Include_test=0" -Wait -PassThru
    L "Python installer exit $($p.ExitCode)"
    if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 3010) { throw "Python installer failed (code $($p.ExitCode))" }
    Start-Sleep -Seconds 2
    $cand = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"
    if (Test-Path -LiteralPath $cand) { return $cand }
    $found = Get-ChildItem (Join-Path $env:LOCALAPPDATA "Programs\Python") -Filter "python.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { return $found.FullName }
    throw "python.exe not found after install"
}

try {
    $here = $PSScriptRoot
    if (-not $here) { $here = Split-Path -Parent $MyInvocation.MyCommand.Path }
    $Root = Split-Path -Parent $here
    Set-Location -LiteralPath $Root
    try {
        $local = Join-Path $Root "installer\install-log.txt"
        "=== console install $(Get-Date) ===" | Out-File -LiteralPath $local -Encoding utf8
        $Log = $local
    } catch {}

    L "Divar Marketing console install"
    L "root=$Root"
    L "powershell=$($PSVersionTable.PSVersion)"

    $req = Join-Path $Root "requirements.txt"
    $main = Join-Path $Root "main.py"
    if (-not (Test-Path -LiteralPath $req) -or -not (Test-Path -LiteralPath $main)) {
        throw "main.py / requirements.txt missing. Extract the ZIP first (right-click -> Extract All)."
    }

    $py = Find-Python
    if ($py) { L "Python found: $py" } else {
        L "Python not found -> installing"
        $py = Install-Python
        L "Python installed: $py"
    }
    & $py --version

    $venvPy = Join-Path $Root ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $venvPy)) {
        L "Creating .venv ..."
        & $py -m venv (Join-Path $Root ".venv")
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPy)) {
            throw "venv creation failed"
        }
    } else {
        L "venv exists"
    }

    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    L "Upgrading pip ..."
    & $venvPy -m pip install --upgrade pip --disable-pip-version-check --progress-bar off
    L "Installing requirements ..."
    & $venvPy -m pip install --disable-pip-version-check --progress-bar off -r $req
    if ($LASTEXITCODE -ne 0) {
        L "PyPI failed -> mirror"
        & $venvPy -m pip install --disable-pip-version-check --progress-bar off -r $req -i "https://mirror-pypi.runflare.com/simple"
        if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
    }

    L "Installing app Chromium (ungoogled-chromium, multi-source) ..."
    $chromeDir = Join-Path $env:LOCALAPPDATA "DivarMarketing\app-chromium"
    New-Item -ItemType Directory -Force -Path $chromeDir | Out-Null
    $env:PLAYWRIGHT_BROWSERS_PATH = $chromeDir
    $env:DIVAR_CHROMIUM_DIR = $chromeDir
    $env:PYTHONUNBUFFERED = "1"
    & $venvPy "main.py" "--install-chromium"
    if ($LASTEXITCODE -ne 0) {
        L "Chromium download failed - app will retry from the panel"
    } else {
        L "App Chromium OK -> $chromeDir"
    }





    L "Health check (main.py --check) ..."

    & $venvPy "main.py" "--check"
    if ($LASTEXITCODE -ne 0) { throw "health check failed" }

    $dataDir = Join-Path $env:LOCALAPPDATA "DivarMarketing"
    New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
    L "settings persist in $dataDir (never wiped)"

    try {
        $desktop = [Environment]::GetFolderPath("Desktop")
        $w = New-Object -ComObject WScript.Shell
        $icon = Join-Path $Root "installer\app.ico"
        if (-not (Test-Path -LiteralPath $icon)) { $icon = "imageres.dll,109" }
        $lnk = Join-Path $desktop "Divar Marketing.lnk"
        $sc = $w.CreateShortcut($lnk)
        $sc.TargetPath = $venvPy
        $sc.Arguments = "main.py"
        $sc.WorkingDirectory = $Root
        $sc.WindowStyle = 1
        $sc.Description = "Divar Marketing"
        $sc.IconLocation = $icon
        $sc.Save()
        L "shortcut $lnk"
    } catch { L "shortcut skipped: $_" }

    try { netsh advfirewall firewall add rule name="Divar Marketing" dir=in action=allow protocol=TCP localport=8642 | Out-Null } catch {}

    L "Starting app ..."
    Start-Process -FilePath $venvPy -ArgumentList "main.py" -WorkingDirectory $Root
    Start-Sleep -Seconds 3
    L "App will open the panel in dedicated Chromium (not Edge)"
    L "DONE. Panel URL: http://localhost:8642"
    L "Phone on same Wi-Fi: http://<this-PC-IP>:8642"
    Write-Host ""
    Write-Host "Install complete. This window can stay open."
    exit 0
} catch {
    L "ERROR $_"
    Write-Host ""
    Write-Host "INSTALL FAILED"
    Write-Host $_
    Write-Host "Log: $Log"
    try { Read-Host "Press Enter to close" } catch {}
    exit 1
}
