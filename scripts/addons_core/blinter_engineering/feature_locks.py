"""Feature locks for mesh-native engineering edits.

Select one vertex/edge/face feature to pin its selected vertices in WORLD coordinates.
Select two or more disjoint features and their vertices form one rigid relationship.
All selected vertices are stored as one protected group, retaining their offsets.

Blinter Scale Unlocked uses native vertex positions, scaling only unprotected verts.
No automatic interception of vanilla Blender transforms or adaptive surface rebuilding.
Persistent IDs use a custom BMesh vertex int layer so index reordering is tolerated.
Topology deletion and duplicate IDs are reported, never silently reassigned.
"""
import json
import bpy
import bmesh
from mathutils import Vector
from bpy.props import EnumProperty, FloatVectorProperty, FloatProperty, IntProperty, StringProperty, BoolProperty, CollectionProperty

LAYER = "blinter_vertex_identity"
TOL = 1e-7


class BLINTER_PG_feature_lock(bpy.types.PropertyGroup):
    title: StringProperty(default="Locked Feature")
    ids_json: StringProperty(default="[]")
    points_json: StringProperty(default="[]")
    # ANCHOR for one connected selected component; RELATIVE for 2+.
    kind: EnumProperty(items=[
        ('ANCHOR', "World Grid", "Keep feature at its world-space coordinates"),
        ('RELATIVE', "Relative Group", "Preserve dimensions/position among selected features"),
    ], default='ANCHOR')
    enabled: BoolProperty(default=True)


def current_mesh(context):
    obj = context.edit_object
    if not obj or obj.type != 'MESH':
        raise ValueError("Mesh Edit Mode required")
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    return obj, bm


def identity_map(obj, bm, create=False):
    layer = bm.verts.layers.int.get(LAYER)
    if layer is None:
        if not create:
            return None, {}
        layer = bm.verts.layers.int.new(LAYER)
    mapping = {}
    duplicates = set()
    for v in bm.verts:
        ident = v[layer]
        if ident <= 0:
            continue
        if ident in mapping:
            duplicates.add(ident)
        else:
            mapping[ident] = v
    if duplicates:
        raise ValueError("Duplicated locked vertex IDs; repair/relock before editing")
    if create:
        next_id = max(int(obj.data.get("blinter_next_vertex_id", 1)), max(mapping, default=0) + 1)
        for v in bm.verts:
            if v[layer] <= 0:
                v[layer] = next_id
                mapping[next_id] = v
                next_id += 1
        obj.data["blinter_next_vertex_id"] = next_id
    return layer, mapping


def selected_vertices(bm):
    # Blender selection in edit mode includes vertices for selected edges and faces.
    return [v for v in bm.verts if v.select and not v.hide]


def components(vertices):
    selected = set(vertices)
    seen = set()
    result = []
    for v in vertices:
        if v in seen:
            continue
        group = set()
        queue = [v]
        seen.add(v)
        while queue:
            p = queue.pop()
            group.add(p)
            for e in p.link_edges:
                neighbor = e.other_vert(p)
                if neighbor in selected and neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        result.append(group)
    return result


def load_group(lock):
    ids = json.loads(lock.ids_json)
    points = json.loads(lock.points_json)
    if not ids or len(ids) != len(points) or len(set(ids)) != len(ids):
        raise ValueError("Corrupt lock data")
    return ids, [Vector(p) for p in points]


def resolve_all(obj, bm):
    """Validate every active lock before modifying geometry."""
    _, mapping = identity_map(obj, bm)
    protected = {}
    groups = []
    for lock in obj.data.blinter_feature_locks:
        if not lock.enabled:
            continue
        ids, points = load_group(lock)
        vertices = []
        for ident, position in zip(ids, points):
            v = mapping.get(ident)
            if v is None:
                raise ValueError(f"Lock '{lock.title}' lost vertex ID {ident}; recapture it")
            # A vertex may belong to more than one feature only if the positions agree.
            if ident in protected and (protected[ident] - position).length > TOL:
                raise ValueError("Conflicting locks refer to the same vertex")
            protected[ident] = position
            vertices.append(v)
        groups.append((lock, vertices, points))
    return protected, mapping, groups


class BLINTER_OT_lock_features(bpy.types.Operator):
    """One connected selection pins to world; disconnected selections lock together."""
    bl_idname = "blinter.lock_features"
    bl_label = "Lock Selected Features"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        try:
            obj, bm = current_mesh(context)
            verts = selected_vertices(bm)
            if not verts:
                raise ValueError("Select at least one vertex, edge, or face")
            parts = components(verts)
            layer, mapping = identity_map(obj, bm, create=True)
            ids = sorted(v[layer] for v in verts)
            pts = {v[layer]: list(obj.matrix_world @ v.co) for v in verts}
            lock = obj.data.blinter_feature_locks.add()
            lock.kind = 'ANCHOR' if len(parts) == 1 else 'RELATIVE'
            lock.title = "World Feature" if len(parts) == 1 else f"Relative Pattern ({len(parts)} features)"
            lock.ids_json = json.dumps(ids)
            lock.points_json = json.dumps([pts[i] for i in ids])
            lock.enabled = True
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
            self.report({'INFO'}, f"Locked {len(verts)} vertices in {len(parts)} feature(s)")
            return {'FINISHED'}
        except ValueError as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}


class BLINTER_OT_scale_unlocked(bpy.types.Operator):
    """Scale unprotected vertices only. Feature coordinates remain identical."""
    bl_idname = "blinter.scale_unlocked"
    bl_label = "Resize Around Locked Features"
    bl_options = {'REGISTER', 'UNDO'}

    factor_x: FloatProperty(name="X Scale", default=1.0, min=0.001, max=1000)
    factor_y: FloatProperty(name="Y Scale", default=1.0, min=0.001, max=1000)
    factor_z: FloatProperty(name="Z Scale", default=1.0, min=0.001, max=1000)

    pivot: EnumProperty(items=[
        ('BOUNDS', "Bounds Center", "World bounding box center of mesh vertices"),
        ('ORIGIN', "Object Origin", "Object origin in world space"),
        ('CURSOR', "3D Cursor", "Use 3D cursor"),
    ], default='BOUNDS')

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        try:
            obj, bm = current_mesh(context)
            protected, mapping, groups = resolve_all(obj, bm)
            if not protected:
                raise ValueError("Lock a feature before using this constrained resize")
            points = [obj.matrix_world @ v.co for v in bm.verts]
            if not points:
                raise ValueError("Mesh is empty")
            if self.pivot == 'ORIGIN':
                pivot = obj.matrix_world.translation.copy()
            elif self.pivot == 'CURSOR':
                pivot = context.scene.cursor.location.copy()
            else:
                pivot = Vector(tuple((min(p[i] for p in points) + max(p[i] for p in points)) / 2 for i in range(3)))
            factors = Vector((self.factor_x, self.factor_y, self.factor_z))
            matrix_inv = obj.matrix_world.inverted_safe()
            layer = bm.verts.layers.int.get(LAYER)
            if layer is None:
                raise ValueError("Lock identity layer missing")
            modified = 0
            for v in bm.verts:
                if v[layer] in protected:
                    continue
                world = obj.matrix_world @ v.co
                next_world = pivot + Vector(tuple((world[i] - pivot[i]) * factors[i] for i in range(3)))
                v.co = matrix_inv @ next_world
                modified += 1
            # Locked vertices have not moved. Verify the saved world positions.
            for lock, vertices, originals in groups:
                for v, pos in zip(vertices, originals):
                    if ((obj.matrix_world @ v.co) - pos).length > TOL:
                        raise ValueError("Protected geometry moved unexpectedly")
            bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=False)
            self.report({'INFO'}, f"Resized {modified} free vertices; locked features unchanged")
            return {'FINISHED'}
        except ValueError as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}


class BLINTER_OT_move_relative_group(bpy.types.Operator):
    """Move a relative feature group as one rigid vertex set; anchors stay fixed."""
    bl_idname = "blinter.move_relative_group"
    bl_label = "Move Relative Group"
    bl_options = {'REGISTER', 'UNDO'}

    offset_mm: FloatVectorProperty(
        name="Move XYZ (mm)", size=3, default=(0.0, 0.0, 0.0), precision=3,
        subtype='TRANSLATION',
    )

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        try:
            obj, bm = current_mesh(context)
            _, _, groups = resolve_all(obj, bm)
            movable = [(lock, verts, points) for lock, verts, points in groups
                       if lock.kind == 'RELATIVE']
            if len(movable) != 1:
                raise ValueError("Select exactly one active relative group in this prototype")
            lock, vertices, positions = movable[0]
            # Do not move geometry included in an anchored group.
            others = {v for other, verts, _ in groups if other != lock for v in verts}
            if others.intersection(vertices):
                raise ValueError("Relative group overlaps another lock")
            delta = Vector(self.offset_mm) / 1000.0
            inv = obj.matrix_world.inverted_safe()
            new_positions = [point + delta for point in positions]
            for vertex, position in zip(vertices, new_positions):
                vertex.co = inv @ position
            lock.points_json = json.dumps([list(p) for p in new_positions])
            bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=False)
            return {'FINISHED'}
        except ValueError as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}


class BLINTER_OT_remove_feature_locks(bpy.types.Operator):
    bl_idname = "blinter.remove_feature_locks"
    bl_label = "Unlock All Features"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        context.edit_object.data.blinter_feature_locks.clear()
        return {'FINISHED'}


class BLINTER_PT_feature_locks(bpy.types.Panel):
    bl_label = "Feature Locks"
    bl_idname = "BLINTER_PT_feature_locks"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Blinter'

    def draw(self, context):
        col = self.layout.column(align=True)
        col.label(text="1 feature: World Grid anchor")
        col.label(text="Multiple: Relative group")
        col.operator("blinter.lock_features", icon='DECORATE_LOCKED')
        col.operator("blinter.scale_unlocked", icon='TRANSFORM_SCALE')
        col.operator("blinter.move_relative_group", icon='TRANSFORM_MOVE')
        col.operator("blinter.remove_feature_locks", icon='UNLOCKED')
        obj = context.edit_object
        if obj and obj.type == 'MESH':
            col.label(text=f"Lock groups: {len(obj.data.blinter_feature_locks)}")
        col.label(text="Protected vertices do not scale", icon='INFO')


classes = (
    BLINTER_PG_feature_lock,
    BLINTER_OT_lock_features,
    BLINTER_OT_scale_unlocked,
    BLINTER_OT_move_relative_group,
    BLINTER_OT_remove_feature_locks,
    BLINTER_PT_feature_locks,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Mesh.blinter_feature_locks = CollectionProperty(type=BLINTER_PG_feature_lock)


def unregister():
    del bpy.types.Mesh.blinter_feature_locks
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
