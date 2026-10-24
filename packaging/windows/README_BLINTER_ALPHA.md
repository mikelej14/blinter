# Blinter Alpha for Windows — independent installation

Blinter is built from the native Blender source fork, not installed as an add-on.

## Install

After the GitHub Windows build workflow completes successfully, download its
Blinter-Alpha-Windows-x64 artifact and extract the whole ZIP. Double-click
SETUP_BLINTER.cmd. Open Blinter Alpha from the Windows Start Menu or desktop.

The program installs by default to:
%LOCALAPPDATA%\Programs\Blinter Alpha

## Independent of regular Blender

* Executable in package is Blinter.exe.
* Windows app ID, native window title, and executable metadata say Blinter.
* Blinter uses a private portable preferences/extensions location inside
  its own installation, rather than Blender Foundation/Blender roaming data.
* No .blend file association changes, no Blender uninstallation.
* Own Blinter Alpha Add/Remove Programs entry.
* Uninstall preserves private Blinter preferences unless specifically requested.

## Build and smoke checks

The native Windows workflow compiles the fork, stages the executable, runs
headless startup tests, installs Blinter separately on the runner, launches
that installed copy, checks identity/portable files and registry, then
uninstalls before publishing the alpha ZIP.

If any of these stages fails, no installable artifact is published.
Source and Python-only tests cannot be represented as a verified release.

The geometry and CAD-like constraint engine is still experimental;
automated solid reconstruction and full Fusion/Plasticity parity are not
implemented or validated. Save copies of work before editing with alpha tools.
