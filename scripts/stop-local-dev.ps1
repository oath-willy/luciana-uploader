param(
  [int[]]$Ports = @(8000, 3000)
)

$ErrorActionPreference = "Stop"

foreach ($port in $Ports) {
  $connections = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
    Where-Object { $_.OwningProcess -gt 0 } |
    Select-Object -ExpandProperty OwningProcess -Unique

  foreach ($processId in $connections) {
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process) {
      Write-Host "Stop processo $($process.ProcessName) ($processId) sulla porta $port"
      Stop-Process -Id $processId -Force
    }
  }
}

Write-Host "Server locali fermati."
