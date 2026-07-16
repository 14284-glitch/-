$ProjectPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $ProjectPath "logs\dashboard.pid"
if (-not (Test-Path $PidFile)) {
    Write-Host "No dashboard process created by the launcher was found."
    exit 0
}
$DashboardPid = Get-Content $PidFile
Stop-Process -Id $DashboardPid -Force -ErrorAction SilentlyContinue
Remove-Item $PidFile -ErrorAction SilentlyContinue
Write-Host "Dashboard stopped."
