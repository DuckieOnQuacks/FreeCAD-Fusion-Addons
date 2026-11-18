# Installs (or updates) the add-ons into FreeCAD's user add-on folder.
# In FreeCAD's Python console (View > Panels > Python Console) run, with your own path:
#     import runpy; runpy.run_path('/path/to/FreeCAD-Fusion-Addons/install.py')
# then restart FreeCAD.
import os, shutil
import FreeCAD as App

ADDONS = ('ModelBrowser', 'FusionLook', 'JointSlider', 'ClaudeBridge')
try:
    here = os.path.dirname(os.path.abspath(__file__))
except NameError:
    from PySide import QtWidgets
    here = QtWidgets.QFileDialog.getExistingDirectory(None, 'Choose the FreeCAD-Fusion-Addons folder')
mod = os.path.join(App.getUserAppDataDir(), 'Mod')
done = []
for name in ADDONS:
    src = os.path.join(here, name)
    if not os.path.isdir(src):
        print('missing:', src); continue
    dst = os.path.join(mod, name); os.makedirs(dst, exist_ok=True)
    for f in os.listdir(src):
        if f.endswith('.py'): shutil.copy(os.path.join(src, f), os.path.join(dst, f))
    done.append(name)
print('Installed %s into %s. Restart FreeCAD.' % (', '.join(done), mod))
