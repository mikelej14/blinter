"""Prototype mesh edge-length constraints.

Locks are stored on the mesh datablock (saved in .blend). Apply/restore is explicit
until there is a validated topology-aware transformation pipeline.
"""
import bpy
import bmesh
from bpy.props import FloatProperty, IntProperty, CollectionProperty

TOL = 1e-8


class BLINTER_PG_edge_lock(bpy.types.PropertyGroup):
    vertex_a: IntProperty()
    vertex_b: IntProperty()
    edge_count: IntProperty()
    vertex_count: IntProperty()
    length_mm: FloatProperty(precision=4)


def find_edge(bm, lock):
    bm.verts.ensure_lookup_table()
    bm.verts.index_update()
    bm.edges.index_update()
    if len(bm.verts) != lock.vertex_count or len(bm.edges) != lock.edge_count:
        return None
    for e in bm.edges:
        pair = {e.verts[0].index, e.verts[1].index}
        if pair == {lock.vertex_a, lock.vertex_b}:
            return e
    return None


class BLINTER_OT_lock_selected_edge(bpy.types.Operator):
    """Store selected edge length, or refresh an existing lock."""
    bl_idname = "blinter.lock_selected_edge"
    bl_label = "Lock Selected Edge Length"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.edit_object is not None

    def execute(self, context):
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.index_update()
        edges = [e for e in bm.edges if e.select and not e.hide]
        if len(edges) != 1:
            self.report({'WARNING'}, "Select exactly one edge to lock")
            return {'CANCELLED'}
        edge = edges[0]
        a, b = (v.index for v in edge.verts)
        pair = {a, b}
        locks = obj.data.blinter_edge_locks
        lock = next((entry for entry in locks if {entry.vertex_a, entry.vertex_b} == pair), None)
        if lock is None:
            lock = locks.add()
        lock.vertex_a, lock.vertex_b = a, b
        lock.vertex_count = len(bm.verts)
        lock.edge_count = len(bm.edges)
        p, q = (obj.matrix_world @ v.co for v in edge.verts)
        lock.length_mm = (p - q).length * 1000.0
        return {'FINISHED'}


class BLINTER_OT_restore_edge_locks(bpy.types.Operator):
    """Restore lock lengths manually; topology changes invalidate the lock."""
    bl_idname = "blinter.restore_edge_locks"
    bl_label = "Restore Edge Length Locks"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.edit_object is not None

    def execute(self, context):
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        inv = obj.matrix_world.inverted_safe()
        resolved = []
        for lock in obj.data.blinter_edge_locks:
            edge = find_edge(bm, lock)
            if edge is None:
                self.report({'WARNING'}, "Mesh topology changed; lock restoration cancelled")
                return {'CANCELLED'}
            resolved.append((edge, lock.length_mm))
        if not resolved:
            self.report({'INFO'}, "No stored locks")
            return {'CANCELLED'}
        # Precheck degenerate edges before mutating any geometry.
        for edge, _ in resolved:
            a, b = (obj.matrix_world @ v.co for v in edge.verts)
            if (b - a).length < TOL:
                self.report({'WARNING'}, "Zero-length edge; lock restoration cancelled")
                return {'CANCELLED'}
        for edge, length in resolved:
            v0, v1 = edge.verts
            a, b = (obj.matrix_world @ v.co for v in edge.verts)
            mid = (a + b) * 0.5
            half = (b - a).normalized() * (length / 2000.0)
            v0.co = inv @ (mid - half)
            v1.co = inv @ (mid + half)
        bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=False)
        self.report({'INFO'}, f"Restored {len(resolved)} edge length lock(s)")
        return {'FINISHED'}


class BLINTER_OT_clear_edge_locks(bpy.types.Operator):
    bl_idname = "blinter.clear_edge_locks"
    bl_label = "Clear Edge Length Locks"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.edit_object is not None

    def execute(self, context):
        context.edit_object.data.blinter_edge_locks.clear()
        return {'FINISHED'}


class BLINTER_PT_edge_locks(bpy.types.Panel):
    bl_label = "Edge Length Locks"
    bl_idname = "BLINTER_PT_edge_locks"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Blinter'

    def draw(self, context):
        col = self.layout.column(align=True)
        col.label(text="Manual restore (prototype)", icon='INFO')
        col.operator("blinter.lock_selected_edge", icon='DECORATE_LOCKED')
        col.operator("blinter.restore_edge_locks", icon='FILE_REFRESH')
        col.operator("blinter.clear_edge_locks", icon='X')
        if context.edit_object and context.edit_object.type == 'MESH':
            col.label(text=f"Stored: {len(context.edit_object.data.blinter_edge_locks)}")


classes = (
    BLINTER_PG_edge_lock,
    BLINTER_OT_lock_selected_edge,
    BLINTER_OT_restore_edge_locks,
    BLINTER_OT_clear_edge_locks,
    BLINTER_PT_edge_locks,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Mesh.blinter_edge_locks = CollectionProperty(type=BLINTER_PG_edge_lock)


def unregister():
    del bpy.types.Mesh.blinter_edge_locks
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
