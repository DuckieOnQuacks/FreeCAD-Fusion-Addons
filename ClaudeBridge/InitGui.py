# Claude bridge add-on (off until switched on from the Models panel menu). See claude_bridge.py.
try:
    import claude_bridge
    claude_bridge.setup()
except Exception as _e:
    import FreeCAD
    FreeCAD.Console.PrintWarning('Claude bridge failed to load: %s\n' % _e)
