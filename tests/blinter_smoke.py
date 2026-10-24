"""Blinter smoke test. Run with Blender -b --python tests/blinter_smoke.py -- <repo-root>"""
import os
import sys

import bpy
import bmesh

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
root = args[0] if args else os.getcwd()
sys.path.insert(0, os.path.join(root, "scripts", "addons_core"))

import blinter_engineering


def main():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.context.scene.cursor.location = (0, 0, 0)
    blinter_engineering.register()
    try:
        assert bpy.ops.blinter.metric_scene() == {'FINISHED'}
        assert bpy.context.scene.unit_settings.length_unit == 'MILLIMETERS'
        bpy.ops.mesh.primitive_cube_add(size=0.02)
        target = bpy.context.object
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(target.data)
        bpy.ops.mesh.select_all(action='DESELECT')
        bm = bmesh.from_edit_mesh(target.data)
        edge = bm.edges[0]
        edge.select_set(True)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(target.data)
        assert bpy.ops.blinter.set_edge_length(length_mm=12.7) == {'FINISHED'}
        bm = bmesh.from_edit_mesh(target.data)
        selected = [e for e in bm.edges if e.select]
        assert len(selected) == 1
        p0, p1 = (target.matrix_world @ v.co for v in selected[0].verts)
        assert abs((p0 - p1).length - .0127) < 1e-6
        bpy.ops.object.mode_set(mode='OBJECT')
        assert bpy.ops.blinter.add_hole_cutter(diameter_mm=6.0, depth_mm=25.0) == {'FINISHED'}
        cutters = [o for o in bpy.data.objects if o.name.startswith("Blinter Hole Cutter")]
        assert len(cutters) == 1
        boolean_mods = [m for m in target.modifiers if m.type == 'BOOLEAN']
        assert len(boolean_mods) == 1
        assert boolean_mods[0].object == cutters[0]
        print("BLINTER_SMOKE_OK")
    finally:
        blinter_engineering.unregister()


if __name__ == "__main__":
    main()
