"""Experimental edge-to-hole clearance relationship for polygonal mesh holes.

Workflow:
  1. Select exactly one straight part edge; capture as reference.
  2. Select only the closed boundary loop of a circular hole; lock clearance.
  3. Move the reference with Blinter's controlled operator; hole loop follows.

This is NOT a global constraint solver. Native arbitrary Blender transforms are not
intercepted. Vertex-index references are rejected when topology counts change,
but same-count reindexing is not detectable in this prototype.
"""
import math
import bpy
import bmesh
from mathutils import Vector
from bpy.props import FloatProperty, IntProperty, BoolProperty, PointerProperty

EPS = 1e-9
MAX_RADIAL_ERROR = 0.08
PLANE_ERROR = 0.05


class BLINTER_PG_edge_hole_relation(bpy.types.PropertyGroup):
    reference_a: IntProperty(default=-1)
    reference_b: IntProperty(default=-1)
    ring_indices: bpy.props.StringProperty(default="")
    vertex_count: IntProperty(default=0)
    edge_count: IntProperty(default=0)
    target_clearance_mm: FloatProperty(default=0.0, precision=4)
    enabled: BoolProperty(default=False)


def mesh(context):
    obj = context.edit_object
    if obj is None or obj.type != "MESH":
        raise ValueError("Enter Edit Mode on a mesh object")
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.verts.index_update()
    return obj, bm


def selected_edge(context):
    obj, bm = mesh(context)
    edges = [e for e in bm.edges if e.select and not e.hide]
    if len(edges) != 1:
        raise ValueError("Select exactly one reference edge")
    return obj, bm, edges[0]


def selected_closed_loop(bm):
    edges = [e for e in bm.edges if e.select and not e.hide]
    if len(edges) < 8:
        raise ValueError("Select a closed hole boundary loop of at least 8 edges")
    verts = set(v for edge in edges for v in edge.verts)
    if len(verts) != len(edges):
        raise ValueError("Selected edges must form one simple closed loop")
    degrees = {v: 0 for v in verts}
    for e in edges:
        for v in e.verts:
            degrees[v] += 1
    if any(n != 2 for n in degrees.values()):
        raise ValueError("Loop must be closed, connected, without branches")
    visited = {next(iter(verts))}
    stack = list(visited)
    adjacency = {v: [] for v in verts}
    for e in edges:
        a, b = e.verts
        adjacency[a].append(b)
        adjacency[b].append(a)
    while stack:
        for v in adjacency[stack.pop()]:
            if v not in visited:
                visited.add(v)
                stack.append(v)
    if visited != verts:
        raise ValueError("Multiple disconnected loops selected")
    return [v.index for v in verts]


def circle_fit(points):
    """Approximate planar circular polygon, returning centroid/normal/mean radius.

    Not a least-squares CAD circle reconstruction. Reject obvious noncircular loops.
    """
    center = sum(points, Vector((0.0, 0.0, 0.0))) / len(points)
    # A noncollinear triple defines a plane (works regardless of loop order).
    normal = None
    for i in range(1, len(points) - 1):
        cross = (points[i] - points[0]).cross(points[i + 1] - points[0])
        if cross.length > EPS:
            normal = cross.normalized()
            break
    if normal is None:
        raise ValueError("Hole boundary vertices are collinear")
    radii = [(p - center).length for p in points]
    radius = sum(radii) / len(radii)
    if radius < EPS or max(abs(r - radius) for r in radii) > MAX_RADIAL_ERROR * radius:
        raise ValueError("Selected loop is not sufficiently circular")
    if max(abs((p - center).dot(normal)) for p in points) > PLANE_ERROR * radius:
        raise ValueError("Selected loop is not sufficiently planar")
    return center, normal, radius


def geometry(obj, bm, data):
    if not data.enabled:
        raise ValueError("No active edge-to-hole lock")
    if len(bm.verts) != data.vertex_count or len(bm.edges) != data.edge_count:
        raise ValueError("Mesh topology count changed; relationship must be recaptured")
    ring_ids = [int(i) for i in data.ring_indices.split(",") if i.strip()]
    ids = [data.reference_a, data.reference_b] + ring_ids
    if not ring_ids or min(ids) < 0 or max(ids) >= len(bm.verts) or len(set(ids)) != len(ids):
        raise ValueError("Invalid reference vertices; recapture relationship")
    a, b = (obj.matrix_world @ bm.verts[idx].co for idx in ids[:2])
    points = [obj.matrix_world @ bm.verts[idx].co for idx in ring_ids]
    center, normal, radius = circle_fit(points)
    axis = b - a
    if axis.length < EPS:
        raise ValueError("Reference edge has zero length")
    direction = axis.normalized()
    if abs(direction.dot(normal)) > 0.08:
        raise ValueError("Reference edge not in hole plane")
    sideways = normal.cross(direction).normalized()
    signed = (center - a).dot(sideways)
    if abs(signed) <= radius:
        raise ValueError("Reference line intersects hole; positive edge clearance needed")
    sign = 1.0 if signed > 0 else -1.0
    clearance = abs(signed) - radius
    return ring_ids, (data.reference_a, data.reference_b), sideways * sign, clearance


def translate_indices(obj, bm, vertex_indices, delta_world):
    # convert world-space displacement to mesh local coordinates (handles object scale/rotation).
    delta_local = obj.matrix_world.inverted_safe().to_3x3() @ delta_world
    for idx in set(vertex_indices):
        bm.verts[idx].co += delta_local


class BLINTER_OT_capture_reference_edge(bpy.types.Operator):
    bl_idname = "blinter.capture_reference_edge"
    bl_label = "1. Choose Part Edge"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        try:
            obj, bm, edge = selected_edge(context)
            edge.verts[0].index, edge.verts[1].index
            relation = obj.data.blinter_edge_hole
            relation.reference_a = edge.verts[0].index
            relation.reference_b = edge.verts[1].index
            relation.ring_indices = ""
            relation.vertex_count = len(bm.verts)
            relation.edge_count = len(bm.edges)
            relation.enabled = False
            self.report({'INFO'}, "Reference chosen. Select just the hole rim loop next.")
            return {'FINISHED'}
        except ValueError as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}


class BLINTER_OT_lock_hole_clearance(bpy.types.Operator):
    bl_idname = "blinter.lock_hole_clearance"
    bl_label = "2. Lock Hole Clearance"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        try:
            obj, bm = mesh(context)
            data = obj.data.blinter_edge_hole
            if data.reference_a < 0 or data.reference_b < 0:
                raise ValueError("First choose a reference part edge")
            if len(bm.verts) != data.vertex_count or len(bm.edges) != data.edge_count:
                raise ValueError("Mesh topology changed; capture edge again")
            ring = selected_closed_loop(bm)
            if data.reference_a in ring or data.reference_b in ring:
                raise ValueError("Part edge cannot share vertices with hole loop")
            data.ring_indices = ",".join(str(i) for i in sorted(ring))
            data.enabled = True
            try:
                _, _, _, clearance = geometry(obj, bm, data)
            except ValueError:
                data.enabled = False
                raise
            data.target_clearance_mm = clearance * 1000.0
            self.report({'INFO'}, f"Locked edge-to-hole clearance: {clearance * 1000.0:.3f} mm")
            return {'FINISHED'}
        except ValueError as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}


class BLINTER_OT_set_hole_clearance(bpy.types.Operator):
    bl_idname = "blinter.set_hole_clearance"
    bl_label = "Set Edge-to-Hole Clearance"
    bl_options = {'REGISTER', 'UNDO'}

    clearance_mm: FloatProperty(name="Clearance (mm)", default=6.35, min=0.001, precision=3)

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.edit_object.data.blinter_edge_hole.enabled

    def invoke(self, context, event):
        self.clearance_mm = context.edit_object.data.blinter_edge_hole.target_clearance_mm
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        try:
            obj, bm = mesh(context)
            data = obj.data.blinter_edge_hole
            ring, _, toward_hole, current = geometry(obj, bm, data)
            delta = (self.clearance_mm / 1000.0 - current) * toward_hole
            translate_indices(obj, bm, ring, delta)
            data.target_clearance_mm = self.clearance_mm
            bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=False)
            return {'FINISHED'}
        except ValueError as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}


class BLINTER_OT_move_reference_edge(bpy.types.Operator):
    """Translate part edge and hole ring together normal to the reference edge."""
    bl_idname = "blinter.move_reference_edge"
    bl_label = "Move Part Edge + Follow Hole"
    bl_options = {'REGISTER', 'UNDO'}

    distance_mm: FloatProperty(name="Move (mm)", default=5.0, precision=3)

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.edit_object.data.blinter_edge_hole.enabled

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        try:
            obj, bm = mesh(context)
            data = obj.data.blinter_edge_hole
            ring, part, toward_hole, _ = geometry(obj, bm, data)
            delta = toward_hole * (self.distance_mm / 1000.0)
            translate_indices(obj, bm, list(part) + ring, delta)
            bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=False)
            return {'FINISHED'}
        except ValueError as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}


class BLINTER_OT_clear_hole_relation(bpy.types.Operator):
    bl_idname = "blinter.clear_hole_relation"
    bl_label = "Clear Hole Relationship"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.edit_object or context.edit_object.type != 'MESH':
            return {'CANCELLED'}
        rel = context.edit_object.data.blinter_edge_hole
        rel.enabled = False
        rel.reference_a = -1
        rel.reference_b = -1
        rel.ring_indices = ""
        return {'FINISHED'}


class BLINTER_PT_edge_hole_relation(bpy.types.Panel):
    bl_label = "Relative Hole Position"
    bl_idname = "BLINTER_PT_edge_hole_relation"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Blinter'

    def draw(self, context):
        col = self.layout.column(align=True)
        col.label(text="Mesh-native edge-to-hole distance")
        col.operator("blinter.capture_reference_edge", icon='EDGESEL')
        col.operator("blinter.lock_hole_clearance", icon='DECORATE_LOCKED')
        obj = context.edit_object
        if obj and obj.type == 'MESH' and obj.data.blinter_edge_hole.enabled:
            rel = obj.data.blinter_edge_hole
            col.label(text=f"Clearance: {rel.target_clearance_mm:.3f} mm")
            col.operator("blinter.set_hole_clearance", icon='DRIVER_DISTANCE')
            col.operator("blinter.move_reference_edge", icon='TRANSFORM_MOVE')
            col.operator("blinter.clear_hole_relation", icon='X')
        col.label(text="Only Blinter moves preserve this link")


classes = (
    BLINTER_PG_edge_hole_relation,
    BLINTER_OT_capture_reference_edge,
    BLINTER_OT_lock_hole_clearance,
    BLINTER_OT_set_hole_clearance,
    BLINTER_OT_move_reference_edge,
    BLINTER_OT_clear_hole_relation,
    BLINTER_PT_edge_hole_relation,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Mesh.blinter_edge_hole = PointerProperty(type=BLINTER_PG_edge_hole_relation)


def unregister():
    del bpy.types.Mesh.blinter_edge_hole
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
