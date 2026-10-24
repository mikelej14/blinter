"""Compact rigid mesh regions: one group tag per member, one reference frame.

Vertices still need to be visited to apply a transform, but there is no saved
per-vertex coordinate list or separate solve per vertex. Boundary/bounds are
computed once at capture. Does not automatically intercept Blender transforms.
"""
import bpy
import bmesh
import json
from mathutils import Vector
from bpy.props import IntProperty, StringProperty, BoolProperty, CollectionProperty, FloatVectorProperty

TAG = "blinter_region_tag"


class BLINTER_PG_rigid_region(bpy.types.PropertyGroup):
    group_id: IntProperty(default=0)
    count: IntProperty(default=0)
    boundary_edges: IntProperty(default=0)
    bounds_json: StringProperty(default="[]")
    enabled: BoolProperty(default=True)


def edit_mesh(context):
    obj = context.edit_object
    if obj is None or obj.type != 'MESH':
        raise ValueError("Mesh edit mode required")
    return obj, bmesh.from_edit_mesh(obj.data)


def selection_vertices(bm):
    if 'FACE' in bm.select_mode:
        faces = [f for f in bm.faces if f.select and not f.hide]
        if faces:
            return list({v for f in faces for v in f.verts})
    if 'EDGE' in bm.select_mode:
        edges = [e for e in bm.edges if e.select and not e.hide]
        if edges:
            return list({v for e in edges for v in e.verts})
    return [v for v in bm.verts if v.select and not v.hide]


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
    if any(tag not in registered for tag in members):
        raise ValueError("Orphan rigid tags found; clear and rebuild group data")
    return layer, members


class BLINTER_OT_capture_rigid_region(bpy.types.Operator):
    """Any selected vertices, edges or faces become one rigid tagged region."""
    bl_idname = "blinter.capture_rigid_region"
    bl_label = "Lock Selection as Rigid Region"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        try:
            obj, bm = edit_mesh(context)
            selected = selection_vertices(bm)
            if not selected:
                raise ValueError("Select mesh vertices, edges or faces")
            layer, groups = validate_regions(obj, bm)
            if any(v in selected for group in groups.values() for v in group):
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
            lock.count = len(selected)
            lock.boundary_edges = boundary
            lock.bounds_json = json.dumps(bounds)
            obj.data["blinter_next_rigid_group"] = group_id + 1
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
            self.report({'INFO'}, f"One rigid region: {len(selected)} vertices, {boundary} boundary edges")
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

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        try:
            obj, bm = edit_mesh(context)
            layer, groups = validate_regions(obj, bm)
            if len(obj.data.blinter_rigid_regions) != 1:
                raise ValueError("Exactly one rigid region required for this prototype")
            lock = obj.data.blinter_rigid_regions[0]
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
            if not any(x.enabled for x in obj.data.blinter_rigid_regions):
                raise ValueError("Create a rigid region first")
            positions = [obj.matrix_world @ v.co for v in bm.verts]
            if not positions:
                raise ValueError("Empty mesh")
            pivot = Vector([(min(p[i] for p in positions) + max(p[i] for p in positions)) / 2
                            for i in range(3)])
            inv = obj.matrix_world.inverted_safe()
            factors = Vector(self.factor)
            for v in bm.verts:
                if layer is not None and v[layer]:
                    continue
                world = obj.matrix_world @ v.co
                v.co = inv @ (pivot + Vector([(world[i] - pivot[i]) * factors[i]
                                               for i in range(3)]))
            bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=False)
            return {'FINISHED'}
        except ValueError as error:
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


class BLINTER_PT_rigid_regions(bpy.types.Panel):
    bl_label = "Compact Rigid Regions"
    bl_idname = "BLINTER_PT_rigid_regions"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Blinter'

    def draw(self, context):
        col = self.layout.column(align=True)
        col.operator("blinter.capture_rigid_region", icon='DECORATE_LOCKED')
        col.operator("blinter.move_rigid_region", icon='TRANSFORM_MOVE')
        col.operator("blinter.scale_outside_regions", icon='TRANSFORM_SCALE')
        col.operator("blinter.clear_rigid_regions", icon='UNLOCKED')
        if context.edit_object and context.edit_object.type == 'MESH':
            col.label(text=f"Regions: {len(context.edit_object.data.blinter_rigid_regions)}")
        col.label(text="One transform for all tagged vertices")


classes = (BLINTER_PG_rigid_region, BLINTER_OT_capture_rigid_region,
           BLINTER_OT_move_rigid_region, BLINTER_OT_scale_outside_regions,
           BLINTER_OT_clear_rigid_regions, BLINTER_PT_rigid_regions)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Mesh.blinter_rigid_regions = CollectionProperty(type=BLINTER_PG_rigid_region)


def unregister():
    del bpy.types.Mesh.blinter_rigid_regions
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
