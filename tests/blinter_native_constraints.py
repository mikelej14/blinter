"""Native Blinter lock-aware modeling regression test.
Requires Blender built with this branch's startup scripts.
Run: blender -b --python tests/blinter_native_constraints.py
"""
import bpy
import bmesh


def pick(mesh, indices):
    bpy.context.tool_settings.mesh_select_mode = (True, False, False)
    bm = bmesh.from_edit_mesh(mesh)
    bm.verts.ensure_lookup_table()
    for v in bm.verts:
        v.select_set(v.index in indices)
    bm.select_mode = {'VERT'}
    bm.select_flush_mode()
    bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)


def world_positions(obj):
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    return [obj.matrix_world @ v.co.copy() for v in bm.verts]


def main():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    assert hasattr(bpy.types.Mesh, "blinter_rigid_regions")
    bpy.ops.mesh.primitive_cube_add(size=.02)
    obj = bpy.context.object
    bpy.ops.object.mode_set(mode='EDIT')
    data = obj.data
    pick(data, [0])
    assert bpy.ops.blinter.capture_rigid_region(lock_type='AUTO') == {'FINISHED'}
    world_lock = data.blinter_rigid_regions[0]
    assert world_lock.kind == 'ANCHOR'
    pick(data, [1, 2])
    assert bpy.ops.blinter.capture_rigid_region(lock_type='AUTO') == {'FINISHED'}
    relative = data.blinter_rigid_regions[1]
    assert relative.kind == 'RELATIVE'
    before = world_positions(obj)
    distance = (before[1] - before[2]).length
    pick(data, list(range(len(before))))
    assert bpy.ops.blinter.transform_selection(action='SCALE', factor=(1.5, 1.2, 1.0)) == {'FINISHED'}
    after = world_positions(obj)
    assert (after[0] - before[0]).length < 1e-7, "World anchor moved"
    assert abs((after[1] - after[2]).length - distance) < 1e-7, "Rigid group stretched"
    assert any((after[i] - before[i]).length > 1e-6 for i in range(3, len(after))), "Free mesh did not resize"

    pick(data, [1])
    # Selecting one vertex of the tagged relative group moves the entire region.
    assert bpy.ops.blinter.transform_selection(action='MOVE', offset_mm=(5.0, 0, 0)) == {'FINISHED'}
    moved = world_positions(obj)
    for i in (1, 2):
        assert abs((moved[i] - after[i]).x - .005) < 1e-7
    assert (moved[0] - before[0]).length < 1e-7
    assert abs((moved[1] - moved[2]).length - distance) < 1e-7
    print("BLINTER_NATIVE_CONSTRAINTS_OK")


if __name__ == '__main__':
    main()
