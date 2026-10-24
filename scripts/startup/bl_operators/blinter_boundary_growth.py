# SPDX-License-Identifier: GPL-2.0-or-later
"""Native mesh boundary envelope editing for selected circular features.

First safe topology-preserving case: planar connected annular mesh, one inner
ring selected, one exterior boundary. Move hole, push the exterior boundary to
keep requested radial material clearance. No STL, B-rep, boolean or NURBS export.
This deliberately rejects ambiguous solids, locked borders, or configurations
which cannot preserve an attached manifold without local retopology.
"""
import bpy
import bmesh
from mathutils import Vector
from bpy.props import FloatProperty, FloatVectorProperty, BoolProperty
from .blinter_features import analyze_selection
from .blinter_mesh_integrity import preflight_and_apply

EPS = 1e-10


def _boundary_loops(bm):
    """Read-only boundary topology: one closed sequence per component."""
    boundary = [e for e in bm.edges if e.is_boundary]
    if not boundary:
        raise ValueError("No open surface boundaries; solid remodeling not implemented")
    links = {}
    for edge in boundary:
        a, b = edge.verts
        links.setdefault(a, []).append(b)
        links.setdefault(b, []).append(a)
    if any(len(n) != 2 for n in links.values()):
        raise ValueError("Boundary must consist of closed, non-branching loops")
    remaining = set(links)
    loops = []
    while remaining:
        start = next(iter(remaining))
        seq = [start]
        remaining.remove(start)
        previous = None
        current = start
        while True:
            candidates = [v for v in links[current] if v != previous]
            if not candidates:
                raise ValueError("Broken boundary")
            neighbor = candidates[0]
            if neighbor == start:
                break
            if neighbor not in remaining:
                raise ValueError("Self-touching boundary")
            seq.append(neighbor)
            remaining.remove(neighbor)
            previous, current = current, neighbor
        loops.append(seq)
    return loops


def _point_segment_distance(point, a, b):
    segment = b - a
    length_sq = segment.length_squared
    if length_sq < EPS * EPS:
        return (point - a).length
    t = max(0.0, min(1.0, (point - a).dot(segment) / length_sq))
    return (point - (a + segment * t)).length


def _new_boundary_positions(obj, loop, old_center, new_center, target_radius,
                            clearance, normal, push_straight):
    """Reposition exterior boundary vertices to preserve radial material envelope.

    This is a displacement-based first pass, not a new contour topology engine.
    A rigidly straight side moves as a whole when push_straight is enabled and
    its vertices lie on the same line. Otherwise only nearby vertices move.
    """
    old = [obj.matrix_world @ v.co for v in loop]
    required = target_radius + clearance
    proposals = {}
    # Determine outward shift direction from the original hole to the closest
    # exterior edge, then make sure the moved hole is inside that boundary.
    edges = [(old[i], old[(i+1) % len(old)], i) for i in range(len(old))]
    # Choose the MOST CONSTRAINING side for the target center, not the
    # nearest original side. Moving left must extend left, not right.
    candidates = []
    for a, b, index in edges:
        tangent = b - a
        if tangent.length < EPS:
            raise ValueError("Collapsed outer edge")
        tangent.normalize()
        outward = normal.cross(tangent).normalized()
        if (old_center - a).dot(outward) > 0:
            outward.negate()
        shift = (new_center - a).dot(outward) + required
        candidates.append((shift, index, a, b, tangent, outward))
    shift, index, a, b, tangent, outward = max(candidates, key=lambda item: item[0])
    shift = max(0.0, shift)
    if shift <= EPS:
        return {}
    inv = obj.matrix_world.inverted()
    if push_straight:
        # Move the full collinear border segment, to remain perfectly straight.
        members = [index, (index+1) % len(loop)]
        for k, point in enumerate(old):
            # Other vertices on the very same infinite line belong to the side.
            if abs((point - a).dot(outward)) < 1e-7:
                members.append(k)
        for i in set(members):
            proposals[loop[i]] = inv @ (old[i] + outward * shift)
    else:
        # Local wing deformation. Arc-distance falloff between edge-neighborhood
        # vertices; all selected boundary vertices remain on their own mesh.
        # For a two-vertex side this creates a broad extension, not a wing;
        # explicit contour refinement will be needed for more localized tabs.
        p = (a + b) / 2
        reach = max(required * 2.5, (new_center - old_center).length * 1.5, .001)
        for k, point in enumerate(old):
            side_distance = abs((point - p).dot(tangent))
            t = min(1.0, side_distance / reach)
            smooth = (1.0 - t * t)**2
            if k == index or k == (index+1) % len(loop):
                smooth = 1.0
            if smooth > 1e-8:
                proposals[loop[k]] = inv @ (point + outward * (shift * smooth))
    return proposals


def _boundary_valid(obj, outer, new_center, normal, needed, proposals):
    """Check closed contour encloses center with requested radial rim clearance."""
    positions = [obj.matrix_world @ proposals[v] if v in proposals
                 else obj.matrix_world @ v.co for v in outer]
    axis_u = normal.orthogonal().normalized()
    axis_v = normal.cross(axis_u).normalized()
    flat = [((p-new_center).dot(axis_u), (p-new_center).dot(axis_v)) for p in positions]
    inside = False
    x, y = 0.0, 0.0
    for i in range(len(flat)):
        ax, ay = flat[i]
        bx, by = flat[(i+1) % len(flat)]
        if (ay > y) != (by > y):
            crossing = ax + (y-ay) * (bx-ax) / (by-ay)
            if crossing > x:
                inside = not inside
    if not inside:
        return False
    # Reject perimeter foldovers/self-intersections, including apparently
    # acceptable local clearances that would create a crossed contour.
    def turn(a, b, d):
        return (b[0]-a[0])*(d[1]-a[1]) - (b[1]-a[1])*(d[0]-a[0])
    for i in range(len(flat)):
        a, b = flat[i], flat[(i+1) % len(flat)]
        for j in range(i+1, len(flat)):
            if j == i or (i+1) % len(flat) == j or (j+1) % len(flat) == i:
                continue
            d, e = flat[j], flat[(j+1) % len(flat)]
            if turn(a,b,d)*turn(a,b,e) < -1e-18 and turn(d,e,a)*turn(d,e,b) < -1e-18:
                return False
    gap = min(_point_segment_distance(new_center, positions[i],
                                      positions[(i+1) % len(positions)])
              for i in range(len(positions)))
    return gap >= needed - 1e-7


def _repair_boundary(obj, outer, new_center, normal, needed, proposals, straight):
    """Nudge violating contour segments outward, without replacing topology.

    Repeatedly increase the radius of nearby contour portions until the entire
    circular material envelope fits. Strictly reject if this simple planar
    reconstruction cannot accommodate it without corrupting the mesh.
    """
    inv = obj.matrix_world.inverted()
    for _ in range(12):
        if _boundary_valid(obj, outer, new_center, normal, needed, proposals):
            return proposals
        points = [obj.matrix_world @ proposals[v] if v in proposals
                  else obj.matrix_world @ v.co for v in outer]
        additions = {}
        for i in range(len(outer)):
            a, b = points[i], points[(i+1) % len(points)]
            segment = b - a
            if segment.length_squared < EPS*EPS:
                raise ValueError("Outer boundary contains a collapsed segment")
            t = max(0.0, min(1.0, (new_center-a).dot(segment)/segment.length_squared))
            nearest = a + segment * t
            radial = nearest - new_center
            distance = radial.length
            if distance >= needed - 1e-7:
                continue
            if distance <= EPS:
                raise ValueError("Hole center lies on boundary; rebuild topology first")
            direction = radial / distance
            delta = direction * (needed - distance + 1e-6)
            for vert in (outer[i], outer[(i+1) % len(outer)]):
                # Collect largest outward correction at each vertex per pass.
                old = additions.get(vert)
                if old is None or delta.length > old.length:
                    additions[vert] = delta
        if not additions:
            break
        # A named straight-edge constraint must be enforced by the outer
        # boundary transform. If the repair would break that constraint, the
        # initial straight translation was insufficient and we must reject.
        if straight:
            raise ValueError("Straight-edge clearance requires larger rigid boundary translation")
        for vertex, change in additions.items():
            world = obj.matrix_world @ proposals[vertex] if vertex in proposals else obj.matrix_world @ vertex.co
            proposals[vertex] = inv @ (world + change)
    if not _boundary_valid(obj, outer, new_center, normal, needed, proposals):
        raise ValueError("Cannot preserve material clearance with existing mesh boundary; retopology required")
    return proposals


class BLINTER_OT_grow_boundary_for_feature(bpy.types.Operator):
    """Move circular mesh feature, extend exterior surface to maintain clearance."""
    bl_idname = "blinter.grow_boundary_for_feature"
    bl_label = "Move Feature + Extend Boundary"
    bl_options = {'REGISTER', 'UNDO'}

    offset_mm: FloatVectorProperty(
        name="Feature Move XYZ (mm)", size=3,
        default=(0.0, 7.0, 0.0), precision=3,
        subtype='TRANSLATION',
    )
    clearance_mm: FloatProperty(
        name="Minimum Material Around Feature (mm)",
        default=6.35, min=.01, precision=3,
    )
    keep_edge_straight: BoolProperty(
        name="Keep Extended Edge Straight", default=False,
        description="Move the full existing collinear outer edge instead of only nearby vertices",
    )

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.edit_object is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=390)

    def execute(self, context):
        try:
            obj, bm, ring, center, normal, radius = analyze_selection(context)
            if abs(obj.matrix_world.determinant()) < EPS:
                raise ValueError("Object transform is singular")
            delta = Vector(self.offset_mm) / 1000.0
            if abs(delta.dot(normal)) > 1e-7:
                raise ValueError("This first boundary-growth tool moves within the feature plane")
            if not any(face for face in bm.faces):
                raise ValueError("Feature must be connected to a mesh surface")
            loops = _boundary_loops(bm)
            selected = set(ring)
            matches = [loop for loop in loops if set(loop) == selected]
            if len(matches) != 1 or len(loops) != 2:
                raise ValueError("Supported case: one planar connected hole loop and one outer boundary")
            outer = next(loop for loop in loops if set(loop) != selected)
            # Boundary counts alone cannot prove one part: verify the annular
            # surface actually connects the inner ring to the outer contour.
            reachable = {ring[0]}
            pending = [ring[0]]
            while pending:
                vertex = pending.pop()
                for edge in vertex.link_edges:
                    other = edge.other_vert(vertex)
                    if other not in reachable:
                        reachable.add(other)
                        pending.append(other)
            if not all(v in reachable for v in outer):
                raise ValueError("Outer boundary is a separate island, not connected to this feature")
            if len(outer) < 3:
                raise ValueError("Outer boundary is degenerate")
            # Protect other locked regions. Moving hole+adjacent boundary must not
            # override a world anchor or an existing independent rigid group.
            tag = bm.verts.layers.int.get("blinter_region_tag")
            if tag and any(v[tag] for v in ring + outer):
                raise ValueError("Boundary or hole has a stored lock; unlock before reshaping")
            frame = obj.matrix_world
            tol = 1e-6
            for v in outer:
                if abs(((frame @ v.co) - center).dot(normal)) > tol:
                    raise ValueError("Outer boundary is not coplanar with the hole")
            proposed = {v: frame.inverted() @ (frame @ v.co + delta) for v in ring}
            boundary = _new_boundary_positions(
                obj, outer, center, center + delta, radius,
                self.clearance_mm / 1000.0, normal, self.keep_edge_straight,
            )
            proposed.update(boundary)
            needed = radius + self.clearance_mm / 1000.0
            proposed = _repair_boundary(
                obj, outer, center + delta, normal, needed,
                proposed, self.keep_edge_straight,
            )
            preflight_and_apply(obj, bm, proposed)
            bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=False)
            self.report({'INFO'}, "Adjusted existing boundary and hole mesh together")
            return {'FINISHED'}
        except (ValueError, ZeroDivisionError) as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}


classes = (BLINTER_OT_grow_boundary_for_feature,)
