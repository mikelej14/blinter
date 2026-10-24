# SPDX-License-Identifier: GPL-2.0-or-later
"""Blinter native engineering operations. Registered by Blender bl_operators.

No dependency on add-on registration. Geometry edits use BMesh / native Boolean.
"""
import bpy
import bmesh
from bpy.props import FloatProperty, IntProperty
from bpy_extras.view3d_utils import location_3d_to_region_2d
import blf
import math

_overlay = None


def selected_edges(context):
    obj = context.edit_object
    if obj is None or obj.type != 'MESH':
        return []
    bm = bmesh.from_edit_mesh(obj.data)
    bm.edges.ensure_lookup_table()
    bm.edges.index_update()
    mat = obj.matrix_world
    return [(e.index, *(mat @ v.co for v in e.verts))
            for e in bm.edges if e.select and not e.hide]


class BLINTER_OT_edge_dimension(bpy.types.Operator):
    """Set one selected mesh edge length in world units (mm)."""
    bl_idname = "blinter.edge_dimension"
    bl_label = "Set Edge Dimension"
    bl_options = {'REGISTER', 'UNDO'}

    length_mm: FloatProperty(name="Length (mm)", default=10, min=0.001, precision=3)
    edge_index: IntProperty(default=-1, options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.edit_object is not None

    def invoke(self, context, event):
        edges = selected_edges(context)
        if self.edge_index >= 0:
            edges = [entry for entry in edges if entry[0] == self.edge_index]
        if len(edges) != 1:
            self.report({'WARNING'}, "Select exactly one edge")
            return {'CANCELLED'}
        self.length_mm = (edges[0][1] - edges[0][2]).length * 1000
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        bm.edges.index_update()
        edges = [e for e in bm.edges if e.select and not e.hide]
        if self.edge_index >= 0:
            edges = [e for e in edges if e.index == self.edge_index]
        if len(edges) != 1:
            self.report({'WARNING'}, "Select exactly one edge")
            return {'CANCELLED'}
        a, b = edges[0].verts
        world_a = obj.matrix_world @ a.co
        world_b = obj.matrix_world @ b.co
        diff = world_b - world_a
        if diff.length < 1e-10:
            self.report({'WARNING'}, "Edge has zero length")
            return {'CANCELLED'}
        center = (world_a + world_b) / 2
        half = diff.normalized() * (self.length_mm / 2000)
        inv = obj.matrix_world.inverted_safe()
        a.co = inv @ (center - half)
        b.co = inv @ (center + half)
        bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=False)
        return {'FINISHED'}


class BLINTER_OT_hole_cutter(bpy.types.Operator):
    """Create an editable Boolean difference hole using built-in mesh operations."""
    bl_idname = "blinter.hole_cutter"
    bl_label = "Hole Cutter"
    bl_options = {'REGISTER', 'UNDO'}

    diameter_mm: FloatProperty(name="Diameter (mm)", min=.01, default=6.0, precision=3)
    depth_mm: FloatProperty(name="Depth (mm)", min=.01, default=25.0, precision=3)
    segments: IntProperty(name="Segments", min=12, max=256, default=64)

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
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=self.segments,
            radius=self.diameter_mm / 2000,
            depth=self.depth_mm / 1000,
            location=context.scene.cursor.location,
        )
        cutter = context.active_object
        cutter.name = "Blinter Hole Cutter"
        cutter.display_type = 'WIRE'
        cutter.hide_render = True
        modifier = target.modifiers.new(name="Blinter Hole", type='BOOLEAN')
        modifier.operation = 'DIFFERENCE'
        modifier.solver = 'EXACT'
        modifier.object = cutter
        bpy.ops.object.select_all(action='DESELECT')
        target.select_set(True)
        context.view_layer.objects.active = target
        return {'FINISHED'}


def draw_dimensions():
    context = bpy.context
    if context.mode != 'EDIT_MESH' or not context.region or not context.region_data:
        return
    blf.size(0, 13)
    blf.color(0, .25, .8, 1.0, 1.0)
    for index, a, b in selected_edges(context)[:150]:
        pixel = location_3d_to_region_2d(context.region, context.region_data, (a + b) * .5)
        if pixel is None:
            continue
        blf.position(0, pixel.x + 8, pixel.y + 8, 0)
        blf.draw(0, f"{(a - b).length * 1000:.3f} mm")


classes = (BLINTER_OT_edge_dimension, BLINTER_OT_hole_cutter)


def register():
    global _overlay
    if _overlay is None:
        _overlay = bpy.types.SpaceView3D.draw_handler_add(
            draw_dimensions, (), 'WINDOW', 'POST_PIXEL')


def unregister():
    global _overlay
    if _overlay is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_overlay, 'WINDOW')
        _overlay = None
