# Helper library for Claude bridge jobs. Jobs start with:  from claude_lib import *
# This file lives in ~/FreeCAD Models/_bridge/lib and is reloaded automatically when it changes.
import os, math, time, json
import FreeCAD as App
import FreeCADGui as Gui
import Part
V = App.Vector
MODELS = os.path.expanduser('~/FreeCAD Models')
__all__ = ['V', 'MODELS', 'App', 'Gui', 'Part', 'math', 'os', 'open_model', 'view3d', 'snap', 'info', 'bbox', 'world_shape', 'clash', 'style',
           'save', 'add', 'box', 'cyl', 'prism', 'bar', 'assembly', 'joints', 'jvalue']


def open_model(name):
    """Open (or return the already-open) model. `name` is a file name in FreeCAD Models without .FCStd, or a full path."""
    path = name if os.path.isabs(name) else os.path.join(MODELS, name + ('' if name.lower().endswith('.fcstd') else '.FCStd'))
    for d in App.listDocuments().values():
        if d.FileName and os.path.exists(d.FileName) and os.path.samefile(d.FileName, path):
            App.setActiveDocument(d.Name); return d
    return App.openDocument(path)


def view3d(doc=None):
    d = doc or App.ActiveDocument
    vs = Gui.getDocument(d.Name).mdiViewsOfType('Gui::View3DInventor')
    return vs[0] if vs else None


def snap(views=('iso',), tag='', w=1200, h=900, fit=True, doc=None):
    """Save pictures of the 3D view to the outbox. views: iso, front, rear, top, bottom, left, right, current. The user's camera is put back afterwards."""
    import claude_bridge
    v = view3d(doc)
    if v is None: raise Exception('no 3D view')
    p = App.ParamGet('User parameter:BaseApp/Preferences/View'); anim = p.GetBool('UseNavigationAnimations', True)
    p.SetBool('UseNavigationAnimations', False)
    cam = v.getCamera(); paths = []
    try:
        for name in views:
            f = dict(iso=v.viewIsometric, front=v.viewFront, rear=v.viewRear, top=v.viewTop, bottom=v.viewBottom, left=v.viewLeft, right=v.viewRight).get(name)
            if f: f()
            if fit and name != 'current': v.fitAll()
            for _ in range(8):
                Gui.updateGui(); time.sleep(0.03)
            path = os.path.join(claude_bridge.OUTBOX, '%s%s_%s.png' % (claude_bridge.JOB or 'snap', ('_' + tag) if tag else '', name))
            v.saveImage(path, w, h, 'Current'); paths.append(path)
    finally:
        try: v.setCamera(cam)
        except Exception: pass
        p.SetBool('UseNavigationAnimations', anim)
        Gui.updateGui()
    return paths


def world_shape(o):
    sh = o.Shape.copy(); sh.Placement = o.getGlobalPlacement(); return sh


def bbox(doc=None):
    d = doc or App.ActiveDocument; bb = None
    for o in d.Objects:
        if o.isDerivedFrom('Part::Feature') and not o.Shape.isNull():
            b = world_shape(o).BoundBox; bb = b if bb is None else bb.united(b)
    return bb


def info(doc=None, limit=80):
    """Print a compact table of the solids in a document: label, type, volume, bounding box (world), colour."""
    d = doc or App.ActiveDocument; rows = []
    for o in d.Objects:
        if not o.isDerivedFrom('Part::Feature') or o.Shape.isNull(): continue
        s = world_shape(o); b = s.BoundBox
        rows.append('%-40s %-14s vol %10.1f  x %7.1f..%-7.1f y %7.1f..%-7.1f z %7.1f..%-7.1f' % (o.Label[:40], o.Name[:14], s.Volume, b.XMin, b.XMax, b.YMin, b.YMax, b.ZMin, b.ZMax))
    print('%s: %d solids' % (d.Label, len(rows)))
    for r in rows[:limit]: print(r)
    return len(rows)


def clash(objs=None, doc=None, tol=0.5):
    """Pairwise interference volumes (mm3) between solids; returns [(labelA, labelB, volume)] above tol."""
    d = doc or App.ActiveDocument
    objs = objs or [o for o in d.Objects if o.isDerivedFrom('Part::Feature') and not o.Shape.isNull() and o.Shape.Solids]
    shapes = [(o.Label, world_shape(o)) for o in objs]; out = []
    for i in range(len(shapes)):
        for k in range(i + 1, len(shapes)):
            a, b = shapes[i][1], shapes[k][1]
            if not a.BoundBox.intersect(b.BoundBox): continue
            try: v = a.common(b).Volume
            except Exception: v = -1.0
            if v > tol or v < 0: out.append((shapes[i][0], shapes[k][0], round(v, 1)))
    return sorted(out, key=lambda t: -t[2])


def style(doc=None):
    import fusion_look
    return fusion_look.style_doc(doc or App.ActiveDocument)


def save(doc=None, path=None):
    """Save with a proper preview picture (fits the view first). Does not leave a backup file behind."""
    d = doc or App.ActiveDocument
    prefs = App.ParamGet('User parameter:BaseApp/Preferences/Document'); keep = prefs.GetBool('CreateBackupFiles', True)
    prefs.SetBool('CreateBackupFiles', False)
    try:
        v = view3d(d)
        if v is not None:
            cam = v.getCamera(); v.viewIsometric(); v.fitAll()
            for _ in range(6): Gui.updateGui()
        if path: d.saveAs(path)
        else: d.save()
        if v is not None:
            try: v.setCamera(cam)
            except Exception: pass
    finally:
        prefs.SetBool('CreateBackupFiles', keep)
    return d.FileName


# ---- simple solids (mm). All return Part shapes; add() puts one in the document. ----
def box(x0, y0, z0, x1, y1, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(center, r, z0, z1, axis=(0, 0, 1)):
    """Cylinder of radius r. With the default axis, center is (x, y) and it runs from z0 to z1; otherwise center is the 3D start point and z1 - z0 the length."""
    a = V(*axis)
    base = V(center[0], center[1], z0) if len(center) == 2 else V(*center)
    return Part.makeCylinder(r, z1 - z0, base, a)


def prism(points, z0, z1):
    """Extrude a closed polygon [(x, y), ...] from z0 to z1."""
    pts = [V(p[0], p[1], z0) for p in points]; pts.append(pts[0])
    return Part.Face(Part.makePolygon(pts)).extrude(V(0, 0, z1 - z0))


def bar(a, b, w, z0, z1):
    """Flat bar with round ends between points a and b (x, y), width w."""
    d = V(b[0] - a[0], b[1] - a[1], 0); L = d.Length; d.normalize(); n = V(-d.y, d.x, 0) * (w / 2.0)
    A = V(a[0], a[1], z0); B = V(b[0], b[1], z0)
    body = Part.Face(Part.makePolygon([A + n, B + n, B - n, A - n, A + n])).extrude(V(0, 0, z1 - z0))
    return body.fuse([cyl(a, w / 2.0, z0, z1), cyl(b, w / 2.0, z0, z1)]).removeSplitter()


def add(shape, name, doc=None, color=None, transparency=None):
    d = doc or App.ActiveDocument
    o = d.addObject('Part::Feature', ''.join(c if c.isalnum() else '_' for c in name)); o.Label = name; o.Shape = shape
    try:
        import fusion_look
        o.ViewObject.LineWidth = 1.0; o.ViewObject.LineColor = fusion_look.EDGE; o.ViewObject.ShapeColor = color or fusion_look.STEEL
    except Exception:
        if color: o.ViewObject.ShapeColor = color
    if transparency is not None: o.ViewObject.Transparency = transparency
    return o


# ---- assemblies ----
def assembly(doc=None):
    d = doc or App.ActiveDocument
    return next((o for o in d.Objects if o.TypeId == 'Assembly::AssemblyObject'), None)


def joints(doc=None):
    import UtilsAssembly
    a = assembly(doc)
    return [j for j in UtilsAssembly.getJointGroup(a).Group if hasattr(j, 'JointType')] if a is not None else []


def jvalue(j):
    import UtilsAssembly
    return math.degrees(UtilsAssembly.getJointXYAngle(j)) if j.JointType == 'Revolute' else UtilsAssembly.getJointDistance(j)
