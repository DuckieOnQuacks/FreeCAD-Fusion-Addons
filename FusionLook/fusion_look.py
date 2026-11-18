# Fusion-style look for FreeCAD's 3D view: draws a ground grid on the XY plane in every 3D view.
# Also loads fusion_appearance.py (Appearance menu: glass, rubber, plastics, metals, paints).
# Installed as an add-on (Mod/FusionLook). To remove it, delete that folder. View > Ground Grid toggles it.
import math
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets
from pivy import coin

PARAM = 'User parameter:BaseApp/Preferences/Mod/FusionLook'
NODE = 'FusionLookGrid'
MINOR = (0.205, 0.232, 0.283)     # thin lines, just lighter than the background
MAJOR = (0.262, 0.295, 0.355)     # every tenth line
_timer = None


STEEL = (0.34, 0.35, 0.37)        # dark satin steel, close to how plain bodies read in Fusion's dark view
EDGE = (0.07, 0.08, 0.10)


def _plain_grey(c):
    r, g, b = c[0], c[1], c[2]
    return abs(r - g) < 0.03 and abs(g - b) < 0.03 and 0.45 <= r <= 0.95


def style_doc(doc):
    """Thin dark edges on every part; parts that are plain light grey become dark steel. Coloured parts are left alone."""
    n = 0
    for o in doc.Objects:
        try:
            if not o.isDerivedFrom('Part::Feature'): continue
            vo = o.ViewObject
            vo.LineWidth = 1.0; vo.LineColor = EDGE
            try: cols = list(vo.DiffuseColor)
            except Exception: cols = []
            if not cols: cols = [vo.ShapeColor]
            if all(_plain_grey(c) for c in cols):
                t = vo.Transparency
                vo.ShapeColor = STEEL
                try:
                    m = vo.ShapeAppearance[0]
                    m.SpecularColor = (0.28, 0.28, 0.30, 1.0); m.Shininess = 0.35
                    vo.ShapeAppearance = (m,)
                except Exception:
                    pass
                vo.Transparency = t
                n += 1
        except Exception:
            pass
    return n


def enabled():
    return App.ParamGet(PARAM).GetBool('ShowGrid', True)


def _dims(doc):
    """Grid half-size and line spacing (mm) chosen from how far the model reaches from the origin."""
    half = 0.0
    for o in doc.Objects:
        try:
            if not o.isDerivedFrom('Part::Feature') or o.Shape.isNull(): continue
            m = o.getGlobalPlacement().multiply(o.Placement.inverse()).toMatrix()
            b = o.Shape.BoundBox.transformed(m)
            half = max(half, abs(b.XMin), abs(b.XMax), abs(b.YMin), abs(b.YMax))
        except Exception:
            pass
    if half < 1.0: half = 100.0
    minor = 10.0 ** math.floor(math.log10(half / 5.0))
    minor = min(max(minor, 1.0), 1000.0)
    major = minor * 10.0
    size = max(math.ceil(half * 2.5 / major) * major, major * 2.0)
    return size, minor


def _grid(size, minor):
    root = None
    try: root = coin.SoType.fromName('SoSkipBoundingGroup').createInstance()   # keeps the grid out of "fit all"
    except Exception: root = None
    if root is None or not hasattr(root, 'addChild'): root = coin.SoSeparator()
    sw = coin.SoSwitch(); sw.setName(NODE)
    sep = coin.SoSeparator()
    ps = coin.SoPickStyle(); ps.style = coin.SoPickStyle.UNPICKABLE
    lm = coin.SoLightModel(); lm.model = coin.SoLightModel.BASE_COLOR
    sep.addChild(ps); sep.addChild(lm)
    n = int(round(size / minor))
    for major_pass in (False, True):
        pts = []
        for i in range(-n, n + 1):
            if (i % 10 == 0) != major_pass: continue
            v = i * minor
            pts += [(v, -size, 0.0), (v, size, 0.0), (-size, v, 0.0), (size, v, 0.0)]
        if not pts: continue
        g = coin.SoSeparator()
        col = coin.SoBaseColor(); col.rgb.setValue(*(MAJOR if major_pass else MINOR))
        ds = coin.SoDrawStyle(); ds.lineWidth = 1
        co = coin.SoCoordinate3(); co.point.setValues(0, len(pts), pts)
        ls = coin.SoLineSet(); ls.numVertices.setValues(0, len(pts) // 2, [2] * (len(pts) // 2))
        for x in (col, ds, co, ls): g.addChild(x)
        sep.addChild(g)
    root.addChild(sep); sw.addChild(root)
    sw.whichChild = coin.SO_SWITCH_ALL if enabled() else coin.SO_SWITCH_NONE
    return sw


def _find(sg):
    for i in range(sg.getNumChildren()):
        c = sg.getChild(i)
        try:
            if c.getName().getString() == NODE: return c
        except Exception:
            pass
    return None


def attach_all(rebuild=False):
    count = 0
    for d in list(App.listDocuments().values()):
        try:
            gd = Gui.getDocument(d.Name)
            for v in gd.mdiViewsOfType('Gui::View3DInventor'):
                sg = v.getSceneGraph(); node = _find(sg)
                if node is not None and rebuild:
                    sg.removeChild(node); node = None
                if node is None:
                    size, minor = _dims(d); sg.addChild(_grid(size, minor))
                else:
                    node.whichChild = coin.SO_SWITCH_ALL if enabled() else coin.SO_SWITCH_NONE
                count += 1
        except Exception:
            pass
    return count


class _ToggleGrid:
    def GetResources(self):
        return {'MenuText': 'Ground Grid', 'ToolTip': 'Show or hide the ground grid in the 3D view (resized to fit the model each time it is turned on)'}

    def Activated(self):
        p = App.ParamGet(PARAM); p.SetBool('ShowGrid', not p.GetBool('ShowGrid', True))
        attach_all(rebuild=enabled())

    def IsActive(self):
        return True


class _Manipulator:
    def modifyMenuBar(self):
        return [{'append': 'FusionLook_ToggleGrid', 'menuItem': 'Std_ViewStatusBar'}]


# ---- text labels under the toolbar icons ----
def labels_on():
    return App.ParamGet(PARAM).GetBool('ToolbarLabels', True)


def apply_labels():
    """Show each toolbar button's name under its icon (or icons only when switched off). Re-applied as FreeCAD rebuilds toolbars."""
    want = QtCore.Qt.ToolButtonTextUnderIcon if labels_on() else QtCore.Qt.ToolButtonIconOnly
    n = 0
    for tb in Gui.getMainWindow().findChildren(QtWidgets.QToolBar):
        try:
            if tb.toolButtonStyle() != want:
                tb.setToolButtonStyle(want)
                tb.setStyleSheet('QToolButton { font-size: 10px; }' if labels_on() else '')
            n += 1
        except Exception:
            pass
    return n


# ---- "Panels" menu in the top menu bar ----
MENU_NAME = 'FusionLookPanelsMenu'
# ---- panel layout: repair and reset --------------------------------------------------------
# FreeCAD's main window can get stuck with its panel layout frozen (panels drawn on top of each other, new panels
# never placed). Saving the layout and loading it straight back un-sticks it without moving anything.
TREE_NAMES = ('Model', 'Combo View', 'Tree view')


def in_overlay(d):
    """True when a panel is held by FreeCAD's overlay (transparent panels over the 3D view) instead of docked."""
    p = d.parentWidget()
    while p is not None:
        if 'Overlay' in p.metaObject().className(): return True
        p = p.parentWidget()
    return False


def docked(d):
    """True for a panel that sits in the main window's normal dock layout."""
    return d is not None and not d.isFloating() and not in_overlay(d) and d.parentWidget() == Gui.getMainWindow()


def tree_dock():
    """FreeCAD's own model tree panel (or None)."""
    for o in Gui.getMainWindow().findChildren(QtWidgets.QDockWidget):
        if o.objectName() in TREE_NAMES or o.windowTitle() in TREE_NAMES: return o
    return None


def layout_broken():
    """True when two docked panels overlap, or one overlaps the 3D view: the sign of a frozen layout."""
    mw = Gui.getMainWindow(); rects = []
    for d in mw.findChildren(QtWidgets.QDockWidget):
        if not d.isVisible() or not docked(d): continue
        g = d.geometry()
        if g.right() < 0 or g.bottom() < 0: continue          # a tab that is not in front: Qt parks it off-screen
        rects.append((d.objectName(), g))
    c = mw.centralWidget().geometry() if mw.centralWidget() is not None else None
    for i, (name, a) in enumerate(rects):
        if c is not None and name != 'Ribbon' and a.intersects(c): return True
        for _, b in rects[i + 1:]:
            if a.intersects(b): return True
    return False


def unfreeze():
    mw = Gui.getMainWindow()
    return bool(mw.restoreState(mw.saveState()))


def heal_layout():
    """Run at start-up: un-stick the layout only if it looks broken."""
    try:
        if layout_broken():
            unfreeze()
            App.Console.PrintMessage('Fusion look: panel layout was stuck; repaired\n')
            return True
    except Exception as e:
        App.Console.PrintWarning('Fusion look: layout check failed (%s)\n' % e)
    return False


_bad = 0; _heals = 0


def _watch_layout():
    """Called every couple of seconds: repair a layout that stays broken (at most three times per session)."""
    global _bad, _heals
    if _heals >= 3: return
    if QtWidgets.QApplication.mouseButtons() != QtCore.Qt.NoButton or not layout_broken():   # never while a panel is being dragged
        _bad = 0; return
    _bad += 1
    if _bad >= 3:
        _bad = 0; _heals += 1
        unfreeze()
        App.Console.PrintMessage('Fusion look: panel layout was stuck; repaired\n')


def reset_panels():
    """Panels menu > Reset Panel Layout: Models at the far left, then the Model tree with Joint Slider as a tab behind it."""
    mw = Gui.getMainWindow()
    unfreeze()
    by = {d.objectName(): d for d in mw.findChildren(QtWidgets.QDockWidget)}
    models, joint, tree = by.get('ModelBrowserDock'), by.get('JointSliderDock'), tree_dock()
    if tree is not None and (tree.isFloating() or in_overlay(tree)): tree = None      # leave floating / overlay panels alone
    left = QtCore.Qt.LeftDockWidgetArea
    first = next((d for d in (models, tree, joint) if d is not None), None)
    if first is None: return
    mw.addDockWidget(left, first)
    if models is not None and tree is not None: mw.splitDockWidget(models, tree, QtCore.Qt.Horizontal)
    if joint is not None:
        if tree is not None: mw.tabifyDockWidget(tree, joint)
        elif models is not None: mw.tabifyDockWidget(models, joint)
    for d in (models, tree, joint):
        if d is not None: d.show()
    if tree is not None: tree.raise_()

    def size():
        ds = [d for d in (models, tree) if d is not None]
        if ds: mw.resizeDocks(ds, [280, 300][:len(ds)], QtCore.Qt.Horizontal)
    QtCore.QTimer.singleShot(500, size)                       # after the layout settles



_menu = None; _acts = {}


def _dock_toggle(module):
    def run():
        try:
            m = __import__(module); d = m.dock()
            if d is None: m.install()
            else: d.setVisible(not d.isVisible())
        except Exception as e:
            App.Console.PrintWarning('Panels menu: %s\n' % e)
    return run


def _dock_shown(module):
    try:
        d = __import__(module).dock()
        return bool(d is not None and d.isVisible())
    except Exception:
        return False


def _bridge_toggle():
    try:
        import claude_bridge; claude_bridge.toggle()
    except Exception as e:
        App.Console.PrintWarning('Panels menu: %s\n' % e)


def _bridge_on():
    try:
        import claude_bridge; return claude_bridge.is_on()
    except Exception:
        return False


def _toggle_labels():
    p = App.ParamGet(PARAM); p.SetBool('ToolbarLabels', not p.GetBool('ToolbarLabels', True)); apply_labels()


def _sync_menu():
    state = {'Models': _dock_shown('model_browser'), 'Joint Slider': _dock_shown('joint_slider'), 'Ground Grid': enabled(),
             'Toolbar Labels': labels_on(), 'Claude Bridge': _bridge_on()}
    for name, a in _acts.items():
        a.blockSignals(True); a.setChecked(bool(state.get(name))); a.blockSignals(False)


def build_menu():
    """Add (or bring back) the Panels menu. FreeCAD hides menus it does not own whenever the workbench changes, so this is re-run."""
    global _menu
    mb = Gui.getMainWindow().menuBar()
    if _menu is None:
        _menu = QtWidgets.QMenu('Panels', mb); _menu.setObjectName(MENU_NAME)
        items = (('Models', _dock_toggle('model_browser')), ('Joint Slider', _dock_toggle('joint_slider')), None,
                 ('Ground Grid', lambda: _ToggleGrid().Activated()), ('Toolbar Labels', _toggle_labels), None, ('Claude Bridge', _bridge_toggle))
        for it in items:
            if it is None: _menu.addSeparator(); continue
            a = _menu.addAction(it[0]); a.setCheckable(True); a.triggered.connect(lambda checked=False, f=it[1]: (f(), _sync_menu()))
            _acts[it[0]] = a
        _menu.addSeparator(); _menu.addAction('Reset Panel Layout').triggered.connect(lambda checked=False: reset_panels())
        _menu.aboutToShow.connect(_sync_menu)
        mb.addMenu(_menu)
    act = _menu.menuAction()
    if not any(a == act for a in mb.actions()): mb.addAction(act)     # FreeCAD (or the Ribbon) dropped it: put it back once
    if not act.isVisible(): act.setVisible(True)
    try:   # the Appearance menu sits just before Panels
        import fusion_appearance
        aact = fusion_appearance.menu(mb).menuAction()
        if not any(x == aact for x in mb.actions()): mb.insertAction(act, aact)
        if not aact.isVisible(): aact.setVisible(True)
    except Exception:
        aact = None
    try: _sync_ribbon_menu([x for x in (aact, act) if x is not None])
    except Exception: pass
    return True


def _sync_ribbon_menu(ours):
    """FreeCAD Ribbon hides the menu bar (on Windows / Linux) and copies its menus into its Menu button when it builds
    that menu, which can be before our menus exist. Put ours in (before Help) and drop stale copies."""
    mw = Gui.getMainWindow()
    for btn in mw.findChildren(QtWidgets.QToolButton):
        if type(btn).__name__ != 'RibbonApplicationButton': continue
        m = btn.menu()
        if m is None: continue
        names = (MENU_NAME, 'FusionLookAppearanceMenu')
        for x in m.actions():   # copies of an older Panels / Appearance menu (after a reload)
            if x.menu() is not None and x.menu().objectName() in names and not any(x == o for o in ours): m.removeAction(x)
        help_act = next((x for x in m.actions() if x.text().replace('&', '').strip() == 'Help'), None)
        for o in ours:
            if not any(x == o for x in m.actions()):
                if help_act is not None: m.insertAction(help_act, o)
                else: m.addAction(o)


def _tick():
    n = attach_all()
    try: apply_labels()
    except Exception: pass
    try: build_menu()
    except Exception: pass
    try: _watch_layout()
    except Exception: pass
    return n


def start_timer():
    global _timer
    if _timer is None:
        mw = Gui.getMainWindow()
        _timer = QtCore.QTimer(mw); _timer.setInterval(2000)
        _timer.timeout.connect(lambda: _tick())
        _timer.start()
        try: mw.workbenchActivated.connect(lambda *_: QtCore.QTimer.singleShot(300, _tick))
        except Exception: pass
    return _tick()


def setup():
    """Called once at FreeCAD start-up."""
    try:
        import fusion_appearance; fusion_appearance.setup()
    except Exception as e:
        App.Console.PrintWarning('Fusion look: appearance presets not loaded (%s)\n' % e)
    try:
        Gui.addCommand('FusionLook_ToggleGrid', _ToggleGrid())
        Gui.addWorkbenchManipulator(_Manipulator())
    except Exception as e:
        App.Console.PrintWarning('Fusion look: menu entry not added (%s)\n' % e)
    QtCore.QTimer.singleShot(2000, start_timer)
    QtCore.QTimer.singleShot(6000, heal_layout)          # after every add-on has placed its panels
