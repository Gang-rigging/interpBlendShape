# InterpBlendShape

InterpBlendShape is a Maya deformation toolset with a custom editor for managing targets, inbetweens, paint data, surface drivers, and target-shape editing.
It is built around a custom Qt model/view workflow with Maya callback-driven refresh, asynchronous model loading, and undo-friendly editing.

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

- Create and manage `interpBlendShape` deformers from a custom editor
- Real-time DG and UI sync through Maya API callbacks
- Thread-aware model loading with Maya data collected on the main thread and tree-building moved to a background `QThread`
- Undo-friendly editing with chunked undo for drag-release and batch operations
- Add targets and inbetweens directly from scene selection
- Paint and edit target weights
- Vertex weight editor with normalization and lock controls
- Copy, mirror, and flip target weights
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
