# One-shot setup: makes a fresh FreeCAD 1.1 look and work like Joe's.
#
# Paste this one line into FreeCAD's Python console (View > Panels > Python Console), press Enter,
# wait for "Setup finished", then restart FreeCAD:
#
#   import urllib.request as u; exec(u.urlopen('https://raw.githubusercontent.com/DuckieOnQuacks/FreeCAD-Fusion-Addons/main/setup_everything.py').read().decode())
#
# What it does (safe to run again; it skips what is already there):
#   1. installs the four add-ons in this repo (ModelBrowser, FusionLook, JointSlider, ClaudeBridge)
#   2. installs FreeCAD Ribbon, Detessellate, SearchBar, SaveAndRestore and Render
#      (and on Windows the LuxCoreRender 2.6 renderer, ~142 MB, for Render)
#   3. applies the Fusion-like view settings (old values saved to ~/FreeCAD Models/_settings_backup.json)
#   4. creates ~/FreeCAD Models, the folder the Models panel lists


def _setup_everything():
    import os, io, json, shutil, zipfile, traceback
    import FreeCAD as App

    REPO = 'DuckieOnQuacks/FreeCAD-Fusion-Addons'
    OWN = ('ModelBrowser', 'FusionLook', 'JointSlider', 'ClaudeBridge')
    THIRD = (('FreeCAD-Ribbon', 'APEbbers/FreeCAD-Ribbon', 'main'),
             ('Detessellate', 'DesignWeaver3D/Detessellate', 'main'),
             ('SearchBar', 'APEbbers/SearchBar', 'main'),
             ('SaveAndRestore', 'APEbbers/SaveAndRestore', 'main'),
             ('Render', 'FreeCAD/FreeCAD-render', 'master'))
    mod = os.path.join(App.getUserAppDataDir(), 'Mod')
    models = os.path.expanduser('~/FreeCAD Models')
    os.makedirs(mod, exist_ok=True)
    os.makedirs(models, exist_ok=True)
    report = []

    def say(text):
        report.append(text)
        App.Console.PrintMessage('[setup] ' + text + '\n')
        try:
            import FreeCADGui as Gui
            Gui.updateGui()
        except Exception:
            pass

    def fetch(url):
        """Download a URL: Python first, FreeCAD's own downloader if that fails."""
        try:
            import urllib.request
            with urllib.request.urlopen(url, timeout=120) as r:
                return r.read()
        except Exception as first:
            try:
                import NetworkManager
                if getattr(NetworkManager, 'AM_NETWORK_MANAGER', None) is None:
                    NetworkManager.InitializeNetworkManager()
                data = NetworkManager.AM_NETWORK_MANAGER.blocking_get(url)
                if data:
                    return bytes(data.data()) if hasattr(data, 'data') else bytes(data)
            except Exception:
                pass
            raise first

    def unzip_repo(data, wanted, dest_for):
        """Extract top-level folders of a GitHub zip. wanted(name) -> bool, dest_for(name) -> folder."""
        z = zipfile.ZipFile(io.BytesIO(data))
        count = 0
        for info in z.infolist():
            parts = info.filename.split('/', 1)          # '<repo>-<branch>/rest'
            if len(parts) < 2 or not parts[1] or info.is_dir():
                continue
            rest = parts[1]
            top = rest.split('/', 1)[0]
            if not wanted(top, rest):
                continue
            target = os.path.normpath(os.path.join(dest_for(top, rest)))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(info) as src, open(target, 'wb') as out:
                shutil.copyfileobj(src, out)
            count += 1
        return count

    # ---- 1. the four add-ons from this repo ------------------------------------------------
    try:
        here = None
        try:
            here = os.path.dirname(os.path.abspath(__file__))     # run from a local copy of the repo
        except NameError:
            pass
        if here and all(os.path.isdir(os.path.join(here, n)) for n in OWN):
            for n in OWN:
                dst = os.path.join(mod, n)
                os.makedirs(dst, exist_ok=True)
                for f in os.listdir(os.path.join(here, n)):
                    if f.endswith('.py'):
                        shutil.copy(os.path.join(here, n, f), os.path.join(dst, f))
            say('Installed %s from %s' % (', '.join(OWN), here))
        else:
            data = fetch('https://codeload.github.com/%s/zip/refs/heads/main' % REPO)
            n = unzip_repo(data,
                           lambda top, rest: top in OWN and rest.endswith('.py'),
                           lambda top, rest: os.path.join(mod, *rest.split('/')))
            say('Installed %s (%d files) from GitHub' % (', '.join(OWN), n))
    except Exception:
        say('PROBLEM installing the repo add-ons:\n' + traceback.format_exc())

    # ---- 2. third-party add-ons ------------------------------------------------------------
    for name, repo, branch in THIRD:
        dst = os.path.join(mod, name)
        if os.path.isdir(dst) and os.listdir(dst):
            say('%s already installed' % name)
            continue
        url = 'https://github.com/' + repo
        ok = False
        try:                                              # FreeCAD's own Addon Manager installer
            import Addon as AddonMod, addonmanager_installer as ai
            try:
                import NetworkManager
                if getattr(NetworkManager, 'AM_NETWORK_MANAGER', None) is None:
                    NetworkManager.InitializeNetworkManager()
            except Exception:
                pass
            msgs = []
            inst = ai.AddonInstaller(AddonMod.Addon(name, url, AddonMod.Addon.Status.NOT_INSTALLED, branch))
            inst.success.connect(lambda *a: msgs.append('ok'))
            inst.failure.connect(lambda *a: msgs.append('failed: ' + ' '.join(str(i) for i in a[1:])[:200]))
            say('Downloading %s ...' % name)
            inst.run()
            ok = os.path.isdir(dst) and bool(os.listdir(dst))
            if ok:
                say('Installed %s with the Addon Manager installer' % name)
            else:
                say('Addon Manager installer did not install %s (%s); trying a plain download' % (name, msgs))
        except Exception as e:
            say('Addon Manager installer not usable for %s (%s); trying a plain download' % (name, e))
        if not ok:
            try:
                data = fetch('https://codeload.github.com/%s/zip/refs/heads/%s' % (repo, branch))
                n = unzip_repo(data, lambda top, rest: True,
                               lambda top, rest: os.path.join(dst, *rest.split('/')))
                say('Installed %s (%d files, %.1f MB download)' % (name, n, len(data) / 1e6))
            except Exception:
                say('PROBLEM installing %s - install it from Tools > Addon Manager instead:\n%s'
                    % (name, traceback.format_exc()))

    # ---- 2a. SearchBar 1.8.3 bug: getAllToolbars() calls workbench.name() on workbenches that are not loaded
    #          yet, which raises inside its own error handler; every search then fails. One-line fix.
    try:
        f = os.path.join(mod, 'SearchBar', 'ResultsToolbar.py')
        if os.path.exists(f):
            s = open(f, encoding='utf-8').read()
            old = 'print(f"{workbench.name()} not available")'
            if old in s:
                open(f, 'w', encoding='utf-8').write(s.replace(old, 'print(f"{wbname} not available")  # patched: workbench.name() fails for workbenches not loaded yet'))
                say('Patched the SearchBar bug that broke searching')
    except Exception:
        say('PROBLEM patching SearchBar:\n' + traceback.format_exc())

    # ---- 2b. LuxCoreRender for the Render workbench (Windows) ------------------------------
    try:
        import sys
        p = App.ParamGet('User parameter:BaseApp/Preferences/Mod/Render')
        if sys.platform.startswith('win'):
            root = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'Programs', 'LuxCoreRender')
            sdk = os.path.join(root, 'luxcorerender-v2.6-win64-sdk')
            binp = os.path.join(sdk, 'bin')
            if not os.path.exists(os.path.join(binp, 'luxcoreconsole.exe')):
                say('Downloading LuxCoreRender 2.6 (about 142 MB) ...')
                data = fetch('https://github.com/LuxCoreRender/LuxCore/releases/download/'
                             'luxcorerender_v2.6/luxcorerender-v2.6-win64-sdk.zip')
                os.makedirs(root, exist_ok=True)
                z = zipfile.ZipFile(io.BytesIO(data))
                if any(n.startswith('/') or '..' in n.split('/') for n in z.namelist()):
                    raise Exception('unexpected paths in the LuxCore zip')
                z.extractall(root)
            lib = os.path.join(sdk, 'lib')
            for f in os.listdir(lib):            # luxcore.dll etc. must sit next to the programs
                if f.lower().endswith('.dll') and not os.path.exists(os.path.join(binp, f)):
                    shutil.copy2(os.path.join(lib, f), os.path.join(binp, f))
            p.SetString('LuxCorePath', os.path.join(binp, 'luxcoreui.exe'))
            p.SetString('LuxCoreConsolePath', os.path.join(binp, 'luxcoreconsole.exe'))
            App.saveParameter()
            say('LuxCoreRender ready in %s and connected to Render' % sdk)
        elif not p.GetString('LuxCorePath', ''):
            say('LuxCoreRender: download it from luxcorerender.org for this computer, then set its path in '
                'Edit > Preferences > Render (LuxCore UI path and LuxCore command (cli) path)')
    except Exception:
        say('PROBLEM setting up LuxCoreRender:\n' + traceback.format_exc())

    # ---- 3. Fusion-like view settings ------------------------------------------------------
    try:
        def rgb(r, g, b):
            return (r << 24) | (g << 16) | (b << 8) | 255

        view = App.ParamGet('User parameter:BaseApp/Preferences/View')
        wanted = (('Bool', 'Simple', False), ('Bool', 'Gradient', True), ('Bool', 'RadialGradient', False),
                  ('Unsigned', 'BackgroundColor2', rgb(42, 49, 61)),
                  ('Unsigned', 'BackgroundColor3', rgb(50, 57, 69)),
                  ('Unsigned', 'DefaultShapeColor', rgb(87, 89, 94)),
                  ('Int', 'AntiAliasing', 3),
                  ('Bool', 'EnableBacklight', True), ('Bool', 'EnableFillLight', True),
                  ('String', 'NavigationStyle', 'Gui::RevitNavigationStyle'),
                  ('Int', 'OrbitStyle', 0))
        backup_path = os.path.join(models, '_settings_backup.json')
        if not os.path.exists(backup_path):               # keep the very first backup only
            have = {c[1] for c in (view.GetContents() or [])}
            old = {key: (getattr(view, 'Get' + kind)(key) if key in have else None) for kind, key, _ in wanted}
            with open(backup_path, 'w') as f:
                json.dump(old, f, indent=1)
        for kind, key, value in wanted:
            getattr(view, 'Set' + kind)(key, value)
        App.saveParameter()
        say('Applied the view settings (dark gradient background, steel parts, anti-aliasing, '
            'middle-button pan / Shift+middle orbit / wheel zoom)')
    except Exception:
        say('PROBLEM applying view settings:\n' + traceback.format_exc())

    say('Models folder: %s' % models)
    say('Setup finished. Restart FreeCAD now.')
    try:
        with open(os.path.join(models, '_setup_log.txt'), 'w') as f:
            f.write('\n'.join(report) + '\n')
    except Exception:
        pass


_setup_everything()
