# ── AXIOM Edge — Windows Task Scheduler Setup ────────────────────────────────
#
# Run this ONCE in PowerShell as Administrator:
#   Right-click PowerShell → "Run as administrator"
#   cd "C:\Users\sronn\OneDrive\Desktop\NBA-Model"
#   .\setup_tasks.ps1
#
# This creates three scheduled tasks:
#   AXIOM-Edge-Morning    →  8:00 AM daily  (data pull + picks + Discord alert)
#   AXIOM-Edge-Afternoon  →  4:00 PM daily  (closing odds for CLV tracking)
#   AXIOM-Edge-Evening    →  2:00 AM daily  (results fetch + ROI update)
#
# To view tasks after setup:  taskschd.msc
# To remove tasks:            Unregister-ScheduledTask -TaskName "AXIOM-Edge-Morning" -Confirm:$false

$Project = "C:\Users\sronn\OneDrive\Desktop\NBA-Model"
$Python  = "$Project\venv\Scripts\python.exe"
$Script  = "$Project\run_daily.py"

# Verify python exists in venv
if (-not (Test-Path $Python)) {
    Write-Host "ERROR: Python not found at $Python" -ForegroundColor Red
    Write-Host "Make sure your virtual environment is set up: python -m venv venv" -ForegroundColor Yellow
    exit 1
}

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -StartWhenAvailable `
    -DontStopOnIdleEnd

# ── Morning task: 8:00 AM — data + picks + Discord alert ──────────────────────
$MorningAction  = New-ScheduledTaskAction `
    -Execute  $Python `
    -Argument "$Script --morning" `
    -WorkingDirectory $Project

$MorningTrigger = New-ScheduledTaskTrigger -Daily -At 8:00AM

Register-ScheduledTask `
    -TaskName   "AXIOM-Edge-Morning" `
    -Action     $MorningAction `
    -Trigger    $MorningTrigger `
    -Settings   $Settings `
    -RunLevel   Highest `
    -Force | Out-Null

Write-Host "✓ Morning task created  →  8:00 AM daily" -ForegroundColor Green

# ── Afternoon task: 4:00 PM — closing odds fetch for CLV ──────────────────────
$AfternoonAction  = New-ScheduledTaskAction `
    -Execute  $Python `
    -Argument "$Script --afternoon" `
    -WorkingDirectory $Project

$AfternoonTrigger = New-ScheduledTaskTrigger -Daily -At 4:00PM

Register-ScheduledTask `
    -TaskName   "AXIOM-Edge-Afternoon" `
    -Action     $AfternoonAction `
    -Trigger    $AfternoonTrigger `
    -Settings   $Settings `
    -RunLevel   Highest `
    -Force | Out-Null

Write-Host "✓ Afternoon task created →  4:00 PM daily (closing odds for CLV)" -ForegroundColor Green

# ── Evening task: 2:00 AM — results fetch + ROI update ────────────────────────
# Runs at 2 AM so all west coast games (which can finish past midnight ET) are done.
$EveningAction  = New-ScheduledTaskAction `
    -Execute  $Python `
    -Argument "$Script --evening" `
    -WorkingDirectory $Project

$EveningTrigger = New-ScheduledTaskTrigger -Daily -At 2:00AM

Register-ScheduledTask `
    -TaskName   "AXIOM-Edge-Evening" `
    -Action     $EveningAction `
    -Trigger    $EveningTrigger `
    -Settings   $Settings `
    -RunLevel   Highest `
    -Force | Out-Null

Write-Host "✓ Evening task created  →  2:00 AM daily (catches all west coast games)" -ForegroundColor Green

Write-Host ""
Write-Host "All done! 3 tasks registered. Open Task Scheduler to verify:" -ForegroundColor Cyan
Write-Host "  taskschd.msc  (look under Task Scheduler Library)" -ForegroundColor Cyan
Write-Host ""
Write-Host "To test immediately (morning pipeline):" -ForegroundColor Yellow
Write-Host "  python run_daily.py --morning" -ForegroundColor Yellow
Write-Host ""
Write-Host "To test Discord alert only:" -ForegroundColor Yellow
Write-Host "  python discord_alert.py" -ForegroundColor Yellow
