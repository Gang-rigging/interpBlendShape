def onMayaDroppedPythonFile(*args):
    """
    Called when this file is dragged and dropped into Maya.
    Copies userSetup.py into the Maya user scripts folder, or appends
    the path setup block to an existing userSetup.py.
    Also activates the path for the current session immediately.
    """
    import sys
    import os
    import shutil
    import maya.cmds as cmds

    this_dir = os.path.dirname(os.path.abspath(__file__))
    interp_scripts = os.path.join(this_dir, "scripts")

    # Add to current session immediately
    if interp_scripts not in sys.path:
        sys.path.insert(0, interp_scripts)

    # Find Maya's user scripts folder
    maya_scripts = cmds.internalVar(userScriptDir=True)
    dest = os.path.join(maya_scripts, "userSetup.py")
    source = os.path.join(this_dir, "userSetup.py")

    append_block = (
        "\n# -- interpBlendShape --\n"
        "import sys, os\n"
        "_ib_scripts = os.path.join(os.path.dirname(__file__), "
        '"interpBlendShape", "scripts")\n'
        "if _ib_scripts not in sys.path:\n"
        "    sys.path.insert(0, _ib_scripts)\n"
        "# -- end interpBlendShape --\n"
    )

    if os.path.exists(dest):
        with open(dest, "r") as f:
            content = f.read()
        if "interpBlendShape" in content:
            cmds.warning("interpBlendShape path already found in userSetup.py — skipping.")
            return
        with open(dest, "a") as f:
            f.write(append_block)
        cmds.inViewMessage(
            amg="interpBlendShape: path appended to existing <b>userSetup.py</b>.",
            pos="botCenter", fade=True
        )
    else:
        shutil.copy2(source, dest)
        cmds.inViewMessage(
            amg="interpBlendShape: <b>userSetup.py</b> copied to Maya scripts folder.",
            pos="botCenter", fade=True
        )
