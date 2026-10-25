"""Blinter native BMesh topology regression. Run inside built Blinter."""
import bpy
import bmesh
from mathutils import Vector
from bl_operators.blinter_topology import inspect_topology, weld_specific_pairs


def main():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.mesh.primitive_plane_add(size=.02)
    obj = bpy.context.object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.tool_settings.mesh_select_mode = (False, True, False)
    bpy.ops.mesh.select_all(action='DESELECT')
    bm = bmesh.from_edit_mesh(obj.data)
    bm.edges.ensure_lookup_table()
    edge = bm.edges[0]
    edge.select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)
    before = (len(bm.verts), len(bm.edges), len(bm.faces))
    assert inspect_topology(bm) == 1
    assert bpy.ops.blinter.refine_boundary(cuts=3) == {'FINISHED'}
    bm = bmesh.from_edit_mesh(obj.data)
    assert len(bm.verts) == before[0]+3
    assert len(bm.edges) == before[1]+3
    assert len(bm.faces) == before[2]
    assert inspect_topology(bm) == 1
    assert all(e.is_boundary for e in bm.edges)
    # A targeted weld should never connect nearby but distinct intentional
    # feature points unless an explicit approved pair and tolerance is supplied.
    a = bm.verts.new((.03, .03, 0))
    b = bm.verts.new((.0300001, .03, 0))
    c = bm.verts.new((.0300002, .03, 0))
    try:
        weld_specific_pairs(bm, [(a, b)], tolerance=.001, minimum_gap=.00635)
    except ValueError:
        pass
    else:
        raise AssertionError("Oversized weld tolerance was accepted")
    weld_specific_pairs(bm, [(a, b)], tolerance=.000001, minimum_gap=.00635)
    assert not a.is_valid
    assert c.is_valid, "Nearby unrelated vertex was accidentally merged"
    print("BLINTER_NATIVE_TOPOLOGY_OK")


if __name__ == '__main__':
    main()
