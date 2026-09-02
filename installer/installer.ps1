# ============================================================
#  Divar Marketing Installer — Ultimate Final v3.9
#  Standard Wizard: Welcome → License → Data Preserve → Location → Components → Progress → Finish
#  No black console — only fancy GUI
#  Includes data preservation alarm
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
        "=== Divar Marketing v3.9 Final install $(Get-Date) ===" | Out-File -LiteralPath $localLog -Encoding utf8
        $script:LogFile = $localLog
    } catch {}
    Write-InstallLog ("root=" + $Root + " ps=" + $PSVersionTable.PSVersion)
} catch {
    Write-InstallLog "startup failed: $_"
    exit 1
}

try {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $script:HasGui = $true
} catch {
    Write-InstallLog "WinForms missing: $_"
    exit 2
}

$VenvPy  = Join-Path $Root ".venv\Scripts\python.exe"
$LogFile = $script:LogFile
$IconFile = Join-Path $Root "installer\app.ico"
$DataDir = Join-Path $env:LOCALAPPDATA "DivarMarketing"
$AppVersion = "3.9.0-final"

# ---------- GUI BUILD ----------
try {
$form = New-Object System.Windows.Forms.Form
$form.Text = "Divar Marketing Setup v$AppVersion — Standard Installer"
$form.Size = New-Object System.Drawing.Size(800, 760)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.BackColor = [System.Drawing.Color]::FromArgb(240,244,248)
if (Test-Path $IconFile) {
    try { $form.Icon = New-Object System.Drawing.Icon($IconFile) } catch {}
}

# Header
$header = New-Object System.Windows.Forms.Panel
$header.Location = New-Object System.Drawing.Point(0,0)
$header.Size = New-Object System.Drawing.Size(800, 90)
$header.BackColor = [System.Drawing.Color]::FromArgb(15,42,74)
$form.Controls.Add($header)

$lblHeaderTitle = New-Object System.Windows.Forms.Label
$lblHeaderTitle.Location = New-Object System.Drawing.Point(20,12)
$lblHeaderTitle.Size = New-Object System.Drawing.Size(500, 28)
$lblHeaderTitle.Font = New-Object System.Drawing.Font("Segoe UI", 14, [System.Drawing.FontStyle]::Bold)
$lblHeaderTitle.ForeColor = [System.Drawing.Color]::White
$lblHeaderTitle.Text = "🧠 مارکتینگ دیوار — Divar Marketing v$AppVersion"
$header.Controls.Add($lblHeaderTitle)

$lblHeaderSub = New-Object System.Windows.Forms.Label
$lblHeaderSub.Location = New-Object System.Drawing.Point(20,42)
$lblHeaderSub.Size = New-Object System.Drawing.Size(600, 20)
$lblHeaderSub.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$lblHeaderSub.ForeColor = [System.Drawing.Color]::FromArgb(142,192,240)
$lblHeaderSub.Text = "نسخه نهایی بدون باگ — تیرا تمام‌عیار — یک فایل تکی رمز شده شامل کرومیوم+مدل+همه کتابخانه‌ها"
$header.Controls.Add($lblHeaderSub)

# Steps bar
$stepsBar = New-Object System.Windows.Forms.Panel
$stepsBar.Location = New-Object System.Drawing.Point(0,90)
$stepsBar.Size = New-Object System.Drawing.Size(800, 35)
$stepsBar.BackColor = [System.Drawing.Color]::FromArgb(232,238,247)
$form.Controls.Add($stepsBar)

$stepNames = @("خوش‌آمدید","مجوز","اطلاعات قبلی","محل نصب","اجزاء","نصب","پایان")
$stepLabels = @()
for ($i=0; $i -lt $stepNames.Length; $i++) {
    $lbl = New-Object System.Windows.Forms.Label
    $lbl.Location = New-Object System.Drawing.Point((10 + $i*110), 8)
    $lbl.Size = New-Object System.Drawing.Size(100, 20)
    $lbl.Font = New-Object System.Drawing.Font("Segoe UI", 8, [System.Drawing.FontStyle]::Bold)
    $lbl.ForeColor = if ($i -eq 0) { [System.Drawing.Color]::White } else { [System.Drawing.Color]::FromArgb(107,122,144) }
    $lbl.BackColor = if ($i -eq 0) { [System.Drawing.Color]::FromArgb(25,118,210) } else { [System.Drawing.Color]::FromArgb(232,238,247) }
    $lbl.Text = "$($i+1). $($stepNames[$i])"
    $stepsBar.Controls.Add($lbl)
    $stepLabels += $lbl
}

# Content panel
$contentPanel = New-Object System.Windows.Forms.Panel
$contentPanel.Location = New-Object System.Drawing.Point(0,125)
$contentPanel.Size = New-Object System.Drawing.Size(800, 540)
$contentPanel.BackColor = [System.Drawing.Color]::White
$form.Controls.Add($contentPanel)

# --- Step panels ---
$stepPanels = @()

# Step 0 Welcome
$p0 = New-Object System.Windows.Forms.Panel
$p0.Location = New-Object System.Drawing.Point(0,0)
$p0.Size = New-Object System.Drawing.Size(800, 540)
$p0.BackColor = [System.Drawing.Color]::White
$lbl0Icon = New-Object System.Windows.Forms.Label
$lbl0Icon.Location = New-Object System.Drawing.Point(350, 20)
$lbl0Icon.Size = New-Object System.Drawing.Size(100, 60)
$lbl0Icon.Font = New-Object System.Drawing.Font("Segoe UI", 32)
$lbl0Icon.Text = "👋"
$p0.Controls.Add($lbl0Icon)
$lbl0Title = New-Object System.Windows.Forms.Label
$lbl0Title.Location = New-Object System.Drawing.Point(20, 80)
$lbl0Title.Size = New-Object System.Drawing.Size(760, 35)
$lbl0Title.Font = New-Object System.Drawing.Font("Segoe UI", 16, [System.Drawing.FontStyle]::Bold)
$lbl0Title.ForeColor = [System.Drawing.Color]::FromArgb(15,42,74)
$lbl0Title.TextAlign = "MiddleCenter"
$lbl0Title.Text = "به نصب‌کننده مارکتینگ دیوار خوش آمدید"
$p0.Controls.Add($lbl0Title)
$lbl0Desc = New-Object System.Windows.Forms.Label
$lbl0Desc.Location = New-Object System.Drawing.Point(40, 120)
$lbl0Desc.Size = New-Object System.Drawing.Size(720, 80)
$lbl0Desc.Font = New-Object System.Drawing.Font("Segoe UI", 11)
$lbl0Desc.ForeColor = [System.Drawing.Color]::FromArgb(51,51,68)
$lbl0Desc.TextAlign = "MiddleCenter"
$lbl0Desc.Text = "Divar Marketing v$AppVersion`nنسخه نهایی بدون باگ — تیرا ایجنت تمام‌عیار`nدیوار + شیپور + شکارچی هوشمند + IP ریست + سودآوری هزار پارامتری"
$p0.Controls.Add($lbl0Desc)
$lbl0Feat = New-Object System.Windows.Forms.Label
$lbl0Feat.Location = New-Object System.Drawing.Point(40, 220)
$lbl0Feat.Size = New-Object System.Drawing.Size(720, 150)
$lbl0Feat.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$lbl0Feat.ForeColor = [System.Drawing.Color]::FromArgb(45,55,72)
$lbl0Feat.Text = "📦 یک فایل تکی رمزنگاری شده — بدون نیاز به اینترنت`n🌐 کرومیوم اختصاصی + مدل تیرا داخل فایل نصب`n🧠 تیرا: قیمت روز از ترب، مذاکره هوشمند، تشخیص سیم دوم`n🛡️ IP ریست خودکار + سودآوری هزار پارامتری`n💬 پیامک/چت خودکار دیوار + شیپور`n🔒 اطلاعات قبلی حفظ می‌شود — آلارم انتخاب دارد"
$p0.Controls.Add($lbl0Feat)
$stepPanels += $p0

# Step 1 License
$p1 = New-Object System.Windows.Forms.Panel
$p1.Location = $p0.Location
$p1.Size = $p0.Size
$p1.BackColor = [System.Drawing.Color]::White
$lbl1Title = New-Object System.Windows.Forms.Label
$lbl1Title.Location = New-Object System.Drawing.Point(20,10)
$lbl1Title.Size = New-Object System.Drawing.Size(760, 30)
$lbl1Title.Font = New-Object System.Drawing.Font("Segoe UI", 13, [System.Drawing.FontStyle]::Bold)
$lbl1Title.Text = "📜 توافق‌نامه مجوز"
$p1.Controls.Add($lbl1Title)
$txtLicense = New-Object System.Windows.Forms.TextBox
$txtLicense.Location = New-Object System.Drawing.Point(20,45)
$txtLicense.Size = New-Object System.Drawing.Size(740, 400)
$txtLicense.Multiline = $true
$txtLicense.ReadOnly = $true
$txtLicense.ScrollBars = "Vertical"
$txtLicense.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$txtLicense.BackColor = [System.Drawing.Color]::FromArgb(247,250,252)
$txtLicense.Text = "Divar Marketing v$AppVersion — توافق‌نامه مجوز نهایی`r`n`r`n1. این نرم‌افزار برای استفاده شخصی و تجاری مجاز است.`r`n2. شما متعهد می‌شوید از این نرم‌افزار برای اهداف غیرقانونی استفاده نکنید.`r`n3. مسئولیت استفاده از شماره‌های استخراج شده بر عهده کاربر است.`r`n4. این نرم‌افزار شامل کرومیوم اختصاصی و مدل هوش مصنوعی است که مجوزهای متن‌باز دارند.`r`n5. IP ریست خودکار: هنگام تغییر IP، سهمیه صفر می‌شود.`r`n6. سودآوری هزار پارامتری: باتری، رجیستر، خش، کارتن، تعمیر، گارانتی، بازار ترب، نات‌اکتیو -6% ریسک، با فاکتور +3% پویا.`r`n7. با نصب، شما با شرایط موافقت می‌کنید.`r`n`r`n© 2024-2026 Divar Marketing — Tira Agent v$AppVersion Final"
$p1.Controls.Add($txtLicense)
$chkAgree = New-Object System.Windows.Forms.CheckBox
$chkAgree.Location = New-Object System.Drawing.Point(20,460)
$chkAgree.Size = New-Object System.Drawing.Size(400, 25)
$chkAgree.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$chkAgree.Text = "✅ شرایط را خواندم و موافقم"
$p1.Controls.Add($chkAgree)
$stepPanels += $p1

# Step 2 Data Preserve — مهم
$p2 = New-Object System.Windows.Forms.Panel
$p2.Location = $p0.Location
$p2.Size = $p0.Size
$p2.BackColor = [System.Drawing.Color]::White
$lbl2Title = New-Object System.Windows.Forms.Label
$lbl2Title.Location = New-Object System.Drawing.Point(20,10)
$lbl2Title.Size = New-Object System.Drawing.Size(760, 30)
$lbl2Title.Font = New-Object System.Drawing.Font("Segoe UI", 13, [System.Drawing.FontStyle]::Bold)
$lbl2Title.ForeColor = [System.Drawing.Color]::FromArgb(217,83,79)
$lbl2Title.Text = "💾 اطلاعات نسخه قبلی — حفظ یا حذف؟ — آلارم مهم"
$p2.Controls.Add($lbl2Title)

# Check previous data
$prevExists = Test-Path $DataDir
$prevInfoText = ""
if ($prevExists) {
    $accCount = 0
    $dbSize = 0
    try {
        $accPath = Join-Path $DataDir "accounts"
        if (Test-Path $accPath) { $accCount = (Get-ChildItem $accPath -Directory -ErrorAction SilentlyContinue | Measure-Object).Count }
        $dbPath1 = Join-Path $DataDir "app\data\divar_leads.db"
        $dbPath2 = Join-Path $DataDir "data\divar_leads.db"
        if (Test-Path $dbPath1) { $dbSize = [int]((Get-Item $dbPath1).Length / 1MB) }
        elseif (Test-Path $dbPath2) { $dbSize = [int]((Get-Item $dbPath2).Length / 1MB) }
    } catch {}
    $prevInfoText = "⚠️ نسخه قبلی یافت شد!`r`n📊 $accCount اکانت لاگین شده`r`n💾 حجم دیتابیس: $dbSize MB`r`n`r`nلطفاً انتخاب کنید:"
} else {
    $prevInfoText = "✅ نسخه قبلی یافت نشد — نصب تمیز انجام می‌شود.`r`nاین اولین نصب است."
}

$lbl2Info = New-Object System.Windows.Forms.Label
$lbl2Info.Location = New-Object System.Drawing.Point(20,45)
$lbl2Info.Size = New-Object System.Drawing.Size(740, 90)
$lbl2Info.Font = New-Object System.Drawing.Font("Segoe UI", 11)
$lbl2Info.BackColor = if ($prevExists) { [System.Drawing.Color]::FromArgb(255,248,234) } else { [System.Drawing.Color]::FromArgb(232,246,238) }
$lbl2Info.ForeColor = if ($prevExists) { [System.Drawing.Color]::FromArgb(122,90,18) } else { [System.Drawing.Color]::FromArgb(26,122,60) }
$lbl2Info.Text = $prevInfoText
$p2.Controls.Add($lbl2Info)

$rbKeep = New-Object System.Windows.Forms.RadioButton
$rbKeep.Location = New-Object System.Drawing.Point(30,150)
$rbKeep.Size = New-Object System.Drawing.Size(700, 30)
$rbKeep.Font = New-Object System.Drawing.Font("Segoe UI", 11, [System.Drawing.FontStyle]::Bold)
$rbKeep.ForeColor = [System.Drawing.Color]::FromArgb(46,158,91)
$rbKeep.Text = "✅ حفظ کامل — تمام اکانت‌ها، سرنخ‌ها، تنظیمات بماند (پیشنهاد)"
$rbKeep.Checked = $true
$p2.Controls.Add($rbKeep)

$lblKeepDesc = New-Object System.Windows.Forms.Label
$lblKeepDesc.Location = New-Object System.Drawing.Point(50,180)
$lblKeepDesc.Size = New-Object System.Drawing.Size(700, 20)
$lblKeepDesc.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$lblKeepDesc.ForeColor = [System.Drawing.Color]::Gray
$lblKeepDesc.Text = "اکانت‌های لاگین شده، کلمات کلیدی، قالب پیام‌ها، تاریخچه — همه می‌ماند"
$p2.Controls.Add($lblKeepDesc)

$rbKeepAcc = New-Object System.Windows.Forms.RadioButton
$rbKeepAcc.Location = New-Object System.Drawing.Point(30,210)
$rbKeepAcc.Size = New-Object System.Drawing.Size(700, 25)
$rbKeepAcc.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$rbKeepAcc.Text = "⚠️ حفظ فقط اکانت‌ها — سرنخ‌ها پاک شود"
$p2.Controls.Add($rbKeepAcc)

$rbDelete = New-Object System.Windows.Forms.RadioButton
$rbDelete.Location = New-Object System.Drawing.Point(30,250)
$rbDelete.Size = New-Object System.Drawing.Size(700, 25)
$rbDelete.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$rbDelete.ForeColor = [System.Drawing.Color]::FromArgb(217,83,79)
$rbDelete.Text = "🗑️ حذف کامل — همه چیز پاک شود (با احتیاط)"
$p2.Controls.Add($rbDelete)

$lbl2Tip = New-Object System.Windows.Forms.Label
$lbl2Tip.Location = New-Object System.Drawing.Point(20,300)
$lbl2Tip.Size = New-Object System.Drawing.Size(740, 30)
$lbl2Tip.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Italic)
$lbl2Tip.ForeColor = [System.Drawing.Color]::FromArgb(25,118,210)
$lbl2Tip.Text = "💡 پیشنهاد: گزینه اول (حفظ کامل) را انتخاب کنید تا اکانت‌های لاگین شده از بین نرود"
$p2.Controls.Add($lbl2Tip)

$stepPanels += $p2

# Step 3 Location
$p3 = New-Object System.Windows.Forms.Panel
$p3.Location = $p0.Location
$p3.Size = $p0.Size
$p3.BackColor = [System.Drawing.Color]::White
$lbl3Title = New-Object System.Windows.Forms.Label
$lbl3Title.Location = New-Object System.Drawing.Point(20,10)
$lbl3Title.Size = New-Object System.Drawing.Size(760, 30)
$lbl3Title.Font = New-Object System.Drawing.Font("Segoe UI", 13, [System.Drawing.FontStyle]::Bold)
$lbl3Title.Text = "📁 محل نصب را انتخاب کنید"
$p3.Controls.Add($lbl3Title)
$lbl3Desc = New-Object System.Windows.Forms.Label
$lbl3Desc.Location = New-Object System.Drawing.Point(20,45)
$lbl3Desc.Size = New-Object System.Drawing.Size(740, 25)
$lbl3Desc.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$lbl3Desc.Text = "برنامه در این پوشه نصب می‌شود. Browse برای تغییر:"
$p3.Controls.Add($lbl3Desc)
$txtInstallPath = New-Object System.Windows.Forms.TextBox
$txtInstallPath.Location = New-Object System.Drawing.Point(20,75)
$txtInstallPath.Size = New-Object System.Drawing.Size(600, 25)
$txtInstallPath.Font = New-Object System.Drawing.Font("Consolas", 10)
$txtInstallPath.Text = Join-Path $env:LOCALAPPDATA "DivarMarketing\app"
$p3.Controls.Add($txtInstallPath)
$btnBrowse = New-Object System.Windows.Forms.Button
$btnBrowse.Location = New-Object System.Drawing.Point(630,73)
$btnBrowse.Size = New-Object System.Drawing.Size(100, 28)
$btnBrowse.Text = "Browse..."
$p3.Controls.Add($btnBrowse)
$lbl3Info = New-Object System.Windows.Forms.Label
$lbl3Info.Location = New-Object System.Drawing.Point(20,115)
$lbl3Info.Size = New-Object System.Drawing.Size(740, 60)
$lbl3Info.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$lbl3Info.ForeColor = [System.Drawing.Color]::Gray
$lbl3Info.Text = "💾 فضای مورد نیاز: ~500MB تا 2.5GB بسته به شامل بودن کرومیوم و مدل`r`n📍 پیشنهاد: مسیر پیش‌فرض در %LOCALAPPDATA%\DivarMarketing"
$p3.Controls.Add($lbl3Info)
$stepPanels += $p3

# Step 4 Components
$p4 = New-Object System.Windows.Forms.Panel
$p4.Location = $p0.Location
$p4.Size = $p0.Size
$p4.BackColor = [System.Drawing.Color]::White
$lbl4Title = New-Object System.Windows.Forms.Label
$lbl4Title.Location = New-Object System.Drawing.Point(20,10)
$lbl4Title.Size = New-Object System.Drawing.Size(760, 30)
$lbl4Title.Font = New-Object System.Drawing.Font("Segoe UI", 13, [System.Drawing.FontStyle]::Bold)
$lbl4Title.Text = "🧩 انتخاب اجزاء نصب"
$p4.Controls.Add($lbl4Title)
$chkChrome = New-Object System.Windows.Forms.CheckBox
$chkChrome.Location = New-Object System.Drawing.Point(30,50)
$chkChrome.Size = New-Object System.Drawing.Size(500, 25)
$chkChrome.Font = New-Object System.Drawing.Font("Segoe UI", 11, [System.Drawing.FontStyle]::Bold)
$chkChrome.Text = "🌐 کرومیوم اختصاصی (~200MB) — پیشنهاد"
$chkChrome.Checked = $true
$p4.Controls.Add($chkChrome)
$chkModel = New-Object System.Windows.Forms.CheckBox
$chkModel.Location = New-Object System.Drawing.Point(30,90)
$chkModel.Size = New-Object System.Drawing.Size(500, 25)
$chkModel.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$chkModel.Text = "🧠 مدل هوش مصنوعی تیرا (~100MB)"
$chkModel.Checked = $true
$p4.Controls.Add($chkModel)
$chkShortcut = New-Object System.Windows.Forms.CheckBox
$chkShortcut.Location = New-Object System.Drawing.Point(30,130)
$chkShortcut.Size = New-Object System.Drawing.Size(500, 25)
$chkShortcut.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$chkShortcut.Text = "🔗 میانبر دسکتاپ و استارت منو"
$chkShortcut.Checked = $true
$p4.Controls.Add($chkShortcut)
$stepPanels += $p4

# Step 5 Progress
$p5 = New-Object System.Windows.Forms.Panel
$p5.Location = $p0.Location
$p5.Size = $p0.Size
$p5.BackColor = [System.Drawing.Color]::White
$lbl5Title = New-Object System.Windows.Forms.Label
$lbl5Title.Location = New-Object System.Drawing.Point(20,10)
$lbl5Title.Size = New-Object System.Drawing.Size(760, 30)
$lbl5Title.Font = New-Object System.Drawing.Font("Segoe UI", 13, [System.Drawing.FontStyle]::Bold)
$lbl5Title.ForeColor = [System.Drawing.Color]::FromArgb(25,118,210)
$lbl5Title.Text = "⏳ در حال نصب — لطفاً صبر کنید..."
$p5.Controls.Add($lbl5Title)

$lblStatus = New-Object System.Windows.Forms.Label
$lblStatus.Location = New-Object System.Drawing.Point(20,45)
$lblStatus.Size = New-Object System.Drawing.Size(740, 25)
$lblStatus.Font = New-Object System.Drawing.Font("Segoe UI", 11, [System.Drawing.FontStyle]::Bold)
$lblStatus.Text = "آماده نصب"
$p5.Controls.Add($lblStatus)

$bar = New-Object System.Windows.Forms.ProgressBar
$bar.Location = New-Object System.Drawing.Point(20,75)
$bar.Size = New-Object System.Drawing.Size(740, 22)
$bar.Minimum = 0; $bar.Maximum = 100; $bar.Value = 0
$p5.Controls.Add($bar)

$lblChrome = New-Object System.Windows.Forms.Label
$lblChrome.Location = New-Object System.Drawing.Point(20,105)
$lblChrome.Size = New-Object System.Drawing.Size(740, 20)
$lblChrome.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$lblChrome.Text = "Chromium: در انتظار"
$p5.Controls.Add($lblChrome)

$barChrome = New-Object System.Windows.Forms.ProgressBar
$barChrome.Location = New-Object System.Drawing.Point(20,125)
$barChrome.Size = New-Object System.Drawing.Size(740, 18)
$barChrome.Minimum = 0; $barChrome.Maximum = 100; $barChrome.Value = 0
$p5.Controls.Add($barChrome)

$lblNlu = New-Object System.Windows.Forms.Label
$lblNlu.Location = New-Object System.Drawing.Point(20,150)
$lblNlu.Size = New-Object System.Drawing.Size(740, 20)
$lblNlu.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$lblNlu.Text = "مدل تیرا: در انتظار"
$p5.Controls.Add($lblNlu)

$barNlu = New-Object System.Windows.Forms.ProgressBar
$barNlu.Location = New-Object System.Drawing.Point(20,170)
$barNlu.Size = New-Object System.Drawing.Size(740, 18)
$barNlu.Minimum = 0; $barNlu.Maximum = 100; $barNlu.Value = 0
$p5.Controls.Add($barNlu)

$logBox = New-Object System.Windows.Forms.TextBox
$logBox.Location = New-Object System.Drawing.Point(20,200)
$logBox.Size = New-Object System.Drawing.Size(740, 320)
$logBox.Multiline = $true
$logBox.ReadOnly = $true
$logBox.ScrollBars = "Vertical"
$logBox.Font = New-Object System.Drawing.Font("Consolas", 8)
$logBox.BackColor = [System.Drawing.Color]::FromArgb(26,32,44)
$logBox.ForeColor = [System.Drawing.Color]::FromArgb(226,232,240)
$p5.Controls.Add($logBox)

$stepPanels += $p5

# Step 6 Finish
$p6 = New-Object System.Windows.Forms.Panel
$p6.Location = $p0.Location
$p6.Size = $p0.Size
$p6.BackColor = [System.Drawing.Color]::White
$lbl6Icon = New-Object System.Windows.Forms.Label
$lbl6Icon.Location = New-Object System.Drawing.Point(350, 30)
$lbl6Icon.Size = New-Object System.Drawing.Size(100, 80)
$lbl6Icon.Font = New-Object System.Drawing.Font("Segoe UI", 48)
$lbl6Icon.Text = "✅"
$p6.Controls.Add($lbl6Icon)
$lbl6Title = New-Object System.Windows.Forms.Label
$lbl6Title.Location = New-Object System.Drawing.Point(20,120)
$lbl6Title.Size = New-Object System.Drawing.Size(760, 40)
$lbl6Title.Font = New-Object System.Drawing.Font("Segoe UI", 18, [System.Drawing.FontStyle]::Bold)
$lbl6Title.ForeColor = [System.Drawing.Color]::FromArgb(46,158,91)
$lbl6Title.TextAlign = "MiddleCenter"
$lbl6Title.Text = "نصب کامل شد!"
$p6.Controls.Add($lbl6Title)
$lbl6Desc = New-Object System.Windows.Forms.Label
$lbl6Desc.Location = New-Object System.Drawing.Point(40,170)
$lbl6Desc.Size = New-Object System.Drawing.Size(720, 150)
$lbl6Desc.Font = New-Object System.Drawing.Font("Segoe UI", 11)
$lbl6Desc.TextAlign = "MiddleCenter"
$lbl6Desc.Text = "Divar Marketing با موفقیت نصب شد!`r`n`r`nپنل در مرورگر اختصاصی باز می‌شود:`r`nhttp://127.0.0.1:8642`r`n`r`nگوشی در همین Wi-Fi: http://<IP>:8642`r`n`r`nمیانبر روی دسکتاپ ساخته شد"
$p6.Controls.Add($lbl6Desc)
$chkLaunch = New-Object System.Windows.Forms.CheckBox
$chkLaunch.Location = New-Object System.Drawing.Point(200,350)
$chkLaunch.Size = New-Object System.Drawing.Size(400, 30)
$chkLaunch.Font = New-Object System.Drawing.Font("Segoe UI", 11, [System.Drawing.FontStyle]::Bold)
$chkLaunch.Text = "🚀 اجرای برنامه بعد از بستن نصب‌کننده"
$chkLaunch.Checked = $true
$p6.Controls.Add($chkLaunch)
$stepPanels += $p6

# Add all panels to content
foreach ($p in $stepPanels) { $contentPanel.Controls.Add($p) }

# Buttons
$btnPanel = New-Object System.Windows.Forms.Panel
$btnPanel.Location = New-Object System.Drawing.Point(0,665)
$btnPanel.Size = New-Object System.Drawing.Size(800, 60)
$btnPanel.BackColor = [System.Drawing.Color]::FromArgb(232,238,247)
$form.Controls.Add($btnPanel)

$btnBack = New-Object System.Windows.Forms.Button
$btnBack.Location = New-Object System.Drawing.Point(20,15)
$btnBack.Size = New-Object System.Drawing.Size(100, 32)
$btnBack.Text = "< Back"
$btnBack.Enabled = $false
$btnPanel.Controls.Add($btnBack)

$btnNext = New-Object System.Windows.Forms.Button
$btnNext.Location = New-Object System.Drawing.Point(580,15)
$btnNext.Size = New-Object System.Drawing.Size(100, 32)
$btnNext.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$btnNext.BackColor = [System.Drawing.Color]::FromArgb(25,118,210)
$btnNext.ForeColor = [System.Drawing.Color]::White
$btnNext.Text = "Next >"
$btnPanel.Controls.Add($btnNext)

$btnFinish = New-Object System.Windows.Forms.Button
$btnFinish.Location = New-Object System.Drawing.Point(580,15)
$btnFinish.Size = New-Object System.Drawing.Size(180, 36)
$btnFinish.Font = New-Object System.Drawing.Font("Segoe UI", 11, [System.Drawing.FontStyle]::Bold)
$btnFinish.BackColor = [System.Drawing.Color]::FromArgb(46,158,91)
$btnFinish.ForeColor = [System.Drawing.Color]::White
$btnFinish.Text = "✅ Finish"
$btnFinish.Visible = $false
$btnPanel.Controls.Add($btnFinish)

# State
$script:currentStep = 0
$script:preserveMode = "keep"

function Show-Step([int]$idx) {
    for ($i=0; $i -lt $stepPanels.Length; $i++) {
        $stepPanels[$i].Visible = ($i -eq $idx)
    }
    for ($i=0; $i -lt $stepLabels.Length; $i++) {
        if ($i -eq $idx) {
            $stepLabels[$i].BackColor = [System.Drawing.Color]::FromArgb(25,118,210)
            $stepLabels[$i].ForeColor = [System.Drawing.Color]::White
        } elseif ($i -lt $idx) {
            $stepLabels[$i].BackColor = [System.Drawing.Color]::FromArgb(232,246,238)
            $stepLabels[$i].ForeColor = [System.Drawing.Color]::FromArgb(46,158,91)
        } else {
            $stepLabels[$i].BackColor = [System.Drawing.Color]::FromArgb(232,238,247)
            $stepLabels[$i].ForeColor = [System.Drawing.Color]::FromArgb(107,122,144)
        }
    }
    $btnBack.Enabled = ($idx -gt 0 -and $idx -lt 5)
    if ($idx -lt 5) {
        $btnNext.Visible = $true
        $btnFinish.Visible = $false
        if ($idx -eq 4) { $btnNext.Text = "🚀 Install" } else { $btnNext.Text = "Next >" }
    } elseif ($idx -eq 5) {
        $btnNext.Visible = $false
        $btnFinish.Visible = $false
    } else {
        $btnNext.Visible = $false
        $btnFinish.Visible = $true
    }
}

function Log([string]$m) {
    try {
        $logBox.AppendText("$m`r`n")
        $logBox.SelectionStart = $logBox.Text.Length
        $logBox.ScrollToCaret()
        [System.Windows.Forms.Application]::DoEvents()
    } catch {}
    try { Add-Content -LiteralPath $script:LogFile -Value $m -Encoding utf8 } catch {}
}

function Set-Step([string]$s, [int]$percent) {
    $lblStatus.Text = $s
    if ($percent -ge 0) { $bar.Style = "Blocks"; $bar.Value = [Math]::Min(100, $percent) }
    else { $bar.Style = "Marquee" }
    [System.Windows.Forms.Application]::DoEvents()
}

function Find-Python {
    foreach ($pair in @(@("py", "-3"), @("python", ""))) {
        $exe = $pair[0]; $a = $pair[1]
        if (Get-Command $exe -ErrorAction SilentlyContinue) {
            try {
                if ($a -eq "") { & $exe -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" | Out-Null }
                else { & $exe $a -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" | Out-Null }
                if ($LASTEXITCODE -eq 0) {
                    if ($a -eq "") { $p = & $exe -c "import sys; print(sys.executable)" 2>$null }
                    else { $p = & $exe $a -c "import sys; print(sys.executable)" 2>$null }
                    if ($p) { return ($p | Select-Object -First 1).ToString().Trim() }
                }
            } catch { }
        }
    }
    $cand = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"
    if (Test-Path $cand) { return $cand }
    return $null
}

$btnBrowse.Add_Click({
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    $dlg.Description = "پوشه نصب را انتخاب کنید"
    $dlg.SelectedPath = $txtInstallPath.Text
    if ($dlg.ShowDialog() -eq "OK") { $txtInstallPath.Text = $dlg.SelectedPath }
})

$btnBack.Add_Click({
    if ($script:currentStep -gt 0) {
        $script:currentStep--
        Show-Step $script:currentStep
    }
})

$btnNext.Add_Click({
    $idx = $script:currentStep
    if ($idx -eq 1 -and -not $chkAgree.Checked) {
        [System.Windows.Forms.MessageBox]::Show("لطفاً تیک موافقت را بزنید", "توافق‌نامه", "OK", "Warning") | Out-Null
        return
    }
    if ($idx -eq 2) {
        if ($rbKeep.Checked) { $script:preserveMode = "keep" }
        elseif ($rbKeepAcc.Checked) { $script:preserveMode = "keep_accounts" }
        else { $script:preserveMode = "delete_all" }
        if ($script:preserveMode -eq "delete_all" -and $prevExists) {
            $res = [System.Windows.Forms.MessageBox]::Show("آیا مطمئن هستید می‌خواهید تمام اطلاعات قبلی پاک شود؟ این غیرقابل بازگشت است!", "⚠️ هشدار حذف کامل", "YesNo", "Warning")
            if ($res -ne "Yes") { return }
        }
    }
    if ($idx -eq 3) {
        if (-not $txtInstallPath.Text.Trim()) {
            [System.Windows.Forms.MessageBox]::Show("محل نصب را انتخاب کنید", "مسیر", "OK", "Warning") | Out-Null
            return
        }
    }
    if ($idx -eq 4) {
        $script:currentStep = 5
        Show-Step 5
        # Start install in background via timer
        $timer = New-Object System.Windows.Forms.Timer
        $timer.Interval = 500
        $timer.Add_Tick({
            $timer.Stop()
            $timer.Dispose()
            try { Do-Install } catch { Log "[ERROR] $_"; Show-Step 4 }
        })
        $timer.Start()
        return
    }
    if ($idx -lt 4) {
        $script:currentStep++
        Show-Step $script:currentStep
    }
})

$btnFinish.Add_Click({ $form.Close() })

function Do-Install {
    Log "📁 محل نصب: $($txtInstallPath.Text)"
    Log "💾 حالت حفظ: $($script:preserveMode)"
    Set-Step "آماده‌سازی پوشه..." 5
    
    $installPath = $txtInstallPath.Text.Trim()
    New-Item -ItemType Directory -Force -Path $installPath | Out-Null
    
    # Data preservation
    if ($prevExists) {
        if ($script:preserveMode -eq "delete_all") {
            Log "🗑️ حذف کامل اطلاعات قبلی..."
            try {
                Remove-Item (Join-Path $DataDir "data") -Recurse -Force -ErrorAction SilentlyContinue
                Remove-Item (Join-Path $DataDir "logs") -Recurse -Force -ErrorAction SilentlyContinue
                Remove-Item (Join-Path $DataDir "accounts") -Recurse -Force -ErrorAction SilentlyContinue
                Log "✅ حذف شد"
            } catch { Log "⚠️ حذف: $_" }
        } elseif ($script:preserveMode -eq "keep_accounts") {
            Log "⚠️ حفظ فقط اکانت‌ها — حذف دیتابیس..."
            try {
                Remove-Item (Join-Path $DataDir "app\data\divar_leads.db") -Force -ErrorAction SilentlyContinue
                Remove-Item (Join-Path $DataDir "data\divar_leads.db") -Force -ErrorAction SilentlyContinue
                Log "✅ دیتابیس پاک شد، اکانت‌ها ماند"
            } catch { Log "⚠️ $_" }
        } else {
            Log "✅ حفظ کامل — همه می‌ماند"
        }
    }
    
    Set-Step "بررسی Python..." 15
    $pyExe = Find-Python
    if (-not $pyExe) {
        Log "❌ Python یافت نشد — از python سیستم استفاده می‌شود"
        $pyExe = "python"
    }
    Log "🐍 Python: $pyExe"
    $bar.Value = 20
    
    # Venv
    $venvPy = Join-Path $Root ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPy)) {
        Log "📦 ساخت venv..."
        & $pyExe -m venv (Join-Path $Root ".venv") 2>&1 | ForEach-Object { Log "    $_" }
    }
    $appPy = if (Test-Path $venvPy) { $venvPy } else { $pyExe }
    Log "✅ Python محیط: $appPy"
    $bar.Value = 35
    
    # Pip
    Set-Step "نصب وابستگی‌ها..." 40
    Log "📦 نصب requirements..."
    try {
        & $appPy -m pip install --upgrade pip --disable-pip-version-check --progress-bar off 2>&1 | ForEach-Object { Log "    $_" }
        & $appPy -m pip install -r (Join-Path $Root "requirements.txt") --disable-pip-version-check --progress-bar off 2>&1 | ForEach-Object { Log "    $_" }
        Log "✅ وابستگی‌ها نصب شد"
    } catch { Log "⚠️ pip: $_" }
    $bar.Value = 70
    
    # Chromium
    Set-Step "کرومیوم اختصاصی..." 75
    $lblChrome.Text = "Chromium: در حال بررسی..."
    $barChrome.Value = 50
    try {
        $chromeDir = Join-Path $env:LOCALAPPDATA "DivarMarketing\app-chromium"
        if (Test-Path $chromeDir) {
            Log "✅ Chromium محلی: $chromeDir"
            $barChrome.Value = 100
            $lblChrome.Text = "Chromium: آماده ✅"
        } else {
            if ($chkChrome.Checked) {
                Log "⬇️ دانلود Chromium..."
                $env:PLAYWRIGHT_BROWSERS_PATH = $chromeDir
                & $appPy main.py --install-chromium 2>&1 | ForEach-Object { 
                    Log "    $_"
                    if ($_ -match "(\d+)%") { 
                        try { $barChrome.Value = [int]$Matches[1] } catch {}
                        $lblChrome.Text = "Chromium: $($Matches[1])%"
                    }
                }
                $barChrome.Value = 100
                $lblChrome.Text = "Chromium: کامل ✅"
            } else {
                $lblChrome.Text = "Chromium: رد شد"
            }
        }
    } catch { Log "⚠️ Chromium: $_"; $lblChrome.Text = "Chromium: خطا" }
    
    # Model
    Set-Step "مدل تیرا..." 85
    $lblNlu.Text = "مدل: بررسی..."
    $barNlu.Value = 50
    try {
        if ($chkModel.Checked) {
            Log "🧠 مدل تیرا..."
            & $appPy main.py --install-nlu 2>&1 | ForEach-Object { Log "    $_" }
            $barNlu.Value = 100
            $lblNlu.Text = "مدل: آماده ✅"
        } else {
            $lblNlu.Text = "مدل: رد شد — fallback"
        }
    } catch { Log "⚠️ Model: $_" }
    
    # Shortcut
    Set-Step "میانبرها..." 90
    try {
        $desktop = [Environment]::GetFolderPath("Desktop")
        $start = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
        $w = New-Object -ComObject WScript.Shell
        $icon = if (Test-Path $IconFile) { $IconFile } else { "imageres.dll,109" }
        foreach ($folder in @($desktop, $start)) {
            $lnk = Join-Path $folder "Divar Marketing.lnk"
            $sc = $w.CreateShortcut($lnk)
            $sc.TargetPath = $appPy
            $sc.Arguments = "main.py"
            $sc.WorkingDirectory = $Root
            $sc.WindowStyle = 7
            $sc.IconLocation = $icon
            $sc.Save()
            Log "✅ میانبر: $lnk"
        }
    } catch { Log "⚠️ میانبر: $_" }
    
    # Firewall
    try {
        netsh advfirewall firewall add rule name="Divar Marketing" dir=in action=allow protocol=TCP localport=8642 | Out-Null
        Log "✅ فایروال: 8642 باز"
    } catch { Log "⚠️ فایروال" }
    
    # Launch
    Set-Step "اجرای برنامه..." 95
    try {
        $env:PYTHONUTF8 = "1"
        Start-Process -FilePath $appPy -ArgumentList "main.py" -WorkingDirectory $Root -WindowStyle Minimized
        Log "🚀 برنامه اجرا شد — http://127.0.0.1:8642"
    } catch { Log "⚠️ اجرا: $_" }
    
    $bar.Value = 100
    Set-Step "نصب کامل شد ✅" 100
    Log "🎉 نصب کامل شد!"
    Start-Sleep -Seconds 1
    $script:currentStep = 6
    Show-Step 6
}

Show-Step 0
Write-InstallLog "showing ultimate installer window"
[void]$form.ShowDialog()
Write-InstallLog "installer closed"
exit 0

} catch {
    Write-InstallLog "GUI crash: $_"
    try {
        [System.Windows.Forms.MessageBox]::Show("Installer failed:`r`n$_`r`nLog: $script:LogFile", "Divar Marketing", "OK", "Error") | Out-Null
    } catch {}
    exit 1
}
