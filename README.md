Blinter
=======

**Blinter** is an open-source, engineering-focused fork of **Blender**.
It keeps Blender's native mesh modeling engine, existing geometry tools, and
underlying source code while developing a simpler mechanical-design workflow
with dimensional controls, constraint-aware selections, and intelligent mesh
topology reconstruction.

Blinter is a separate application, not an add-on to an installed copy of
Blender. Its Windows build packages a distinct executable, application ID,
installer entry, and private preferences, allowing both programs to coexist.

## Windows alpha build

The development branch includes a native Windows build pipeline and installer
sources in [packaging/windows](packaging/windows/README_BLINTER_ALPHA.md).
Only a successfully compiled and smoke-tested Windows build is offered as an
installable alpha. A source checkout is not a runnable installer.

## Upstream acknowledgment

Blinter is based on the Blender project, developed by the Blender Foundation
and its contributors. The full original engine, applicable source notices and
copyrights are retained. See [blender.org](https://www.blender.org/) and the
[Blender developer documentation](https://developer.blender.org/docs/).

## Licensing

This project inherits Blender's GNU General Public License, version 3, with
individual source files subject to their compatible existing licenses.
Blinter is not affiliated with or endorsed by the Blender Foundation.
