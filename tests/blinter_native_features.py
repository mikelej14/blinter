"""Blinter local analytic feature regression (Blender fork required).

Run blender --background --python tests/blinter_native_features.py
"""
import math
import bpy
import bmesh
from mathutils import Vector
from bl_operators.blinter_features import analyze_selection


def create_circle(count=64, radius=.005):
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    mesh = bpy.data.meshes.new("Blinter Circle Test")
    obj = bpy.data.objects.new("Sample Mesh", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bm = bmesh.new()
    vertices = [bm.verts.new((radius * math.cos(i * math.tau / count),
                              radius * math.sin(i * math.tau / count), .003))
                for i in range(count)]
    for index in range(count):
        edge = bm.edges.new((vertices[index], vertices[(index + 1) % count]))
        edge.select_set(True)
    bm.to_mesh(mesh)
    bm.free()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.tool_settings.mesh_select_mode = (False, True, False)
    bpy.ops.mesh.select_all(action='SELECT')
    return obj


def main():
    obj = create_circle()
    _, _, vertices, _, _, r = analyze_selection(bpy.context)
    assert len(vertices) == 64
    assert abs(r - .005) < 1e-7
    assert bpy.ops.blinter.circle_diameter(diameter_mm=6.35) == {'FINISHED'}
    _, _, _, center, _, radius = analyze_selection(bpy.context)
    assert abs(radius * 2000 - 6.35) < 1e-5
    # Reject noncircular feature rather than falsely present it as precise.
    bm = bmesh.from_edit_mesh(obj.data)
    v = next(iter(bm.verts))
    v.co += Vector((.003, 0, 0))
    bmesh.update_edit_mesh(obj.data)
    try:
        analyze_selection(bpy.context)
    except ValueError:
        pass
    else:
        raise AssertionError("Noncircular loop was incorrectly accepted")
    print("BLINTER_NATIVE_FEATURES_OK")


if __name__ == '__main__':
    main()
