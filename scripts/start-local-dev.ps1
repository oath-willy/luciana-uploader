param(
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 3000,
  [string]$ResourceGroup = "luciana_resource_group",
  [string]$WebAppName = "luciana-backend"
)

$ErrorActionPreference = "Stop"

function Test-PortInUse {
  param([int]$Port)

  $connection = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    Where-Object { $_.State -in @("Listen", "Established") } |
    Select-Object -First 1

  return $null -ne $connection
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "frontend"
$logDir = Join-Path $repoRoot ".local-logs"
$backendPython = Join-Path $backendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $backendPython)) {
  throw "Backend virtualenv non trovato: $backendPython"
}

if (Test-PortInUse $BackendPort) {
  throw "Porta backend $BackendPort gia in uso. Chiudi il processo o usa -BackendPort."
}

if (Test-PortInUse $FrontendPort) {
  throw "Porta frontend $FrontendPort gia in uso. Chiudi il processo o usa -FrontendPort."
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

Write-Host "Carico app settings da Azure App Service $WebAppName..."
$settings = az webapp config appsettings list `
  --resource-group $ResourceGroup `
  --name $WebAppName | ConvertFrom-Json

foreach ($setting in $settings) {
  [Environment]::SetEnvironmentVariable($setting.name, $setting.value, "Process")
}

[Environment]::SetEnvironmentVariable("FRONTEND_ORIGIN", "http://localhost:$FrontendPort", "Process")
[Environment]::SetEnvironmentVariable("REACT_APP_BACKEND_URL", "http://localhost:$BackendPort", "Process")
[Environment]::SetEnvironmentVariable("BROWSER", "none", "Process")
[Environment]::SetEnvironmentVariable("PORT", "$FrontendPort", "Process")

$backendOut = Join-Path $logDir "backend.out.log"
$backendErr = Join-Path $logDir "backend.err.log"
$frontendOut = Join-Path $logDir "frontend.out.log"
$frontendErr = Join-Path $logDir "frontend.err.log"

Write-Host "Avvio backend FastAPI su http://localhost:$BackendPort ..."
$backendProcess = Start-Process `
  -FilePath $backendPython `
  -ArgumentList @("-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "$BackendPort", "--reload") `
  -WorkingDirectory $backendDir `
  -RedirectStandardOutput $backendOut `
  -RedirectStandardError $backendErr `
  -WindowStyle Hidden `
  -PassThru

Write-Host "Avvio frontend React su http://localhost:$FrontendPort ..."
$frontendProcess = Start-Process `
  -FilePath "npm.cmd" `
  -ArgumentList @("start") `
  -WorkingDirectory $frontendDir `
  -RedirectStandardOutput $frontendOut `
  -RedirectStandardError $frontendErr `
  -WindowStyle Hidden `
  -PassThru

Write-Host ""
Write-Host "Ambiente locale avviato."
Write-Host "Frontend: http://localhost:$FrontendPort"
Write-Host "Backend:  http://localhost:$BackendPort"
Write-Host "Backend docs: http://localhost:$BackendPort/docs"
Write-Host ""
Write-Host "PID backend:  $($backendProcess.Id)"
Write-Host "PID frontend: $($frontendProcess.Id)"
Write-Host "Log backend:  $backendOut"
Write-Host "Log frontend: $frontendOut"
