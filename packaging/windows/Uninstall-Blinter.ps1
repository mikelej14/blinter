# Blinter's per-user uninstaller, independent from regular Blender.
param([switch]$RemovePreferences)
$ErrorActionPreference='Stop'
$install = Split-Path -Parent $MyInvocation.MyCommand.Path
$processes = Get-CimInstance Win32_Process -Filter "Name = 'Blinter.exe'" -ErrorAction SilentlyContinue
if ($processes | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($install, [StringComparison]::OrdinalIgnoreCase) }) {
  throw "Close Blinter before uninstalling."
}
$programs = Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs'
$shortcuts = @((Join-Path $programs 'Blinter Alpha.lnk'))
$desktop = [Environment]::GetFolderPath('Desktop')
if ($desktop) { $shortcuts += Join-Path $desktop 'Blinter Alpha.lnk' }
foreach ($shortcut in $shortcuts) {
  if (Test-Path -LiteralPath $shortcut) { Remove-Item -LiteralPath $shortcut -Force }
}
$key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\BlinterAlpha'
if (Test-Path $key) { Remove-Item $key -Recurse -Force }
# Preserve local config unless the user explicitly requests removal.
Get-ChildItem -LiteralPath $install -Force |
  Where-Object { $_.Name -notin @('portable','Uninstall-Blinter.ps1') } |
  Remove-Item -Recurse -Force
if ($RemovePreferences) {
  $saved = Join-Path $install 'portable'
  if (Test-Path $saved) { Remove-Item -LiteralPath $saved -Recurse -Force }
}
Write-Host 'Blinter Alpha uninstalled; your regular Blender was not affected.'
if (-not $RemovePreferences) {
  Write-Host "Blinter preferences remain in $install\portable"
}
