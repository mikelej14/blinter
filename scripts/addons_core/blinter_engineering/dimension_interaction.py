"""Viewport click-to-edit dimensions, reusing Blender's mesh measurement operator.

Click mode is explicitly activated, avoiding interception of normal selection.
Coordinates and edge distance are evaluated on demand, not globally cached.
"""
import bpy
import bmesh
import blf
from bpy_extras.view3d_utils import location_3d_to_region_2d

MAX_VISIBLE = 150
PICK_PAD_PX = 7


def edge_labels(context):
    obj = context.edit_object
    if not obj or obj.type != "MESH" or context.region_data is None:
        return []
    bm = bmesh.from_edit_mesh(obj.data)
    bm.edges.index_update()
    transform = obj.matrix_world
    labels = []
    for edge in bm.edges:
        if not edge.select or edge.hide:
            continue
        a, b = (transform @ v.co for v in edge.verts)
        p = location_3d_to_region_2d(
            context.region, context.region_data, (a + b) * 0.5,
        )
        if p is not None:
            label = f"{(a - b).length * 1000:.3f} mm"
            x, y = p.x + 8, p.y + 8
            width, height = blf.dimensions(0, label)
            labels.append((edge.index, x, y, width, height, label))
        if len(labels) >= MAX_VISIBLE:
            break
    return labels


class BLINTER_OT_click_dimension(bpy.types.Operator):
    """Click a selected edge's dimension label to edit its length"""
    bl_idname = "blinter.click_dimension"
    bl_label = "Edit Dimension on Model"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.area and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        self._area = context.area
        self._window = context.window
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set("Blinter: click an edge dimension to edit, Esc/right-click to cancel")
        return {'RUNNING_MODAL'}

    def _finish(self, context):
        context.workspace.status_text_set(None)
        if self._area:
            self._area.tag_redraw()

    def modal(self, context, event):
        if context.area != self._area or context.window != self._window:
            self._finish(context)
            return {'CANCELLED'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._finish(context)
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            x, y = event.mouse_region_x, event.mouse_region_y
            blf.size(0, 13)
            labels = edge_labels(context)
            hits = [item for item in labels if (
                item[1] - PICK_PAD_PX <= x <= item[1] + item[3] + PICK_PAD_PX
                and item[2] - PICK_PAD_PX <= y <= item[2] + item[4] + PICK_PAD_PX
            )]
            if not hits:
                return {'RUNNING_MODAL'}
            edge_index = min(hits, key=lambda item: (x-item[1])**2 + (y-item[2])**2)[0]
            bm = bmesh.from_edit_mesh(context.edit_object.data)
            bm.edges.ensure_lookup_table()
            bm.edges.index_update()
            edge = bm.edges[edge_index] if edge_index < len(bm.edges) else None
            if edge is None or not edge.select or edge.hide:
                self._finish(context)
                return {'CANCELLED'}
            self._finish(context)
            # Operator asks which edge explicitly; it does not mutate selection to use UI.
            bpy.ops.blinter.set_edge_length('INVOKE_DEFAULT', edge_index=edge_index)
            return {'FINISHED'}
        return {'RUNNING_MODAL'}


classes = (BLINTER_OT_click_dimension,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
