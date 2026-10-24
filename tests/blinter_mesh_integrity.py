"""Blinter connected-surface integrity regression.

Must run within a real Blender build; no add-on registration required.
"""
import bpy
import bmesh
import math
from mathutils import Vector
from bl_operators.blinter_features import analyze_selection


def make_annulus(segments=48, inner=.005, outer=.008):
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    mesh = bpy.data.meshes.new("Blinter Connected Annulus")
    obj = bpy.data.objects.new("Connected Circle Feature", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bm = bmesh.new()
    inner_ring = []
    outer_ring = []
    for i in range(segments):
        angle = i * math.tau / segments
        x, y = math.cos(angle), math.sin(angle)
        inner_ring.append(bm.verts.new((inner*x, inner*y, 0.0)))
        outer_ring.append(bm.verts.new((outer*x, outer*y, 0.0)))
    for i in range(segments):
        j = (i+1) % segments
        bm.faces.new((inner_ring[i], inner_ring[j], outer_ring[j], outer_ring[i]))
    bm.to_mesh(mesh)
    bm.free()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.tool_settings.mesh_select_mode = (False, True, False)
    bpy.ops.mesh.select_all(action='DESELECT')
    bm = bmesh.from_edit_mesh(mesh)
    for edge in bm.edges:
        if all(v.co.length < .006 for v in edge.verts):
            edge.select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(mesh)
    return obj


def local_positions(obj):
    bm = bmesh.from_edit_mesh(obj.data)
    return [tuple(v.co) for v in bm.verts]


def main():
    obj = make_annulus()
    before = local_positions(obj)
    assert len(analyze_selection(bpy.context)[2]) == 48

    # Resize inner edge loop within available surrounding material.
    assert bpy.ops.blinter.circle_diameter(diameter_mm=6.35) == {'FINISHED'}
    _, _, _, _, _, radius = analyze_selection(bpy.context)
    assert abs(2000*radius-6.35) < 1e-5

    saved = local_positions(obj)
    # Trying to push the inner ring beyond the outer ring must be rejected.
    assert bpy.ops.blinter.circle_diameter(diameter_mm=19.0) == {'CANCELLED'}
    after = local_positions(obj)
    assert len(after) == len(saved)
    assert all((Vector(a)-Vector(b)).length < 1e-10
               for a, b in zip(after, saved)), "Rejected edit did not roll back"

    print("BLINTER_MESH_INTEGRITY_OK")


if __name__ == '__main__':
    main()
