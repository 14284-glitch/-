$ErrorActionPreference = "Stop"
$ProjectPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectPath ".venv\Scripts\python.exe"
$BundledPython = "C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$PidFile = Join-Path $ProjectPath "logs\dashboard.pid"

if (Test-Path $VenvPython) {
    $Python = $VenvPython
} elseif (Test-Path $BundledPython) {
    $Python = $BundledPython
} else {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $PythonCommand) {
        throw "Python not found. Install Python 3.11 and run: pip install -r requirements.txt"
    }
    $Python = $PythonCommand.Source
}

try {
    & $Python -c "import streamlit, plotly, pandas" 2>$null
} catch {
    throw "Required packages are missing. Run: pip install -r requirements.txt"
}

$ExistingPid = if (Test-Path $PidFile) { Get-Content $PidFile -ErrorAction SilentlyContinue } else { $null }
if ($ExistingPid -and (Get-Process -Id $ExistingPid -ErrorAction SilentlyContinue)) {
    Start-Process "http://127.0.0.1:8501"
    exit 0
}

$Process = Start-Process -FilePath $Python `
    -ArgumentList "-m", "streamlit", "run", "app.py", "--server.address", "127.0.0.1", "--server.port", "8501" `
    -WorkingDirectory $ProjectPath -WindowStyle Hidden -PassThru
$Process.Id | Set-Content -Path $PidFile -Encoding ascii

for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
    Start-Sleep -Seconds 1
    try {
        $Response = Invoke-WebRequest "http://127.0.0.1:8501" -UseBasicParsing -TimeoutSec 2
        if ($Response.StatusCode -eq 200) {
            Start-Process "http://127.0.0.1:8501"
            Write-Host "Dashboard started."
            Write-Host "URL: http://127.0.0.1:8501"
            exit 0
        }
    } catch {
        # Wait for Streamlit to finish starting.
    }
}

Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
Remove-Item $PidFile -ErrorAction SilentlyContinue
throw "Dashboard did not start within 30 seconds. Check packages and firewall settings."
