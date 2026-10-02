# Packaging (PROJ-9)

| File | Purpose |
|------|---------|
| `umgebungssensoren-panel.spec` | PyInstaller spec — produces `dist/UmgebungssensorenPanel/` (one-dir) |
| `installer.iss` | Inno Setup script — produces `dist/installer/UmgebungssensorenPanel-Setup-<version>.exe` |
| `build.py` | Runs both steps; `--no-installer` stops after the bundle |
| `release.py` | Builds and publishes one version into the update folder on the institute share (`--dry-run` changes nothing) |
| `version_source.py` | Reads the three version numbers without importing the app |
| `make_icon.py` | Regenerates the committed `app.ico` (thermometer) from the standard library |

The full story — including what the user sees while installing and updating — is in
[`docs/installation.md`](../docs/installation.md). Same layout as the sibling project
"RFB Controll Panel" (its PROJ-6/PROJ-10).

## One-time setup

```bash
pip install -e "pc[dev,panel]"   # PySide6, platformdirs, pytest, ruff
pip install pyinstaller          # build tool only, not a runtime dependency
```

Install [Inno Setup 6.3 or newer](https://jrsoftware.org/isdl.php) for the installer
step. `build.py` finds `ISCC.exe` on PATH, under `%LOCALAPPDATA%\Programs\Inno Setup 6\`
(per-user install) or under `Program Files (x86)` / `Program Files`, and fails early with a
German hint if it is missing.

## Build

```bash
python packaging/build.py
```

## Publish (update folder on the NAS)

```bash
python packaging/release.py --dry-run   # check everything, change nothing
python packaging/release.py             # gates, build, copy + verify, latest.json, local tag
python packaging/release.py --push-tag  # … and push the tag panel-v<version> (approval!)
```

`release.py` is the **only** thing that writes into the update folder
`\\131.234.237.14\Gutmann\01_Interna\05_Software\Umgebungssensoren` (or the folder named by
`UMWELT_UPDATE_DIR`). The folder must exist; it needs a clean working tree. Installers are
never overwritten; `latest.json` is written last and atomically.

## Notes

- **One-dir, not one-file.** One-file bundles unpack to a temp directory on every launch,
  which slows startup and trips antivirus heuristics.
- **The install directory is read-only.** Everything the app writes (measurement database,
  settings, logs) goes to `%LOCALAPPDATA%\Umgebungssensoren\` via `umwelt_panel.config`.
  Never write next to the executable.
- **Per-user install** (`PrivilegesRequired=lowest`) — no admin rights, no "for all users?"
  dialog.
- **`AppId` is a stable GUID** (`918D6EB2-1FCC-4E91-85C0-5A5CFCD0C4F3`). Changing it makes
  Windows treat the next release as a separate product.
- **Uninstall keeps user data.** The data folder is outside `[Files]` on purpose.
- **`installer.iss` is UTF-8 with BOM.** Without the BOM Inno Setup 6 reads it in the ANSI
  code page and mangles the umlauts.
- **Version bump:** `__version__` in `pc/src/umwelt_panel/__init__.py` and
  `pc/src/umwelt_ctl/__init__.py` plus `version` in `pc/pyproject.toml` (one distribution
  ships both packages); `build.py` and `release.py` refuse to run while they disagree.
- **Tags:** `release.py` tags `panel-v<version>`; plain `vX.Y.Z` belongs to the combined
  firmware + PC release (`/release`).
