# Blinter — Blender-native engineering workstation

Blinter is a manufacturing-focused Blender fork. It retains Blender's mesh and sculpt engines and reshapes the workflows around mechanical design and 3D printing. **It is not a B-rep CAD port or a SolidCraft integration.**

## Architecture

- **Blender is the geometry engine**: BMesh, modifiers, booleans, sculpt, UV, materials.
- **Selection-scoped measurements**: calculate relevant geometry on demand, not full-model CAD reconstruction.
- **Engineering overlays**: place dimensions on selected geometry using viewport draw handlers.
- **Numerical edits**: feed user dimensions back into native mesh operations.
- **Future persisted relationships**: maintain references, validate topology changes, and apply constraints through controlled operators.
- **Manufacturing tool orchestration**: compose native booleans, bevel, screw, solidify, patterns, and repair functionality.

## First working prototype

File: `scripts/addons_core/blinter_engineering/__init__.py`.

In a Blender build that includes this directory, enable the **Blinter Engineering Viewport** extension/add-on if available in your build. For development testing import the `blinter_engineering` package with its parent folder on Blender's Python module path. Running `__init__.py` alone from the Text Editor does not support relative imports. In Edit Mode, select an edge: its measured world-space length is drawn next to the edge in millimeters. Two connected selected edges also show their included angle. Open **N > Blinter > Precision Design > Set Edge Length** to edit the value.

The **Quick Modeling** panel includes a **Use Millimeters** display-unit preset, which does not rescale geometry. It also offers a context-sensitive **Quick Actions** menu in Edit Mode, using Blender's own extrude, inset, bevel, move, rotate, and other operators. In Object Mode, **Add Hole Cutter** creates a dimensioned cylinder cutter and an unapplied Boolean Difference modifier on the selected mesh. Place the 3D cursor at the desired hole center; the cutter initially points along global Z and remains movable/editable.

### Smoke test

From a Blender source checkout with a built Blender executable:

```
blender --background --python tests/blinter_smoke.py -- /absolute/path/to/blinter
```

The smoke test checks add-on registration, numeric edge editing, and non-destructive cutter creation. It has **not yet been executed here** because the development runtime has no Blender executable.

**Current prototype limitations**: the numeric edit moves only the two edge endpoints; connected geometry may deform. It is not yet topology-aware, does not maintain constraint locks, and cannot edit by clicking the drawn text. The quick menu is an explicit sidebar command, not yet a context auto-popup. The cylinder cutter is a first tool prototype, not a full hole/thread wizard. The overlay processes up to 150 selected edges, and large meshes may need caching. No manufacturing-grade precision or production readiness is claimed.

## Development sequence

1. Selection overlay, editable lengths, and consistent units.
2. Viewport-native dimension hit-testing and editor; selection-specific quick-action menus.
3. Stable feature IDs and topology-change notifications.
4. Persistent distance/angle locks and conflict handling.
5. Hole recognition, parametric cutters, screw-thread tool, and bolt patterns using Blender mesh operations.
6. Manifold checks/repair, wall thickness, clearances, and manufacturing export.
7. Workspaces, application branding, de-emphasize unrelated CGI features, Windows build/test automation.

## Upstream

Derived from Blender, GPL-3.0 compatible; retain upstream notices and license. Do not rewrite or flatten Blender history solely for branding.

## Important

The current first commit is **a prototype**, not a rebuilt Blender executable. A Blender build and interactive verification are still required.

## Interactive viewport measurements (prototype)

In Edit Mode, select an edge and choose **Blinter > Precision Design > Edit Dimension on Model**. Click a displayed edge-length label to open a numerical edit dialog, or Esc/right-click to exit picking mode. This is an explicit modal tool; Blender's ordinary selection is unchanged outside it. The active face/edge menu remains available in Quick Modeling.

## Persistent edge length locks (manual restore, experimental)

Select one mesh edge and choose **Blinter > Edge Length Locks > Lock Selected Edge Length**. Locks are saved on the mesh datablock inside a .blend file. You may edit that edge length and choose **Restore Edge Length Locks** to bring it back to the saved world-space length. **Automatic constraint enforcement is not implemented**. This does not constrain neighboring faces, hole-to-edge offsets, bolt patterns, or every native Blender transform. Locked edge measurements are not yet always-on overlays.

Lock references currently use vertex indices plus vertex/edge counts. This detects some topology changes, but **cannot detect vertex reordering with identical counts**. Multiple adjoining locks may conflict and restoration currently processes them sequentially, so it is not a general constraint solver. Always keep a saved original when testing. These limitations must be addressed before claiming manufacturing-grade constraint integrity.

## Validation status

Changes remain unverified inside a real Blender GUI, including click-hit coordinates, Blender 4.3+ API details and overlay event routing. Run the headless smoke test and interactive manual checks before merging. No automated build has been run from this workspace.

## Relative positional constraints — part edge to hole rim (experimental)

This implements the **relative edge-to-hole clearance** workflow: a circular polygon hole remains a specified distance from a part edge as a Blinter-controlled move changes the reference edge's position.

1. In mesh Edit Mode select exactly one straight part edge; choose **Relative Hole Position > 1. Choose Part Edge**.
2. Deselect it, and select only the complete edge loop around a circular hole with at least 8 segments.
3. Choose **2. Lock Hole Clearance**. The measured clearance is the perpendicular distance from the infinite line along the reference edge to the fitted hole boundary, in world units; it is **not** the nearest distance to a finite edge endpoint.
4. **Set Edge-to-Hole Clearance** moves the hole rim vertices to establish a chosen spacing, e.g. 6.35 mm.
5. **Move Part Edge + Follow Hole** translates the two reference edge endpoints and the whole hole rim together along their measured relative direction, maintaining the measured spacing.

This deliberately uses mesh geometry and native BMesh vertex transforms rather than STEP/B-rep CAD reconstruction. It fits approximate planar circular rim loops, not analytic CAD circles. **It moves the rim vertices, not all nearby supporting mesh vertices, and therefore may distort connected faces**. It is proof of constraint propagation, *not* an engineering-grade solid edit. It currently stores one edge-to-hole relationship per mesh, and native Blender move/extrude/bevel do **not** yet trigger constraint propagation. Invalid topology changes may escape checks if vertex/edge counts do not change, so save before editing and recapture relationships after topology modifications.

Headless geometry regression script (requires built Blender):

```
blender --background --python tests/blinter_relative_clearance.py -- /absolute/path/to/blinter
```

The test creates an isolated reference edge and a 32-segment circular ring; it checks the initial 15 mm edge-to-rim clearance, the same clearance after a 4 mm coupled move, and a subsequent requested 6.35 mm clearance. **Not yet executed in Blender.**

## Feature locks and bolt-pattern-safe mesh resizing (experimental)

**Feature Locks** are general to mesh vertices, edges, and faces; geometry uses Blender BMesh only.

- One connected selected feature/component: **World Grid anchor**. It records every selected vertex's world-space position. Blinter constrained resizing will not move those vertices.
- Two or more disconnected selected components: **Relative Pattern**. It stores all selected vertices as one rigid group, preserving individual feature sizes as well as feature-to-feature spacing.
- **Resize Around Locked Features** scales every *unlocked* mesh vertex around a chosen pivot (world bounding center, object origin, or cursor). Locked vertices stay unchanged. This is deliberately an *edit-mode mesh operation*, not ordinary Object Mode scale, and does not change object transforms.
- **Move Relative Group** translates one stored relative group as a rigid vertex set and updates its stored positions. World-anchored features remain pinned.
- **Unlock All Features** removes all stored lock groups on this mesh.

Each participating vertex gets an int BMesh identity layer rather than depending only on its current vertex index. Lost/duplicated IDs are reported. Lock data is persisted on the mesh datablock for .blend saves. This does **not** mean arbitrary topology edits are supported: cloning vertices can duplicate their IDs and requires repair/relocking.

**Important design limitation:** Only explicitly Blinter-controlled operations honor these locks. Ordinary Blender Scale, Move, Sculpt and modifiers are intentionally not overridden yet. The current resize scales all unprotected vertices without automatically smoothing or remeshing adjoining faces; boundary geometry can be distorted. It is a controllable mechanism for keeping holes and bolt patterns unchanged, *not* yet a robust production-ready solid-resize tool. The next step is region-aware propagation and automatic lock-aware transformation wrappers with validation.

### Regression test

```
blender --background --python tests/blinter_feature_locks.py -- /absolute/path/to/blinter
```

The test creates two disjoint 24-sided hole loops and a rectangular outer loop. It verifies that the hole loops remain fixed while the outer loop scales and then verifies rigid translation of the locked hole pattern. This test has not yet been executed in Blender.

## Arbitrary multi-selection locking (vertex, edge, face)

Feature Locks now work with Blender's normal high-poly multi-selection workflow:

- **Vertex mode:** one selected vertex defaults to WORLD lock, two or more selected vertices default to one RELATIVE group.
- **Edge mode:** one selected edge defaults to WORLD lock, two or more selected edges default to one RELATIVE group.
- **Face mode:** one selected face defaults to WORLD lock, two or more selected faces default to one RELATIVE group, even when adjoining and sharing edges/vertices.
- Lock Selected Features exposes **Automatic / Fixed to World / Relative**. The explicit override lets you pin many faces to world coordinates or form a rigid group from one face.
- A selection resolves to the union of participating vertices, deduplicating shared vertices; no requirement for separate disconnected islands.
- Only vertices participating in the selection are assigned persistent BMesh IDs. Other vertices remain untouched, reducing overhead on large meshes.
- Locked vertices remain unchanged under **Resize Around Locked Features**; nonlocked vertices are scaled by the operation. The current implementation does not soften/deform surrounding mesh regions intelligently.

Do not confuse *selection element count* with disconnected feature count. These new semantics intentionally use Blender's active selection domain. Because a single face can contain many vertices, a one-face anchor can still lock that entire face's shape and coordinates.

The lock data contains a full coordinate snapshot of every participating vertex. This is not yet optimized for enormous million-vertex lock sets, and it may consume substantial .blend storage at that scale. Further work includes compact indexed storage, spatially-local transformation propagation and stress tests.

Test with:
```
blender -b --python tests/blinter_multiselect_locks.py -- /absolute/path/to/blinter
```
This regression tests one vertex, two edges, two adjacent faces, and explicit lock-type overrides. It has not yet run in a Blender executable.
