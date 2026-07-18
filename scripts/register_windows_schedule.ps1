param(
    [string]$ProjectPath = (Split-Path -Parent $PSScriptRoot),
    [string]$PythonPath = (Join-Path (Split-Path -Parent $PSScriptRoot) ".venv\Scripts\python.exe")
)

$dailyTaskName = "TaiwanStockPredictorDataUpdate"
$dailyArguments = "-m scripts.update_daily_data --trigger schedule"
$dailyAction = New-ScheduledTaskAction -Execute $PythonPath -Argument $dailyArguments -WorkingDirectory $ProjectPath
$dailyTriggers = @()
$dailyTriggers += New-ScheduledTaskTrigger -Daily -At "07:00"
$dailyTriggers += New-ScheduledTaskTrigger -Daily -At "14:00"
$dailyTriggers += New-ScheduledTaskTrigger -Daily -At "21:00"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $dailyTaskName -Action $dailyAction -Trigger $dailyTriggers -Settings $settings -Description "Taiwan stock predictor daily data update" -Force

$marketTaskName = "TaiwanStockPredictorMarketUpdate"
$marketArguments = "-m scripts.update_daily_data --trigger market --market-open-only"
$marketAction = New-ScheduledTaskAction -Execute $PythonPath -Argument $marketArguments -WorkingDirectory $ProjectPath
$marketTrigger = New-ScheduledTaskTrigger -Once -At "00:00" `
    -RepetitionInterval (New-TimeSpan -Minutes 3) `
    -RepetitionDuration (New-TimeSpan -Days 1)
Register-ScheduledTask -TaskName $marketTaskName -Action $marketAction -Trigger $marketTrigger -Settings $settings -Description "Taiwan market update every 3 minutes while open" -Force

Write-Host "Schedules registered: every 3 minutes while market is open, plus 07:00, 14:00 and 21:00 daily."
