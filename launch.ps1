param()
$ErrorActionPreference = 'SilentlyContinue'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$serverPy = Join-Path $scriptDir 'server.py'
$pythonw = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\pythonw.exe'

if (-not (Test-Path -LiteralPath $pythonw)) {
    $python = 'python.exe'
} else {
    $python = $pythonw
}

$p = Start-Process -FilePath $python -ArgumentList "`"$serverPy`"" -WorkingDirectory $scriptDir -PassThru -WindowStyle Hidden
if (-not $p) {
    exit 1
}

for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:5173/' -UseBasicParsing -TimeoutSec 1
        if ($r.StatusCode -eq 200) {
            Start-Process 'http://127.0.0.1:5173/'
            exit 0
        }
    } catch {
    }
}

Start-Process 'http://127.0.0.1:5173/'
exit 0
