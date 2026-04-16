# InterpBlendShape Editor

A production-grade Maya blend shape editor with real-time DG sync,
thread-safe loading, full undo support, and custom Qt MVC architecture.

## Features
- Real-time Maya sync via Maya API callbacks
- Thread-safe background data loading
- Full undo/redo support with single chunk per drag
- Normalized weight painting
- Vertex weight editor
- Copy / Mirror / Flip weights
- Drag and drop target reordering
- Scene state persistence

## Requirements
- Maya 2022+ (PySide2)
- Python 3.x

## Installation
1. Copy `plug-ins/` folder to your Maya plug-ins path
2. Load `interpBlendShape` plugin in Maya Plugin Manager
3. Run in Script Editor:
   import interpBlendShape_ui
   interpBlendShape_ui.showUI()
