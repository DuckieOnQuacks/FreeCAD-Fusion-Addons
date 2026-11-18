# Claude bridge for FreeCAD: when switched on, runs Python job files dropped into ~/FreeCAD Models/_bridge/inbox
# and writes each result (printed output, errors, optional pictures) to ~/FreeCAD Models/_bridge/outbox.
# It is OFF every time FreeCAD starts; switch it on from the Models panel menu. Every job is copied to _bridge/done
# and listed in _bridge/log.txt. Installed as an add-on (Mod/ClaudeBridge); delete that folder to remove it.
import os, sys, io, json, time, shutil, traceback, contextlib, importlib
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

ROOT = os.path.expanduser('~/FreeCAD Models/_bridge')
INBOX, OUTBOX, DONE, LIB = (os.path.join(ROOT, d) for d in ('inbox', 'outbox', 'done', 'lib'))
JOB = None            # name of the job being run (used by the helper library for picture names)
_timer = None; _label = None; _ns = None; _busy = False; _mtimes = {}; _beat = 0.0


def _ensure():
    for d in (INBOX, OUTBOX, DONE, LIB): os.makedirs(d, exist_ok=True)
    try:      # first run on a new machine: put the bundled helper library where jobs can import it
        mine = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'claude_lib.py'); theirs = os.path.join(LIB, 'claude_lib.py')
        if os.path.exists(mine) and not os.path.exists(theirs): shutil.copy(mine, theirs)
    except Exception:
        pass


def is_on():
    return _timer is not None and _timer.isActive()


def _log(line):
    try:
        with open(os.path.join(ROOT, 'log.txt'), 'a') as f: f.write('%s  %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), line))
    except Exception:
        pass
    App.Console.PrintMessage('Claude bridge: %s\n' % line)


def _status():
    try:
        tmp = os.path.join(ROOT, 'status.json.tmp')
        json.dump(dict(on=is_on(), time=time.time(), stamp=time.strftime('%Y-%m-%d %H:%M:%S'), freecad='.'.join(App.Version()[:3]),
                       docs=[d.Label for d in App.listDocuments().values()], active=App.ActiveDocument.Label if App.ActiveDocument else None), open(tmp, 'w'))
        os.replace(tmp, os.path.join(ROOT, 'status.json'))
    except Exception:
        pass


def _reload_lib():
    if LIB not in sys.path: sys.path.insert(0, LIB)
    for name, mod in list(sys.modules.items()):
        f = getattr(mod, '__file__', None)
        if not f or not f.startswith(LIB): continue
        try:
            m = os.path.getmtime(f)
            if _mtimes.get(f) is not None and m != _mtimes[f]: importlib.reload(mod)
            _mtimes[f] = m
        except Exception:
            pass


def _run(path):
    global JOB, _ns
    name = os.path.splitext(os.path.basename(path))[0]
    try: code = open(path).read()
    except Exception: return
    if _ns is None: _ns = {'__name__': '__claude_job__', 'App': App, 'FreeCAD': App, 'Gui': Gui, 'FreeCADGui': Gui}
    _ns['JOB'] = name; _ns['OUT'] = OUTBOX; _ns.pop('RESULT', None); JOB = name
    out = io.StringIO(); err = None; t0 = time.time()
    try:
        _reload_lib()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            exec(compile(code, name + '.py', 'exec'), _ns)
    except Exception:
        err = traceback.format_exc()
    dt = time.time() - t0
    res = dict(job=name, ok=err is None, seconds=round(dt, 2), output=out.getvalue()[-30000:], error=err, result=_ns.get('RESULT'),
               active=App.ActiveDocument.Label if App.ActiveDocument else None)
    try:
        tmp = os.path.join(OUTBOX, name + '.json.tmp')
        with open(tmp, 'w') as f: json.dump(res, f, indent=1, default=str)
        os.replace(tmp, os.path.join(OUTBOX, name + '.json'))
    except Exception:
        pass
    try:
        dst = os.path.join(DONE, os.path.basename(path))
        if os.path.exists(dst): os.remove(dst)
        shutil.move(path, dst)
    except Exception:
        try: os.remove(path)
        except Exception: pass
    JOB = None
    _log('%s %s (%.1f s)' % (name, 'ok' if err is None else 'FAILED', dt))


def _tick():
    global _busy, _beat
    if _busy: return
    _busy = True
    try:
        if time.time() - _beat > 5: _beat = time.time(); _status()
        jobs = sorted(f for f in os.listdir(INBOX) if f.endswith('.py'))
        if jobs: _run(os.path.join(INBOX, jobs[0])); _status()
    except Exception:
        pass
    finally:
        _busy = False


def turn_on():
    global _timer, _label
    _ensure()
    mw = Gui.getMainWindow()
    if _timer is None:
        _timer = QtCore.QTimer(mw); _timer.setInterval(400); _timer.timeout.connect(_tick)
    _timer.start()
    if _label is None:
        _label = QtWidgets.QLabel('  Claude bridge ON  '); _label.setStyleSheet('background:#b3541e; color:white; border-radius:3px;')
        _label.setToolTip('FreeCAD is running job files from FreeCAD Models/_bridge/inbox. Switch off in the Models panel menu.')
        mw.statusBar().addPermanentWidget(_label)
    _label.show(); _status(); _log('switched ON')


def turn_off():
    if _timer is not None: _timer.stop()
    if _label is not None: _label.hide()
    _status(); _log('switched OFF')


def toggle():
    turn_off() if is_on() else turn_on()
    return is_on()


def setup():
    """Called once at FreeCAD start-up. The bridge stays off until it is switched on."""
    try:
        _ensure(); _status()
    except Exception:
        pass
