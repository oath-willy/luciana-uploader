param([switch]$Disable)
$ErrorActionPreference = "Stop"
$settingsPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
$backupPath = Join-Path $env:LOCALAPPDATA 'Luciana\proxy-backup.xml'
if ($Disable) {
  if (-not (Test-Path -LiteralPath $backupPath)) { throw 'Nessuna configurazione precedente salvata.' }
  $backup = Import-Clixml -LiteralPath $backupPath
  if ($backup.HadAutoConfigURL) {
    Set-ItemProperty -LiteralPath $settingsPath -Name AutoConfigURL -Value $backup.AutoConfigURL
  } else {
    Remove-ItemProperty -LiteralPath $settingsPath -Name AutoConfigURL -ErrorAction SilentlyContinue
  }
  Remove-Item -LiteralPath $backupPath
  Write-Host 'Configurazione proxy precedente ripristinata. Riavvia il browser.'
} else {
  if (-not (Test-Path -LiteralPath $backupPath)) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $backupPath) -Force | Out-Null
    $current = Get-ItemProperty -LiteralPath $settingsPath
    [pscustomobject]@{HadAutoConfigURL=$null -ne $current.AutoConfigURL; AutoConfigURL=$current.AutoConfigURL} | Export-Clixml -LiteralPath $backupPath
  }
  Set-ItemProperty -LiteralPath $settingsPath -Name AutoConfigURL -Value 'https://rstudio-ks.westeurope.cloudapp.azure.com/luciana-proxy.pac'
  Write-Host 'Proxy Luciana configurato. Connetti Azure VPN e riavvia il browser prima di aprire la webapp.'
}
