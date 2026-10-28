# One-time setup for Windows. Run it by double-clicking "Install (Windows).cmd" in the project folder.
# Safe to run again: it keeps your settings and only updates what changed.
param(
    [string]$Time = ""
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$TaskName = "Job Agent - daily search"
Set-Location $Repo

function Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }

# 1. Python ---------------------------------------------------------------------------------
Step "Checking Python"
$Python = $null
foreach ($candidate in @("py", "python")) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if (-not $cmd) { continue }
    $args3 = @()
    if ($candidate -eq "py") { $args3 = @("-3") }
    try {
        $ok = & $candidate @args3 -c "import sys; print(sys.version_info >= (3, 10))" 2>$null
    } catch { $ok = $null }
    if ($ok -eq "True") { $Python = @($candidate) + $args3; break }
}
if (-not $Python) {
    Write-Host "Python 3.10 or newer was not found." -ForegroundColor Red
    Write-Host "Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run this again."
    exit 1
}
Write-Host "Using: $($Python -join ' ')"

# 2. Private Python environment + packages ------------------------------------------------------
Step "Installing packages (first run takes a minute)"
$VenvPython = Join-Path $Repo ".venv\Scripts\python.exe"
$VenvPythonW = Join-Path $Repo ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $VenvPython)) {
    $exe = $Python[0]
    $rest = @()
    if ($Python.Count -gt 1) { $rest = $Python[1..($Python.Count - 1)] }
    & $exe @rest -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Python environment" }
}
& $VenvPython -m pip install --quiet --upgrade pip
& $VenvPython -m pip install --quiet -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Package installation failed" }

# 3. Preferences ------------------------------------------------------------------------------
Step "Preferences"
$Prefs = Join-Path $Repo "preferences.yaml"
$NewPrefs = $false
if (-not (Test-Path $Prefs)) {
    Copy-Item (Join-Path $Repo "preferences.example.yaml") $Prefs
    $NewPrefs = $true
    Write-Host "Created preferences.yaml from the example."
} else {
    Write-Host "Keeping your existing preferences.yaml."
}

# 4. API key, saved once in .env (only readable by your Windows account) ------------------------------
Step "Claude API key"
$EnvFile = Join-Path $Repo ".env"
$HasKey = (Test-Path $EnvFile) -and (Select-String -Path $EnvFile -Pattern "^\s*ANTHROPIC_API_KEY\s*=\s*\S" -Quiet)
if ($HasKey) {
    $answer = Read-Host "An API key is already saved. Replace it? (y/N)"
    if ($answer -match "^[yY]") { $HasKey = $false }
}
if (-not $HasKey) {
    Write-Host "Create a key at https://console.anthropic.com (Settings > API keys), then paste it here."
    Write-Host "(Nothing will appear as you paste. That's expected.)"
    $secure = Read-Host "API key" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $NewKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr).Trim() }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    if (-not $NewKey.StartsWith("sk-ant-")) {
        Write-Host "That doesn't look like an Anthropic API key (they start with sk-ant-). Run this again to retry." -ForegroundColor Red
        exit 1
    }
    $kept = @()
    if (Test-Path $EnvFile) { $kept = Get-Content $EnvFile | Where-Object { $_ -notmatch "^\s*ANTHROPIC_API_KEY\s*=" } }
    Set-Content -Path $EnvFile -Value ($kept + "ANTHROPIC_API_KEY=$NewKey") -Encoding ASCII
    # Restrict the file to the current user.
    & icacls $EnvFile /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null
    Write-Host "Saved. You won't need to enter it again."
}

# 5. Daily scheduled task ------------------------------------------------------------------------
Step "Daily schedule"
if (-not $Time) {
    $Time = Read-Host "What time should the daily search run? (24-hour, e.g. 08:00) [08:00]"
    if (-not $Time) { $Time = "08:00" }
}
$At = [datetime]::Parse($Time)
$Action = New-ScheduledTaskAction -Execute $VenvPythonW -Argument "-m job_agent daily --open" -WorkingDirectory $Repo
$Trigger = New-ScheduledTaskTrigger -Daily -At $At
# StartWhenAvailable: if the PC was off or asleep at that time, run as soon as it's back.
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RunOnlyIfNetworkAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings `
    -Description "Searches LinkedIn for new jobs, scores them, and opens a summary. Created by job-agent." -Force | Out-Null
Write-Host "Scheduled every day at $($At.ToString('HH:mm')). The summary opens in your browser when it's ready."

# 6. Desktop shortcuts ------------------------------------------------------------------------------
Step "Desktop shortcuts"
$Desktop = [Environment]::GetFolderPath("Desktop")
$Shell = New-Object -ComObject WScript.Shell
function Shortcut($name, $target, $arguments, $description) {
    $link = $Shell.CreateShortcut((Join-Path $Desktop "$name.lnk"))
    $link.TargetPath = $target
    $link.Arguments = $arguments
    $link.WorkingDirectory = $Repo
    $link.Description = $description
    $link.Save()
}
Shortcut "Review jobs" $VenvPython "-m job_agent review --pause" "Approve or skip suggested jobs; writes CVs and cover letters for approved ones"
Shortcut "Search jobs now" $VenvPythonW "-m job_agent daily --open" "Run today's job search now instead of waiting for the schedule"
Shortcut "Job agent folder" "explorer.exe" "`"$Repo`"" "Preferences, knowledge base and generated documents"
Write-Host "Added 'Review jobs', 'Search jobs now' and 'Job agent folder' to your desktop."

# 7. Next steps ------------------------------------------------------------------------------------
Step "Almost done"
$Kb = Join-Path $Repo "knowledge_base"
$Example = Join-Path $Kb "example_profile.md"
Write-Host "1. Edit preferences.yaml (opening it in Notepad now): search terms, locations, what you want."
Write-Host "2. Put your CV, career history and project notes in the knowledge_base folder (opening it now)."
if (Test-Path $Example) { Write-Host "   Then delete example_profile.md from that folder, or it will be treated as your profile." }
Write-Host "3. Double-click 'Search jobs now' on your desktop to try it straight away."
Start-Process notepad.exe $Prefs
Start-Process explorer.exe $Kb
Write-Host "`nSetup complete." -ForegroundColor Green
