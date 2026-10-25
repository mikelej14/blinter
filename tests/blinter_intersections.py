"""Native crossing repair regression, requires actual Blinter Blender build."""
import bpy
import bmesh
from mathutils import Vector
from bl_operators.blinter_topology import inspect_topology


def main():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    mesh = bpy.data.meshes.new('Crossing wire sample')
    obj = bpy.data.objects.new('Crossing Lines', mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bm = bmesh.new()
    a = bm.verts.new((-.01, 0, 0))
    b = bm.verts.new((.01, 0, 0))
    c = bm.verts.new((0, -.01, 0))
    d = bm.verts.new((0, .01, 0))
    bm.edges.new((a,b))
    bm.edges.new((c,d))
    bm.to_mesh(mesh)
    bm.free()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.tool_settings.mesh_select_mode = (False, True, False)
    bpy.ops.mesh.select_all(action='SELECT')
    bm = bmesh.from_edit_mesh(mesh)
    assert len(bm.verts) == 4 and len(bm.edges) == 2
    assert inspect_topology(bm) == 2
    assert bpy.ops.blinter.join_crossing_edges(tolerance_mm=.001) == {'FINISHED'}
    bm = bmesh.from_edit_mesh(mesh)
    assert len(bm.verts) == 5 and len(bm.edges) == 4
    assert len(bm.faces) == 0
    assert inspect_topology(bm) == 1
    hubs = [v for v in bm.verts if len(v.link_edges) == 4]
    assert len(hubs) == 1 and hubs[0].co.length < 1e-8
    print('BLINTER_CROSSINGS_OK')


if __name__ == '__main__':
    main()
