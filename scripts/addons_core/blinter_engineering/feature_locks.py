"""Feature locks for mesh-native engineering edits.

Lock any selection of vertices, edges, or faces. Selection elements are counted
in the active Blender selection mode: one element defaults to WORLD anchor,
multiple elements default to RELATIVE rigid group even when adjacent/connected.
Users can explicitly override AUTO to WORLD or RELATIVE.
Selected elements resolve to their participating vertices, without needing
to treat high-poly connected regions as independent CAD surfaces.

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


def identity_map(obj, bm, create=False, selected_only=None):
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
        # No need to label every vertex of a million-poly mesh.
        targets = selected_only if selected_only is not None else bm.verts
        for v in targets:
            if v[layer] <= 0:
                v[layer] = next_id
                mapping[next_id] = v
                next_id += 1
        obj.data["blinter_next_vertex_id"] = next_id
    return layer, mapping


def selected_vertices(bm):
    # Blender selection in edit mode includes vertices for selected edges and faces.
    return [v for v in bm.verts if v.select and not v.hide]


def selection_info(bm):
    """Count explicitly selected elements in the active mesh selection domain.

    Faces include all of their verts, edges both endpoints. Count face selection
    as faces, not their incidental selected edges/verts. This supports adjacent
    face selections as one relative feature group and avoids graph traversal.
    """
    mode = bm.select_mode
    if 'FACE' in mode:
        elements = [f for f in bm.faces if f.select and not f.hide]
        if elements:
            return len(elements), list({v for f in elements for v in f.verts}), 'faces'
    if 'EDGE' in mode:
        elements = [e for e in bm.edges if e.select and not e.hide]
        if elements:
            return len(elements), list({v for e in elements for v in e.verts}), 'edges'
    verts = selected_vertices(bm)
    return len(verts), verts, 'vertices'



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

    lock_type: EnumProperty(
        name="Lock Behavior",
        items=[
            ('AUTO', "Automatic", "One selected element anchors to world; multiple selected elements become a relative group"),
            ('ANCHOR', "Fixed to World", "Pin all selected geometry to fixed world coordinates"),
            ('RELATIVE', "Relative", "Keep all selected geometry rigidly related even when touching"),
        ],
        default='AUTO',
    )

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        try:
            obj, bm = current_mesh(context)
            element_count, verts, domain = selection_info(bm)
            if not verts:
                raise ValueError("Select at least one vertex, edge, or face")
            resolved_type = (
                ('ANCHOR' if element_count == 1 else 'RELATIVE')
                if self.lock_type == 'AUTO' else self.lock_type
            )
            layer, _ = identity_map(obj, bm, create=True, selected_only=verts)
            pairs = sorted(((v[layer], list(obj.matrix_world @ v.co)) for v in verts), key=lambda p: p[0])
            ids = [ident for ident, _ in pairs]
            pts = [point for _, point in pairs]
            if len(set(ids)) != len(ids):
                raise ValueError("Selection has duplicated feature vertex IDs")
            lock = obj.data.blinter_feature_locks.add()
            lock.kind = resolved_type
            lock.title = ("World Feature" if resolved_type == 'ANCHOR'
                          else f"Relative Group ({element_count} {domain})")
            lock.ids_json = json.dumps(ids, separators=(',', ':'))
            lock.points_json = json.dumps(pts, separators=(',', ':'))
            lock.enabled = True
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
            self.report({'INFO'}, f"Locked {element_count} {domain}, {len(verts)} vertices ({resolved_type})")
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
        col.label(text="One selected element: world anchor")
        col.label(text="Multiple elements: relative group")
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
