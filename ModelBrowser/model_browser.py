# Models panel for FreeCAD: a docked list of the FreeCAD files in one folder, with thumbnails. Double-click opens a file.
# Installed as an add-on (Mod/ModelBrowser). To remove it, delete that folder.
import os, sys, time, zipfile, subprocess
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

PARAM = 'User parameter:BaseApp/Preferences/Mod/ModelBrowser'
DEFAULT_FOLDER = os.path.expanduser('~/FreeCAD Models')
DOCK_NAME = 'ModelBrowserDock'
ROLE = QtCore.Qt.UserRole


def _reveal(path):
    """Show a file or folder in Finder / Explorer / the desktop's file manager."""
    try:
        if sys.platform == 'darwin': subprocess.Popen(['open', path] if os.path.isdir(path) else ['open', '-R', path])
        elif sys.platform.startswith('win'): subprocess.Popen(['explorer', path] if os.path.isdir(path) else ['explorer', '/select,', os.path.normpath(path)])
        else: QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path if os.path.isdir(path) else os.path.dirname(path)))
    except Exception:
        pass


def _thumbnail(path):
    try:
        with zipfile.ZipFile(path) as z:
            data = z.read('thumbnails/Thumbnail.png')
        pm = QtGui.QPixmap()
        if pm.loadFromData(data) and not pm.isNull():
            return QtGui.QIcon(pm)
    except Exception:
        pass
    return None


class Panel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.params = App.ParamGet(PARAM)
        self.cache = {}
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4); lay.setSpacing(4)
        row = QtWidgets.QHBoxLayout(); row.setSpacing(4)
        self.folderBtn = QtWidgets.QToolButton()
        self.folderBtn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.folderBtn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon))
        self.folderBtn.setToolTip('Choose which folder to show')
        self.folderBtn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.folderBtn.clicked.connect(self.chooseFolder)
        self.refreshBtn = QtWidgets.QToolButton()
        self.refreshBtn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_BrowserReload))
        self.refreshBtn.setToolTip('Refresh the list'); self.refreshBtn.setText('Refresh'); self.refreshBtn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.refreshBtn.clicked.connect(self.refresh)
        self.moreBtn = QtWidgets.QToolButton(); self.moreBtn.setText('More'); self.moreBtn.setToolTip('Import STEP files, rebuild previews')
        self.moreBtn.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        mm = QtWidgets.QMenu(self.moreBtn)
        mm.addAction('Import STEP files...', self.importStep)
        mm.addAction('Rebuild blank previews', lambda: self.rebuildPreviews(False))
        mm.addAction('Rebuild all previews', lambda: self.rebuildPreviews(True))
        mm.addSeparator(); mm.addAction('Choose folder...', self.chooseFolder)
        mm.addAction('Show folder in file manager', lambda: _reveal(self.folder()))
        mm.addSeparator()
        mm.addAction('Ground grid on / off', self.toggleGrid)
        mm.addAction('Joint Slider panel on / off', self.toggleSlider)
        mm.addAction('Claude bridge on / off', self.toggleBridge)
        mm.addSeparator(); mm.addAction('Reset panel layout', self.resetPanels)
        self.moreBtn.setMenu(mm)
        row.addWidget(self.folderBtn, 1); row.addWidget(self.refreshBtn, 0); row.addWidget(self.moreBtn, 0)
        lay.addLayout(row)
        self.search = QtWidgets.QLineEdit(); self.search.setPlaceholderText('Search'); self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.applyFilter)
        lay.addWidget(self.search)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True); self.tree.setIconSize(QtCore.QSize(72, 72)); self.tree.setIndentation(14)
        self.tree.setWordWrap(True); self.tree.setTextElideMode(QtCore.Qt.ElideNone); self.tree.setUniformRowHeights(False)
        self.tree.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        try:
            self.tree.header().setStretchLastSection(True)
            self.tree.header().sectionResized.connect(lambda *_: self.tree.scheduleDelayedItemsLayout())
        except Exception:
            pass
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.menu)
        self.tree.itemDoubleClicked.connect(self.openItem)
        try:
            SC = getattr(QtGui, 'QShortcut', None) or QtWidgets.QShortcut
            for key in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
                sc = SC(QtGui.QKeySequence(key), self.tree); sc.setContext(QtCore.Qt.WidgetShortcut); sc.activated.connect(lambda: self.trashItem(None))
        except Exception:
            pass
        lay.addWidget(self.tree, 1)
        self.status = QtWidgets.QLabel(''); self.status.setEnabled(False)
        lay.addWidget(self.status)
        self.watcher = QtCore.QFileSystemWatcher(self)
        self.timer = QtCore.QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(700)
        self.timer.timeout.connect(self.refresh)
        self.watcher.directoryChanged.connect(lambda *_: self.timer.start())
        self.watcher.fileChanged.connect(lambda *_: self.timer.start())
        self.refresh()

    def folder(self):
        return self.params.GetString('Folder', DEFAULT_FOLDER) or DEFAULT_FOLDER

    def chooseFolder(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, 'Choose the folder to show', self.folder())
        if d:
            self.params.SetString('Folder', d); self.refresh()

    def icon(self, path):
        try: key = (path, os.path.getmtime(path))
        except OSError: key = (path, 0)
        if key not in self.cache:
            self.cache[key] = _thumbnail(path) or QtWidgets.QFileIconProvider().icon(QtCore.QFileInfo(path))
        return self.cache[key]

    def refresh(self):
        root = self.folder()
        expanded = set()
        it = QtWidgets.QTreeWidgetItemIterator(self.tree)
        while it.value():
            i = it.value()
            if i.isExpanded() and i.data(0, ROLE + 1): expanded.add(i.data(0, ROLE + 1))
            it += 1
        self.tree.clear()
        watched = self.watcher.directories() + self.watcher.files()
        if watched: self.watcher.removePaths(watched)
        self.folderBtn.setText(os.path.basename(root.rstrip('/')) or root)
        dirs, files = [], []

        def fill(parent, d, depth):
            try: names = sorted(os.listdir(d), key=str.lower)
            except OSError: return 0
            dirs.append(d); count = 0
            if depth < 4:
                for n in names:
                    p = os.path.join(d, n)
                    if n.startswith('.') or not os.path.isdir(p): continue
                    node = QtWidgets.QTreeWidgetItem([n])
                    node.setIcon(0, self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon)); node.setData(0, ROLE + 1, p)
                    c = fill(node, p, depth + 1)
                    if c:
                        (parent.addChild(node) if parent else self.tree.addTopLevelItem(node))
                        node.setExpanded(p in expanded); count += c
            for n in names:
                p = os.path.join(d, n)
                if not n.lower().endswith('.fcstd') or n.startswith('.') or not os.path.isfile(p): continue
                try: when = time.strftime('%b %d, %Y  %I:%M %p', time.localtime(os.path.getmtime(p))).replace(' 0', ' ')
                except OSError: when = ''
                item = QtWidgets.QTreeWidgetItem([os.path.splitext(n)[0] + '\n' + when])
                item.setIcon(0, self.icon(p)); item.setData(0, ROLE, p); item.setToolTip(0, p)
                (parent.addChild(item) if parent else self.tree.addTopLevelItem(item))
                files.append(p); count += 1
            return count

        if os.path.isdir(root):
            n = fill(None, root, 0)
            self.status.setText('%d model%s' % (n, '' if n == 1 else 's'))
            paths = dirs + files
            if paths: self.watcher.addPaths(paths)
        else:
            self.status.setText('Folder not found. Choose another.')
        self.applyFilter()

    # ---- actions that open files in FreeCAD briefly ----
    def _batch(self, jobs, label):
        """jobs: list of callables returning a short result string. Runs them with backups off and restores the active document."""
        prefs = App.ParamGet('User parameter:BaseApp/Preferences/Document'); keep = prefs.GetBool('CreateBackupFiles', True)
        prefs.SetBool('CreateBackupFiles', False)
        was = App.ActiveDocument.Name if App.ActiveDocument else None
        ok = 0; failed = []
        try:
            for k, job in enumerate(jobs):
                self.status.setText('%s %d of %d...' % (label, k + 1, len(jobs))); Gui.updateGui()
                try:
                    job(); ok += 1
                except Exception as e:
                    failed.append(str(e)[:80])
        finally:
            prefs.SetBool('CreateBackupFiles', keep)
            try:
                if was and was in App.listDocuments(): App.setActiveDocument(was)
            except Exception:
                pass
        self.refresh()
        self.status.setText('%s: %d done%s' % (label, ok, (', %d failed' % len(failed)) if failed else ''))
        if failed:
            QtWidgets.QMessageBox.warning(self, 'Models', '%s - some files failed:\n\n%s' % (label, '\n'.join(failed[:8])))

    @staticmethod
    def _finish(doc, out=None, style=False):
        if style:
            try:
                import fusion_look; fusion_look.style_doc(doc)
            except Exception:
                pass
        try:
            v = Gui.getDocument(doc.Name).ActiveView; v.viewIsometric(); v.fitAll()
        except Exception:
            pass
        for _ in range(6): Gui.updateGui()
        if out: doc.saveAs(out)
        else: doc.save()
        App.closeDocument(doc.Name)

    def importStep(self):
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(self, 'Choose STEP files to import', os.path.expanduser('~'), 'STEP files (*.step *.stp *.STEP *.STP)')
        if not files: return
        import re, ImportGui
        folder = self.folder()

        def job(f):
            def run():
                name = os.path.splitext(os.path.basename(f))[0]; out = os.path.join(folder, name + '.FCStd'); k = 2
                while os.path.exists(out):
                    out = os.path.join(folder, '%s (%d).FCStd' % (name, k)); k += 1
                doc = App.newDocument(re.sub(r'[^A-Za-z0-9_]', '_', name)); doc.Label = name
                try:
                    ImportGui.insert(f, doc.Name); doc.recompute()
                    if not any(o.isDerivedFrom('Part::Feature') for o in doc.Objects): raise Exception('%s has no 3D geometry' % os.path.basename(f))
                except Exception:
                    App.closeDocument(doc.Name); raise
                self._finish(doc, out, style=True)
            return run
        self._batch([job(f) for f in files], 'Importing')

    def rebuildPreviews(self, everything=False):
        opened = [d.FileName for d in App.listDocuments().values()]
        todo = []
        for base, dirs, names in os.walk(self.folder()):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for n in names:
                p = os.path.join(base, n)
                if not n.lower().endswith('.fcstd') or p in opened: continue
                if not everything:
                    try:
                        with zipfile.ZipFile(p) as z:
                            if z.getinfo('thumbnails/Thumbnail.png').file_size > 2500: continue
                    except Exception:
                        pass
                todo.append(p)
        if not todo:
            self.status.setText('No previews needed rebuilding'); return

        def job(p):
            return lambda: self._finish(App.openDocument(p))
        self._batch([job(p) for p in todo], 'Rebuilding previews')

    @staticmethod
    def _trash(path):
        """Close the document if it is open, then move the file to the macOS Trash (recoverable). Returns True on success."""
        for d in list(App.listDocuments().values()):
            try:
                if d.FileName and os.path.exists(d.FileName) and os.path.samefile(d.FileName, path): App.closeDocument(d.Name)
            except Exception:
                pass
        try:
            r = QtCore.QFile.moveToTrash(path)
            if isinstance(r, (tuple, list)): r = r[0]
        except Exception:
            r = False
        return bool(r) and not os.path.exists(path)

    def trashItem(self, item=None):
        item = item or self.tree.currentItem()
        path = item.data(0, ROLE) if item else None
        if not path: return
        name = os.path.splitext(os.path.basename(path))[0]
        is_open = False
        for d in App.listDocuments().values():
            try:
                if d.FileName and os.path.exists(d.FileName) and os.path.samefile(d.FileName, path): is_open = True
            except Exception:
                pass
        text = 'Move "%s" to the Trash?' % name
        if is_open: text += '\n\nIt is open in FreeCAD and will be closed first. Unsaved changes will be lost.'
        box = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Question, 'Models', text, QtWidgets.QMessageBox.Cancel, self)
        yes = box.addButton('Move to Trash', QtWidgets.QMessageBox.DestructiveRole)
        box.setDefaultButton(QtWidgets.QMessageBox.Cancel)
        (box.exec if hasattr(box, 'exec') else box.exec_)()
        if box.clickedButton() is not yes: return
        if self._trash(path): self.status.setText('Moved "%s" to the Trash' % name)
        else: QtWidgets.QMessageBox.warning(self, 'Models', 'Could not move this file to the Trash:\n%s' % path)
        self.refresh()

    def toggleBridge(self):
        try:
            import claude_bridge
            on = claude_bridge.toggle()
            self.status.setText('Claude bridge is %s' % ('ON: FreeCAD runs job files from the _bridge folder' if on else 'off'))
        except Exception as e:
            self.status.setText('Claude bridge not available (%s)' % str(e)[:40])

    def resetPanels(self):
        try:
            import fusion_look; fusion_look.reset_panels()
        except Exception as e:
            App.Console.PrintWarning('Models: could not reset the panel layout (%s)\n' % e)

    def toggleGrid(self):
        try:
            import fusion_look; fusion_look._ToggleGrid().Activated()
        except Exception as e:
            self.status.setText('Grid add-on not available (%s)' % str(e)[:40])

    def toggleSlider(self):
        try:
            import joint_slider
            d = joint_slider.dock()
            if d is None: joint_slider.install()
            else: d.setVisible(not d.isVisible())
        except Exception as e:
            self.status.setText('Joint slider not available (%s)' % str(e)[:40])

    def applyFilter(self, *_):
        text = self.search.text().strip().lower()

        def visit(item):
            if item.data(0, ROLE):
                show = text in os.path.basename(item.data(0, ROLE)).lower()
            else:
                show = False
                for k in range(item.childCount()):
                    show = visit(item.child(k)) or show
                if text and show: item.setExpanded(True)
            item.setHidden(not show)
            return show
        for k in range(self.tree.topLevelItemCount()): visit(self.tree.topLevelItem(k))

    def openItem(self, item, *_):
        path = item.data(0, ROLE)
        if not path: return
        try:
            for d in App.listDocuments().values():
                if d.FileName and os.path.exists(d.FileName) and os.path.samefile(d.FileName, path):
                    App.setActiveDocument(d.Name)
                    mdi = Gui.getMainWindow().findChild(QtWidgets.QMdiArea)
                    views = Gui.getDocument(d.Name).mdiViewsOfType('Gui::View3DInventor')
                    if mdi and views:
                        for sw in mdi.subWindowList():
                            if sw.widget() is views[0] or sw.windowTitle().startswith(d.Label):
                                mdi.setActiveSubWindow(sw); break
                    return
            App.openDocument(path)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, 'Models', 'Could not open this file:\n%s\n\n%s' % (path, e))

    def menu(self, pos):
        item = self.tree.itemAt(pos)
        m = QtWidgets.QMenu(self)
        path = item.data(0, ROLE) or item.data(0, ROLE + 1) if item else None
        if item and item.data(0, ROLE):
            m.addAction('Open', lambda: self.openItem(item))
            m.addAction('Move to Trash...', lambda: self.trashItem(item))
        if path:
            m.addAction('Show in file manager', lambda: _reveal(path))
            m.addSeparator()
        m.addAction('Refresh', self.refresh)
        m.addAction('Choose folder...', self.chooseFolder)
        (m.exec if hasattr(m, 'exec') else m.exec_)(self.tree.viewport().mapToGlobal(pos))


def dock():
    return Gui.getMainWindow().findChild(QtWidgets.QDockWidget, DOCK_NAME)


def _tree_dock(mw):
    """FreeCAD's own model tree panel."""
    for o in mw.findChildren(QtWidgets.QDockWidget):
        if o.objectName() != DOCK_NAME and (o.windowTitle() in ('Model', 'Combo View', 'Tree view') or o.objectName() in ('Model', 'Combo View', 'Tree view')): return o
    return None


def _usable(mw, o):
    """A panel we may dock against: really docked in the main window (not floating, not in FreeCAD's overlay)."""
    if o is None or o.isFloating() or o.parentWidget() != mw: return False
    return mw.dockWidgetArea(o) != QtCore.Qt.NoDockWidgetArea


def install():
    mw = Gui.getMainWindow()
    d = dock()
    if d:
        d.show(); d.raise_(); return d
    d = QtWidgets.QDockWidget('Models', mw); d.setObjectName(DOCK_NAME)
    d.setWidget(Panel(d))
    try: restored = mw.restoreDockWidget(d)          # put it back where it was when FreeCAD last closed
    except Exception: restored = False
    if not restored:
        mw.addDockWidget(QtCore.Qt.LeftDockWidgetArea, d)
        try:   # its own column at the far left, like a project panel
            tree = _tree_dock(mw)
            if _usable(mw, tree): mw.splitDockWidget(d, tree, QtCore.Qt.Horizontal)
            QtCore.QTimer.singleShot(400, lambda: mw.resizeDocks([d], [300], QtCore.Qt.Horizontal))   # after the layout settles
        except Exception:
            pass
    d.show()
    return d


class _ToggleCommand:
    def GetResources(self):
        return {'MenuText': 'Models Panel', 'ToolTip': 'Show or hide the Models panel (the list of files in your models folder)'}

    def Activated(self):
        d = dock()
        if d is None: install()
        else: d.setVisible(not d.isVisible())

    def IsActive(self):
        return True


class _Manipulator:
    def modifyMenuBar(self):
        return [{'append': 'ModelBrowser_Toggle', 'menuItem': 'Std_ViewStatusBar'}]


def setup():
    """Called once at FreeCAD start-up."""
    try:
        Gui.addCommand('ModelBrowser_Toggle', _ToggleCommand())
        Gui.addWorkbenchManipulator(_Manipulator())
    except Exception as e:
        App.Console.PrintWarning('Models panel: menu entry not added (%s)\n' % e)
    QtCore.QTimer.singleShot(1500, install)
