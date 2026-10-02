"""One-command release build: PyInstaller bundle + Inno Setup installer (PROJ-9).

    python packaging/build.py                 # bundle + installer
    python packaging/build.py --no-installer  # bundle only
    python packaging/build.py --keep-build    # keep the PyInstaller work directory

This script is pure orchestration. What goes into the bundle is decided in
``umgebungssensoren-panel.spec``, how the installation behaves in ``installer.iss``.

Requirements: PyInstaller (``pip install pyinstaller``) plus the panel extra
(``pip install -e "pc[panel]"``) and, for the installer step, Inno Setup 6.3 or newer
(``ISCC.exe`` on PATH, or in the per-user or per-machine default installation directory).

All user-facing output is German — this is a tool for the person cutting the release.
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

from version_source import read_version, version_mismatch, version_tuple

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"
SPEC = PACKAGING / "umgebungssensoren-panel.spec"
ISS = PACKAGING / "installer.iss"
ICON = PACKAGING / "app.ico"

BUILD = ROOT / "build"
DIST = ROOT / "dist"
EXE_NAME = "UmgebungssensorenPanel"
BUNDLE = DIST / EXE_NAME
INSTALLER_DIR = DIST / "installer"

INNO_DIRECTORY = "Inno Setup 6"
ISCC_EXECUTABLE = "ISCC.exe"

# Inno Setup 6 installs either per user or per machine. The per-user variant lands under
# %LOCALAPPDATA%\Programs and puts nothing on PATH, so a machine can have Inno Setup
# installed and still look "missing" when only Program Files is checked. Every root is
# derived from the environment — never a hardcoded user name or drive letter.
ISCC_ROOT_VARIABLES = (
    ("LOCALAPPDATA", "Programs"),
    ("ProgramFiles", None),
    ("ProgramFiles(x86)", None),
)

INNO_DOWNLOAD_URL = "https://jrsoftware.org/isdl.php"


def log(message: str) -> None:
    print(message, flush=True)


def use_utf8_console() -> None:
    """Umlauts in paths and messages must not kill the build on a cp1252 console."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def installer_name(version: str) -> str:
    return f"{EXE_NAME}-Setup-{version}.exe"


def resolve_version() -> str:
    """``__version__`` of the panel decides; umwelt_ctl and pyproject.toml have to agree."""
    problem = version_mismatch(ROOT)
    if problem is not None:
        raise SystemExit(problem)
    return read_version(ROOT)


def iscc_candidates() -> list[Path]:
    """Full paths to ISCC.exe to probe, in search order (PATH is handled separately)."""
    candidates: list[Path] = []
    for variable, subdirectory in ISCC_ROOT_VARIABLES:
        value = os.environ.get(variable)
        if not value:
            continue
        root = Path(value)
        if subdirectory is not None:
            root = root / subdirectory
        candidate = root / INNO_DIRECTORY / ISCC_EXECUTABLE
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def inno_missing_hint() -> str:
    """Name every location that was searched — otherwise the message is a dead end."""
    searched = "\n".join(f"  {candidate}" for candidate in iscc_candidates())
    return (
        "Inno Setup wurde nicht gefunden (ISCC.exe).\n"
        "\n"
        f"Bitte Inno Setup 6.3 oder neuer installieren: {INNO_DOWNLOAD_URL}\n"
        "\n"
        "Gesucht wurde in der PATH-Variable und unter:\n"
        f"{searched}\n"
        "\n"
        "Liegt Inno Setup an einer anderen Stelle, bitte dessen Installations-\n"
        "verzeichnis in die PATH-Variable aufnehmen.\n"
        "\n"
        "Nur das Bundle ohne Installer bauen: python packaging/build.py --no-installer"
    )


def find_iscc() -> str | None:
    found = shutil.which("iscc") or shutil.which("ISCC")
    if found:
        return found
    return next((str(path) for path in iscc_candidates() if path.is_file()), None)


def check_prerequisites(*, with_installer: bool) -> str | None:
    """Fail before the slow PyInstaller run, not after it."""
    if not SPEC.is_file():
        raise SystemExit(f"Die PyInstaller-Spec fehlt: {SPEC}")
    if not ICON.is_file():
        raise SystemExit(
            f"Das Anwendungssymbol fehlt: {ICON}\n"
            "Bitte einmal `python packaging/make_icon.py` ausführen."
        )

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        raise SystemExit(
            "PyInstaller ist nicht installiert.\nBitte installieren: pip install pyinstaller"
        ) from None
    try:
        import platformdirs  # noqa: F401
        import PySide6  # noqa: F401
    except ImportError:
        raise SystemExit(
            "Das Control Panel braucht PySide6 und platformdirs.\n"
            'Bitte installieren: pip install -e "pc[panel]"'
        ) from None

    if not with_installer:
        return None

    if not ISS.is_file():
        raise SystemExit(f"Das Inno-Setup-Skript fehlt: {ISS}")
    iscc = find_iscc()
    if iscc is None:
        raise SystemExit(inno_missing_hint())
    return iscc


def force_remove(function, path, excinfo):  # type: ignore[no-untyped-def]
    """Retry a failed rmtree step after clearing the read-only attribute.

    Windows refuses to delete a file or directory that carries FILE_ATTRIBUTE_READONLY,
    and a synced folder (OneDrive) hands that attribute out readily.
    """
    del excinfo
    try:
        os.chmod(path, stat.S_IWRITE)
        function(path)
    except OSError as error:
        raise SystemExit(
            f"Das alte Build-Artefakt konnte nicht gelöscht werden: {path}\n"
            f"  {error}\n"
            "\n"
            "Bitte prüfen, ob die Anwendung noch läuft oder ein Virenscanner bzw. die\n"
            "OneDrive-Synchronisierung die Datei sperrt, und den Ordner von Hand löschen."
        ) from error


def clean(*, keep_build: bool) -> None:
    """Remove leftovers from earlier runs so nothing stale can end up in the release."""
    targets = [BUNDLE, INSTALLER_DIR]
    if not keep_build:
        targets.append(BUILD)
    for target in targets:
        if target.exists():
            log(f"Aufräumen: {target}")
            # onexc lands in 3.12+, onerror is the 3.11 spelling; the project targets 3.11.
            shutil.rmtree(target, onerror=force_remove)


def run(command: list[str]) -> None:
    log("$ " + " ".join(command))
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode != 0:
        raise SystemExit(f"Abbruch: {Path(command[0]).name} endete mit Code {result.returncode}.")


def build_bundle() -> None:
    log("\n[1/2] PyInstaller-Bundle wird gebaut …")
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            str(SPEC),
            "--noconfirm",
            "--clean",
            "--distpath",
            str(DIST),
            "--workpath",
            str(BUILD),
        ]
    )
    executable = BUNDLE / f"{EXE_NAME}.exe"
    if not executable.is_file():
        raise SystemExit(
            f"Der Build lief durch, aber {executable} fehlt.\n"
            "Bitte die PyInstaller-Ausgabe auf Fehler prüfen."
        )
    log(f"Bundle fertig: {BUNDLE}")


def build_installer(iscc: str, version: str) -> Path:
    log("\n[2/2] Inno-Setup-Installer wird gebaut …")
    numeric = ".".join(str(part) for part in version_tuple(version))
    run([iscc, f"/DAppVersion={version}", f"/DAppVersionNumeric={numeric}", str(ISS)])
    setup = INSTALLER_DIR / installer_name(version)
    if not setup.is_file():
        raise SystemExit(f"Inno Setup lief durch, aber {setup} fehlt.")
    size_mb = setup.stat().st_size / (1024 * 1024)
    log(f"Installer fertig: {setup} ({size_mb:.1f} MB)")
    return setup


def main() -> int:
    use_utf8_console()

    parser = argparse.ArgumentParser(
        description="Baut das PyInstaller-Bundle und den Windows-Installer des "
        "Umgebungssensoren Control Panels."
    )
    parser.add_argument(
        "--no-installer", action="store_true", help="nur das Bundle bauen, ohne Installer"
    )
    parser.add_argument(
        "--keep-build",
        action="store_true",
        help="das PyInstaller-Arbeitsverzeichnis build/ nicht löschen",
    )
    args = parser.parse_args()

    with_installer = not args.no_installer
    version = resolve_version()
    iscc = check_prerequisites(with_installer=with_installer)

    log(f"Umgebungssensoren Control Panel {version} wird gebaut")
    clean(keep_build=args.keep_build)

    build_bundle()
    if iscc is not None:
        build_installer(iscc, version)
    else:
        log("\nInstaller übersprungen (--no-installer).")

    log("\nFertig.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
