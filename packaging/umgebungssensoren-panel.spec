# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Umgebungssensoren Control Panel (PROJ-9).

Build:  pyinstaller packaging/umgebungssensoren-panel.spec --noconfirm --clean
Output: dist/UmgebungssensorenPanel/ (one-dir; consumed by packaging/installer.iss)

One-dir on purpose: a one-file bundle unpacks into a temp directory on every launch,
which slows startup, trips antivirus heuristics and breaks relative paths. The
installer hides the directory from the user anyway.
"""

import sys
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

SPEC_DIR = Path(SPECPATH)
ROOT = SPEC_DIR.parent
SRC = ROOT / "pc" / "src"
PACKAGE = SRC / "umwelt_panel"

sys.path.insert(0, str(SPEC_DIR))
from version_source import read_version, version_tuple  # noqa: E402

VERSION = read_version(ROOT)
APP_NAME = "Umgebungssensoren Control Panel"
EXE_NAME = "UmgebungssensorenPanel"

ICON = SPEC_DIR / "app.ico"
if not ICON.exists():
    raise SystemExit(f"Icon missing: {ICON}. Run `python packaging/make_icon.py` first.")


def package_data(relative_path):
    """Ship a directory under pc/src/umwelt_panel/ into the bundle, file by file.

    Listing files explicitly keeps __pycache__ and stray .pyc files out of the bundle,
    and makes a missing directory fail the build instead of silently shipping nothing.
    """
    source = PACKAGE / relative_path
    if not source.is_dir():
        raise SystemExit(f"Expected data directory is missing: {source}")

    entries = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        destination = Path("umwelt_panel") / relative_path / path.relative_to(source).parent
        entries.append((str(path), str(destination)))
    return entries


# The stylesheet is opened via importlib.resources.files("umwelt_panel.ui.resources"),
# which PyInstaller's FrozenImporter maps to _MEIPASS/umwelt_panel/ui/resources — it does
# not show up in the import graph, so it has to be declared here.
datas = package_data("ui/resources")

hiddenimports = [
    # pyserial picks its port enumeration per platform at runtime.
    "serial.tools.list_ports_windows",
    # platformdirs selects its Windows backend by platform check.
    "platformdirs.windows",
    # Imported lazily inside functions of app.py; listed so the bundle never depends on
    # how deep the analysis looks.
    "umwelt_panel.config",
    "umwelt_panel.logging_setup",
    "umwelt_panel.ui.main_window",
    "umwelt_panel.ui.device_controller",
]

# Qt is the bulk of the download. Only modules the panel demonstrably does not use are
# listed. The panel needs QtCore, QtGui and QtWidgets only; the measurement log uses the
# stdlib sqlite3 module (no QtSql), the serial link pyserial (no QtSerialPort).
excludes = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQml",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtSpatialAudio",
    "PySide6.QtTextToSpeech",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtGraphs",
    "PySide6.QtDesigner",
    "PySide6.QtUiTools",
    "PySide6.QtHelp",
    "PySide6.QtTest",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtScxml",
    "PySide6.QtRemoteObjects",
    "PySide6.QtNetworkAuth",
    "PySide6.QtBluetooth",
    "PySide6.QtSql",
    "PySide6.QtSerialPort",
    # Not used by the panel; would only arrive through whatever else sits in the build venv.
    "numpy",
    "PIL",
    "pygments",
    # The Tk GUI of umwelt_ctl is not part of the panel.
    "tkinter",
    "umwelt_ctl.gui",
    # Development-only packages that must never end up in a release bundle.
    "pytest",
    "_pytest",
    "pytestqt",
    "coverage",
    "ruff",
    "PyInstaller",
]

version_resource = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=version_tuple(VERSION),
        prodvers=version_tuple(VERSION),
        mask=0x3F,
        flags=0x0,
        OS=0x40004,  # VOS_NT_WINDOWS32
        fileType=0x1,  # VFT_APP
        subtype=0x0,
    ),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040704B0",  # German (Germany), Unicode
                    [
                        StringStruct("CompanyName", "Universität Paderborn"),
                        StringStruct("FileDescription", APP_NAME),
                        StringStruct("FileVersion", VERSION),
                        StringStruct("InternalName", EXE_NAME),
                        StringStruct("LegalCopyright", "© Universität Paderborn"),
                        StringStruct("OriginalFilename", f"{EXE_NAME}.exe"),
                        StringStruct("ProductName", APP_NAME),
                        StringStruct("ProductVersion", VERSION),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [0x0407, 1200])]),
    ],
)

a = Analysis(
    [str(PACKAGE / "__main__.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=EXE_NAME,
    debug=False,
    strip=False,
    # No UPX: it saves little and raises antivirus flags.
    upx=False,
    console=False,  # GUI app: no console window may flash up on launch
    icon=str(ICON),
    version=version_resource,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=EXE_NAME,
)
