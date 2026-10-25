# SPDX-License-Identifier: GPL-2.0-or-later
"""Blinter mesh edit preflight: validate, commit or restore BMesh coordinates.

This is geometry validation, not a claim that a polygon mesh is analytically
watertight in every possible case. It detects local collapse, flipped faces,
zero-length edges, and changes to edge/face incidence. It never remeshes or
replaces the Blender mesh, and never exports an intermediate triangulation.
"""
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

EPS = 1.0e-12
MIN_TRIANGLE_AREA_RATIO = 1.0e-5
MIN_EDGE_RATIO = 1.0e-5


def _local_neighborhood(changed):
    vertices = set(changed)
    faces = {face for vert in changed for face in vert.link_faces}
    edges = {edge for vert in changed for edge in vert.link_edges}
    return vertices, edges, faces


def _triangles(faces, coordinates):
    result = {}
    for face in faces:
        loops = list(face.verts)
        positions = [coordinates[v] for v in loops]
        if len(loops) < 3:
            raise ValueError("Degenerate mesh face")
        # Triangulation is used only for validation; BMesh topology stays intact.
        tris = tessellate_polygon([positions])
        if not tris:
            raise ValueError("Face cannot be triangulated safely")
        # tessellate_polygon returns coordinate triplets, not vertex IDs.
        # Here the coordinate vectors belong to the positions supplied above.
        normals = []
        for tri in tris:
            a, b, c = tri
            cross = (b - a).cross(c - a)
            normals.append(cross)
        result[face] = normals
    return result


def preflight_and_apply(obj, bm, proposals):
    """Apply candidate coordinates atomically or restore the original mesh.

    Only intended vertex coordinates may change. All local adjacent faces and
    edges are checked before accepting. Raises ValueError on unsafe edits.
    """
    if not proposals:
        return
    selected, edges, faces = _local_neighborhood(proposals)
    old_positions = {v: v.co.copy() for v in selected}
    before_coordinates = {v: v.co.copy() for face in faces for v in face.verts}
    for v in selected:
        before_coordinates.setdefault(v, v.co.copy())
    before_edges = {edge: ((edge.verts[0].co - edge.verts[1].co).length,
                           len(edge.link_faces)) for edge in edges}
    before_faces = {face: (len(face.verts), tuple(face.verts)) for face in faces}
    try:
        original_triangles = _triangles(faces, before_coordinates)
        for vertex, coord in proposals.items():
            if not all(abs(coord[i]) < 1e30 for i in range(3)):
                raise ValueError("Non-finite or excessively large coordinate")
            vertex.co = coord.copy()
        after_coordinates = {v: v.co.copy() for face in faces for v in face.verts}
        changed_triangles = _triangles(faces, after_coordinates)
        for edge in edges:
            previous_length, previous_incidence = before_edges[edge]
            length = (edge.verts[0].co - edge.verts[1].co).length
            if previous_length <= EPS:
                raise ValueError("Existing zero-length edge: cannot safely modify feature")
            if length <= max(EPS, previous_length * MIN_EDGE_RATIO):
                raise ValueError("Edit collapses or nearly collapses a connected edge")
            if len(edge.link_faces) != previous_incidence:
                raise ValueError("Unexpected edge incidence change")
        for face in faces:
            original_count, vertices = before_faces[face]
            if len(face.verts) != original_count or tuple(face.verts) != vertices:
                raise ValueError("Unexpected face topology change")
            before_tri = original_triangles[face]
            after_tri = changed_triangles[face]
            if len(before_tri) != len(after_tri):
                raise ValueError("Connected face triangulation changed unexpectedly")
            for old, new in zip(before_tri, after_tri):
                if old.length <= EPS:
                    raise ValueError("Preexisting degenerate face triangle")
                if new.length <= max(EPS, old.length * MIN_TRIANGLE_AREA_RATIO):
                    raise ValueError("Edit collapses a connected face")
                if old.dot(new) <= 0:
                    raise ValueError("Edit flips a connected face triangle")
    except Exception:
        for vertex, coordinate in old_positions.items():
            vertex.co = coordinate
        raise
