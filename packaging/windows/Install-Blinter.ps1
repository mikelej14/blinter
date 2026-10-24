# SPDX-License-Identifier: GPL-2.0-or-later
# Blinter Alpha side-by-side per-user installer. No Blender install is touched.
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "Programs\Blinter Alpha"),
    [switch]$NoDesktopShortcut
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $root "Blinter"
$exeSource = Join-Path $source "Blinter.exe"
if (-not (Test-Path -LiteralPath $exeSource)) {
    throw "Package incomplete: Blinter\Blinter.exe not found. Extract the WHOLE ZIP before installing."
}
if (([IO.Path]::GetFullPath($InstallDir)).TrimEnd('\') -eq ([IO.Path]::GetFullPath($source)).TrimEnd('\')) {
    throw "Install location must differ from extracted source package."
}
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
# Copy one entire native program tree, keeping config separate under this install.
# Do not delete existing Portable folder during upgrades.
$payload = Get-ChildItem -LiteralPath $source -Force
foreach ($item in $payload) {
    if ($item.Name -eq 'portable') { continue }
    Copy-Item -LiteralPath $item.FullName -Destination $InstallDir -Force -Recurse
}
$exe = Join-Path $InstallDir "Blinter.exe"
if (-not (Test-Path -LiteralPath $exe)) { throw "Blinter.exe missing after copy." }
# Blender's built-in portable preference mechanism ensures it never reads or
# writes normal Blender Foundation\Blender user settings or extensions.
New-Item -ItemType Directory -Path (Join-Path $InstallDir "portable") -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $root "Uninstall-Blinter.ps1") -Destination $InstallDir -Force

$shell = New-Object -ComObject WScript.Shell
$programs = Join-Path ([Environment]::GetFolderPath('StartMenu')) "Programs"
New-Item -ItemType Directory -Path $programs -Force | Out-Null
$startShortcut = Join-Path $programs "Blinter Alpha.lnk"
$link = $shell.CreateShortcut($startShortcut)
$link.TargetPath = $exe
$link.WorkingDirectory = $InstallDir
$link.Description = "Blinter - precision mesh modeling"
$link.IconLocation = "$exe,0"
$link.Save()
if (-not $NoDesktopShortcut) {
    $desktop = [Environment]::GetFolderPath('Desktop')
    if ($desktop -and (Test-Path $desktop)) {
        $deskLink = $shell.CreateShortcut((Join-Path $desktop "Blinter Alpha.lnk"))
        $deskLink.TargetPath = $exe
        $deskLink.WorkingDirectory = $InstallDir
        $deskLink.IconLocation = "$exe,0"
        $deskLink.Save()
    }
}
# Separate Windows Apps & Features entry; never register .blend associations.
$reg = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\BlinterAlpha"
New-Item -Path $reg -Force | Out-Null
$uninstall = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $InstallDir 'Uninstall-Blinter.ps1') + '"'
New-ItemProperty -Path $reg -Name DisplayName -Value 'Blinter Alpha' -PropertyType String -Force | Out-Null
New-ItemProperty -Path $reg -Name Publisher -Value 'Blinter contributors' -PropertyType String -Force | Out-Null
New-ItemProperty -Path $reg -Name DisplayVersion -Value '0.1.0-alpha' -PropertyType String -Force | Out-Null
New-ItemProperty -Path $reg -Name InstallLocation -Value $InstallDir -PropertyType String -Force | Out-Null
New-ItemProperty -Path $reg -Name UninstallString -Value $uninstall -PropertyType String -Force | Out-Null
New-ItemProperty -Path $reg -Name NoModify -Value 1 -PropertyType DWord -Force | Out-Null

Write-Host "Blinter Alpha installed in $InstallDir"
Write-Host "Regular Blender's executable, settings, add-ons, file associations and shortcuts were not modified."
Write-Host "Launch using the Blinter Alpha Start Menu shortcut."
