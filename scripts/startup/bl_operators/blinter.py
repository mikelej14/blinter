"""Blinter built-in mesh engineering core: rigid tagged selection constraints.

Vertices still need to be visited to apply a transform, but there is no saved
per-vertex coordinate list or separate solve per vertex. Boundary/bounds are
computed once at capture. Does not automatically intercept Blender transforms.
"""
import bpy
import bmesh
import json
from mathutils import Vector
from bpy.props import IntProperty, StringProperty, BoolProperty, CollectionProperty, FloatVectorProperty, EnumProperty

TAG = "blinter_region_tag"


class BLINTER_PG_rigid_region(bpy.types.PropertyGroup):
    group_id: IntProperty(default=0)
    count: IntProperty(default=0)
    boundary_edges: IntProperty(default=0)
    bounds_json: StringProperty(default="[]")
    enabled: BoolProperty(default=True)
    name: StringProperty(default='Rigid Feature')
    kind: EnumProperty(items=[('ANCHOR', 'World Fixed', 'Hold world coordinates'), ('RELATIVE', 'Rigid Group', 'Preserve region shape as a movable group')], default='RELATIVE')


def edit_mesh(context):
    obj = context.edit_object
    if obj is None or obj.type != 'MESH':
        raise ValueError("Mesh edit mode required")
    return obj, bmesh.from_edit_mesh(obj.data)


def selection_elements(bm):
    """Return explicitly selected domain elements and participating vertices."""
    if 'FACE' in bm.select_mode:
        faces = [f for f in bm.faces if f.select and not f.hide]
        if faces:
            return len(faces), list({v for f in faces for v in f.verts}), 'faces'
    if 'EDGE' in bm.select_mode:
        edges = [e for e in bm.edges if e.select and not e.hide]
        if edges:
            return len(edges), list({v for e in edges for v in e.verts}), 'edges'
    verts = [v for v in bm.verts if v.select and not v.hide]
    return len(verts), verts, 'vertices'


def selection_vertices(bm):
    return selection_elements(bm)[1]

def region_members(bm):
    layer = bm.verts.layers.int.get(TAG)
    members = {}
    if layer is not None:
        for v in bm.verts:
            tag = v[layer]
            if tag:
                members.setdefault(tag, []).append(v)
    return layer, members


def summary(obj, bm, selected):
    selected_set = set(selected)
    boundary = 0
    for edge in bm.edges:
        a = edge.verts[0] in selected_set
        b = edge.verts[1] in selected_set
        if a != b or (a and b and len(edge.link_faces) < 2):
            boundary += 1
    mins = [float('inf')] * 3
    maxs = [float('-inf')] * 3
    for v in selected:
        p = obj.matrix_world @ v.co
        for i in range(3):
            mins[i] = min(mins[i], p[i])
            maxs[i] = max(maxs[i], p[i])
    return boundary, [mins, maxs]


def validate_regions(obj, bm):
    layer, members = region_members(bm)
    locks = [x for x in obj.data.blinter_rigid_regions if x.enabled]
    for lock in locks:
        if lock.group_id <= 0 or len(members.get(lock.group_id, [])) != lock.count:
            raise ValueError("Rigid group membership changed; unlock and recapture")
    registered = {lock.group_id for lock in obj.data.blinter_rigid_regions}
    if len(registered) != len(obj.data.blinter_rigid_regions):
        raise ValueError("Duplicate rigid group IDs")
    if any(tag not in registered for tag in members):
        raise ValueError("Orphan rigid tags found; clear and rebuild group data")
    return layer, members


class BLINTER_OT_capture_rigid_region(bpy.types.Operator):
    """Any selected vertices, edges or faces become one rigid tagged region."""
    bl_idname = "blinter.capture_rigid_region"
    bl_label = "Lock Selection as Rigid Region"
    bl_options = {'REGISTER', 'UNDO'}
    lock_type: EnumProperty(
        name="Lock",
        items=[('AUTO', 'Automatic', 'One selected element fixes to world; multiple create relative group'),
               ('ANCHOR', 'World Fixed', 'Pin this region to world coordinates'),
               ('RELATIVE', 'Rigid Group', 'Move as a single rigid region')],
        default='AUTO',
    )

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        try:
            obj, bm = edit_mesh(context)
            selected_count, selected, domain = selection_elements(bm)
            kind = (('ANCHOR' if selected_count == 1 else 'RELATIVE')
                    if self.lock_type == 'AUTO' else self.lock_type)
            if not selected:
                raise ValueError("Select mesh vertices, edges or faces")
            layer, groups = validate_regions(obj, bm)
            existing = {v for group in groups.values() for v in group}
            if any(v in existing for v in selected):
                raise ValueError("Selection overlaps an existing rigid region")
            if layer is None:
                layer = bm.verts.layers.int.new(TAG)
            group_id = max(int(obj.data.get("blinter_next_rigid_group", 1)),
                           max(groups, default=0) + 1)
            boundary, bounds = summary(obj, bm, selected)
            for v in selected:
                v[layer] = group_id
            lock = obj.data.blinter_rigid_regions.add()
            lock.group_id = group_id
            lock.name = ("World Anchor" if kind == 'ANCHOR' else "Rigid Region") + f" {group_id}"
            lock.kind = kind
            lock.count = len(selected)
            lock.boundary_edges = boundary
            lock.bounds_json = json.dumps(bounds)
            obj.data["blinter_next_rigid_group"] = group_id + 1
            obj.data.blinter_active_rigid_region = len(obj.data.blinter_rigid_regions) - 1
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
            self.report({'INFO'}, f"{kind}: {selected_count} {domain}, {len(selected)} vertices, {boundary} boundary edges")
            return {'FINISHED'}
        except ValueError as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}


class BLINTER_OT_move_rigid_region(bpy.types.Operator):
    """Single displacement applied to tagged vertices, preserving group shape."""
    bl_idname = "blinter.move_rigid_region"
    bl_label = "Move Rigid Region"
    bl_options = {'REGISTER', 'UNDO'}
    offset_mm: FloatVectorProperty(name="XYZ (mm)", size=3, default=(0, 0, 0), precision=3)
    group_id: IntProperty(name="Group ID", default=0, min=0, description="0 uses first enabled group")

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        try:
            obj, bm = edit_mesh(context)
            layer, groups = validate_regions(obj, bm)
            eligible = [entry for entry in obj.data.blinter_rigid_regions if entry.enabled]
            lock = (next((entry for entry in eligible if entry.group_id == self.group_id), None)
                    if self.group_id else (eligible[0] if eligible else None))
            if lock is None:
                raise ValueError("No enabled rigid group matches the requested ID")
            if lock.kind == 'ANCHOR':
                raise ValueError("World-fixed region cannot move until changed to Relative")
            vertices = groups.get(lock.group_id, [])
            delta = Vector(self.offset_mm) / 1000.0
            local_delta = obj.matrix_world.inverted_safe().to_3x3() @ delta
            for v in vertices:
                v.co += local_delta
            bounds = json.loads(lock.bounds_json)
            lock.bounds_json = json.dumps([[bounds[j][i] + delta[i] for i in range(3)]
                                           for j in range(2)])
            bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=False)
            return {'FINISHED'}
        except ValueError as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}


class BLINTER_OT_scale_outside_regions(bpy.types.Operator):
    """Scale all unlocked mesh vertices, keeping region interiors unchanged."""
    bl_idname = "blinter.scale_outside_regions"
    bl_label = "Resize Outside Rigid Regions"
    bl_options = {'REGISTER', 'UNDO'}
    factor: FloatVectorProperty(name="XYZ Scale", size=3, default=(1, 1, 1), min=0.001)

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        try:
            obj, bm = edit_mesh(context)
            layer, groups = validate_regions(obj, bm)
            active_ids = {x.group_id for x in obj.data.blinter_rigid_regions if x.enabled}
            if not active_ids:
                raise ValueError("Create a rigid region first")
            minimum = [float('inf')] * 3
            maximum = [float('-inf')] * 3
            found = False
            for vert in bm.verts:
                found = True
                p = obj.matrix_world @ vert.co
                for i in range(3):
                    minimum[i] = min(minimum[i], p[i])
                    maximum[i] = max(maximum[i], p[i])
            if not found:
                raise ValueError("Empty mesh")
            pivot = Vector([(minimum[i] + maximum[i]) / 2 for i in range(3)])
            inv = obj.matrix_world.inverted_safe()
            factors = Vector(self.factor)
            for v in bm.verts:
                if layer is not None and v[layer] in active_ids:
                    continue
                world = obj.matrix_world @ v.co
                v.co = inv @ (pivot + Vector([(world[i] - pivot[i]) * factors[i]
                                               for i in range(3)]))
            bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=False)
            return {'FINISHED'}
        except ValueError as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}


class BLINTER_OT_transform_selection(bpy.types.Operator):
    """Numerical mesh transform honoring Blinter groups.

    A relative group touched by selection transforms rigidly. A world anchor
    remains stationary. Unlocked selected vertices receive the requested
    transform directly. This does not replace Blender G/S hotkeys yet.
    """
    bl_idname = "blinter.transform_selection"
    bl_label = "Transform With Locks"
    bl_options = {'REGISTER', 'UNDO'}

    action: EnumProperty(
        name="Transform",
        items=[('MOVE', "Move", "Translate selected mesh vertices"),
               ('SCALE', "Scale", "Scale selection, moving rigid groups without distortion")],
        default='MOVE',
    )
    offset_mm: FloatVectorProperty(name="Move XYZ (mm)", size=3, default=(0, 0, 0), precision=3)
    factor: FloatVectorProperty(name="Scale XYZ", size=3, default=(1, 1, 1), min=0.001, precision=4)

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.edit_object is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=350)

    def execute(self, context):
        try:
            obj, bm = edit_mesh(context)
            selected = set(selection_vertices(bm))
            if not selected:
                raise ValueError("Select vertices, edges, or faces")
            layer, members = validate_regions(obj, bm)
            by_id = {lock.group_id: lock for lock in obj.data.blinter_rigid_regions}
            selected_tags = set()
            if layer is not None:
                selected_tags = {v[layer] for v in selected if v[layer] > 0}
            # World anchors simply stay fixed, even when the user selects
            # everything for a larger resize. No need to deselect anchor faces.
            active_groups = [by_id[tag] for tag in selected_tags
                             if by_id[tag].enabled and by_id[tag].kind == 'RELATIVE']
            active_member_vertices = {v for lock in active_groups
                                      for v in members[lock.group_id]}
            free_vertices = {v for v in selected
                             if layer is None or not v[layer] or
                             not by_id[v[layer]].enabled}
            relevant = active_member_vertices | free_vertices
            if not relevant:
                raise ValueError("Selection contains only world-fixed geometry")
            # Validate before edits: a full relative region must be available
            # and overlapping linked legacy locks cannot be silently satisfied.
            if self.action == 'SCALE':
                origin = sum((obj.matrix_world @ v.co for v in relevant),
                             Vector((0.0, 0.0, 0.0))) / len(relevant)
            else:
                origin = Vector((0.0, 0.0, 0.0))
            scale = Vector(self.factor)
            delta = Vector(self.offset_mm) / 1000.0
            inverse = obj.matrix_world.inverted_safe()
            # Compute the new group translation once from group center.
            group_displacements = {}
            new_bounds = {}
            for lock in active_groups:
                vertices = members[lock.group_id]
                center = sum((obj.matrix_world @ v.co for v in vertices),
                             Vector((0.0, 0.0, 0.0))) / len(vertices)
                if self.action == 'MOVE':
                    movement = delta
                else:
                    target = origin + Vector((center[i] - origin[i]) * scale[i]
                                             for i in range(3))
                    movement = target - center
                group_displacements[lock.group_id] = inverse.to_3x3() @ movement
                bounds = json.loads(lock.bounds_json)
                new_bounds[lock.group_id] = [[bounds[k][i] + movement[i] for i in range(3)]
                                             for k in range(2)]
            for vertex in free_vertices:
                world = obj.matrix_world @ vertex.co
                target = world + delta if self.action == 'MOVE' else (
                    origin + Vector((world[i] - origin[i]) * scale[i] for i in range(3)))
                vertex.co = inverse @ target
            for lock in active_groups:
                movement = group_displacements[lock.group_id]
                for vertex in members[lock.group_id]:
                    vertex.co += movement
                lock.bounds_json = json.dumps(new_bounds[lock.group_id])
            bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=False)
            self.report({'INFO'}, "Blinter transform preserved locked region geometry")
            return {'FINISHED'}
        except (ValueError, KeyError, ZeroDivisionError) as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}


class BLINTER_OT_clear_rigid_regions(bpy.types.Operator):
    bl_idname = "blinter.clear_rigid_regions"
    bl_label = "Unlock Rigid Regions"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        obj, bm = edit_mesh(context)
        layer = bm.verts.layers.int.get(TAG)
        if layer is not None:
            for v in bm.verts:
                v[layer] = 0
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        obj.data.blinter_rigid_regions.clear()
        return {'FINISHED'}

def active_region(obj):
    regions = obj.data.blinter_rigid_regions
    index = obj.data.blinter_active_rigid_region
    if not 0 <= index < len(regions):
        raise ValueError("Choose a locked region in the list")
    return regions[index]


class BLINTER_OT_select_locked_region(bpy.types.Operator):
    """Reselect the named locked region as vertices without splitting the mesh."""
    bl_idname = "blinter.select_locked_region"
    bl_label = "Select Locked Region"
    bl_options = {'REGISTER', 'UNDO'}

    extend: BoolProperty(name="Add to Selection", default=False)

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.edit_object is not None

    def execute(self, context):
        try:
            obj, bm = edit_mesh(context)
            lock = active_region(obj)
            _, members = validate_regions(obj, bm)
            vertices = members.get(lock.group_id, [])
            if len(vertices) != lock.count:
                raise ValueError("Stored region member count is invalid")
            # Vertex mode avoids inadvertently selecting adjacent faces outside
            # the saved region. This operation intentionally changes select mode.
            context.tool_settings.mesh_select_mode = (True, False, False)
            bm.select_mode = {'VERT'}
            if not self.extend:
                for v in bm.verts:
                    v.select_set(False)
            for v in vertices:
                v.select_set(True)
            bm.select_flush_mode()
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
            return {'FINISHED'}
        except ValueError as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}


class BLINTER_OT_remove_selected_region(bpy.types.Operator):
    """Unlock one named region without deleting any mesh geometry."""
    bl_idname = "blinter.remove_selected_region"
    bl_label = "Unlock Listed Region"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.edit_object is not None

    def execute(self, context):
        try:
            obj, bm = edit_mesh(context)
            lock = active_region(obj)
            layer, groups = validate_regions(obj, bm)
            if layer is None:
                raise ValueError("Missing region membership layer")
            for v in groups.get(lock.group_id, []):
                v[layer] = 0
            index = obj.data.blinter_active_rigid_region
            obj.data.blinter_rigid_regions.remove(index)
            obj.data.blinter_active_rigid_region = min(
                index, len(obj.data.blinter_rigid_regions) - 1
            )
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
            return {'FINISHED'}
        except ValueError as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}


class BLINTER_OT_toggle_selection_lock(bpy.types.Operator):
    """One-click context lock/unlock for arbitrary mesh selections."""
    bl_idname = "blinter.toggle_selection_lock"
    bl_label = "Lock / Unlock Selection"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.edit_object is not None

    def execute(self, context):
        try:
            obj, bm = edit_mesh(context)
            selected = set(selection_vertices(bm))
            if not selected:
                raise ValueError("Select vertices, edges, or faces first")
            layer, groups = validate_regions(obj, bm)
            hits = [lock for lock in obj.data.blinter_rigid_regions
                    if any(v in selected for v in groups.get(lock.group_id, []))]
            if hits:
                if len(hits) != 1 or selected != set(groups[hits[0].group_id]):
                    raise ValueError(
                        "Selection overlaps a lock. Select the complete named region "
                        "to unlock it, or use the region list"
                    )
                lock = hits[0]
                for v in groups[lock.group_id]:
                    v[layer] = 0
                index = next(i for i, item in enumerate(obj.data.blinter_rigid_regions)
                             if item.group_id == lock.group_id)
                obj.data.blinter_rigid_regions.remove(index)
                obj.data.blinter_active_rigid_region = min(
                    index, len(obj.data.blinter_rigid_regions) - 1
                )
                bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
                self.report({'INFO'}, f"Unlocked region {lock.name}")
                return {'FINISHED'}
            # Reuse the same capture backend as the right sidebar.
            return bpy.ops.blinter.capture_rigid_region('EXEC_DEFAULT', lock_type='AUTO')
        except ValueError as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}



# Built-in Blinter operators register along with Blender's bl_operators modules.
# The panel and context-menu UI live under bl_ui.blinter instead.
classes = (
    BLINTER_PG_rigid_region,
    BLINTER_OT_capture_rigid_region,
    BLINTER_OT_move_rigid_region,
    BLINTER_OT_scale_outside_regions,
    BLINTER_OT_clear_rigid_regions,
    BLINTER_OT_select_locked_region,
    BLINTER_OT_remove_selected_region,
    BLINTER_OT_toggle_selection_lock,
    BLINTER_OT_transform_selection,
)


def register():
    bpy.types.Mesh.blinter_rigid_regions = CollectionProperty(type=BLINTER_PG_rigid_region)
    bpy.types.Mesh.blinter_active_rigid_region = IntProperty(default=-1)
    bpy.types.Scene.blinter_focus_ui = BoolProperty(name="Focused Design UI", description="Simplified engineering top bar, preserves all Blender functionality", default=True)


def unregister():
    del bpy.types.Scene.blinter_focus_ui
    del bpy.types.Mesh.blinter_active_rigid_region
    del bpy.types.Mesh.blinter_rigid_regions
