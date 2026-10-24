# SPDX-License-Identifier: GPL-2.0-or-later
"""Blinter local analytic feature recognition, operating on native BMesh.

A selected polygon loop is temporarily treated as a circle in world space for
precise diameter edits. Nothing converts the mesh to NURBS or B-rep: analytic
data is computed on demand, then translated back into mesh vertex coordinates.
"""
import math
import bpy
import bmesh
from mathutils import Vector
from bpy.props import FloatProperty

MIN_EDGES = 8
RADIAL_REL_TOL = .025
PLANE_REL_TOL = .01
EPS = 1e-9


def selected_loop(bm):
    edges = [e for e in bm.edges if e.select and not e.hide]
    if len(edges) < MIN_EDGES:
        raise ValueError("Select one closed circular edge loop (8+ edges)")
    adj = {}
    for e in edges:
        a, b = e.verts
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    if len(adj) != len(edges) or any(len(n) != 2 for n in adj.values()):
        raise ValueError("Selection is not one closed, unbranched loop")
    start = next(iter(adj))
    order = [start]
    previous = None
    current = start
    for _ in range(len(edges)-1):
        next_candidates = [v for v in adj[current] if v is not previous]
        nxt = next_candidates[0]
        if nxt in order:
            raise ValueError("Selection has overlapping loops")
        order.append(nxt)
        previous, current = current, nxt
    if start not in adj[current]:
        raise ValueError("Selected edges are disconnected")
    return order


def circle_parameters(obj, vertices):
    """Fit plane from polygon area normal, radius from world-space centroid.

    Assumes a nearly uniformly sampled circle. Reject noncircular outlines;
    we do not falsely claim to have recognized a precise analytic circle.
    """
    points = [obj.matrix_world @ v.co for v in vertices]
    center = sum(points, Vector((0, 0, 0))) / len(points)
    normal = Vector((0, 0, 0))
    for a, b in zip(points, points[1:] + points[:1]):
        normal += (a-center).cross(b-center)
    if normal.length <= EPS:
        raise ValueError("Cannot determine circle plane")
    normal.normalize()
    radii = [(point-center).length for point in points]
    radius = sum(radii) / len(radii)
    if radius <= EPS:
        raise ValueError("Degenerate circular loop")
    radial_error = max(abs(r-radius) for r in radii)
    plane_error = max(abs((p-center).dot(normal)) for p in points)
    if radial_error > radius * RADIAL_REL_TOL or plane_error > radius * PLANE_REL_TOL:
        raise ValueError("Loop is not sufficiently planar and circular")
    return center, normal, radius


def analyze_selection(context):
    obj = context.edit_object
    if obj is None or obj.type != 'MESH':
        raise ValueError("Enter mesh Edit Mode")
    bm = bmesh.from_edit_mesh(obj.data)
    vertices = selected_loop(bm)
    center, normal, radius = circle_parameters(obj, vertices)
    return obj, bm, vertices, center, normal, radius


class BLINTER_OT_circle_diameter(bpy.types.Operator):
    """Set precise diameter of selected polygon loop, retaining Blender mesh."""
    bl_idname = "blinter.circle_diameter"
    bl_label = "Dimension Circular Feature"
    bl_options = {'REGISTER', 'UNDO'}

    diameter_mm: FloatProperty(name="Diameter (mm)", default=6.35, min=.001, precision=4)

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.edit_object is not None

    def invoke(self, context, event):
        try:
            _, _, _, _, _, radius = analyze_selection(context)
            self.diameter_mm = radius * 2000
        except ValueError as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        try:
            obj, bm, vertices, center, normal, radius = analyze_selection(context)
            # Do not silently break a stored lock. A more complete solver will
            # eventually update or reject dependent dimensions transactionally.
            locked = bm.verts.layers.int.get("blinter_region_tag")
            if locked and any(v[locked] for v in vertices):
                raise ValueError("Circular feature is locked. Unlock it before changing diameter")
            if obj.matrix_world.determinant() == 0:
                raise ValueError("Object has singular transform; apply scale first")
            target_radius = self.diameter_mm / 2000
            # Project onto the recognized circle plane, then change just radius.
            # Keep vertex angular distribution and neighboring topology.
            inverse = obj.matrix_world.inverted()
            new_positions = []
            for v in vertices:
                world = obj.matrix_world @ v.co
                radial = world - center
                radial -= normal * radial.dot(normal)
                if radial.length <= EPS:
                    raise ValueError("Degenerate vertex on circle center")
                new_positions.append(inverse @ (center + radial.normalized() * target_radius))
            for vertex, position in zip(vertices, new_positions):
                vertex.co = position
            bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=False)
            self.report({'INFO'}, f"Adjusted mesh loop diameter to {self.diameter_mm:.3f} mm")
            return {'FINISHED'}
        except ValueError as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}


classes = (BLINTER_OT_circle_diameter,)
