# FreeCAD-Fusion-Addons

Four small add-ons that make FreeCAD look and work more like Fusion. Written for FreeCAD 1.1 and so far only run on macOS.

| Add-on | What it adds |
|---|---|
| **ModelBrowser** | A "Models" panel listing the FreeCAD files in one folder with preview pictures. Double-click opens. Search, refresh, choose folder, import STEP files, rebuild previews, move to Trash (right-click or Delete). |
| **FusionLook** | A ground grid in every 3D view, optional text under toolbar icons, dark-steel styling for plain grey parts, and a **Panels** menu in the menu bar to show or hide everything here. |
| **JointSlider** | A "Joint Slider" panel: pick a joint in an assembly and move it with a slider, a typed value, Min / Max or Play. Every step is checked so fixed parts never move and limits are respected. |
| **ClaudeBridge** | Lets Claude run scripts inside FreeCAD and get results and pictures back through a folder (`~/FreeCAD Models/_bridge`). **Off every time FreeCAD starts**; switch it on from the Panels menu. |

## Install

1. Download or clone this repository.
2. In FreeCAD open **View > Panels > Python Console** and run, with your own path:

   ```python
   import runpy; runpy.run_path('/path/to/FreeCAD-Fusion-Addons/install.py')
   ```

3. Restart FreeCAD.

To update, pull the latest version and run `install.py` again. To remove an add-on, delete its folder from FreeCAD's user `Mod` folder (the installer prints where that is).

## Notes

- The Models panel starts on `~/FreeCAD Models`; use **More > Choose folder** to point it elsewhere.
- The view settings that go with the look (background colours, anti-aliasing, lighting, mouse navigation style) are FreeCAD preferences, not part of these add-ons.
- **ClaudeBridge runs any Python file placed in its inbox folder while it is switched on.** Leave it off unless you are using it. Every job is copied to `_bridge/done` and listed in `_bridge/log.txt`.
- The joint slider only lists joints it can really move, and measures how far each one travels when an assembly is first opened.
