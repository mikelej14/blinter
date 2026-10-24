# SPDX-License-Identifier: GPL-2.0-or-later
"""Blinter built-in engineering controls, integrated with Blender View3D UI."""
import bpy

class BLINTER_UL_locked_regions(bpy.types.UIList):
    """Renameable groups within the same mesh, not separate Blender objects."""
    bl_idname = "BLINTER_UL_locked_regions"

    def draw_item(self, context, layout, data, item, icon, active_data,
                  active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.prop(item, "name", text="", emboss=False, icon='GROUP_VERTEX')
            row.prop(item, "enabled", text="", emboss=False,
                     icon='DECORATE_LOCKED' if item.enabled else 'DECORATE_UNLOCKED')
        else:
            layout.label(text="", icon='GROUP_VERTEX')



class VIEW3D_PT_blinter_engineering(bpy.types.Panel):
    bl_label = "Blinter | Precision Modeling"
    bl_idname = "VIEW3D_PT_blinter_engineering"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Blinter'

    def draw(self, context):
        layout = self.layout
        obj = context.edit_object
        if not obj or obj.type != 'MESH':
            layout.label(text="Enter Mesh Edit Mode", icon='INFO')
            return
        data = obj.data
        layout.operator("blinter.toggle_selection_lock", text="Lock / Unlock Selection",
                        icon='DECORATE_LOCKED')
        row = layout.row()
        row.template_list("BLINTER_UL_locked_regions", "", data, "blinter_rigid_regions",
                          data, "blinter_active_rigid_region", rows=6)
        actions = row.column(align=True)
        actions.operator("blinter.select_locked_region", text="", icon='RESTRICT_SELECT_OFF')
        actions.operator("blinter.remove_selected_region", text="", icon='REMOVE')
        i = data.blinter_active_rigid_region
        if 0 <= i < len(data.blinter_rigid_regions):
            region = data.blinter_rigid_regions[i]
            box = layout.box()
            box.label(text=f"{region.count:,} vertices | {region.boundary_edges:,} boundary edges")
            op = box.operator("blinter.move_rigid_region", text="Move Region", icon='TRANSFORM_MOVE')
            op.group_id = region.group_id
        layout.separator()
        layout.operator("blinter.scale_outside_regions", text="Resize Unlocked",
                        icon='TRANSFORM_SCALE')
        layout.label(text="Mesh-native grouped constraints", icon='INFO')


def draw_blinter_context(self, context):
    if context.mode != 'EDIT_MESH' or not context.edit_object:
        return
    self.layout.separator()
    self.layout.operator("blinter.toggle_selection_lock",
                         text="Lock / Unlock Selection", icon='DECORATE_LOCKED')


classes = (BLINTER_UL_locked_regions, VIEW3D_PT_blinter_engineering)
