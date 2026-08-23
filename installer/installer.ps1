# ============================================================
#  DivarLead Installer — GUI installer with progress bar
#  Requires: Windows + built-in PowerShell (no prerequisites)
#  Fixes: SmartScreen (Unblock-File), garbled Persian in cmd,
#         clear progress for every step
# ============================================================
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $Root   # repo root (installer/ is one level down)
Set-Location $Root
$LogFile = Join-Path $Root "installer\install-log.txt"
"=== DivarLead install $(Get-Date) ===" | Out-File $LogFile -Encoding utf8

# ---------- bilingual labels (WinForms renders Persian correctly) ----------
$L = @{
    fa = @{
        title = "دیوار لید — نصب و راه‌اندازی"
        status = "آماده شروع. دکمه «شروع نصب» را بزنید."
        start = "شروع نصب"
        close = "بستن"
        lang  = "English"
        step1 = "بررسی پایتون"
        step2 = "دانلود و نصب پایتون"
        step3 = "نصب کتابخانه‌ها"
        step4 = "تست سلامت"
        step5 = "اجرای برنامه"
        done  = "نصب کامل شد ✔ برنامه در حال اجراست — مرورگر: http://localhost:8642"
        fail  = "نصب ناتمام ماند — علت در لاگ پایین مشخص است؛ می‌توانید دوباره شروع نصب را بزنید. اگر تکرار شد، فایل installer\install-log.txt را بفرستید."
        found = "پایتون موجود پیدا شد"
        dl    = "دانلود پایتون"
        inst  = "نصب بی‌صدای پایتون (۱ تا ۳ دقیقه صبر کنید)"
        deps  = "نصب پیش‌نیازها (چند دقیقه)"
        ok    = "موفق"
    }
    en = @{
        title = "DivarLead — Install & Run"
        status = "Ready. Click 'Start Install'."
        start = "Start Install"
        close = "Close"
        lang  = "فارسی"
        step1 = "Checking Python"
        step2 = "Downloading & installing Python"
        step3 = "Installing libraries"
        step4 = "Health check"
        step5 = "Launching app"
        done  = "Install complete! App is running — browser: http://localhost:8642"
        fail  = "Install incomplete — reason is in the log below. You may press Start again. If it repeats, send installer\install-log.txt to support."
        found = "Existing Python found"
        dl    = "Downloading Python"
        inst  = "Silent Python install (wait 1-3 min)"
        deps  = "Installing dependencies (a few minutes)"
        ok    = "OK"
    }
}
$Lang = "fa"

# ---------- GUI ----------
$form = New-Object System.Windows.Forms.Form
$form.Text = "DivarLead Installer"
$form.Size = New-Object System.Drawing.Size(640, 520)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false

$lblTitle = New-Object System.Windows.Forms.Label
$lblTitle.Location = New-Object System.Drawing.Point(20, 16)
$lblTitle.Size = New-Object System.Drawing.Size(480, 30)
$lblTitle.Font = New-Object System.Drawing.Font("Tahoma", 13, [System.Drawing.FontStyle]::Bold)
$lblTitle.Text = $L[$Lang].title

$btnLang = New-Object System.Windows.Forms.Button
$btnLang.Location = New-Object System.Drawing.Point(510, 12)
$btnLang.Size = New-Object System.Drawing.Size(96, 32)
$btnLang.Text = $L[$Lang].lang

$lblStatus = New-Object System.Windows.Forms.Label
$lblStatus.Location = New-Object System.Drawing.Point(20, 56)
$lblStatus.Size = New-Object System.Drawing.Size(586, 26)
$lblStatus.Font = New-Object System.Drawing.Font("Tahoma", 10)
$lblStatus.Text = $L[$Lang].status

$bar = New-Object System.Windows.Forms.ProgressBar
$bar.Location = New-Object System.Drawing.Point(20, 88)
$bar.Size = New-Object System.Drawing.Size(586, 24)
$bar.Minimum = 0; $bar.Maximum = 100; $bar.Value = 0

$lblStep = New-Object System.Windows.Forms.Label
$lblStep.Location = New-Object System.Drawing.Point(20, 118)
$lblStep.Size = New-Object System.Drawing.Size(586, 22)
$lblStep.Font = New-Object System.Drawing.Font("Tahoma", 9)
$lblStep.Text = ""

$logBox = New-Object System.Windows.Forms.TextBox
$logBox.Location = New-Object System.Drawing.Point(20, 146)
$logBox.Size = New-Object System.Drawing.Size(586, 280)
$logBox.Multiline = $true
$logBox.ReadOnly = $true
$logBox.ScrollBars = "Vertical"
$logBox.Font = New-Object System.Drawing.Font("Consolas", 9)
$logBox.Anchor = "Top,Left,Right,Bottom"

$btnStart = New-Object System.Windows.Forms.Button
$btnStart.Location = New-Object System.Drawing.Point(20, 438)
$btnStart.Size = New-Object System.Drawing.Size(180, 36)
$btnStart.Font = New-Object System.Drawing.Font("Tahoma", 10, [System.Drawing.FontStyle]::Bold)
$btnStart.Text = $L[$Lang].start

$btnClose = New-Object System.Windows.Forms.Button
$btnClose.Location = New-Object System.Drawing.Point(426, 438)
$btnClose.Size = New-Object System.Drawing.Size(180, 36)
$btnClose.Text = $L[$Lang].close

$form.Controls.AddRange(@($lblTitle, $btnLang, $lblStatus, $bar, $lblStep, $logBox, $btnStart, $btnClose))

function Log([string]$m) {
    $logBox.AppendText("$m`r`n")
    $logBox.SelectionStart = $logBox.Text.Length
    $logBox.ScrollToCaret()
    Add-Content -Path $LogFile -Value $m -Encoding utf8
    [System.Windows.Forms.Application]::DoEvents()
}
function Set-Step([string]$s, [int]$percent) {
    $lblStep.Text = $s
    if ($percent -ge 0) { $bar.Style = "Blocks"; $bar.Value = [Math]::Min(100, $percent) }
    else { $bar.Style = "Marquee" }   # marquee = در حال کار، درصد نامشخص
    [System.Windows.Forms.Application]::DoEvents()
}
function Apply-Lang {
    $lblTitle.Text = $L[$Lang].title
    $lblStatus.Text = $L[$Lang].status
    $btnStart.Text = $L[$Lang].start
    $btnClose.Text = $L[$Lang].close
    $btnLang.Text = $L[$Lang].lang
    $form.Text = "DivarLead Installer"
    [System.Windows.Forms.Application]::DoEvents()
}
$btnLang.Add_Click({ if ($script:Lang -eq "fa") { $script:Lang = "en" } else { $script:Lang = "fa" }; Apply-Lang })

# ---------- helpers ----------
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
    Log "[2] $($L[$Lang].dl): $url"
    Set-Step $L[$Lang].dl -1
    $wc = New-Object System.Net.WebClient
    $done = $false
    $wc.add_DownloadProgressChanged({
        $bar.Style = "Blocks"
        $bar.Value = [int]$args[1].ProgressPercentage
        $lblStep.Text = "$($L[$Lang].dl) ... $([int]$args[1].ProgressPercentage)%"
        [System.Windows.Forms.Application]::DoEvents()
    })
    $wc.add_DownloadFileCompleted({ $script:done = $true })
    $wc.DownloadFileAsync([Uri]$url, $dl)
    while (-not $done) { Start-Sleep -Milliseconds 150; [System.Windows.Forms.Application]::DoEvents() }
    if (-not (Test-Path $dl) -or (Get-Item $dl).Length -lt 5MB) {
        throw "Python download failed (file too small)"
    }
    # رفع SmartScreen: حذف Zone.Identifier از فایل دانلودی
    try { Unblock-File -Path $dl } catch { }
    Log "[2] $($L[$Lang].inst) ..."
    Set-Step $L[$Lang].inst -1
    $p = Start-Process -FilePath $dl -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1 Include_test=0" -Wait -PassThru
    Log "[2] Python installer exit code: $($p.ExitCode)"
    if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 3010) { throw "Python installer failed (code $($p.ExitCode))" }
    Start-Sleep -Seconds 2
    $cand = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"
    if (Test-Path $cand) { return $cand }
    # جستجو در نسخه‌های دیگر نصب‌شده
    $found = Get-ChildItem (Join-Path $env:LOCALAPPDATA "Programs\Python") -Filter "python.exe" -Recurse -ErrorAction SilentlyContinue |
             Select-Object -First 1
    if ($found) { return $found.FullName }
    throw "Python installed but python.exe not found"
}

function Run-Pip([string]$pyExe, [string[]]$pipArgs, [string]$label) {
    Log "[3] $label"
    Set-Step $label -1
    $pinfo = New-Object System.Diagnostics.ProcessStartInfo
    $pinfo.FileName = $pyExe
    $pinfo.Arguments = $pipArgs -join " "
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
    # خواندن رویدادمحور تا اگر خروجی زیاد شد pipe قفل نشود
    $outBuilder = New-Object System.Text.StringBuilder
    $errBuilder = New-Object System.Text.StringBuilder
    $outHandler = [System.Diagnostics.DataReceivedEventHandler]{
        param($s, $e)
        if ($e.Data) { [void]$script:outBuilder.AppendLine($e.Data) }
    }
    $errHandler = [System.Diagnostics.DataReceivedEventHandler]{
        param($s, $e)
        if ($e.Data) { [void]$script:errBuilder.AppendLine($e.Data) }
    }
    $proc.add_OutputDataReceived($outHandler)
    $proc.add_ErrorDataReceived($errHandler)
    [void]$proc.Start()
    $proc.BeginOutputReadLine()
    $proc.BeginErrorReadLine()
    while (-not $proc.HasExited) {
        Start-Sleep -Milliseconds 250
        [System.Windows.Forms.Application]::DoEvents()
    }
    $proc.WaitForExit()
    foreach ($line in $outBuilder.ToString().Split("`n")) {
        $t = $line.Trim(); if ($t) { Log "    $t" }
    }
    foreach ($line in $errBuilder.ToString().Split("`n")) {
        $t = $line.Trim(); if ($t) { Log "    [!] $t" }
    }
    return $proc.ExitCode
}

# ---------- main flow ----------
$btnStart.Add_Click({
    $btnStart.Enabled = $false
    $btnLang.Enabled = $false
    $pyExe = $null
    try {
        # STEP 1 — python
        Log "[1] $($L[$Lang].step1)"
        Set-Step $L[$Lang].step1 5
        $pyExe = Find-Python
        if ($pyExe) {
            Log "[1] $($L[$Lang].found): $pyExe"
            & $pyExe --version 2>&1 | ForEach-Object { Log "    $_" }
            $bar.Value = 40
        } else {
            Log "[1] Python not found -> auto-install"
            $pyExe = Install-Python
            Log "[1] $($L[$Lang].ok): $pyExe"
            & $pyExe --version 2>&1 | ForEach-Object { Log "    $_" }
            $bar.Value = 40
        }

        # STEP 2 — deps (pip)
        $rc = Run-Pip $pyExe @("-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", "requirements.txt") $L[$Lang].deps
        if ($rc -ne 0) {
            Log "[3] PyPI failed -> trying mirror ..."
            $rc = Run-Pip $pyExe @("-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", "requirements.txt", "-i", "https://mirror-pypi.runflare.com/simple") "mirror install"
            if ($rc -ne 0) { throw "pip install failed (code $rc)" }
        }
        Log "[3] $($L[$Lang].ok)"
        $bar.Value = 80

        # STEP 3 — health check (stdout + stderr هر دو نمایش داده می‌شوند)
        Log "[4] $($L[$Lang].step4)"
        Set-Step $L[$Lang].step4 85
        $pinfo = New-Object System.Diagnostics.ProcessStartInfo
        $pinfo.FileName = $pyExe; $pinfo.Arguments = "main.py --check"
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
        $bar.Value = 100

        # STEP 4 — launch
        Log "[5] $($L[$Lang].step5)"
        Set-Step $L[$Lang].step5 100
        $env:PYTHONUTF8 = "1"
        Start-Process -FilePath $pyExe -ArgumentList "main.py" -WorkingDirectory $Root
        Start-Sleep -Seconds 3
        Start-Process "http://localhost:8642"
        $lblStatus.Text = $L[$Lang].done
        $lblStatus.ForeColor = [System.Drawing.Color]::Green
        Log $L[$Lang].done
        $btnStart.Enabled = $true
    } catch {
        $lblStatus.Text = $L[$Lang].fail
        $lblStatus.ForeColor = [System.Drawing.Color]::Firebrick
        Log "[ERROR] $_"
        Log "Log file: $LogFile"
        $btnStart.Enabled = $true   # اجازه تلاش دوباره
    }
})
$btnClose.Add_Click({ $form.Close() })
[void]$form.ShowDialog()
