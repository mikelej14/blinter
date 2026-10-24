"""Selection-aware tools; all geometry operators delegate to Blender."""

import bpy
import bmesh
from bpy.props import BoolProperty


def mesh_selection(context):
    obj = context.edit_object
    if not obj or obj.type != 'MESH':
        return (0, 0, 0)
    bm = bmesh.from_edit_mesh(obj.data)
    return (
        sum(v.select and not v.hide for v in bm.verts),
        sum(e.select and not e.hide for e in bm.edges),
        sum(f.select and not f.hide for f in bm.faces),
    )


class BLINTER_MT_quick_actions(bpy.types.Menu):
    bl_label = "Blinter Quick Actions"
    bl_idname = "BLINTER_MT_quick_actions"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        if not obj:
            layout.label(text="Select an object", icon='INFO')
            return
        if context.mode == 'EDIT_MESH':
            vertices, edges, faces = mesh_selection(context)
            if faces:
                layout.label(text="Faces", icon='FACESEL')
                layout.operator("mesh.extrude_region_move", text="Extrude", icon='MOD_SOLIDIFY')
                layout.operator("mesh.inset", text="Inset", icon='SELECT_EXTEND')
                layout.operator("mesh.bevel", text="Bevel", icon='MOD_BEVEL')
                layout.operator("transform.shrink_fatten", text="Offset Faces")
                layout.operator("mesh.flip_normals", text="Flip Normals")
            if edges:
                layout.separator()
                layout.label(text="Edges", icon='EDGESEL')
                layout.operator("blinter.set_edge_length", text="Dimension Edge", icon='DRIVER_DISTANCE')
                layout.operator("mesh.bevel", text="Bevel Edges", icon='MOD_BEVEL')
                layout.operator("mesh.subdivide", text="Subdivide")
                layout.operator("mesh.bridge_edge_loops", text="Bridge Edge Loops")
                layout.operator("mesh.loop_multi_select", text="Select Loop")
            if vertices and not faces and not edges:
                layout.separator()
                layout.label(text="Vertices", icon='VERTEXSEL')
                layout.operator("transform.translate", text="Move")
                layout.operator("mesh.merge", text="Merge")
                layout.operator("mesh.vertices_smooth", text="Smooth")
            if vertices or edges or faces:
                layout.separator()
                layout.operator("transform.translate", text="Move", icon='TRANSFORM_MOVE')
                layout.operator("transform.rotate", text="Rotate", icon='TRANSFORM_ROTATE')
                layout.operator("transform.resize", text="Scale", icon='TRANSFORM_SCALE')
            else:
                layout.label(text="Select mesh geometry", icon='INFO')
        elif context.mode == 'OBJECT':
            layout.label(text="Object", icon='OBJECT_DATA')
            layout.operator("object.transform_apply", text="Apply Transforms")
            layout.operator("object.modifier_add", text="Add Modifier")
            layout.operator("object.convert", text="Convert")
            if obj.type == 'MESH':
                layout.operator("blinter.add_hole_cutter", text="Add Hole Cutter", icon='MOD_BOOLEAN')
        else:
            layout.label(text="Quick actions available in Object or Mesh Edit mode")


class BLINTER_OT_quick_actions(bpy.types.Operator):
    """Open context-aware mesh actions near the cursor."""
    bl_idname = "blinter.quick_actions"
    bl_label = "Blinter Quick Actions"

    def execute(self, context):
        bpy.ops.wm.call_menu(name="BLINTER_MT_quick_actions")
        return {'FINISHED'}


class BLINTER_OT_add_hole_cutter(bpy.types.Operator):
    """Create an editable Boolean hole cutter at the 3D cursor (not applied)."""
    bl_idname = "blinter.add_hole_cutter"
    bl_label = "Add Hole Cutter"
    bl_options = {'REGISTER', 'UNDO'}

    diameter_mm: bpy.props.FloatProperty(name="Diameter (mm)", default=6.0, min=0.01, precision=3)
    depth_mm: bpy.props.FloatProperty(name="Cutter Depth (mm)", default=30.0, min=0.01, precision=3)
    segments: bpy.props.IntProperty(name="Segments", default=64, min=12, max=256)

    @classmethod
    def poll(cls, context):
        return (context.mode == 'OBJECT' and context.active_object is not None
                and context.active_object.type == 'MESH')

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        target = context.active_object
        if target is None or target.type != 'MESH':
            return {'CANCELLED'}
        pos = context.scene.cursor.location.copy()
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=self.segments,
            radius=self.diameter_mm / 2000.0,
            depth=self.depth_mm / 1000.0,
            location=pos,
        )
        cutter = context.active_object
        cutter.name = "Blinter Hole Cutter"
        cutter.display_type = 'WIRE'
        cutter.hide_render = True
        modifier = target.modifiers.new(name="Blinter Hole", type='BOOLEAN')
        modifier.operation = 'DIFFERENCE'
        modifier.solver = 'EXACT'
        modifier.object = cutter
        # Keep cutter editable; selected target shows resulting boolean.
        bpy.ops.object.select_all(action='DESELECT')
        target.select_set(True)
        context.view_layer.objects.active = target
        self.report({'INFO'}, "Boolean cutter created at 3D cursor; move cutter to position hole")
        return {'FINISHED'}


class BLINTER_PT_quick_actions(bpy.types.Panel):
    bl_label = "Quick Modeling"
    bl_idname = "BLINTER_PT_quick_actions"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Blinter'

    def draw(self, context):
        col = self.layout.column(align=True)
        col.operator("blinter.quick_actions", icon='MENU_PANEL')
        if context.mode == 'OBJECT' and context.active_object and context.active_object.type == 'MESH':
            col.operator("blinter.add_hole_cutter", icon='MOD_BOOLEAN')
        elif context.mode == 'EDIT_MESH':
            _, edges, _ = mesh_selection(context)
            if edges == 1:
                col.operator("blinter.set_edge_length", icon='DRIVER_DISTANCE')
        col.label(text="Select geometry, then Quick Actions")


classes = (
    BLINTER_MT_quick_actions,
    BLINTER_OT_quick_actions,
    BLINTER_OT_add_hole_cutter,
    BLINTER_PT_quick_actions,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
