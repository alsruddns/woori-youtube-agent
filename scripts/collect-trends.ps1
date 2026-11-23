$ErrorActionPreference = "Stop"
$project = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $project
$env:PYTHONPATH = Join-Path $project "src"
$python = Join-Path $project ".venv\Scripts\python.exe"
$logDir = Join-Path $project "data"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "trends-scheduler.log"
"$(Get-Date -Format o) collection started" | Add-Content -LiteralPath $log
& $python -X utf8 -m woori_youtube.cli trends --channel us-economy --region US 2>&1 | Out-File -LiteralPath $log -Append -Encoding utf8
$code = $LASTEXITCODE
"$(Get-Date -Format o) collection exit=$code" | Add-Content -LiteralPath $log
exit $code
