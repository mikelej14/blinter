# SPDX-License-Identifier: GPL-2.0-or-later
"""Conservative native edge-intersection repair for Blinter.

Exact interior crossing of two *loose* mesh edges is made into one shared
BMesh vertex. No Boolean, broad remove-doubles, or coincident loose edges.
Face-attached and collinear overlap cases require planar arrangement /
face reconstruction and are intentionally rejected in this first step.
"""
import bpy
import bmesh
from bpy.props import FloatProperty
from mathutils import Vector
from .blinter_topology import inspect_topology

EPS = 1e-12


def intersection(e1, e2, tolerance):
    """Unique interior 3D segment/segment meeting. None if no true crossing."""
    a, b = (v.co.copy() for v in e1.verts)
    c, d = (v.co.copy() for v in e2.verts)
    u, v, w = b-a, d-c, a-c
    uu, vv, uv = u.dot(u), v.dot(v), u.dot(v)
    det = uu*vv-uv*uv
    if det <= max(EPS**4, uu*vv*1e-16):
        # Parallel and collinear overlaps are a DIFFERENT topology operation.
        return None
    uw, vw = u.dot(w), v.dot(w)
    s = (uv*vw-vv*uw)/det
    t = (uu*vw-uv*uw)/det
    # Avoid collapsing endpoint-near features; those need endpoint snapping
    # with separate dimensional/lock checks.
    margin = max(1e-8, tolerance / max(u.length, v.length))
    if not (margin < s < 1-margin and margin < t < 1-margin):
        return None
    p, q = a+u*s, c+v*t
    if (p-q).length > tolerance:
        return None
    return s, t, (p+q)*0.5


def split_and_join(bm, edge_a, edge_b, candidate, tolerance):
    s, t, point = candidate
    if not edge_a.is_valid or not edge_b.is_valid:
        raise ValueError("An edge was removed during reconstruction")
    if edge_a is edge_b or set(edge_a.verts) & set(edge_b.verts):
        raise ValueError("Edges already share a vertex")
    if edge_a.link_faces or edge_b.link_faces:
        raise ValueError("Face-attached crossing needs polygon reconstruction first")
    layer = bm.verts.layers.int.get("blinter_region_tag")
    if layer and any(vert[layer] for edge in (edge_a, edge_b) for vert in edge.verts):
        raise ValueError("Cannot change locked feature topology")
    _, new_a = bmesh.utils.edge_split(edge_a, edge_a.verts[0], s)
    _, new_b = bmesh.utils.edge_split(edge_b, edge_b.verts[0], t)
    new_a.co = point.copy()
    new_b.co = point.copy()
    # Weld ONLY the two new coincident vertices. Not a global Remove Doubles.
    bmesh.ops.weld_verts(bm, targetmap={new_b: new_a})
    inspect_topology(bm)
    if not new_a.is_valid or len(new_a.link_edges) != 4:
        raise ValueError("Intersection did not create one four-way connected vertex")


def find_first_crossing(edges, tolerance):
    for i, edge in enumerate(edges):
        for other in edges[i+1:]:
            if set(edge.verts) & set(other.verts):
                continue
            crossing = intersection(edge, other, tolerance)
            if crossing is not None:
                return edge, other, crossing
    return None


class BLINTER_OT_join_crossing_edges(bpy.types.Operator):
    """Join intersecting loose edges into one shared vertex, preserving topology."""
    bl_idname = "blinter.join_crossing_edges"
    bl_label = "Join Crossing Edges"
    bl_options = {'REGISTER', 'UNDO'}

    tolerance_mm: FloatProperty(
        name="Intersection Tolerance (mm)", default=.001,
        min=.000001, max=.05, precision=6,
    )

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.edit_object is not None

    def execute(self, context):
        try:
            obj = context.edit_object
            bm = bmesh.from_edit_mesh(obj.data)
            bm.edges.ensure_lookup_table()
            bm.edges.index_update()
            edges = [e for e in bm.edges if e.select and not e.hide]
            if len(edges) < 2:
                raise ValueError("Select at least two intersecting edges")
            if any(edge.link_faces for edge in edges):
                raise ValueError("Face-attached crossings require safe face reconstruction")
            if obj.matrix_world.determinant() == 0:
                raise ValueError("Object matrix is singular")
            tol = self.tolerance_mm / 1000.0
            # Solve in world space by preparing a transformed temporary copy
            # and applying the same topological split on original local edges.
            # For now require uniform scale to avoid ambiguous local tolerance.
            s = obj.matrix_world.to_scale()
            if max(s)-min(s) > 1e-8 or min(s) <= 0:
                raise ValueError("Apply nonuniform object scale before edge joining")
            local_tol = tol / s[0]
            candidate = find_first_crossing(edges, local_tol)
            if candidate is None:
                raise ValueError("No unique interior crossing within tolerance")
            ea, eb, hit = candidate
            original_components = inspect_topology(bm)
            index_a, index_b = ea.index, eb.index
            stage = bm.copy()
            try:
                stage.edges.ensure_lookup_table()
                split_and_join(stage, stage.edges[index_a], stage.edges[index_b],
                               hit, local_tol)
                if inspect_topology(stage) != original_components-1:
                    raise ValueError("Crossing should connect exactly two components")
            finally:
                stage.free()
            split_and_join(bm, ea, eb, hit, local_tol)
            bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
            self.report({'INFO'}, "Crossing repaired as one shared mesh vertex")
            return {'FINISHED'}
        except ValueError as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}


classes = (BLINTER_OT_join_crossing_edges,)
