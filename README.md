# InterpBlendShape

**InterpBlendShape** is a custom Maya deformer plugin that offers an alternative to Maya's built-in linear blend — blending targets using surface and bezier interpolation. It supports GPU parallel execution and works on both meshes and curves.

**InterpBlendShapeEditor** is the accompanying toolset: a custom editor for creating and managing targets, inbetweens, paint data, surface drivers, and target-shape editing. Mirror and flip operations are significantly faster than Maya's native equivalents. The UI is built on a Qt MVC framework with real-time Maya synchronization, full undo/redo support, thread-safe scene loading, and draggable target ordering.

For full details on the deformer node, see the [InterpBlendShape documentation](https://www.cgdzg.com/docs/interpblendshape-docs.html).

## What Is Included

- `interpBlendShape_ui.py`
  Main Maya UI entry point.
- `smoke_test_interpblendshape.py`
  Lightweight Maya smoke test for the core happy-path workflow.
- `widgets/`
  Reusable UI components, delegates, popup helpers, and styling.

## Install

1. Copy the `interpBlendShape` folder into:
   ```
   C:\Users\<username>\Documents\maya\2024\scripts\
   ```
2. Set up the Python path by either:
   - **Dragging `install_interpBlendShape.py` into the Maya viewport** — it will install itself automatically, or
   - **Copying `userSetup.py` manually** into:
     ```
     C:\Users\<username>\Documents\maya\2024\scripts\
     ```
     If you already have a `userSetup.py`, append its contents to your existing file instead of replacing it.
3. Download the compiled plugin for your Maya version from the [Releases](https://github.com/Gang-rigging/interpBlendShape/releases) page and copy it into:
   ```
   C:\Program Files\Autodesk\Maya2024\bin\plug-ins\
   ```
4. Copy `AEinterpBlendShapeTemplate.mel` into:
   ```
   C:\Program Files\Autodesk\Maya2024\scripts\AETemplates\
   ```

Restart Maya, then launch the UI from the Script Editor:

```python
from interpBlendShape_ui import showUI
showUI()
```

## Requirements

- Maya 2023+ with PySide2
- Python 3.x
- The compiled `interpBlendShape` plugin available to Maya

## Features

### Deformer
- Surface and bezier interpolation as an alternative to Maya's linear blend
- GPU parallel execution for fast deformation
- Works on meshes and curves

### Editor
- Create and manage `interpBlendShape` deformers from a custom editor
- Real-time DG and UI sync through Maya API callbacks
- Thread-safe scene loading with Maya data collected on the main thread and tree-building moved to a background `QThread`
- Full undo/redo support with chunked undo for drag-release and batch operations
- Add targets and inbetweens directly from scene selection
- Paint and edit target weights
- Vertex weight editor with normalization and lock controls
- Copy, mirror, and flip target weights — significantly faster than Maya's native mirror/flip
- Drag-and-drop target reordering
- Scene state persistence for expanded state and saved node order
- Mirror or flip target geometry
- Surface association modes:
  - `Closest Component`
  - `Closest Point`
  - `Closest UV (Global)`
  - `Closest UV (Shell Center)`

## Known Limits

- UV-based shape editing is mesh-only.
- UV-based shape editing uses the current UV set on the mesh.
- `Closest UV (Global)` mirrors across global `U = 0.5`.
- `Closest UV (Shell Center)` mirrors across each shell's local U center.
- Inbetween weights must stay strictly between `0.0` and `1.0`.

## Smoke Test

Run this inside Maya's Script Editor after the plugin and scripts are available:

```python
from smoke_test_interpblendshape import run_smoke_test
result = run_smoke_test()
print(result)
```

The smoke test covers:

- opening the UI
- creating a deformer node
- adding a target
- adding an inbetween
- opening the shape edit options popup
- executing a mirror target operation

## Release Checklist

- Verify the plugin loads in the target Maya version
- Run the smoke test in Maya
- Confirm icons resolve correctly from the packaged location
- Test one mesh target workflow and one curve target workflow
- Verify shape editing on at least one mirrored mesh asset

## License

The Python UI scripts are open source under the [MIT License](LICENSE).

The compiled `interpBlendShape.mll` plugin is included as a binary. Source code for the C++ plugin is not publicly available.

## Version

Current Python package version: `1.0.0`
