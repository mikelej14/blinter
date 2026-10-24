"""Regression: multi-feature bolt-loop preservation during mesh resizing.

Run: blender -b --python tests/blinter_feature_locks.py -- /path/to/blinter
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
from blinter_engineering.feature_locks import resolve_all


def make_mesh():
    data = bpy.data.meshes.new("Pattern prototype")
    obj = bpy.data.objects.new("Bolt pattern test", data)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bm = bmesh.new()
    rim_ids = []
    for x in (-0.03, 0.03):
        ring = [bm.verts.new((x + .004 * math.cos(i * math.tau / 24),
                             .004 * math.sin(i * math.tau / 24), 0)) for i in range(24)]
        for i in range(24):
            bm.edges.new((ring[i], ring[(i+1) % 24]))
        rim_ids.extend(ring)
    body = [bm.verts.new((-.06, -.025, 0)),
            bm.verts.new((.06, -.025, 0)),
            bm.verts.new((.06, .025, 0)),
            bm.verts.new((-.06, .025, 0))]
    for i in range(4):
        bm.edges.new((body[i], body[(i+1) % 4]))
    for v in bm.verts:
        v.select_set(v in rim_ids)
    bm.to_mesh(data)
    bm.free()
    return obj


def main():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    blinter_engineering.register()
    try:
        obj = make_mesh()
        bpy.ops.object.mode_set(mode='EDIT')
        assert bpy.ops.blinter.lock_features() == {'FINISHED'}
        locks = obj.data.blinter_feature_locks
        assert len(locks) == 1
        assert locks[0].kind == 'RELATIVE', locks[0].kind
        bm = bmesh.from_edit_mesh(obj.data)
        protected, _, groups = resolve_all(obj, bm)
        baseline = {v.index: tuple(obj.matrix_world @ v.co) for v in groups[0][1]}
        free = [v for v in bm.verts if v not in groups[0][1]]
        old_free = [v.co.copy() for v in free]
        assert bpy.ops.blinter.scale_unlocked(factor_x=1.5, factor_y=1.2) == {'FINISHED'}
        bm = bmesh.from_edit_mesh(obj.data)
        _, _, groups = resolve_all(obj, bm)
        for v in groups[0][1]:
            assert ((obj.matrix_world @ v.co) - Vector(baseline[v.index])).length < 1e-7
        assert any((v.co - old).length > 1e-6 for v, old in zip(free, old_free))
        # Lock persists in .blend mesh property storage.
        assert len(obj.data.blinter_feature_locks) == 1
        assert bpy.ops.blinter.remove_feature_locks() == {'FINISHED'}
        assert len(obj.data.blinter_feature_locks) == 0
        print("BLINTER_FEATURE_LOCKS_OK")
    finally:
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        blinter_engineering.unregister()


if __name__ == '__main__':
    main()
