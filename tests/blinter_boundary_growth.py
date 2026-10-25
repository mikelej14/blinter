"""Blinter planar mesh boundary regression. Run with built Blender fork."""
import math
import bpy
import bmesh
from bl_operators.blinter_boundary_growth import _boundary_loops, _boundary_valid
from bl_operators.blinter_features import analyze_selection

def main():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    data = bpy.data.meshes.new('Continuous plate')
    obj = bpy.data.objects.new('Feature envelope', data)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bm = bmesh.new()
    inner = [bm.verts.new((.004*math.cos(i*math.tau/64),.004*math.sin(i*math.tau/64),0)) for i in range(64)]
    outer = [bm.verts.new((.016*math.cos(i*math.tau/64),.016*math.sin(i*math.tau/64),0)) for i in range(64)]
    for i in range(64):
        j=(i+1)%64
        bm.faces.new((inner[i], inner[j], outer[j], outer[i]))
    bm.to_mesh(data)
    bm.free()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.tool_settings.mesh_select_mode=(False,True,False)
    bpy.ops.mesh.select_all(action='DESELECT')
    bm=bmesh.from_edit_mesh(data)
    for edge in bm.edges:
        if all(v.co.length<.005 for v in edge.verts):
            edge.select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(data)
    n=(len(bm.verts),len(bm.edges),len(bm.faces))
    assert bpy.ops.blinter.grow_boundary_for_feature(offset_mm=(7,0,0),clearance_mm=6.35)=={'FINISHED'}
    obj,bm,ring,center,normal,radius=analyze_selection(bpy.context)
    assert (len(bm.verts),len(bm.edges),len(bm.faces))==n
    outer=next(loop for loop in _boundary_loops(bm) if set(loop)!=set(ring))
    assert _boundary_valid(obj,outer,center,normal,radius+.00635,{})
    seen={next(iter(bm.verts))}
    stack=list(seen)
    while stack:
        for edge in stack.pop().link_edges:
            for vertex in edge.verts:
                if vertex not in seen:
                    seen.add(vertex)
                    stack.append(vertex)
    assert len(seen)==len(bm.verts)
    print('BLINTER_BOUNDARY_GROWTH_OK')

if __name__=='__main__':
    main()
