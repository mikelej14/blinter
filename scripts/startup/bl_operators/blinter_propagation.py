# SPDX-License-Identifier: GPL-2.0-or-later
"""Selection-agnostic Blinter mesh deformation, with locked-feature awareness.

Move any selected vertices/edges/faces as a feature, adjusting nearby existing
mesh vertices with a smooth spatial displacement field. Does not remesh, convert
the object, add seams, or create detached geometry. This is an initial LOCAL
deformation tool, not a global CAD solver or general topology reconstruction.
"""
import bpy
import bmesh
from mathutils import Vector
from mathutils.kdtree import KDTree
from bpy.props import FloatVectorProperty, FloatProperty
from .blinter import selection_vertices, validate_regions
from .blinter_mesh_integrity import preflight_and_apply

EPS = 1e-10


def propose_adaptive_move(obj, bm, selection, displacement, reach, group_layer, groups,
                          locks):
    """Make one consistent displacement per moved vertex; do not edit mesh here."""
    frame = obj.matrix_world
    inv = frame.inverted()
    selected = set(selection)
    active_ids = {lock.group_id for lock in locks if lock.enabled}
    # A selected piece of a relative lock moves all of that rigid region.
    selected_groups = {v[group_layer] for v in selected
                       if group_layer and v[group_layer] in active_ids}
    for group_id in selected_groups:
        lock = next(item for item in locks if item.group_id == group_id)
        if lock.kind == 'ANCHOR':
            # Like constrained whole-part scaling, anchored regions stay put.
            selected.difference_update(groups[group_id])
        else:
            selected.update(groups[group_id])
    selected_groups = {gid for gid in selected_groups
                       if next(item for item in locks if item.group_id == gid).kind == 'RELATIVE'}
    # The influence field is based on BEFORE positions, including expanded
    # rigid groups, so it does not tear one group from its neighbours.
    positions = {v: frame @ v.co for v in bm.verts}
    feature_positions = [positions[v] for v in selected]
    if not feature_positions:
        raise ValueError("Only world-fixed geometry selected; nothing can move")
    center = sum(feature_positions, Vector((0, 0, 0))) / len(feature_positions)
    extent = max((p - center).length for p in feature_positions)
    kernel = max(reach, displacement.length * 2.0, extent * .1, EPS)
    tree = KDTree(len(feature_positions))
    for index, point in enumerate(feature_positions):
        tree.insert(point, index)
    tree.balance()

    proposals = {}
    for v in bm.verts:
        tag = v[group_layer] if group_layer else 0
        if v in selected:
            amount = 1.0
        elif tag in active_ids:
            # Other saved locks remain immovable; a conflicting edit is
            # rejected downstream rather than silently violating the lock.
            continue
        else:
            # Spatial index makes this practical on high-poly mesh selections.
            _, _, dist = tree.find(positions[v])
            if dist >= kernel:
                continue
            t = dist / kernel
            amount = (1.0 - t * t) ** 2  # C1 smooth at falloff boundary
        if amount > 0.0:
            proposals[v] = inv @ (positions[v] + displacement * amount)
    return proposals, selected_groups


class BLINTER_OT_adapt_feature_move(bpy.types.Operator):
    """Move selected mesh features and gently propagate changes to neighbours."""
    bl_idname = "blinter.adapt_feature_move"
    bl_label = "Move Feature - Adapt Mesh"
    bl_options = {'REGISTER', 'UNDO'}

    offset_mm: FloatVectorProperty(
        name="XYZ Move (mm)", size=3, default=(2.0, 0.0, 0.0),
        precision=3, subtype='TRANSLATION',
    )
    influence_mm: FloatProperty(
        name="Adaptation Reach (mm)", default=10.0, min=0.001,
        description="Neighbourhood which shifts with the feature; distant geometry stays unchanged",
    )
    expand_reach: bpy.props.BoolProperty(
        name="Expand If Needed", default=True,
        description="Retry with a broader deformation region if the first local edit collapses faces",
    )

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.edit_object is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=370)

    def execute(self, context):
        try:
            obj = context.edit_object
            if obj.matrix_world.determinant() == 0:
                raise ValueError("Object transform is singular")
            bm = bmesh.from_edit_mesh(obj.data)
            selected = selection_vertices(bm)
            if not selected:
                raise ValueError("Select vertices, edges, or faces")
            layer, members = validate_regions(obj, bm)
            locks = list(obj.data.blinter_rigid_regions)
            delta = Vector(self.offset_mm) / 1000.0
            if delta.length < EPS:
                return {'FINISHED'}
            reach = self.influence_mm / 1000.0
            moved_ids = set()
            last_error = None
            used_reach = reach
            for multiplier in ((1, 2, 4) if self.expand_reach else (1,)):
                used_reach = reach * multiplier
                proposals, moved_ids = propose_adaptive_move(
                    obj, bm, selected, delta, used_reach, layer, members, locks,
                )
                try:
                    preflight_and_apply(obj, bm, proposals)
                    last_error = None
                    break
                except ValueError as exc:
                    # Validator restores all positions transactionally.
                    last_error = exc
            if last_error is not None:
                raise ValueError(f"Unable to safely adapt surrounding mesh: {last_error}")
            # Update persistent group bounds only after the edit succeeds.
            for lock in locks:
                if lock.group_id in moved_ids:
                    import json
                    bounds = json.loads(lock.bounds_json)
                    if len(bounds) == 2:
                        lock.bounds_json = json.dumps(
                            [[bounds[j][i] + delta[i] for i in range(3)] for j in range(2)]
                        )
            bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=False)
            self.report({'INFO'}, f"Moved feature; mesh adaptation reach {used_reach * 1000:.2f} mm")
            return {'FINISHED'}
        except ValueError as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}


classes = (BLINTER_OT_adapt_feature_move,)
