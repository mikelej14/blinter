"""Blinter fork native boot test, no add-on enabled.

Execute with a Blender executable built from the Blinter branch:
    blender --background --python tests/blinter_native_startup.py
"""
import bpy
import bmesh


def run():
    # Verify native startup class registrations (no bpy.ops.preferences.addon_enable).
    assert hasattr(bpy.types.Mesh, "blinter_rigid_regions")
    assert hasattr(bpy.ops.blinter, "capture_rigid_region")
    assert hasattr(bpy.ops.blinter, "toggle_selection_lock")
    assert hasattr(bpy.ops.blinter, "edge_dimension")
    assert hasattr(bpy.ops.blinter, "hole_cutter")
    assert getattr(bpy.types, "VIEW3D_PT_blinter_engineering", None) is not None

    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.mesh.primitive_cube_add(size=.02)
    obj = bpy.context.object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.tool_settings.mesh_select_mode = (True, False, False)
    bpy.ops.mesh.select_all(action='DESELECT')
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.verts[0].select_set(True)
    bm.verts[1].select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)
    assert bpy.ops.blinter.toggle_selection_lock() == {'FINISHED'}
    assert len(obj.data.blinter_rigid_regions) == 1
    obj.data.blinter_rigid_regions[0].name = "Mounting Datum"
    assert obj.data.blinter_rigid_regions[0].name == "Mounting Datum"
    assert bpy.ops.blinter.select_locked_region() == {'FINISHED'}
    assert bpy.ops.blinter.scale_outside_regions(factor=(1.2, 1.0, 1.0)) == {'FINISHED'}
    assert bpy.ops.blinter.toggle_selection_lock() == {'FINISHED'}
    assert not obj.data.blinter_rigid_regions

    bpy.ops.mesh.select_all(action='DESELECT')
    bm = bmesh.from_edit_mesh(obj.data)
    bm.edges.ensure_lookup_table()
    bm.edges[0].select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)
    assert bpy.ops.blinter.edge_dimension(length_mm=12.7) == {'FINISHED'}
    bpy.ops.object.mode_set(mode='OBJECT')
    assert bpy.ops.blinter.hole_cutter(diameter_mm=6.0, depth_mm=30.0) == {'FINISHED'}
    assert any(mod.type == 'BOOLEAN' for mod in obj.modifiers)
    print("BLINTER_NATIVE_STARTUP_OK")


if __name__ == '__main__':
    run()
