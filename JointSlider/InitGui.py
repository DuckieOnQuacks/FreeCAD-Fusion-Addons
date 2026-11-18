# Joint slider add-on: move assembly joints with a slider. See joint_slider.py.
try:
    import joint_slider
    joint_slider.setup()
except Exception as _e:
    import FreeCAD
    FreeCAD.Console.PrintWarning('Joint slider failed to load: %s\n' % _e)
