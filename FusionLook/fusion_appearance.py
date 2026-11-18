# Fusion-style appearance presets: glass, rubber, plastics, metals and paints, one click each.
# Part of the FusionLook add-on. Use the Appearance menu in the menu bar, or right-click a part >
# Appearance presets. Applies to the selected parts (a selected container applies to everything in it).
# The presets are also written to FreeCAD's user material library (folder "Appearance - Fusion Look"),
# so they show up in FreeCAD's own appearance pickers too.
import os, uuid
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

EDGE = (0.07, 0.08, 0.10)          # the thin dark edge FusionLook gives every part

# name, group, settings. diffuse = main colour, specular = highlight colour, shininess 0..1 (higher = tighter,
# brighter highlight), transparency 0..1, edge = edge line colour (default dark).
PRESETS = [
    ('Glass - Green Tint (E30)', 'Glass', dict(diffuse=(0.62, 0.80, 0.74), ambient=(0.10, 0.14, 0.13), specular=(1, 1, 1), shininess=0.90, transparency=0.72, edge=(0.45, 0.62, 0.56))),
    ('Glass - Clear', 'Glass', dict(diffuse=(0.82, 0.88, 0.92), ambient=(0.12, 0.13, 0.14), specular=(1, 1, 1), shininess=0.90, transparency=0.80, edge=(0.60, 0.68, 0.72))),
    ('Glass - Dark Tint', 'Glass', dict(diffuse=(0.10, 0.12, 0.13), ambient=(0.02, 0.02, 0.02), specular=(1, 1, 1), shininess=0.90, transparency=0.45, edge=(0.22, 0.26, 0.27))),
    ('Rubber - Black', 'Plastic and rubber', dict(diffuse=(0.045, 0.045, 0.05), ambient=(0.02, 0.02, 0.02), specular=(0.06, 0.06, 0.06), shininess=0.05, transparency=0.0, edge=(0.0, 0.0, 0.0))),
    ('Plastic - Black Matte (printed)', 'Plastic and rubber', dict(diffuse=(0.07, 0.07, 0.08), specular=(0.22, 0.22, 0.23), shininess=0.20, transparency=0.0)),
    ('Plastic - Black Gloss', 'Plastic and rubber', dict(diffuse=(0.03, 0.03, 0.035), specular=(0.90, 0.90, 0.90), shininess=0.85, transparency=0.0)),
    ('Plastic - Grey Trim', 'Plastic and rubber', dict(diffuse=(0.22, 0.22, 0.23), specular=(0.20, 0.20, 0.21), shininess=0.25, transparency=0.0)),
    ('Plastic - White', 'Plastic and rubber', dict(diffuse=(0.86, 0.86, 0.84), specular=(0.30, 0.30, 0.30), shininess=0.30, transparency=0.0)),
    ('Steel - Dark Satin (default)', 'Metal', dict(diffuse=(0.34, 0.35, 0.37), specular=(0.28, 0.28, 0.30), shininess=0.35, transparency=0.0)),
    ('Aluminium - Satin', 'Metal', dict(diffuse=(0.64, 0.65, 0.67), specular=(0.55, 0.55, 0.57), shininess=0.40, transparency=0.0)),
    ('Chrome', 'Metal', dict(diffuse=(0.75, 0.76, 0.78), ambient=(0.30, 0.30, 0.31), specular=(1, 1, 1), shininess=0.95, transparency=0.0)),
    ('Zinc Plated', 'Metal', dict(diffuse=(0.58, 0.60, 0.63), specular=(0.70, 0.72, 0.75), shininess=0.60, transparency=0.0)),
    ('Black Oxide', 'Metal', dict(diffuse=(0.08, 0.08, 0.09), specular=(0.35, 0.35, 0.37), shininess=0.45, transparency=0.0)),
    ('Brass', 'Metal', dict(diffuse=(0.60, 0.48, 0.20), specular=(0.85, 0.78, 0.55), shininess=0.55, transparency=0.0)),
    ('Copper', 'Metal', dict(diffuse=(0.62, 0.36, 0.24), specular=(0.85, 0.65, 0.55), shininess=0.55, transparency=0.0)),
    ('BMW Alpine White (approx.)', 'Paint', dict(diffuse=(0.92, 0.92, 0.89), specular=(0.90, 0.90, 0.90), shininess=0.75, transparency=0.0)),
    ('BMW Brilliant Red (approx.)', 'Paint', dict(diffuse=(0.70, 0.05, 0.06), specular=(0.90, 0.90, 0.90), shininess=0.75, transparency=0.0)),
    ('BMW Diamond Black Metallic (approx.)', 'Paint', dict(diffuse=(0.06, 0.06, 0.08), specular=(0.90, 0.90, 0.95), shininess=0.80, transparency=0.0)),
]
BY_NAME = {p[0]: p[2] for p in PRESETS}

_clip = None        # copied appearance: (material, edge colour)
_menu = None


# ---------------------------------------------------------------------------------------------
def material(spec):
    m = App.Material()
    f = lambda c: tuple(float(x) for x in c[:3]) + (1.0,)      # FreeCAD wants all floats
    d = f(spec['diffuse'])
    m.DiffuseColor = d
    m.AmbientColor = f(spec.get('ambient', tuple(c * 0.25 for c in d[:3])))
    m.SpecularColor = f(spec['specular'])
    m.EmissiveColor = (0.0, 0.0, 0.0, 1.0)
    m.Shininess = float(spec['shininess'])
    m.Transparency = float(spec['transparency'])
    return m


def _has_look(o):
    vo = getattr(o, 'ViewObject', None)
    return vo is not None and hasattr(vo, 'ShapeAppearance')


def targets(objs=None):
    """Objects to colour: the selection, with containers (Part, Assembly, groups, links) opened up."""
    if objs is None: objs = Gui.Selection.getSelection('*')
    out, seen = [], set()

    def add(o, depth=0):
        if o is None or depth > 12: return
        key = (o.Document.Name, o.Name)
        if key in seen: return
        seen.add(key)
        if o.isDerivedFrom('PartDesign::Body') or (_has_look(o) and o.isDerivedFrom('Part::Feature')):
            out.append(o); return
        if o.isDerivedFrom('App::Link'):
            add(o.getLinkedObject(True), depth + 1); return
        for k in (getattr(o, 'Group', None) or []):
            if k.isDerivedFrom('App::Origin') or k.TypeId in ('App::Line', 'App::Plane', 'App::Point'): continue
            add(k, depth + 1)

    for o in objs: add(o)
    return out


def _status(text):
    try: Gui.getMainWindow().statusBar().showMessage(text, 5000)
    except Exception: pass
    App.Console.PrintMessage('Appearance: %s\n' % text)


def apply(spec_or_name, objs=None, label=None):
    """Apply a preset (by name) or a settings dict to the selected parts. Returns how many were changed."""
    spec = BY_NAME[spec_or_name] if isinstance(spec_or_name, str) else spec_or_name
    label = label or (spec_or_name if isinstance(spec_or_name, str) else 'Custom')
    ts = targets(objs)
    if not ts:
        _status('select a part first (in the 3D view or the Model tree)')
        return 0
    m = material(spec)
    docs = {o.Document for o in ts}
    for d in docs: d.openTransaction('Appearance: ' + label)
    for o in ts:
        vo = o.ViewObject
        vo.ShapeAppearance = (m,)
        try: vo.LineColor = tuple(float(x) for x in spec.get('edge', EDGE))
        except Exception: pass
    for d in docs: d.commitTransaction()
    _status('%s applied to %d part%s' % (label, len(ts), '' if len(ts) == 1 else 's'))
    return len(ts)


def custom_colour():
    ts = targets()
    if not ts:
        _status('select a part first (in the 3D view or the Model tree)'); return
    try: start = QtGui.QColor.fromRgbF(*ts[0].ViewObject.ShapeAppearance[0].DiffuseColor[:3])
    except Exception: start = QtGui.QColor(180, 30, 30)
    c = QtWidgets.QColorDialog.getColor(start, Gui.getMainWindow(), 'Paint colour')
    if not c.isValid(): return
    apply(dict(diffuse=(c.redF(), c.greenF(), c.blueF()), specular=(0.9, 0.9, 0.9), shininess=0.75, transparency=0.0), ts, 'Custom paint')


def copy_look():
    global _clip
    ts = targets()
    if not ts:
        _status('select the part to copy from'); return
    vo = ts[0].ViewObject
    _clip = (vo.ShapeAppearance[0], tuple(vo.LineColor[:3]))
    _status('copied the look of %s' % ts[0].Label)


def paste_look():
    if _clip is None:
        _status('copy a look first'); return
    ts = targets()
    if not ts:
        _status('select the parts to paste onto'); return
    m, edge = _clip
    docs = {o.Document for o in ts}
    for d in docs: d.openTransaction('Appearance: paste')
    for o in ts:
        o.ViewObject.ShapeAppearance = (m,)
        try: o.ViewObject.LineColor = edge
        except Exception: pass
    for d in docs: d.commitTransaction()
    _status('pasted onto %d part%s' % (len(ts), '' if len(ts) == 1 else 's'))


# ---- swatches and the menu --------------------------------------------------------------------
def swatch(spec, size=16):
    pm = QtGui.QPixmap(size, size); pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm); p.setRenderHint(QtGui.QPainter.Antialiasing)
    r = QtCore.QRectF(0.5, 0.5, size - 1, size - 1)
    t = spec['transparency']
    if t > 0:   # checkerboard behind see-through looks
        for i in range(0, size, 4):
            for j in range(0, size, 4):
                p.fillRect(i, j, 4, 4, QtGui.QColor(200, 200, 200) if (i + j) // 4 % 2 else QtGui.QColor(120, 120, 120))
    base = QtGui.QColor.fromRgbF(*spec['diffuse']); base.setAlphaF(1.0 - t * 0.75)
    g = QtGui.QLinearGradient(0, 0, size, size)
    g.setColorAt(0.0, base.lighter(100 + int(spec['shininess'] * 80))); g.setColorAt(1.0, base)
    p.setBrush(QtGui.QBrush(g)); p.setPen(QtGui.QPen(QtGui.QColor(20, 20, 24), 1)); p.drawRoundedRect(r, 3, 3)
    p.end()
    return pm


def menu(parent):
    """The Appearance menu (built once)."""
    global _menu
    if _menu is not None: return _menu
    _menu = QtWidgets.QMenu('Appearance', parent); _menu.setObjectName('FusionLookAppearanceMenu')
    _menu.setToolTipsVisible(True)
    group = None
    for name, grp, spec in PRESETS:
        if grp != group:
            _menu.addSection(grp); group = grp
        a = _menu.addAction(QtGui.QIcon(swatch(spec)), name)
        a.setToolTip('Apply to the selected parts')
        a.triggered.connect(lambda checked=False, n=name: apply(n))
    _menu.addSeparator()
    _menu.addAction('Custom paint colour...').triggered.connect(lambda checked=False: custom_colour())
    _menu.addAction('Copy look from selected part').triggered.connect(lambda checked=False: copy_look())
    _menu.addAction('Paste look onto selected parts').triggered.connect(lambda checked=False: paste_look())
    _menu.addSeparator()
    _menu.addAction('More settings (FreeCAD Appearance dialog)...').triggered.connect(lambda checked=False: Gui.runCommand('Std_SetAppearance', 0))
    return _menu


# ---- right-click menu: a FreeCAD command group shown as a submenu after "Appearance..." -------------
def _icon_dir():
    d = os.path.join(App.getUserAppDataDir(), 'FusionLook', 'swatches'); os.makedirs(d, exist_ok=True); return d


class _PresetCommand:
    def __init__(self, name, icon): self.name, self.icon = name, icon
    def GetResources(self): return {'MenuText': self.name, 'ToolTip': 'Apply %s to the selected parts' % self.name, 'Pixmap': self.icon}
    def Activated(self): apply(self.name)
    def IsActive(self): return bool(Gui.Selection.getSelection('*'))


class _PresetGroup:
    def __init__(self, names): self.names = names
    def GetCommands(self): return self.names
    def GetResources(self): return {'MenuText': 'Appearance presets', 'ToolTip': 'Glass, rubber, plastics, metals and paints', 'DropDownMenu': True}
    def IsActive(self): return bool(Gui.Selection.getSelection('*'))


class _ContextManipulator:
    def modifyContextMenu(self, recipient):
        return [{'insert': 'FusionLook_AppearancePresets', 'menuItem': 'Std_SetAppearance', 'after': ''}]


# ---- FreeCAD's own material library ------------------------------------------------------------
def _user_material_dir():
    try:
        import Materials
        for lib in Materials.MaterialManager().MaterialLibraries:
            if isinstance(lib, (tuple, list)) and lib[0] == 'User': return lib[1]
    except Exception:
        pass
    return os.path.join(App.getUserAppDataDir(), 'Material')


def write_library():
    """Write the presets as appearance materials into FreeCAD's user material library (only files that changed)."""
    folder = os.path.join(_user_material_dir(), 'Appearance - Fusion Look'); os.makedirs(folder, exist_ok=True)
    col = lambda c: '"(%.4f, %.4f, %.4f, 1.0)"' % tuple(c)
    n = 0
    for name, grp, spec in PRESETS:
        d = tuple(spec['diffuse'])
        text = ('---\n# Written by the FusionLook add-on (fusion_appearance.py)\nGeneral:\n'
                '  UUID: "%s"\n  Author: "FusionLook"\n  License: "CC0-1.0"\n  Name: "%s"\n  Description: "%s appearance"\n'
                'AppearanceModels:\n  BasicRendering:\n    UUID: \'f006c7e4-35b7-43d5-bbf9-c5d572309e6e\'\n'
                '    AmbientColor: %s\n    DiffuseColor: %s\n    EmissiveColor: "(0.0000, 0.0000, 0.0000, 1.0)"\n'
                '    Shininess: "%.4f"\n    SpecularColor: %s\n    Transparency: "%.4f"\n') % (
            uuid.uuid5(uuid.NAMESPACE_URL, 'fusionlook/appearance/' + name), name, grp,
            col(spec.get('ambient', tuple(c * 0.25 for c in d))), col(d), spec['shininess'], col(spec['specular']), spec['transparency'])
        path = os.path.join(folder, name.replace('/', '-') + '.FCMat')
        try:
            if os.path.exists(path) and open(path, encoding='utf-8').read() == text: continue
        except Exception:
            pass
        with open(path, 'w', encoding='utf-8') as f: f.write(text)
        n += 1
    return n


def setup():
    """Called once from FusionLook at start-up."""
    try:
        names = []
        folder = _icon_dir()
        for i, (name, grp, spec) in enumerate(PRESETS):
            icon = os.path.join(folder, 'preset_%02d.png' % i); swatch(spec, 32).save(icon)
            cmd = 'FusionLook_Appearance_%02d' % i
            Gui.addCommand(cmd, _PresetCommand(name, icon)); names.append(cmd)
        Gui.addCommand('FusionLook_AppearancePresets', _PresetGroup(names))
        Gui.addWorkbenchManipulator(_ContextManipulator())
    except Exception as e:
        App.Console.PrintWarning('Appearance presets: right-click menu not added (%s)\n' % e)
    try: write_library()
    except Exception as e: App.Console.PrintWarning('Appearance presets: material library not written (%s)\n' % e)
