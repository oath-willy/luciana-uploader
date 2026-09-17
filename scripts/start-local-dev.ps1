param(
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 3000,
  [string]$ResourceGroup = "luciana_resource_group",
  [string]$WebAppName = "luciana-backend",
  [string]$NewItemsSubscription = "sub-keystone-research-dev",
  [string]$Vm04Host = "20.160.158.80"
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

$localDataDir = Join-Path $backendDir "data\codex"
[Environment]::SetEnvironmentVariable("MC_CODE_LOCAL_DATA_DIR", $localDataDir, "Process")
[Environment]::SetEnvironmentVariable("MC_CODE_RUNTIME_DB", (Join-Path $localDataDir "runtime.sqlite3"), "Process")
[Environment]::SetEnvironmentVariable("PDB_REF_LOCAL_PATH", (Join-Path $localDataDir "ref_pdb_dump.parquet"), "Process")
[Environment]::SetEnvironmentVariable("PDB_REF_STATUS_DB", (Join-Path $localDataDir "pdb-settings.sqlite3"), "Process")
[Environment]::SetEnvironmentVariable("PDB_MC_CLASSIFICATION_LOCAL_PATH", (Join-Path $localDataDir "pdb_mc_classification.parquet"), "Process")
[Environment]::SetEnvironmentVariable("PDB_MC_CLASSIFICATION_STATUS_DB", (Join-Path $localDataDir "pdb-mc-classification-sync.sqlite3"), "Process")
[Environment]::SetEnvironmentVariable("PDB_REF_VM_HOST", $Vm04Host, "Process")

if (-not $env:PDB_NEW_ITEMS_STORAGE_CONNECTION_STRING -and -not $env:PDB_NEW_ITEMS_STORAGE_SECRET) {
  $newItemsKey = az storage account keys list `
    --subscription $NewItemsSubscription `
    --account-name stkeystoneresearchdev `
    --query '[0].value' -o tsv --only-show-errors
  if ($LASTEXITCODE -eq 0 -and $newItemsKey) {
    $newItemsConnection = "DefaultEndpointsProtocol=https;AccountName=stkeystoneresearchdev;AccountKey=$newItemsKey;EndpointSuffix=core.windows.net"
    [Environment]::SetEnvironmentVariable("PDB_NEW_ITEMS_STORAGE_CONNECTION_STRING", $newItemsConnection, "Process")
    $newItemsKey = $null
    $newItemsConnection = $null
  } else {
    Write-Warning "New Items usera DefaultAzureCredential: occorre Storage Blob Data Reader sul container pdb."
  }
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
  -ArgumentList @("-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "$BackendPort", "--reload", "--reload-exclude", ".venv") `
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
