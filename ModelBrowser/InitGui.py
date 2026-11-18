# Models panel add-on: shows the FreeCAD files in a folder as a docked list. See model_browser.py.
try:
    import model_browser
    model_browser.setup()
except Exception as _e:
    import FreeCAD
    FreeCAD.Console.PrintWarning('Models panel failed to load: %s\n' % _e)
