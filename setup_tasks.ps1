# AXIOM Edge - Windows Task Scheduler Setup
#
# Run this ONCE in PowerShell as Administrator:
#   Right-click PowerShell -> "Run as administrator"
#   cd "C:\Users\sronn\OneDrive\Desktop\NBA-Model"
#   .\setup_tasks.ps1
#
# Creates three scheduled tasks, each with TWO triggers:
#   1. Fixed daily time (original schedule)
#   2. At logon - fires when you log in IF the pipeline has not run yet today
#      (run_daily.py writes a stamp file after each successful run so it never
#       double-runs even if both triggers fire on the same day)
#
#   AXIOM-Edge-Morning    ->  8:00 AM  + at logon
#   AXIOM-Edge-Afternoon  ->  4:00 PM  + at logon (5 min delay)
#   AXIOM-Edge-Evening    ->  2:00 AM  + at logon (10 min delay)
#
# To view tasks:    taskschd.msc
# To remove tasks:  Unregister-ScheduledTask -TaskName "AXIOM-Edge-Morning" -Confirm:$false

$Project = "C:\Users\sronn\OneDrive\Desktop\NBA-Model"
$Python  = "$Project\venv\Scripts\python.exe"
$Script  = "$Project\run_daily.py"

if (-not (Test-Path $Python)) {
    Write-Host "ERROR: Python not found at $Python" -ForegroundColor Red
    Write-Host "Make sure your virtual environment is set up: python -m venv venv" -ForegroundColor Yellow
    exit 1
}

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -MultipleInstances IgnoreNew

# Morning task: 8:00 AM + at logon
$MorningAction   = New-ScheduledTaskAction `
    -Execute  $Python `
    -Argument "$Script --morning" `
    -WorkingDirectory $Project

$MorningTrigger1 = New-ScheduledTaskTrigger -Daily -At 8:00AM
$MorningTrigger2 = New-ScheduledTaskTrigger -AtLogOn

Register-ScheduledTask `
    -TaskName   "AXIOM-Edge-Morning" `
    -Action     $MorningAction `
    -Trigger    @($MorningTrigger1, $MorningTrigger2) `
    -Settings   $Settings `
    -RunLevel   Highest `
    -Force | Out-Null

Write-Host "[OK] Morning task created -> 8:00 AM + at every logon" -ForegroundColor Green

# Afternoon task: 4:00 PM + at logon with 5 min delay
$AfternoonAction   = New-ScheduledTaskAction `
    -Execute  $Python `
    -Argument "$Script --afternoon" `
    -WorkingDirectory $Project

$AfternoonTrigger1 = New-ScheduledTaskTrigger -Daily -At 4:00PM
$AfternoonTrigger2 = New-ScheduledTaskTrigger -AtLogOn
$AfternoonTrigger2.Delay = "PT5M"

Register-ScheduledTask `
    -TaskName   "AXIOM-Edge-Afternoon" `
    -Action     $AfternoonAction `
    -Trigger    @($AfternoonTrigger1, $AfternoonTrigger2) `
    -Settings   $Settings `
    -RunLevel   Highest `
    -Force | Out-Null

Write-Host "[OK] Afternoon task created -> 4:00 PM + at logon (5 min delay)" -ForegroundColor Green

# Evening task: 2:00 AM + at logon with 10 min delay
$EveningAction   = New-ScheduledTaskAction `
    -Execute  $Python `
    -Argument "$Script --evening" `
    -WorkingDirectory $Project

$EveningTrigger1 = New-ScheduledTaskTrigger -Daily -At 2:00AM
$EveningTrigger2 = New-ScheduledTaskTrigger -AtLogOn
$EveningTrigger2.Delay = "PT10M"

Register-ScheduledTask `
    -TaskName   "AXIOM-Edge-Evening" `
    -Action     $EveningAction `
    -Trigger    @($EveningTrigger1, $EveningTrigger2) `
    -Settings   $Settings `
    -RunLevel   Highest `
    -Force | Out-Null

Write-Host "[OK] Evening task created -> 2:00 AM + at logon (10 min delay)" -ForegroundColor Green

Write-Host ""
Write-Host "All done! 3 tasks registered with logon fallbacks." -ForegroundColor Cyan
Write-Host "Open Task Scheduler to verify: taskschd.msc" -ForegroundColor Cyan
Write-Host ""
Write-Host "To test immediately:" -ForegroundColor Yellow
Write-Host "  python run_daily.py --morning" -ForegroundColor Yellow
Write-Host "  python run_daily.py --evening" -ForegroundColor Yellow
