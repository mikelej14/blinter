"""Focused relative-clearance test. Run in Blender background with -- <repo root>."""
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
from blinter_engineering.relative_hole import geometry, mesh


def select_edges(obj, indices):
    bm = bmesh.from_edit_mesh(obj.data)
    bm.edges.ensure_lookup_table()
    bm.edges.index_update()
    for edge in bm.edges:
        edge.select_set(edge.index in indices)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)


def clearance_m(obj):
    _, bm = mesh(bpy.context)
    return geometry(obj, bm, obj.data.blinter_edge_hole)[-1]


def main():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    blinter_engineering.register()
    try:
        mesh_data = bpy.data.meshes.new("Clearance test mesh")
        obj = bpy.data.objects.new("Clearance test part", mesh_data)
        bpy.context.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bm = bmesh.new()
        ref_a = bm.verts.new((-0.02, -0.02, 0))
        ref_b = bm.verts.new((0.02, -0.02, 0))
        ref_edge = bm.edges.new((ref_a, ref_b))
        ring = [
            bm.verts.new((0.005 * math.cos(2 * math.pi * i / 32),
                          0.005 * math.sin(2 * math.pi * i / 32), 0.0))
            for i in range(32)
        ]
        for i in range(32):
            bm.edges.new((ring[i], ring[(i + 1) % 32]))
        bm.to_mesh(mesh_data)
        bm.free()
        bpy.ops.object.mode_set(mode='EDIT')
        select_edges(obj, [0])
        assert bpy.ops.blinter.capture_reference_edge() == {'FINISHED'}
        select_edges(obj, list(range(1, 33)))
        assert bpy.ops.blinter.lock_hole_clearance() == {'FINISHED'}
        before = clearance_m(obj)
        assert abs(before - .015) < 1e-6, before
        assert bpy.ops.blinter.move_reference_edge(distance_mm=4) == {'FINISHED'}
        after = clearance_m(obj)
        assert abs(after - before) < 1e-6, (before, after)
        assert bpy.ops.blinter.set_hole_clearance(clearance_mm=6.35) == {'FINISHED'}
        assert abs(clearance_m(obj) - .00635) < 1e-6
        bpy.ops.object.mode_set(mode='OBJECT')
        print("BLINTER_RELATIVE_CLEARANCE_OK")
    finally:
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        blinter_engineering.unregister()


if __name__ == '__main__':
    main()
