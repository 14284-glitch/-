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

$obsoleteMarketTask = Get-ScheduledTask -TaskName "TaiwanStockPredictorMarketUpdate" -ErrorAction SilentlyContinue
if ($obsoleteMarketTask) {
    Unregister-ScheduledTask -TaskName "TaiwanStockPredictorMarketUpdate" -Confirm:$false
}

Write-Host "Schedule registered: 07:00, 14:00 and 21:00 daily. The obsolete 3-minute schedule was removed."
