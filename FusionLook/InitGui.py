# Fusion-style look add-on: ground grid in the 3D view. See fusion_look.py.
try:
    import fusion_look
    fusion_look.setup()
except Exception as _e:
    import FreeCAD
    FreeCAD.Console.PrintWarning('Fusion look failed to load: %s\n' % _e)
