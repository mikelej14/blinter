"""General feature propagation: selected face with surrounding shared mesh.

Run in a Blender build from this branch:
    blender --background --python tests/blinter_native_propagation.py
"""
import bpy
import bmesh
from mathutils import Vector


def create_plate():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    data = bpy.data.meshes.new("Adaptation sample grid")
    obj = bpy.data.objects.new("Plate sample", data)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bm = bmesh.new()
    verts = [[bm.verts.new(((x - 4) * .005, (y - 4) * .005, 0))
              for y in range(9)] for x in range(9)]
    for x in range(8):
        for y in range(8):
            bm.faces.new((verts[x][y], verts[x + 1][y],
                          verts[x + 1][y + 1], verts[x][y + 1]))
    bm.to_mesh(data)
    bm.free()
    bpy.ops.object.mode_set(mode='EDIT')
    return obj


def nearest(bm, xyz):
    return min(bm.verts, key=lambda v: (v.co - Vector(xyz)).length)


def main():
    obj = create_plate()
    bm = bmesh.from_edit_mesh(obj.data)
    bpy.context.tool_settings.mesh_select_mode = (True, False, False)
    bpy.ops.mesh.select_all(action='DESELECT')
    bm = bmesh.from_edit_mesh(obj.data)
    anchor = nearest(bm, (-.02, -.02, 0))
    anchor.select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)
    assert bpy.ops.blinter.capture_rigid_region(lock_type='ANCHOR') == {'FINISHED'}
    original_anchor = anchor.co.copy()

    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    bpy.ops.mesh.select_all(action='DESELECT')
    bm = bmesh.from_edit_mesh(obj.data)
    center_face = min(bm.faces, key=lambda f: f.calc_center_median().length)
    center_face.select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)
    selected = set(center_face.verts)
    original = {v: v.co.copy() for v in bm.verts}
    assert bpy.ops.blinter.adapt_feature_move(
        offset_mm=(1.0, 0.0, 0.0), influence_mm=12.0
    ) == {'FINISHED'}
    assert (anchor.co - original_anchor).length < 1e-8
    for v in selected:
        assert abs((v.co - original[v]).x - .001) < 1e-7
    adjusted_neighbors = [
        v for v in bm.verts if v not in selected
        and (v.co - original[v]).length > 1e-8
    ]
    assert adjusted_neighbors, "No attached mesh geometry adapted"
    assert len(obj.data.blinter_rigid_regions) == 1
    print("BLINTER_NATIVE_PROPAGATION_OK")


if __name__ == "__main__":
    main()
