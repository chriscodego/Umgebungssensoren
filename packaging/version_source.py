"""Single source of truth for the release version, shared by build.py, release.py and the spec.

``__version__`` in ``pc/src/umwelt_panel/__init__.py`` is authoritative. It is read by
parsing the file rather than by importing the package: the PyInstaller spec must not drag
PySide6 into the analysis process, and a parse works even when the package is not
installed in the environment running the build.

``pc/pyproject.toml`` describes one distribution (``umwelt-ctl``) that ships both the CLI
package ``umwelt_ctl`` and the panel ``umwelt_panel``, so all three numbers have to agree.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

_VERSION_RE = re.compile(r"""^__version__\s*=\s*["'](?P<version>[^"']+)["']""", re.MULTILINE)
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?$")

PANEL_INIT = Path("pc") / "src" / "umwelt_panel" / "__init__.py"
CLI_INIT = Path("pc") / "src" / "umwelt_ctl" / "__init__.py"
PYPROJECT = Path("pc") / "pyproject.toml"


def _read_init_version(init: Path) -> str:
    match = _VERSION_RE.search(init.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"No __version__ assignment found in {init}")
    version = match.group("version")
    if not _SEMVER_RE.match(version):
        raise ValueError(f"__version__ {version!r} in {init} is not a MAJOR.MINOR.PATCH version")
    return version


def read_version(root: Path) -> str:
    """Return ``__version__`` of the Control Panel (``umwelt_panel/__init__.py``)."""
    return _read_init_version(root / PANEL_INIT)


def read_cli_version(root: Path) -> str:
    """Return ``__version__`` of the CLI package (``umwelt_ctl/__init__.py``)."""
    return _read_init_version(root / CLI_INIT)


def read_pyproject_version(root: Path) -> str:
    """Return ``project.version`` from ``pc/pyproject.toml``."""
    pyproject = root / PYPROJECT
    with pyproject.open("rb") as handle:
        data = tomllib.load(handle)
    version = data.get("project", {}).get("version")
    if not isinstance(version, str):
        raise ValueError(f"No project.version found in {pyproject}")
    return version


def version_mismatch(root: Path) -> str | None:
    """German description of a disagreement between the three numbers, or ``None``."""
    panel = read_version(root)
    cli = read_cli_version(root)
    pyproject = read_pyproject_version(root)
    if panel == cli == pyproject:
        return None
    return (
        "Die Versionsnummern stimmen nicht überein:\n"
        f"  {PANEL_INIT.as_posix():<36}: {panel}\n"
        f"  {CLI_INIT.as_posix():<36}: {cli}\n"
        f"  {PYPROJECT.as_posix():<36}: {pyproject}\n"
        "\n"
        "Bitte alle drei auf denselben Wert setzen und erneut starten."
    )


def version_tuple(version: str) -> tuple[int, int, int, int]:
    """Windows VERSIONINFO wants four numbers; a pre-release suffix is dropped."""
    core = re.split(r"[-+]", version, maxsplit=1)[0]
    major, minor, patch = (int(part) for part in core.split("."))
    return major, minor, patch, 0
