# SPDX-License-Identifier: GPL-2.0-or-later
"""Native topology primitives for Blinter manufacturing-accurate mesh edits.

Plan changes on a BMesh COPY, validate them, then replay to original BMesh.
Unlike global Remove Doubles, only explicitly designated vertex pairs are
eligible for welding, with a tolerance bounded by the manufacturing gap.
"""
import bpy
import bmesh
from bpy.props import FloatProperty, IntProperty
from mathutils import Vector

EPS = 1e-10


def inspect_topology(bm, expected_components=None):
    """Enforce valid links, nonzero edges/faces and connectedness as requested."""
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    for edge in bm.edges:
        if not edge.is_valid or (edge.verts[0].co-edge.verts[1].co).length <= EPS:
            raise ValueError("Invalid or collapsed mesh edge")
        if len(edge.link_faces) > 2:
            raise ValueError("Non-manifold edge: more than two connected faces")
    for face in bm.faces:
        if not face.is_valid or face.calc_area() <= EPS * EPS:
            raise ValueError("Degenerate mesh face")
        if len(set(face.verts)) != len(face.verts):
            raise ValueError("Face contains duplicate vertices")
    edge_pairs = set()
    for edge in bm.edges:
        pair = frozenset(edge.verts)
        if pair in edge_pairs:
            raise ValueError("Duplicate edge between the same vertices")
        edge_pairs.add(pair)
    seen = set()
    components = 0
    for vert in bm.verts:
        if vert in seen:
            continue
        components += 1
        seen.add(vert)
        pending = [vert]
        while pending:
            v = pending.pop()
            for edge in v.link_edges:
                other = edge.other_vert(v)
                if other not in seen:
                    seen.add(other)
                    pending.append(other)
    if expected_components is not None and components != expected_components:
        raise ValueError("Mesh connectivity changed: detached or unexpectedly joined region")
    return components


def split_existing_edges(bm, indices, cuts):
    """Split the existing BMesh edge in-place, propagating attached face loops.

    No new independent surface and no coincident duplicate seam. Does not
    triangulate the model or call a Boolean.
    """
    bm.edges.ensure_lookup_table()
    bm.edges.index_update()
    edges = [bm.edges[index] for index in indices]
    for edge in edges:
        if not edge.is_valid:
            raise ValueError("Edge reference lost during split")
        a, b = edge.verts
        # Construct points at even intervals along original edge.
        start, finish = a.co.copy(), b.co.copy()
        current_edge = edge
        start_vert = a
        for step in range(cuts):
            remaining = cuts + 1 - step
            new_edge, new_vert = bmesh.utils.edge_split(
                current_edge, start_vert, 1.0 / remaining
            )
            # edge_split returns the new edge and inserted vertex. Identify
            # the edge continuing towards the original far endpoint.
            new_vert.co = start.lerp(finish, (step + 1) / (cuts + 1))
            next_edges = [e for e in new_vert.link_edges if b in e.verts]
            if not next_edges:
                # Edge orientation may differ: find the half-edge closest to b.
                next_edges = [e for e in new_vert.link_edges
                              if e is new_edge or e is current_edge]
            if not next_edges:
                raise ValueError("Cannot identify remaining edge segment")
            current_edge = next_edges[0]
            start_vert = new_vert


def stage_refine(bm, indices, cuts):
    """Validate refinement on a copy before modifying live Edit Mode BMesh."""
    components = inspect_topology(bm)
    stage = bm.copy()
    try:
        original_vertices = len(stage.verts)
        original_edges = len(stage.edges)
        original_faces = len(stage.faces)
        original_boundary_count = sum(1 for edge in stage.edges if edge.is_boundary)
        split_existing_edges(stage, indices, cuts)
        inspect_topology(stage, expected_components=components)
        if len(stage.verts) != original_vertices + len(indices)*cuts:
            raise ValueError("Refinement vertex count differs from expected")
        if len(stage.edges) != original_edges + len(indices)*cuts:
            raise ValueError("Refinement edge count differs from expected")
        if len(stage.faces) != original_faces:
            raise ValueError("Refinement unexpectedly created or deleted faces")
        if sum(1 for edge in stage.edges if edge.is_boundary) != original_boundary_count + len(indices)*cuts:
            raise ValueError("Refinement changed manifold boundary classification")
        return components
    finally:
        stage.free()


def weld_specific_pairs(bm, pairs, tolerance, minimum_gap):
    """Never use global remove_doubles: only approved, near-coincident pairs.

    The weld tolerance must be much smaller than the intentional CAD clearance.
    """
    if minimum_gap <= 0 or tolerance <= 0 or tolerance >= minimum_gap * .1:
        raise ValueError("Weld tolerance must stay below one tenth of design clearance")
    tag = bm.verts.layers.int.get("blinter_region_tag")
    mapping = {}
    for source, target in pairs:
        if not source.is_valid or not target.is_valid or source is target:
            raise ValueError("Invalid targeted weld")
        if (source.co-target.co).length > tolerance:
            raise ValueError("Target vertices exceed precision weld tolerance")
        if tag is not None and source[tag] != target[tag]:
            raise ValueError("Refusing to weld across two different feature locks")
        if any(target in edge.verts for edge in source.link_edges):
            raise ValueError("Refusing to collapse existing edge by welding endpoints")
        if source in mapping:
            raise ValueError("A source vertex has multiple weld destinations")
        mapping[source] = target
    if mapping:
        bmesh.ops.weld_verts(bm, targetmap=mapping)


class BLINTER_OT_refine_boundary(bpy.types.Operator):
    """Add supporting vertices to selected EXISTING boundary edges, no new seams."""
    bl_idname = "blinter.refine_boundary"
    bl_label = "Refine Mesh Boundary"
    bl_options = {'REGISTER', 'UNDO'}

    cuts: IntProperty(name="New Vertices per Edge", default=2, min=1, max=32)

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.edit_object is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        try:
            obj = context.edit_object
            bm = bmesh.from_edit_mesh(obj.data)
            bm.edges.ensure_lookup_table()
            bm.edges.index_update()
            edges = [e for e in bm.edges if e.select and not e.hide]
            if not edges or any(not e.is_boundary for e in edges):
                raise ValueError("Select only existing exterior/hole boundary edges")
            tag = bm.verts.layers.int.get("blinter_region_tag")
            if tag is not None and any(v[tag] for e in edges for v in e.verts):
                raise ValueError("Unlock constrained edges before changing their topology")
            indices = [e.index for e in edges]
            expected = stage_refine(bm, indices, self.cuts)
            # The same deterministic BMesh edge subdivision is now replayed.
            split_existing_edges(bm, indices, self.cuts)
            inspect_topology(bm, expected_components=expected)
            bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
            self.report({'INFO'}, f"Refined {len(indices)} native boundary edges")
            return {'FINISHED'}
        except ValueError as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}


classes = (BLINTER_OT_refine_boundary,)
