# Record the 3D view while a joint moves, and save it as an MP4 (or an animated GIF).
# Used by the Record button in the Joint Slider panel (joint_slider.py).
import os, re, sys, math, time, shutil, tempfile, subprocess
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

FPS = 30
MOVE_SECONDS = 2.0          # each sweep from one end to the other
HOLD_SECONDS = 0.4          # pause at each end
PARAMS = 'User parameter:BaseApp/Preferences/Mod/JointSlider'


def recordings_dir():
    d = os.path.join(os.path.expanduser('~'), 'FreeCAD Models', 'Recordings')
    os.makedirs(d, exist_ok=True)
    return d


def _safe(s):
    return re.sub(r'[\\/:*?"<>|]+', '-', s).strip() or 'joint'


# ---- finding an encoder ---------------------------------------------------------------------------
def _vendor_dir():
    try:
        import addonmanager_utilities as u
        return u.get_pip_target_directory()
    except Exception:
        return None


def find_ffmpeg():
    c = [shutil.which('ffmpeg'), '/opt/homebrew/bin/ffmpeg', '/usr/local/bin/ffmpeg', '/usr/bin/ffmpeg']
    if sys.platform.startswith('win'):
        c += [os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe'), r'C:\ffmpeg\bin\ffmpeg.exe',
              r'C:\Program Files\ffmpeg\bin\ffmpeg.exe']
    v = _vendor_dir()
    if v and os.path.isdir(v) and v not in sys.path: sys.path.append(v)
    try:
        import imageio_ffmpeg
        c.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass
    return next((x for x in c if x and os.path.exists(x)), None)


def install_ffmpeg(parent):
    """One-time download of the imageio-ffmpeg package (a self-contained ffmpeg) from PyPI, with the user's OK."""
    v = _vendor_dir()
    if not v: return None
    ask = QtWidgets.QMessageBox.question(
        parent, 'Save recording as MP4',
        'Saving MP4 videos needs the ffmpeg video encoder, which is not on this computer.\n\n'
        'Download it now? (the "imageio-ffmpeg" package from PyPI, about 30 MB, installed only for FreeCAD)\n\n'
        'Choose No to save an animated GIF instead.')
    if ask != QtWidgets.QMessageBox.Yes: return None
    try:
        import addonmanager_utilities as u
        os.makedirs(v, exist_ok=True)
        cmd = u.create_pip_call(['install', '--disable-pip-version-check', '--target', v, 'imageio-ffmpeg'])
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        if p.returncode != 0:
            App.Console.PrintWarning('Joint recorder: ffmpeg download failed:\n%s\n' % (p.stdout + p.stderr)[-1500:])
            return None
    except Exception as e:
        App.Console.PrintWarning('Joint recorder: ffmpeg download failed (%s)\n' % e)
        return None
    return find_ffmpeg()


# ---- writing the video --------------------------------------------------------------------------------
def encode_mp4(ffmpeg, frames_dir, out):
    cmd = [ffmpeg, '-y', '-loglevel', 'error', '-framerate', str(FPS), '-i', os.path.join(frames_dir, 'f_%04d.png'),
           '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
           '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=900, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if p.returncode != 0: raise RuntimeError((p.stderr or p.stdout)[-600:])
    return out


def encode_gif(frames, out, max_width=960):
    from PIL import Image
    imgs = []
    for f in frames:
        im = Image.open(f).convert('RGB')
        if im.width > max_width: im = im.resize((max_width, round(im.height * max_width / im.width)), Image.LANCZOS)
        imgs.append(im.quantize(colors=256, method=Image.MEDIANCUT, dither=Image.NONE))
    imgs[0].save(out, save_all=True, append_images=imgs[1:], duration=round(1000 / FPS), loop=0, optimize=False)
    return out


# ---- the recording ------------------------------------------------------------------------------------
def plan(start, end, both_ways):
    """Joint values for every frame: hold, ease from start to end, hold (and back again)."""
    n = max(2, int(round(MOVE_SECONDS * FPS))); h = int(round(HOLD_SECONDS * FPS))
    ease = lambda t: t * t * (3 - 2 * t)
    go = [start + (end - start) * ease(i / (n - 1)) for i in range(n)]
    seq = [start] * h + go + [end] * h
    if both_ways: seq += list(reversed(go)) + [start] * h
    return seq


def frame_size(view, full_hd):
    if full_hd: return 1920, 1080
    try: w, h = view.getSize()
    except Exception: w, h = 1280, 720
    return max(320, int(w)) // 2 * 2, max(240, int(h)) // 2 * 2


def record(panel, both_ways=True, full_hd=False):
    """Drive the panel's current joint through its range, saving the 3D view at every step. Returns the saved file."""
    j = panel.joint()
    doc = App.ActiveDocument
    if j is None or doc is None or Gui.ActiveDocument is None:
        panel.status.setText('Pick a joint to record first.'); return None
    view = Gui.ActiveDocument.ActiveView
    if not hasattr(view, 'saveImage'):
        panel.status.setText('Click in the 3D view first, then record.'); return None
    import joint_slider
    lo, hi = panel.range(j); here = joint_slider._value(j)
    seq = plan(lo + 0.05, hi - 0.05, both_ways)
    w, h = frame_size(view, full_hd)
    stamp = time.strftime('%Y-%m-%d %H.%M.%S')
    base = '%s - %s - %s' % (_safe(doc.Label), _safe(j.Label.split('(')[0]), stamp)
    tmp = tempfile.mkdtemp(prefix='joint_rec_')
    frames, ok = [], True
    panel.recording = True; panel.cancel = False
    doc.openTransaction('Record joint')
    try:
        for i, val in enumerate(seq):
            if panel.cancel: ok = False; break
            if i == 0 or abs(val - seq[i - 1]) > 1e-9:
                if not panel.drive(j, val, quiet=True):
                    panel.status.setText('The mechanism stopped at %.1f; recording what was reached.' % joint_slider._value(j))
            Gui.updateGui()
            f = os.path.join(tmp, 'f_%04d.png' % i)
            view.saveImage(f, w, h, 'Current'); frames.append(f)
            panel.status.setText('Recording frame %d of %d. Click Stop to cancel.' % (i + 1, len(seq)))
            QtWidgets.QApplication.processEvents()
    finally:
        try: doc.abortTransaction()           # puts every part back where it was, with nothing left to undo
        except Exception: pass
        try: doc.recompute()
        except Exception: pass
        if abs(joint_slider._value(j) - here) > 0.05:
            panel.drive(j, here, quiet=True)
        panel.recording = False; panel.show_value()
    if not ok or len(frames) < 2:
        shutil.rmtree(tmp, ignore_errors=True); panel.status.setText('Recording cancelled.'); return None
    out_dir = recordings_dir()
    panel.status.setText('Saving the video...'); QtWidgets.QApplication.processEvents()
    try:
        ff = find_ffmpeg() or install_ffmpeg(panel)
        if ff:
            out = encode_mp4(ff, tmp, os.path.join(out_dir, base + '.mp4'))
        else:
            out = encode_gif(frames, os.path.join(out_dir, base + '.gif'))
        shutil.rmtree(tmp, ignore_errors=True)
    except Exception as e:
        keep = os.path.join(out_dir, base + ' frames')
        shutil.move(tmp, keep)
        panel.status.setText('Could not make the video (%s). The frames are in %s' % (str(e)[:80], keep))
        return None
    panel.status.setText('Saved %s' % os.path.basename(out))
    _saved(panel, out)
    return out


def _saved(parent, path):
    box = QtWidgets.QMessageBox(parent); box.setWindowTitle('Recording saved')
    box.setText('Saved the recording:\n%s' % os.path.basename(path))
    show = box.addButton('Show in Folder', QtWidgets.QMessageBox.ActionRole)
    play = box.addButton('Play', QtWidgets.QMessageBox.ActionRole)
    box.addButton(QtWidgets.QMessageBox.Ok)
    box.exec()
    if box.clickedButton() == show: reveal(path)
    elif box.clickedButton() == play: QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path))


def reveal(path):
    try:
        import model_browser
        return model_browser._reveal(path)
    except Exception:
        pass
    QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(os.path.dirname(path)))
