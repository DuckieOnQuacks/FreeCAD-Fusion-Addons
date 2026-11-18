# Joint slider for FreeCAD assemblies: pick a revolute or slider joint and move it with a slider, a typed value, or Play.
# Installed as an add-on (Mod/JointSlider). To remove it, delete that folder.
import math
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

DOCK_NAME = 'JointSliderDock'
V = App.Vector
STEPS = 1000


def _assembly(doc):
    if doc is None: return None
    try:
        import UtilsAssembly
        a = UtilsAssembly.activeAssembly()
        if a is not None and a.Document == doc: return a
    except Exception:
        pass
    for o in doc.Objects:
        if o.TypeId == 'Assembly::AssemblyObject': return o
    return None


def _joints(asm):
    import UtilsAssembly
    out = []
    try:
        for j in UtilsAssembly.getJointGroup(asm).Group:
            if getattr(j, 'JointType', None) in ('Revolute', 'Slider') and j.Reference1 and j.Reference2 and j.Reference1[0] and j.Reference2[0]:
                out.append(j)
    except Exception:
        pass
    return out


def _value(j):
    import UtilsAssembly
    if j.JointType == 'Revolute': return math.degrees(UtilsAssembly.getJointXYAngle(j))
    return UtilsAssembly.getJointDistance(j)


def _num(q):
    return float(getattr(q, 'Value', q))


class Panel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.asm = None; self.joints = []; self.key = None; self.ranges = {}; self.reach = {}
        self.busy = False; self.txn = False; self.direction = 1.0
        lay = QtWidgets.QVBoxLayout(self); lay.setContentsMargins(6, 6, 6, 6); lay.setSpacing(6)
        self.title = QtWidgets.QLabel('No assembly open'); self.title.setWordWrap(True)
        lay.addWidget(self.title)
        self.combo = QtWidgets.QComboBox(); self.combo.currentIndexChanged.connect(self.jointChanged)
        lay.addWidget(self.combo)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal); self.slider.setRange(0, STEPS)
        self.slider.sliderPressed.connect(self.begin); self.slider.sliderReleased.connect(self.end)
        self.slider.valueChanged.connect(self.sliderChanged)
        lay.addWidget(self.slider)
        row = QtWidgets.QHBoxLayout()
        self.minBtn = QtWidgets.QToolButton(); self.minBtn.setText('Min'); self.minBtn.clicked.connect(lambda: self.goto(0))
        self.spin = QtWidgets.QDoubleSpinBox(); self.spin.setDecimals(1); self.spin.setKeyboardTracking(False)
        self.spin.valueChanged.connect(self.spinChanged)
        self.maxBtn = QtWidgets.QToolButton(); self.maxBtn.setText('Max'); self.maxBtn.clicked.connect(lambda: self.goto(1))
        self.playBtn = QtWidgets.QToolButton(); self.playBtn.setText('Play'); self.playBtn.setCheckable(True); self.playBtn.toggled.connect(self.playToggled)
        row.addWidget(self.minBtn); row.addWidget(self.spin, 1); row.addWidget(self.maxBtn); row.addWidget(self.playBtn)
        lay.addLayout(row)
        self.status = QtWidgets.QLabel(''); self.status.setWordWrap(True); self.status.setEnabled(False)
        lay.addWidget(self.status); lay.addStretch(1)
        self.poll = QtCore.QTimer(self); self.poll.setInterval(1000); self.poll.timeout.connect(self.sync); self.poll.start()
        self.player = QtCore.QTimer(self); self.player.setInterval(40); self.player.timeout.connect(self.tick)
        self.sync()

    # ---- keeping the panel in step with FreeCAD ----
    def joint(self):
        i = self.combo.currentIndex()
        return self.joints[i] if 0 <= i < len(self.joints) else None

    def range(self, j):
        k = (j.Document.Name, j.Name)
        if k in self.reach: return self.reach[k]
        return self.limits(j)

    def limits(self, j):
        if j.JointType == 'Revolute':
            lo = _num(j.AngleMin) if j.EnableAngleMin else None; hi = _num(j.AngleMax) if j.EnableAngleMax else None
            if lo is None: lo = -180.0 if hi is None else hi - 360.0
            if hi is None: hi = lo + 360.0
            return lo, hi
        lo = _num(j.LengthMin) if j.EnableLengthMin else None; hi = _num(j.LengthMax) if j.EnableLengthMax else None
        if lo is None or hi is None:
            k = (j.Document.Name, j.Name)
            if k not in self.ranges:
                v = _value(j); self.ranges[k] = (round(v - 50.0), round(v + 50.0))
            a, b = self.ranges[k]
            lo = a if lo is None else lo; hi = b if hi is None else hi
        return lo, hi

    def sync(self):
        if self.busy or self.player.isActive(): return
        try:
            doc = App.ActiveDocument; asm = _assembly(doc)
            joints = _joints(asm) if asm is not None else []
            key = (doc.Name if doc else None, asm.Name if asm is not None else None, tuple(j.Name for j in joints))
            if key != self.key:
                if joints: joints = self.drivable(asm, joints)
                self.key = key; self.asm = asm; self.joints = joints
                self.combo.blockSignals(True); self.combo.clear()
                for j in joints: self.combo.addItem('%s  (%s)' % (j.Label, 'turn' if j.JointType == 'Revolute' else 'slide'))
                pick = next((i for i, j in enumerate(joints) if (j.JointType == 'Revolute' and j.EnableAngleMin and j.EnableAngleMax)), 0)
                self.combo.setCurrentIndex(pick if joints else -1); self.combo.blockSignals(False)
                self.title.setText(asm.Label if asm is not None else 'No assembly in this document')
                self.status.setText('' if joints else 'Open a model that has movable joints.')
                for w in (self.combo, self.slider, self.spin, self.minBtn, self.maxBtn, self.playBtn): w.setEnabled(bool(joints))
                self.jointChanged()
            else:
                self.show_value()
        except Exception as e:
            self.status.setText('Joint panel: %s' % str(e)[:80])

    def jointChanged(self, *_):
        j = self.joint()
        if j is None: return
        lo, hi = self.range(j)
        self.spin.blockSignals(True)
        self.spin.setRange(lo, hi); self.spin.setSuffix(' °' if j.JointType == 'Revolute' else ' mm')
        self.spin.setSingleStep(1.0); self.spin.blockSignals(False)
        self.show_value()

    def show_value(self):
        j = self.joint()
        if j is None: return
        try:
            lo, hi = self.range(j); v = _value(j)
            self.slider.blockSignals(True); self.spin.blockSignals(True)
            self.slider.setValue(int(round(STEPS * (min(max(v, lo), hi) - lo) / (hi - lo))) if hi > lo else 0)
            self.spin.setValue(v)
            self.slider.blockSignals(False); self.spin.blockSignals(False)
        except Exception:
            self.slider.blockSignals(False); self.spin.blockSignals(False)

    # ---- moving ----
    def begin(self):
        if self.asm is not None and not self.txn:
            try: self.asm.Document.openTransaction('Move joint'); self.txn = True
            except Exception: pass

    def end(self):
        if self.txn:
            try: self.asm.Document.commitTransaction()
            except Exception: pass
            self.txn = False
        try: self.asm.Document.recompute()
        except Exception: pass
        self.show_value()

    def sliderChanged(self, pos):
        j = self.joint()
        if j is None or self.busy: return
        lo, hi = self.range(j)
        own = not self.txn
        if own: self.begin()
        self.drive(j, lo + (hi - lo) * pos / float(STEPS))
        if own: self.end()

    def spinChanged(self, v):
        j = self.joint()
        if j is None or self.busy: return
        self.begin(); self.drive(j, v); self.end()

    def goto(self, end):
        j = self.joint()
        if j is None: return
        lo, hi = self.range(j)
        self.begin(); self.drive(j, hi if end else lo); self.end()

    def playToggled(self, on):
        if on:
            self.begin(); self.player.start(); self.playBtn.setText('Stop')
        else:
            self.player.stop(); self.playBtn.setText('Play'); self.end()

    def tick(self):
        try:
            self._tick()
        except Exception:
            self.playBtn.setChecked(False)

    def _tick(self):
        j = self.joint()
        if j is None:
            self.playBtn.setChecked(False); return
        lo, hi = self.range(j); v = _value(j); step = (hi - lo) / 90.0
        t = v + self.direction * step
        if t >= hi: t = hi; self.direction = -1.0
        elif t <= lo: t = lo; self.direction = 1.0
        if not self.drive(j, t):
            self.direction = -self.direction
        self.show_value()

    def drive(self, j, target, quiet=False):
        """Move the joint to `target` (degrees or mm): turn / slide the part on the far side of the joint, hold it there with
        a temporary ground, and let the solver bring everything else along. Every step is checked; one that would shift
        a fixed part, break a joint or pass a limit is undone. (Pinning the joint with a temporary Fixed joint was tried
        and is not reliable: the solver sometimes moves grounded parts instead.)"""
        import UtilsAssembly, JointObject
        asm = self.asm
        if asm is None or self.busy: return False
        self.busy = True; ok = True; hold = None
        try:
            doc = asm.Document; rev = j.JointType == 'Revolute'
            lo, hi = self.range(j)
            # stay a hair inside any enabled limit: the solver refuses a pose that sits exactly on one
            m = 0.05
            lim_lo = j.EnableAngleMin if rev else j.EnableLengthMin; lim_hi = j.EnableAngleMax if rev else j.EnableLengthMax
            target = min(max(target, lo + (m if lim_lo else 0.0)), hi - (m if lim_hi else 0.0))
            p1, p2 = j.Reference1[0], j.Reference2[0]
            part, sign = p2, 1.0
            if asm.isPartGrounded(p2) and not asm.isPartGrounded(p1): part, sign = p1, -1.0
            if asm.isPartGrounded(part):
                if not quiet: self.status.setText('Both sides of this joint are fixed.')
                return False
            jg = UtilsAssembly.getJointGroup(asm)
            comps = [o for o in asm.Group if hasattr(o, 'Placement') and o.TypeId not in ('Assembly::JointGroup', 'App::Origin')]
            fixed = [o for o in comps if asm.isPartGrounded(o)]
            alljoints = [q for q in jg.Group if getattr(q, 'JointType', None) in ('Fixed', 'Revolute', 'Slider', 'Cylindrical') and q.Reference1 and q.Reference2]

            def state():
                return dict((o.Name, App.Placement(o.Placement)) for o in comps)

            def restore(st):
                for o in comps: o.Placement = st[o.Name]

            def valid(before, want):
                for o in fixed:                                   # nothing that is fixed may move
                    a, b = before[o.Name], o.Placement
                    if (a.Base - b.Base).Length > 1e-4 or (a.Rotation.inverted() * b.Rotation).Angle > 1e-5: return False
                for q in alljoints:
                    g1 = UtilsAssembly.getJcsGlobalPlc(q.Placement1, q.Reference1); g2 = UtilsAssembly.getJcsGlobalPlc(q.Placement2, q.Reference2)
                    z1 = g1.Rotation.multVec(V(0, 0, 1)); z2 = g2.Rotation.multVec(V(0, 0, 1)); dd = g2.Base - g1.Base
                    if z1.cross(z2).Length > 1e-3: return False                                      # joint axes must stay lined up
                    if q.JointType in ('Slider', 'Cylindrical'): off = (dd - z1 * dd.dot(z1)).Length
                    else: off = dd.Length
                    if off > 0.02: return False                                                      # joint must stay together
                    if q.JointType == 'Revolute':
                        v = _value(q)
                        if (q.EnableAngleMin and v < _num(q.AngleMin) - 0.02) or (q.EnableAngleMax and v > _num(q.AngleMax) + 0.02): return False
                    elif q.JointType == 'Slider':
                        v = _value(q)
                        if (q.EnableLengthMin and v < _num(q.LengthMin) - 0.02) or (q.EnableLengthMax and v > _num(q.LengthMax) + 0.02): return False
                return abs(_value(j) - want) < 0.1

            start = _value(j)
            n = max(1, int(math.ceil(abs(target - start) / 4.0)))
            A = asm.Placement
            try: riders = [o for o in asm.getDownstreamParts(part, j) if o is not part and o in comps]   # parts that only hang off this one
            except Exception: riders = []
            def step(want):
                nonlocal hold
                before = state()
                d = (want - _value(j)) * sign
                g1 = UtilsAssembly.getJcsGlobalPlc(j.Placement1, j.Reference1)
                z = g1.Rotation.multVec(V(0, 0, 1)); o = g1.Base
                T = App.Placement(V(0, 0, 0), App.Rotation(z, d), o) if rev else App.Placement(z * d, App.Rotation())
                M = A.inverse() * T * A
                part.Placement = M * part.Placement
                for r in riders: r.Placement = M * r.Placement
                if hold is None:
                    hold = jg.newObject('App::FeaturePython', 'JointSliderHold'); JointObject.GroundedJoint(hold, part)
                    try: hold.ViewObject.Visibility = False
                    except Exception: pass
                if asm.solve() != 0 or not valid(before, want):
                    restore(before); return False
                return True

            last = start
            for k in range(1, n + 1):
                want = start + (target - start) * k / n
                if step(want):
                    last = want; continue
                ok = False
                span = want - last                      # creep up to the stop in smaller steps
                for _ in range(5):
                    span /= 2.0
                    if abs(span) < 0.05: break
                    if step(last + span): last += span
                break
            if hold is not None:
                doc.removeObject(hold.Name); hold = None
            if not quiet: self.status.setText('' if ok else 'The mechanism cannot move any further that way.')
        except Exception as e:
            ok = False
            if not quiet: self.status.setText('Could not move: %s' % str(e)[:90])
        finally:
            try:
                if hold is not None: asm.Document.removeObject(hold.Name)
            except Exception:
                pass
            self.busy = False
        if not quiet: self.show_value()
        return ok

    def drivable(self, asm, joints):
        """Keep only the joints this panel can really move: try a tiny nudge each way on each one, then put everything back."""
        keep = []
        doc = asm.Document; prev = self.asm; self.asm = asm
        comps = [o for o in asm.Group if hasattr(o, 'Placement') and o.TypeId not in ('Assembly::JointGroup', 'App::Origin')]
        saved = dict((o.Name, App.Placement(o.Placement)) for o in comps)
        try:
            doc.openTransaction('Joint slider check')
            for j in joints: self.reach.pop((doc.Name, j.Name), None)
            for j in joints:
                try:
                    v = _value(j); lo, hi = self.range(j); step = 0.4
                    good = False
                    for t in (v + step, v - step):
                        if lo <= t <= hi and self.drive(j, t, quiet=True): good = True; break
                    if good:
                        keep.append(j)
                        # how far does it really go each way? (drive stops at the last valid step)
                        ends = []
                        for t in (lo, hi):
                            for o in comps: o.Placement = saved[o.Name]
                            self.drive(j, t, quiet=True); ends.append(_value(j))
                        a, b = min(ends + [v]), max(ends + [v])
                        if b - a > 0.5: self.reach[(doc.Name, j.Name)] = (round(a, 2), round(b, 2))
                        else: keep.pop()                      # passes a nudge but has no real travel
                except Exception:
                    pass
                for o in comps: o.Placement = saved[o.Name]
            asm.solve()
            for o in comps: o.Placement = saved[o.Name]
        finally:
            try: doc.abortTransaction()
            except Exception: pass
            self.asm = prev
        return keep


def dock():
    return Gui.getMainWindow().findChild(QtWidgets.QDockWidget, DOCK_NAME)


def install():
    mw = Gui.getMainWindow(); d = dock()
    if d:
        d.show(); d.raise_(); return d
    d = QtWidgets.QDockWidget('Joint Slider', mw); d.setObjectName(DOCK_NAME)
    d.setWidget(Panel(d))
    try: restored = mw.restoreDockWidget(d)          # put it back where it was when FreeCAD last closed
    except Exception: restored = False
    if not restored:
        tree = None
        for o in mw.findChildren(QtWidgets.QDockWidget):
            # only a tree that is really docked: not floating, not held by FreeCAD's overlay, and in a dock area
            if (o.windowTitle() in ('Model', 'Combo View', 'Tree view') and not o.isFloating() and o.parentWidget() == mw
                    and mw.dockWidgetArea(o) != QtCore.Qt.NoDockWidgetArea): tree = o
        if tree is not None:
            mw.addDockWidget(mw.dockWidgetArea(tree), d); mw.tabifyDockWidget(tree, d); tree.raise_()   # a tab beside the model tree
        else:
            mw.addDockWidget(QtCore.Qt.LeftDockWidgetArea, d)
            other = mw.findChild(QtWidgets.QDockWidget, 'ModelBrowserDock')
            if other is not None and not other.isFloating() and other.parentWidget() == mw: mw.tabifyDockWidget(other, d)
    d.show()
    return d


def setup():
    """Called once at FreeCAD start-up."""
    QtCore.QTimer.singleShot(2500, install)
