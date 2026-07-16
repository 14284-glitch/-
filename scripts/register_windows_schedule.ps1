param(
    [string]$ProjectPath = (Split-Path -Parent $PSScriptRoot),
    [string]$PythonPath = (Join-Path (Split-Path -Parent $PSScriptRoot) ".venv\Scripts\python.exe")
)

$taskName = "TaiwanStockPredictorDataUpdate"
$arguments = "-m scripts.update_daily_data --trigger schedule"
$action = New-ScheduledTaskAction -Execute $PythonPath -Argument $arguments -WorkingDirectory $ProjectPath
$triggers = @(
    New-ScheduledTaskTrigger -Daily -At "07:00",
    New-ScheduledTaskTrigger -Daily -At "14:00",
    New-ScheduledTaskTrigger -Daily -At "21:00"
)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggers -Settings $settings -Description "台股預測系統每日資料更新" -Force
Write-Host "已建立排程：每天 07:00、14:00、21:00 更新。"

