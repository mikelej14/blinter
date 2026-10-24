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
