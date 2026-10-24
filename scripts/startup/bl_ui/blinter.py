# SPDX-License-Identifier: GPL-2.0-or-later
"""Blinter built-in engineering controls, integrated with Blender View3D UI."""
import bpy


class TOPBAR_MT_blinter_design(bpy.types.Menu):
    bl_label = "Blinter"
    bl_idname = "TOPBAR_MT_blinter_design"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Modeling", icon='EDITMODE_HLT')
        layout.menu("VIEW3D_MT_add", text="Add Geometry")
        layout.menu("TOPBAR_MT_file_import", text="Import")
        layout.menu("TOPBAR_MT_file_export", text="Export")
        layout.separator()
        if context.mode == 'EDIT_MESH':
            layout.operator("blinter.toggle_selection_lock", text="Lock / Unlock Selection",
                            icon='DECORATE_LOCKED')
            layout.operator("blinter.edge_dimension", text="Set Edge Dimension",
                            icon='DRIVER_DISTANCE')
            layout.operator("blinter.circle_diameter", text="Circular Feature Diameter",
                            icon='MESH_CIRCLE')
            layout.operator("blinter.scale_outside_regions", text="Resize Around Locks",
                            icon='TRANSFORM_SCALE')
            layout.menu("VIEW3D_MT_edit_mesh", text="More Mesh Tools")
        elif context.mode == 'OBJECT':
            if context.active_object and context.active_object.type == 'MESH':
                layout.operator("blinter.hole_cutter", text="Hole Cutter", icon='MOD_BOOLEAN')
            layout.menu("VIEW3D_MT_object", text="More Object Tools")
        layout.separator()
        layout.prop(context.scene, "blinter_focus_ui", text="Focused Design Interface",
                    icon='PREFERENCES')
        layout.label(text="Full Blender tools remain available in Advanced UI")


class BLINTER_UL_locked_regions(bpy.types.UIList):
    """Renameable groups within the same mesh, not separate Blender objects."""
    bl_idname = "BLINTER_UL_locked_regions"

    def draw_item(self, context, layout, data, item, icon, active_data,
                  active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.prop(item, "name", text="", emboss=False, icon='GROUP_VERTEX')
            row.prop(item, "kind", text="", emboss=False)
            row.prop(item, "enabled", text="", emboss=False,
                     icon='DECORATE_LOCKED' if item.enabled else 'DECORATE_UNLOCKED')
        else:
            layout.label(text="", icon='GROUP_VERTEX')



class VIEW3D_PT_blinter_engineering(bpy.types.Panel):
    """Primary design hub: selection-scoped actions, minimal permanent chrome."""
    bl_label = "Design"
    bl_idname = "VIEW3D_PT_blinter_engineering"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Blinter'

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            col.label(text="Select a mesh to begin", icon='MESH_CUBE')
            col.menu("VIEW3D_MT_add", text="Create Geometry", icon='ADD')
            return
        if context.mode == 'EDIT_MESH':
            row = col.row(align=True)
            row.operator("blinter.toggle_selection_lock", text="Lock / Unlock",
                         icon='DECORATE_LOCKED')
            row.operator("blinter.edge_dimension", text="Dimension",
                         icon='DRIVER_DISTANCE')
            col.operator("blinter.circle_diameter", text="Diameter of Selected Loop",
                         icon='MESH_CIRCLE')
            row = col.row(align=True)
            move = row.operator("blinter.transform_selection", text="Move", icon='TRANSFORM_MOVE')
            move.action = 'MOVE'
            scale = row.operator("blinter.transform_selection", text="Scale", icon='TRANSFORM_SCALE')
            scale.action = 'SCALE'
            row = col.row(align=True)
            row.operator("mesh.extrude_region_move", text="Extrude", icon='MOD_SOLIDIFY')
            row.operator("mesh.bevel", text="Bevel", icon='MOD_BEVEL')
            col.label(text="Right-click selection for more actions", icon='INFO')
        elif context.mode == 'OBJECT':
            col.operator("blinter.hole_cutter", text="Cut a Hole", icon='MOD_BOOLEAN')
            col.label(text="Tab to edit mesh geometry", icon='EDITMODE_HLT')
        else:
            col.label(text="Mesh and sculpt tools remain available")


class VIEW3D_PT_blinter_regions(bpy.types.Panel):
    bl_label = "Locked Regions"
    bl_idname = "VIEW3D_PT_blinter_regions"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Blinter'
    bl_parent_id = "VIEW3D_PT_blinter_engineering"

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.edit_object is not None

    def draw(self, context):
        layout = self.layout
        data = context.edit_object.data
        row = layout.row(align=True)
        row.template_list("BLINTER_UL_locked_regions", "", data, "blinter_rigid_regions",
                          data, "blinter_active_rigid_region", rows=5)
        tools = row.column(align=True)
        tools.operator("blinter.select_locked_region", text="", icon='RESTRICT_SELECT_OFF')
        tools.operator("blinter.remove_selected_region", text="", icon='REMOVE')
        active = data.blinter_active_rigid_region
        if 0 <= active < len(data.blinter_rigid_regions):
            item = data.blinter_rigid_regions[active]
            box = layout.box()
            box.label(text=f"{item.count:,} mesh vertices | {item.boundary_edges:,} border edges")
            box.label(text="Fixed to world" if item.kind == 'ANCHOR' else "Rigid relative group",
                      icon='DECORATE_LOCKED')
            if item.kind == 'RELATIVE':
                op = box.operator("blinter.move_rigid_region", text="Move Selected Region",
                                  icon='TRANSFORM_MOVE')
                op.group_id = item.group_id
        row = layout.row(align=True)
        row.operator("blinter.scale_outside_regions", text="Resize Unlocked",
                     icon='TRANSFORM_SCALE')
        row.operator("blinter.clear_rigid_regions", text="", icon='UNLOCKED')


class VIEW3D_PT_blinter_precision(bpy.types.Panel):
    bl_label = "Precision & Manufacture"
    bl_idname = "VIEW3D_PT_blinter_precision"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Blinter'
    bl_parent_id = "VIEW3D_PT_blinter_engineering"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        col = self.layout.column(align=True)
        if context.mode == 'EDIT_MESH':
            col.operator("blinter.edge_dimension", text="Set Edge Length",
                         icon='DRIVER_DISTANCE')
            col.operator("blinter.circle_diameter", text="Set Circular Diameter",
                         icon='MESH_CIRCLE')
            col.operator("mesh.bevel", text="Precision Bevel", icon='MOD_BEVEL')
            col.operator("mesh.inset", text="Inset Face", icon='SELECT_EXTEND')
        elif context.mode == 'OBJECT' and context.active_object and context.active_object.type == 'MESH':
            col.operator("blinter.hole_cutter", text="Hole Cutter", icon='MOD_BOOLEAN')
        col.separator()
        col.prop(context.scene, "blinter_focus_ui", text="Focused Design Interface")
        col.label(text="Disable to see the complete Blender UI")



def draw_blinter_context(self, context):
    if context.mode != 'EDIT_MESH' or not context.edit_object:
        return
    self.layout.separator()
    self.layout.operator("blinter.toggle_selection_lock",
                         text="Lock / Unlock Selection", icon='DECORATE_LOCKED')
    self.layout.operator("blinter.edge_dimension", text="Set Edge Length", icon='DRIVER_DISTANCE')
    self.layout.operator("blinter.circle_diameter", text="Set Circle Diameter",
                         icon='MESH_CIRCLE')
    row = self.layout.row(align=True)
    move = row.operator("blinter.transform_selection", text="Move With Locks",
                        icon='TRANSFORM_MOVE')
    move.action = 'MOVE'
    scale = row.operator("blinter.transform_selection", text="Scale With Locks",
                         icon='TRANSFORM_SCALE')
    scale.action = 'SCALE'


classes = (TOPBAR_MT_blinter_design, BLINTER_UL_locked_regions, VIEW3D_PT_blinter_engineering, VIEW3D_PT_blinter_regions, VIEW3D_PT_blinter_precision)
