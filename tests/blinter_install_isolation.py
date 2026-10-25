"""Run from compiled Blinter.exe to prove config cannot collide with Blender."""
import os
import bpy

exe = os.path.abspath(bpy.app.binary_path)
assert os.path.basename(exe).casefold() == "blinter.exe", exe
install = os.path.dirname(exe)
config = bpy.utils.user_resource("CONFIG")
scripts = bpy.utils.user_resource("SCRIPTS")
for label, path in (("config", config), ("scripts", scripts)):
    if not path:
        raise RuntimeError("Blinter could not resolve isolated " + label)
    folder = os.path.normcase(os.path.abspath(path))
    isolated = os.path.normcase(os.path.join(install, "portable"))
    if os.path.commonpath((folder, isolated)) != isolated:
        raise RuntimeError("Blinter " + label + " escapes portable settings: " + path)
print("BLINTER_CONFIG_ISOLATED_OK", config)
