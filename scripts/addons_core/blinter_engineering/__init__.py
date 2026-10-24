bl_info = {
    "name": "Blinter Engineering Viewport",
    "author": "Blinter contributors",
    "version": (0, 1, 0),
    "blender": (4, 3, 0),
    "location": "View3D > Sidebar > Blinter",
    "description": "Selection-scoped mesh dimensions with direct numeric edge-length editing",
    "category": "3D View",
}

import bpy
from . import quick_actions, dimension_interaction
import bmesh
import blf
import math
from bpy.props import FloatProperty
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

_draw_handle = None


def selected_edges_world(context):
    obj = context.edit_object
    if not obj or obj.type != 'MESH':
        return []
    bm = bmesh.from_edit_mesh(obj.data)
    matrix = obj.matrix_world
    output = []
    for edge in bm.edges:
        if edge.select and not edge.hide:
            a, b = (matrix @ v.co for v in edge.verts)
            output.append((a, b, (a - b).length))
    return output


def selected_corner_angle(context):
    """Angle at a shared vertex when exactly two connected edges are selected."""
    obj = context.edit_object
    if not obj or obj.type != 'MESH':
        return None
    bm = bmesh.from_edit_mesh(obj.data)
    edges = [edge for edge in bm.edges if edge.select and not edge.hide]
    if len(edges) != 2:
        return None
    shared = set(edges[0].verts).intersection(edges[1].verts)
    if len(shared) != 1:
        return None
    vertex = next(iter(shared))
    tips = [next(v for v in e.verts if v != vertex) for e in edges]
    mat = obj.matrix_world
    center = mat @ vertex.co
    a = (mat @ tips[0].co) - center
    b = (mat @ tips[1].co) - center
    if a.length < 1e-12 or b.length < 1e-12:
        return None
    radians = math.acos(max(-1.0, min(1.0, a.normalized().dot(b.normalized()))))
    return center, math.degrees(radians)


def draw_dimensions():
    context = bpy.context
    region = context.region
    rv3d = context.region_data
    if not region or not rv3d:
        return
    font = 0
    blf.size(font, 13)
    blf.color(font, 0.25, 0.8, 1.0, 1.0)
    for a, b, length in selected_edges_world(context)[:150]:
        p = location_3d_to_region_2d(region, rv3d, (a + b) * 0.5)
        if p:
            blf.position(font, p.x + 8, p.y + 8, 0)
            blf.draw(font, f"{length * 1000:.3f} mm")
    corner = selected_corner_angle(context)
    if corner:
        pos, angle = corner
        pixel = location_3d_to_region_2d(region, rv3d, pos)
        if pixel:
            blf.position(font, pixel.x + 12, pixel.y - 24, 0)
            blf.draw(font, f"{angle:.2f} deg")


class BLINTER_OT_set_edge_length(bpy.types.Operator):
    """Set the first selected edge length; change endpoint vertices in the mesh"""
    bl_idname = "blinter.set_edge_length"
    bl_label = "Set Edge Length"
    bl_options = {'REGISTER', 'UNDO'}

    length_mm: FloatProperty(name="Length (mm)", default=10.0, min=0.001, precision=3)
    edge_index: bpy.props.IntProperty(name="Target Edge", default=-1, options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.edit_object is not None

    def invoke(self, context, event):
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        bm.edges.index_update()
        if self.edge_index >= 0 and self.edge_index < len(bm.edges):
            edge = bm.edges[self.edge_index]
            a, b = (obj.matrix_world @ v.co for v in edge.verts)
            self.length_mm = (a - b).length * 1000.0
        else:
            edges = selected_edges_world(context)
            if len(edges) == 1:
                self.length_mm = edges[0][2] * 1000.0
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        if self.edge_index >= 0:
            bm.edges.index_update()
            edges = [bm.edges[self.edge_index]] if self.edge_index < len(bm.edges) else []
        else:
            edges = [e for e in bm.edges if e.select and not e.hide]
        if len(edges) != 1 or edges[0].hide:
            self.report({'WARNING'}, "Select exactly one edge")
            return {'CANCELLED'}
        edge = edges[0]
        v0, v1 = edge.verts
        # Compute in world coordinates so object scale and rotation are respected.
        mat = obj.matrix_world
        a, b = mat @ v0.co, mat @ v1.co
        delta = b - a
        if delta.length < 1e-10:
            self.report({'WARNING'}, "Cannot resize zero-length edge")
            return {'CANCELLED'}
        midpoint = (a + b) * 0.5
        half = delta.normalized() * (self.length_mm / 2000.0)
        inv = mat.inverted_safe()
        v0.co = inv @ (midpoint - half)
        v1.co = inv @ (midpoint + half)
        bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=False)
        return {'FINISHED'}


class BLINTER_PT_engineering(bpy.types.Panel):
    bl_label = "Precision Design"
    bl_idname = "BLINTER_PT_engineering"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Blinter'

    def draw(self, context):
        layout = self.layout
        layout.label(text="Selected edge dimensions in viewport")
        layout.operator("blinter.set_edge_length", icon='DRIVER_DISTANCE')
        layout.operator("blinter.click_dimension", icon='RESTRICT_SELECT_OFF')
        layout.label(text="Length edit moves edge endpoints", icon='INFO')


classes = (BLINTER_OT_set_edge_length, BLINTER_PT_engineering)


def register():
    global _draw_handle
    for cls in classes:
        bpy.utils.register_class(cls)
    quick_actions.register()
    dimension_interaction.register()
    if _draw_handle is None:
        _draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            draw_dimensions, (), 'WINDOW', 'POST_PIXEL'
        )


def unregister():
    global _draw_handle
    if _draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, 'WINDOW')
        _draw_handle = None
    dimension_interaction.unregister()
    quick_actions.unregister()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
