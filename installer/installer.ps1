# ============================================================
#  Divar Marketing Installer — GUI with progress bar
#  English only. Windows + built-in PowerShell.
# ============================================================
#requires -Version 3.0
$ErrorActionPreference = "Stop"
$script:HasGui = $false
$script:LogFile = Join-Path $env:TEMP "divar-marketing-install.log"
function Write-InstallLog([string]$m) {
    $line = ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m)
    try { Add-Content -LiteralPath $script:LogFile -Value $line -Encoding UTF8 } catch {}
}
try {
    $here = $PSScriptRoot
    if (-not $here) { $here = Split-Path -Parent $MyInvocation.MyCommand.Path }
    $Root = Split-Path -Parent $here
    Set-Location -LiteralPath $Root
    try {
        $localLog = Join-Path $Root "installer\install-log.txt"
        "=== Divar Marketing install $(Get-Date) ===" | Out-File -LiteralPath $localLog -Encoding utf8
        $script:LogFile = $localLog
    } catch {}
    Write-InstallLog ("root=" + $Root + " ps=" + $PSVersionTable.PSVersion)
} catch {
    Write-InstallLog "startup failed: $_"
    try { Write-Host "STARTUP FAILED: $_"; Read-Host "Press Enter" } catch {}
    exit 1
}

try {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $script:HasGui = $true
} catch {
    Write-InstallLog "WinForms missing: $_"
    Write-Host "GUI not available."
    exit 2
}

$VenvPy  = Join-Path $Root ".venv\Scripts\python.exe"
$LogFile = $script:LogFile
$IconFile = Join-Path $Root "installer\app.ico"

$onCrash = {
    param($sender, $e)
    $msg = ""
    try { $ex = $e.Exception } catch { $ex = $null }
    if ($ex) { $msg = $ex.ToString() } else { $msg = "unknown crash" }
    try { Add-Content -Path (Join-Path $Root "installer\install-log.txt") -Value "`r`n[FATAL] $msg" -Encoding UTF8 } catch {}
    try {
        [System.Windows.Forms.MessageBox]::Show(
            "An unexpected error occurred:`r`n`r`n" + $msg.Substring(0, [Math]::Min(600, $msg.Length)) +
            "`r`n`r`nFull details: installer\install-log.txt",
            "Divar Marketing", "OK", "Error") | Out-Null
    } catch {}
}
[System.Windows.Forms.Application]::add_ThreadException($onCrash)
[System.AppDomain]::CurrentDomain.add_UnhandledException({ param($s, $e)
    try { Add-Content -Path (Join-Path $Root "installer\install-log.txt") -Value ("`r`n[FATAL-Domain] " + $e.ExceptionObject) -Encoding UTF8 } catch {}
})

Get-ChildItem -LiteralPath $Root -Recurse -Include *.ps1,*.bat -ErrorAction SilentlyContinue | ForEach-Object {
    try { Unblock-File -Path $_.FullName } catch {}
}

try {
$form = New-Object System.Windows.Forms.Form
$form.Text = "Divar Marketing Setup"
$form.Size = New-Object System.Drawing.Size(640, 520)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
if (Test-Path $IconFile) {
    try { $form.Icon = New-Object System.Drawing.Icon($IconFile) } catch {}
}

$lblTitle = New-Object System.Windows.Forms.Label
$lblTitle.Location = New-Object System.Drawing.Point(20, 16)
$lblTitle.Size = New-Object System.Drawing.Size(586, 30)
$lblTitle.Font = New-Object System.Drawing.Font("Segoe UI", 13, [System.Drawing.FontStyle]::Bold)
$lblTitle.Text = "Divar Marketing — Install"

$lblStatus = New-Object System.Windows.Forms.Label
$lblStatus.Location = New-Object System.Drawing.Point(20, 56)
$lblStatus.Size = New-Object System.Drawing.Size(586, 26)
$lblStatus.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$lblStatus.Text = "Ready. Click Start Install."

$bar = New-Object System.Windows.Forms.ProgressBar
$bar.Location = New-Object System.Drawing.Point(20, 88)
$bar.Size = New-Object System.Drawing.Size(586, 24)
$bar.Minimum = 0; $bar.Maximum = 100; $bar.Value = 0

$lblStep = New-Object System.Windows.Forms.Label
$lblStep.Location = New-Object System.Drawing.Point(20, 118)
$lblStep.Size = New-Object System.Drawing.Size(586, 22)
$lblStep.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$lblStep.Text = ""

$logBox = New-Object System.Windows.Forms.TextBox
$logBox.Location = New-Object System.Drawing.Point(20, 146)
$logBox.Size = New-Object System.Drawing.Size(586, 280)
$logBox.Multiline = $true
$logBox.ReadOnly = $true
$logBox.ScrollBars = "Vertical"
$logBox.Font = New-Object System.Drawing.Font("Consolas", 9)

$btnStart = New-Object System.Windows.Forms.Button
$btnStart.Location = New-Object System.Drawing.Point(20, 438)
$btnStart.Size = New-Object System.Drawing.Size(180, 36)
$btnStart.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$btnStart.Text = "Start Install"

$btnClose = New-Object System.Windows.Forms.Button
$btnClose.Location = New-Object System.Drawing.Point(426, 438)
$btnClose.Size = New-Object System.Drawing.Size(180, 36)
$btnClose.Text = "Close"

$form.Controls.AddRange(@($lblTitle, $lblStatus, $bar, $lblStep, $logBox, $btnStart, $btnClose))
} catch {
    Write-InstallLog "GUI build failed: $_"
    try { Write-Host "GUI build failed: $_" } catch {}
    exit 2
}

function Log([string]$m) {
    try {
        if ($script:HasGui -and $logBox) {
            $logBox.AppendText("$m`r`n")
            $logBox.SelectionStart = $logBox.Text.Length
            $logBox.ScrollToCaret()
            [System.Windows.Forms.Application]::DoEvents()
        }
    } catch {}
    try { Add-Content -LiteralPath $script:LogFile -Value $m -Encoding utf8 } catch {}
    try { Write-Host $m } catch {}
}
function Set-Step([string]$s, [int]$percent) {
    $lblStep.Text = $s
    if ($percent -ge 0) { $bar.Style = "Blocks"; $bar.Value = [Math]::Min(100, $percent) }
    else { $bar.Style = "Marquee" }
    [System.Windows.Forms.Application]::DoEvents()
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
    if (Test-Path $cand) { return $cand }
    return $null
}

function Install-Python {
    $url = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
    $dl = Join-Path $env:TEMP "divar-python-3.11.9.exe"
    Log "[2] Downloading Python"
    Set-Step "Downloading Python" -1
    $wc = New-Object System.Net.WebClient
    $done = $false
    $wc.add_DownloadProgressChanged({
        $bar.Style = "Blocks"
        $bar.Value = [int]$args[1].ProgressPercentage
        $lblStep.Text = "Downloading Python ... $([int]$args[1].ProgressPercentage)%"
        [System.Windows.Forms.Application]::DoEvents()
    })
    $wc.add_DownloadFileCompleted({ $script:done = $true })
    $wc.DownloadFileAsync([Uri]$url, $dl)
    while (-not $done) { Start-Sleep -Milliseconds 150; [System.Windows.Forms.Application]::DoEvents() }
    if (-not (Test-Path $dl) -or (Get-Item $dl).Length -lt 5MB) {
        throw "Python download failed (file too small)"
    }
    try { Unblock-File -Path $dl } catch { }
    Log "[2] Silent Python install (wait 1-3 min)"
    Set-Step "Installing Python" -1
    $p = Start-Process -FilePath $dl -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1 Include_test=0" -Wait -PassThru
    Log "[2] Python installer exit code: $($p.ExitCode)"
    if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 3010) { throw "Python installer failed (code $($p.ExitCode))" }
    Start-Sleep -Seconds 2
    $cand = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"
    if (Test-Path $cand) { return $cand }
    $found = Get-ChildItem (Join-Path $env:LOCALAPPDATA "Programs\Python") -Filter "python.exe" -Recurse -ErrorAction SilentlyContinue |
             Select-Object -First 1
    if ($found) { return $found.FullName }
    throw "Python installed but python.exe not found"
}

function Ensure-Venv([string]$pyExe) {
    if (Test-Path $VenvPy) {
        Log "[2b] venv exists: $VenvPy"
        return $VenvPy
    }
    Log "[2b] Creating app virtual environment"
    Set-Step "Creating app virtual environment" -1
    $venvDir = Join-Path $Root ".venv"
    & $pyExe -m venv $venvDir
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPy)) {
        throw "venv creation failed (code $LASTEXITCODE)"
    }
    Log "[2b] OK: $VenvPy"
    return $VenvPy
}

function Stream-File([string]$path, [int]$alreadyLogged) {
    try {
        if (-not (Test-Path $path)) { return $alreadyLogged }
        $fs = [System.IO.File]::Open($path, [System.IO.FileMode]::Open,
             [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        $sr = New-Object System.IO.StreamReader($fs, [System.Text.Encoding]::UTF8)
        $lines = @($sr.ReadToEnd() -split "`r?`n")
        $sr.Close()
        for ($i = $alreadyLogged; $i -lt $lines.Count; $i++) {
            $t = $lines[$i].Trim()
            if ($t) { Log "    $t" }
        }
        return $lines.Count
    } catch { return $alreadyLogged }
}

function Run-Pip([string]$pyExe, [string[]]$pipArgs, [string]$label) {
    Log "[3] $label"
    Set-Step $label -1
    $outFile = Join-Path ([System.IO.Path]::GetTempPath()) ("divarpip-" + [guid]::NewGuid().ToString("N") + ".log")
    $inner = '"' + $pyExe + '" ' + ($pipArgs -join " ") + ' > "' + $outFile + '" 2>&1'
    $pinfo = New-Object System.Diagnostics.ProcessStartInfo
    $pinfo.FileName = "cmd.exe"
    $pinfo.Arguments = '/c "' + $inner + '"'
    $pinfo.WorkingDirectory = $Root
    $pinfo.UseShellExecute = $false
    $pinfo.CreateNoWindow = $true
    $pinfo.EnvironmentVariables["PYTHONUTF8"] = "1"
    $pinfo.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8"
    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $pinfo
    [void]$proc.Start()
    $logged = 0
    while (-not $proc.HasExited) {
        Start-Sleep -Milliseconds 350
        [System.Windows.Forms.Application]::DoEvents()
        $logged = Stream-File $outFile $logged
    }
    $proc.WaitForExit()
    $logged = Stream-File $outFile $logged
    Remove-Item $outFile -ErrorAction SilentlyContinue
    return $proc.ExitCode
}

function New-DesktopShortcut([string]$pyExe) {
    Set-Step "Desktop shortcut" 90
    $dataDir = Join-Path $env:LOCALAPPDATA "DivarMarketing"
    New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
    Log "[data] settings persist in $dataDir (never wiped by installer)"
    $desktop = [Environment]::GetFolderPath("Desktop")
    $start = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
    New-Item -ItemType Directory -Force -Path $start | Out-Null
    $w = New-Object -ComObject WScript.Shell
    $icon = if (Test-Path $IconFile) { $IconFile } else { "imageres.dll,109" }
    foreach ($folder in @($desktop, $start)) {
        $lnk = Join-Path $folder "Divar Marketing.lnk"
        $sc = $w.CreateShortcut($lnk)
        $sc.TargetPath = $pyExe
        $sc.Arguments = "main.py"
        $sc.WorkingDirectory = $Root
        $sc.WindowStyle = 1
        $sc.Description = "Divar Marketing"
        $sc.IconLocation = $icon
        $sc.Save()
        Log "[4b] shortcut: $lnk"
    }
    try {
        netsh advfirewall firewall add rule name="Divar Marketing" dir=in action=allow protocol=TCP localport=8642 | Out-Null
        Log "[4c] firewall: TCP 8642 allowed (phone on same Wi-Fi)"
    } catch { Log "[4c] firewall skipped" }
}

$btnStart.Add_Click({
    $btnStart.Enabled = $false
    $pyExe = $null
    try {
        Log "[1] Checking Python"
        Set-Step "Checking Python" 5
        $pyExe = Find-Python
        if ($pyExe) {
            Log "[1] Existing Python found: $pyExe"
            & $pyExe --version 2>&1 | ForEach-Object { Log "    $_" }
            $bar.Value = 20
        } else {
            Log "[1] Python not found -> auto-install"
            $pyExe = Install-Python
            Log "[1] OK: $pyExe"
            & $pyExe --version 2>&1 | ForEach-Object { Log "    $_" }
            $bar.Value = 20
        }

        $appPy = Ensure-Venv $pyExe
        $bar.Value = 35

        $rc = Run-Pip $appPy @("-m", "pip", "install", "--upgrade", "pip", "--disable-pip-version-check", "--progress-bar", "off") "pip upgrade"
        $rc = Run-Pip $appPy @("-m", "pip", "install", "--disable-pip-version-check", "--progress-bar", "off", "-r", "requirements.txt") "Installing dependencies (a few minutes)"
        if ($rc -ne 0) {
            Log "[3] PyPI failed -> trying mirror ..."
            $rc = Run-Pip $appPy @("-m", "pip", "install", "--disable-pip-version-check", "--progress-bar", "off", "-r", "requirements.txt", "-i", "https://mirror-pypi.runflare.com/simple") "mirror install"
            if ($rc -ne 0) { throw "pip install failed (code $rc)" }
        }
        Log "[3] OK"
        $bar.Value = 75

        Log "[4] Health check"
        Set-Step "Health check" 80
        $pinfo = New-Object System.Diagnostics.ProcessStartInfo
        $pinfo.FileName = $appPy; $pinfo.Arguments = "main.py --check"
        $pinfo.WorkingDirectory = $Root
        $pinfo.UseShellExecute = $false
        $pinfo.RedirectStandardOutput = $true
        $pinfo.RedirectStandardError = $true
        $pinfo.CreateNoWindow = $true
        $pinfo.StandardOutputEncoding = [System.Text.Encoding]::UTF8
        $pinfo.StandardErrorEncoding = [System.Text.Encoding]::UTF8
        $pinfo.EnvironmentVariables["PYTHONUTF8"] = "1"
        $proc = New-Object System.Diagnostics.Process
        $proc.StartInfo = $pinfo
        [void]$proc.Start()
        $stdout = $proc.StandardOutput.ReadToEnd()
        $stderr = $proc.StandardError.ReadToEnd()
        $proc.WaitForExit()
        foreach ($line in $stdout.Split("`n")) { $t = $line.Trim(); if ($t) { Log "    $t" } }
        foreach ($line in $stderr.Split("`n")) { $t = $line.Trim(); if ($t) { Log "    [stderr] $t" } }
        if ($proc.ExitCode -ne 0) {
            throw "health check failed (exit $($proc.ExitCode)) — see log above"
        }
        $bar.Value = 88

        try { New-DesktopShortcut $appPy } catch { Log "[4b] shortcut skipped: $_" }

        Log "[5] Launching app"
        Set-Step "Launching app" 100
        $env:PYTHONUTF8 = "1"
        Start-Process -FilePath $appPy -ArgumentList "main.py" -WorkingDirectory $Root
        Start-Sleep -Seconds 3
        Start-Process "http://localhost:8642"
        $lblStatus.Text = "Install complete. App is running — http://localhost:8642  (phone: this-PC-IP:8642)"
        $lblStatus.ForeColor = [System.Drawing.Color]::Green
        Log "Install complete. Browser: http://localhost:8642"
        $btnStart.Enabled = $true
    } catch {
        $lblStatus.Text = "Install incomplete — see the log. You may press Start Install again."
        $lblStatus.ForeColor = [System.Drawing.Color]::Firebrick
        Log "[ERROR] $_"
        Log "Log file: $LogFile"
        $btnStart.Enabled = $true
    }
})
$btnClose.Add_Click({ $form.Close() })
try {
    if (Test-Path $VenvPy) {
        $lblStatus.Text = "Previous install found. Click Start Install to verify and launch."
        $btnStart.Text = "Verify & Run"
    }
    Write-InstallLog "showing installer window"
    [void]$form.ShowDialog()
    Write-InstallLog "installer window closed"
    exit 0
} catch {
    Write-InstallLog "GUI crash: $_"
    try {
        [System.Windows.Forms.MessageBox]::Show(
            "Installer window failed:`r`n$_`r`n`r`nLog: $script:LogFile",
            "Divar Marketing", "OK", "Error") | Out-Null
    } catch {}
    exit 1
}
