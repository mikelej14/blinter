"""Selection-domain feature locks: vertex, edge, adjoining faces, overrides.
Run: blender -b --python tests/blinter_multiselect_locks.py -- /path/to/blinter
"""
import os
import sys
import bpy
import bmesh

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
sys.path.insert(0, os.path.join(args[0] if args else os.getcwd(), "scripts", "addons_core"))
import blinter_engineering
from blinter_engineering.feature_locks import selection_info, resolve_all


def select(obj, domain, indices):
    bpy.context.tool_settings.mesh_select_mode = tuple(key == domain for key in ('VERT', 'EDGE', 'FACE'))
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bpy.ops.mesh.select_all(action='DESELECT')
    bm = bmesh.from_edit_mesh(obj.data)
    bm.select_mode = {domain}
    seq = {'VERT': bm.verts, 'EDGE': bm.edges, 'FACE': bm.faces}[domain]
    seq.ensure_lookup_table()
    for i in indices:
        seq[i].select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)
    return selection_info(bm)


def main():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    blinter_engineering.register()
    try:
        bpy.ops.mesh.primitive_cube_add(size=.02)
        obj = bpy.context.object
        bpy.ops.object.mode_set(mode='EDIT')
        n, verts, label = select(obj, 'VERT', [0])
        assert (n, label) == (1, 'vertices')
        assert bpy.ops.blinter.lock_features(lock_type='AUTO') == {'FINISHED'}
        assert obj.data.blinter_feature_locks[-1].kind == 'ANCHOR'

        n, verts, label = select(obj, 'EDGE', [0, 1])
        assert (n, label) == (2, 'edges')
        assert bpy.ops.blinter.lock_features(lock_type='AUTO') == {'FINISHED'}
        assert obj.data.blinter_feature_locks[-1].kind == 'RELATIVE'

        n, verts, label = select(obj, 'FACE', [0, 1])
        assert n == 2 and label == 'faces'
        assert len(verts) >= 6  # adjoining faces share vertices
        assert bpy.ops.blinter.lock_features(lock_type='AUTO') == {'FINISHED'}
        assert obj.data.blinter_feature_locks[-1].kind == 'RELATIVE'
        assert bpy.ops.blinter.lock_features(lock_type='ANCHOR') == {'FINISHED'}
        assert obj.data.blinter_feature_locks[-1].kind == 'ANCHOR'

        # Same selections can be explicitly treated as rigid relative regions.
        n, verts, label = select(obj, 'FACE', [0])
        assert n == 1
        assert bpy.ops.blinter.lock_features(lock_type='RELATIVE') == {'FINISHED'}
        assert obj.data.blinter_feature_locks[-1].kind == 'RELATIVE'
        _, _, groups = resolve_all(obj, bmesh.from_edit_mesh(obj.data))
        assert len(groups) == 5
        print("BLINTER_MULTISELECT_LOCKS_OK")
    finally:
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        blinter_engineering.unregister()


if __name__ == '__main__':
    main()
