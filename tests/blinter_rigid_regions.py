"""Regression for compact rigid region storage.
Run blender -b --python tests/blinter_rigid_regions.py -- /repo
"""
import os
import sys
import math
import bpy
import bmesh
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
root = args[0] if args else os.getcwd()
sys.path.insert(0, os.path.join(root, "scripts", "addons_core"))
import blinter_engineering
from blinter_engineering.rigid_regions import TAG, region_members, validate_regions


def main():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    blinter_engineering.register()
    try:
        mesh = bpy.data.meshes.new("high-poly rigid region")
        obj = bpy.data.objects.new("test part", mesh)
        bpy.context.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bm = bmesh.new()
        outer = [bm.verts.new((.05 * math.cos(i * math.tau / 128),
                               .05 * math.sin(i * math.tau / 128), 0))
                 for i in range(128)]
        for i in range(128):
            bm.edges.new((outer[i], outer[(i + 1) % 128]))
        inside = [bm.verts.new((.015 * math.cos(i * math.tau / 512),
                                .015 * math.sin(i * math.tau / 512), 0))
                  for i in range(512)]
        for i in range(512):
            bm.edges.new((inside[i], inside[(i + 1) % 512]))
        for vert in inside:
            vert.select = True
        bm.to_mesh(mesh)
        bm.free()
        bpy.ops.object.mode_set(mode='EDIT')
        assert bpy.ops.blinter.capture_rigid_region() == {'FINISHED'}
        lock = mesh.blinter_rigid_regions[0]
        assert lock.count == 512
        assert mesh.blinter_active_rigid_region == 0
        lock.name = "Mounting Hole Pattern"
        assert lock.name == "Mounting Hole Pattern"
        # Group has no 512x coordinate JSON snapshot.
        assert len(lock.bounds_json) < 200
        bm = bmesh.from_edit_mesh(mesh)
        _, members = validate_regions(obj, bm)
        vertices = members[lock.group_id]
        before = {id(v): v.co.copy() for v in vertices}
        assert bpy.ops.blinter.scale_outside_regions(factor=(1.5, 1.5, 1)) == {'FINISHED'}
        for v in vertices:
            assert (v.co - before[id(v)]).length < 1e-7
        # Capture a second independent group from the outer loop.
        bpy.ops.mesh.select_all(action='DESELECT')
        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        layer = bm.verts.layers.int.get(TAG)
        for vertex in bm.verts:
            if vertex[layer] == 0:
                vertex.select_set(True)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(mesh)
        assert bpy.ops.blinter.capture_rigid_region() == {'FINISHED'}
        assert len(mesh.blinter_rigid_regions) == 2
        second = mesh.blinter_rigid_regions[1]
        assert second.count == 128
        assert mesh.blinter_active_rigid_region == 1
        assert bpy.ops.blinter.select_locked_region() == {'FINISHED'}
        bm = bmesh.from_edit_mesh(mesh)
        selected = [v for v in bm.verts if v.select]
        assert len(selected) == second.count
        assert bpy.ops.blinter.toggle_selection_lock() == {'FINISHED'}
        assert len(mesh.blinter_rigid_regions) == 1
        # Lock second group again using the same right-click backend.
        assert bpy.ops.blinter.toggle_selection_lock() == {'FINISHED'}
        assert len(mesh.blinter_rigid_regions) == 2
        second = mesh.blinter_rigid_regions[1]
        assert bpy.ops.blinter.move_rigid_region(group_id=lock.group_id, offset_mm=(6, 0, 0)) == {'FINISHED'}
        for v in vertices:
            assert (v.co - before[id(v)] - Vector((.006, 0, 0))).length < 1e-7
        bm = bmesh.from_edit_mesh(mesh)
        _, groups = validate_regions(obj, bm)
        assert len(groups[second.group_id]) == 128
        assert bpy.ops.blinter.clear_rigid_regions() == {'FINISHED'}
        assert not mesh.blinter_rigid_regions
        print("BLINTER_COMPACT_RIGID_REGIONS_OK")
    finally:
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        blinter_engineering.unregister()


if __name__ == "__main__":
    main()
