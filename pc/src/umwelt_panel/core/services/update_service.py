"""Finding a newer version on the institute file share, and copying its installer.

The update source is one folder on the institute share (PROJ-9, a 1:1 port of PROJ-10
of the sibling project "RFB Controll Panel")::

    <share>\\01_Interna\\05_Software\\Umgebungssensoren\\
        latest.json                       ← points at the current version
        UmgebungssensorenPanel-Setup-0.2.0.exe
        UmgebungssensorenPanel-Setup-0.1.0.exe   ← older installers stay (the way back)

The drive letter must not matter, so the folder is searched in this order and the first
candidate with a valid ``latest.json`` wins:

1. ``UMWELT_UPDATE_DIR`` (:func:`umwelt_panel.config.update_dir_override`), if set
2. the UNC path :data:`UNC_UPDATE_FOLDER` — works without any drive letter
3. every connected **network** drive letter plus :data:`RELATIVE_UPDATE_FOLDER`

A disconnected SMB drive can block a file system call for many seconds. Every probe
therefore runs in its own daemon thread with a time limit (:data:`PROBE_TIMEOUT_S`); a
hanging drive costs at most that long and never keeps the process from exiting.

Security rules this module exists to enforce:

* No credential, no internet. Only the update folder is read; nothing is ever written
  there by the application.
* ``latest.json`` is read with a size cap, parsed as JSON and reduced to five known
  fields. Anything missing or malformed means: no update.
* The installer file name from ``latest.json`` is untrusted. Only a bare
  ``UmgebungssensorenPanel-Setup-<version>.exe`` matching the announced version is accepted,
  and the resolved file must lie inside the update folder.
* The installer is never started from the share. It is copied into a temporary
  directory, its SHA-256 is computed *while* copying, and a mismatch deletes the copy.

No Qt: everything here is callable from a worker thread and testable without a
``QApplication``.
"""

from __future__ import annotations

import enum
import hashlib
import json
import logging
import os
import re
import string
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Generic, TypeVar

from umwelt_panel import __version__
from umwelt_panel.core.errors import (
    ChecksumMismatchError,
    CopyCancelledError,
    CopyFailedError,
    InstallerMissingError,
    TempDirectoryError,
    UpdateError,
    UpdateFolderUnreachableError,
    UpdateManifestInvalidError,
    UpdateManifestMissingError,
)

log = logging.getLogger(__name__)

# -- where to look -----------------------------------------------------------------------

#: The update folder relative to the root of the institute share.
RELATIVE_UPDATE_FOLDER = r"01_Interna\05_Software\Umgebungssensoren"

#: The institute share by IP — reachable without any drive letter. If the server IP
#: ever changes, only the drive-letter search keeps working (open question in the spec).
UNC_SHARE = r"\\131.234.237.14\Gutmann"
UNC_UPDATE_FOLDER = UNC_SHARE + "\\" + RELATIVE_UPDATE_FOLDER

#: Name of the version file inside the update folder.
MANIFEST_NAME = "latest.json"

#: Time limit per folder probe (spec: 5 s). A dead SMB drive blocks much longer.
PROBE_TIMEOUT_S = 5.0

# -- guard rails -------------------------------------------------------------------------

MAX_MANIFEST_BYTES = 64 * 1024
MAX_NOTES_CHARS = 8_000
MAX_INSTALLER_BYTES = 500 * 1024 * 1024
COPY_CHUNK_BYTES = 1024 * 1024

#: ``GetDriveTypeW`` answer for a network drive.
DRIVE_REMOTE = 4

INSTALLER_PREFIX = "UmgebungssensorenPanel-Setup-"
INSTALLER_SUFFIX = ".exe"

_SEMVER = r"\d+\.\d+\.\d+(?:-[0-9A-Za-z][0-9A-Za-z.\-]*)?"
_MANIFEST_VERSION_RE = re.compile(rf"^{_SEMVER}$")
_INSTALLER_NAME_RE = re.compile(
    rf"^{re.escape(INSTALLER_PREFIX)}(?P<version>{_SEMVER}){re.escape(INSTALLER_SUFFIX)}$"
)
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")

_VERSION_RE = re.compile(
    r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.\-]+))?(?:\+[0-9A-Za-z.\-]+)?$"
)

_T = TypeVar("_T")


# -- version handling ------------------------------------------------------------------


@dataclass(frozen=True)
class Version:
    """A semantic version, reduced to what a comparison actually needs."""

    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()

    def __str__(self) -> str:
        core = f"{self.major}.{self.minor}.{self.patch}"
        return f"{core}-{'.'.join(self.prerelease)}" if self.prerelease else core

    def sort_key(self) -> tuple[int, int, int, int, tuple[tuple[int, int, str], ...]]:
        """SemVer ordering: a pre-release sorts *below* the release it precedes."""
        identifiers = tuple(_identifier_key(part) for part in self.prerelease)
        return (self.major, self.minor, self.patch, 0 if self.prerelease else 1, identifiers)

    def is_newer_than(self, other: Version) -> bool:
        return self.sort_key() > other.sort_key()


def _identifier_key(part: str) -> tuple[int, int, str]:
    """Numeric pre-release identifiers rank below alphanumeric ones (SemVer §11)."""
    if part.isdigit():
        return (0, int(part), "")
    return (1, 0, part)


def parse_version(text: str | None) -> Version | None:
    """Read ``1.2.3``/``v1.2.3`` — ``None`` when the text is not a version at all.

    A version that cannot be read is never guessed at: the caller offers nothing.
    """
    if not text:
        return None
    match = _VERSION_RE.match(text.strip())
    if match is None:
        return None
    prerelease = match.group("prerelease")
    return Version(
        major=int(match.group("major")),
        minor=int(match.group("minor")),
        patch=int(match.group("patch")),
        prerelease=tuple(prerelease.split(".")) if prerelease else (),
    )


# -- the version file ------------------------------------------------------------------


@dataclass(frozen=True)
class UpdateManifest:
    """``latest.json``, reduced to the five fields this application reads."""

    version: str
    installer: str
    sha256: str
    published: datetime
    notes: str

    @property
    def published_on(self) -> str:
        """Display date, ``11.09.2026``."""
        return self.published.strftime("%d.%m.%Y")


def installer_file_name(version: str) -> str:
    """The one file name an installer for ``version`` may carry."""
    return f"{INSTALLER_PREFIX}{version}{INSTALLER_SUFFIX}"


def is_valid_installer_name(name: str, version: str) -> bool:
    """A bare ``UmgebungssensorenPanel-Setup-<version>.exe`` whose version matches — nothing else.

    No path separator, no drive, no ``..``: the name from the version file decides only
    what the file is called, never where it is.
    """
    if not name or "/" in name or "\\" in name or ":" in name or ".." in name:
        return False
    match = _INSTALLER_NAME_RE.match(name)
    return match is not None and match.group("version") == version


def build_manifest(
    version: str, installer: str, sha256: str, published: datetime, notes: str
) -> dict[str, str]:
    """The content of ``latest.json`` as ``packaging/release.py`` writes it.

    Writer and reader live side by side so the format cannot drift apart. The result is
    validated with the same rules the application applies when reading.
    """
    moment = published.astimezone(UTC).replace(microsecond=0)
    data = {
        "version": version,
        "installer": installer,
        "sha256": sha256.lower(),
        "published": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "notes": notes[:MAX_NOTES_CHARS],
    }
    parse_manifest(serialize_manifest(data))
    return data


def serialize_manifest(data: dict[str, str]) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def parse_manifest(raw: bytes) -> UpdateManifest:
    """Validate ``latest.json``. Anything odd raises :class:`UpdateManifestInvalidError`.

    Only the five known fields are read; unknown fields are ignored so a later format
    can add information without breaking older installations.
    """
    if len(raw) > MAX_MANIFEST_BYTES:
        raise _invalid(f"larger than {MAX_MANIFEST_BYTES} bytes")
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise _invalid("not readable JSON") from None
    if not isinstance(data, dict):
        raise _invalid("not a JSON object")

    version = data.get("version")
    installer = data.get("installer")
    sha256 = data.get("sha256")
    published = data.get("published")
    notes = data.get("notes")
    if not (
        isinstance(version, str)
        and isinstance(installer, str)
        and isinstance(sha256, str)
        and isinstance(published, str)
        and isinstance(notes, str)
    ):
        raise _invalid("a required field is missing or not text")

    if not _MANIFEST_VERSION_RE.match(version) or parse_version(version) is None:
        raise _invalid("the version is not MAJOR.MINOR.PATCH")
    if not is_valid_installer_name(installer, version):
        raise _invalid("the installer name is not UmgebungssensorenPanel-Setup-<version>.exe")
    if not _SHA256_RE.match(sha256):
        raise _invalid("the SHA-256 is not 64 hex digits")
    moment = _parse_timestamp(published)
    if moment is None:
        raise _invalid("the publication time is not an ISO 8601 timestamp")
    return UpdateManifest(
        version=version,
        installer=installer,
        sha256=sha256.lower(),
        published=moment,
        notes=notes[:MAX_NOTES_CHARS],
    )


def _invalid(reason: str) -> UpdateManifestInvalidError:
    # The reason goes to the log, never the file content: it is untrusted text.
    log.warning("The version file was rejected: %s", reason)
    return UpdateManifestInvalidError()


def _parse_timestamp(text: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


# -- probing with a time limit ---------------------------------------------------------


class _TimedOut(Exception):
    """A probe did not answer within its time limit."""


class _Job(Generic[_T]):
    """One call in a daemon thread. A hung SMB call never keeps the process alive."""

    def __init__(self, function: Callable[[], _T], name: str) -> None:
        self._function = function
        self._done = threading.Event()
        self._result: _T | None = None
        self._error: BaseException | None = None
        self.deadline = 0.0
        thread = threading.Thread(target=self._run, name=name, daemon=True)
        thread.start()

    def _run(self) -> None:
        try:
            self._result = self._function()
        except BaseException as exc:  # handed to the waiting thread, never lost
            self._error = exc
        finally:
            self._done.set()

    def result(self, deadline: float) -> _T:
        """Wait until ``deadline`` (``time.monotonic``); raise :class:`_TimedOut` after."""
        if not self._done.wait(max(0.0, deadline - time.monotonic())):
            raise _TimedOut()
        if self._error is not None:
            raise self._error
        return self._result  # type: ignore[return-value]


def run_with_timeout(
    function: Callable[[], _T], timeout: float, name: str = "umwelt-update-probe"
) -> _T:
    """Call ``function`` in a daemon thread; :class:`UpdateFolderUnreachableError` on timeout."""
    job = _Job(function, name)
    try:
        return job.result(time.monotonic() + timeout)
    except _TimedOut:
        log.warning("%s did not answer within %.1f s", name, timeout)
        raise UpdateFolderUnreachableError() from None


class ProbeStatus(enum.Enum):
    UNREACHABLE = "unreachable"
    NO_MANIFEST = "no manifest"
    INVALID_MANIFEST = "invalid manifest"
    OK = "ok"


@dataclass(frozen=True)
class FolderProbe:
    """What one candidate folder turned out to be."""

    status: ProbeStatus
    manifest: UpdateManifest | None = None


def probe_folder(folder: Path) -> FolderProbe:
    """Look into one candidate folder. Blocking file I/O — call it with a time limit."""
    if not folder.is_dir():
        return FolderProbe(ProbeStatus.UNREACHABLE)
    try:
        with (folder / MANIFEST_NAME).open("rb") as handle:
            # One byte past the limit so an oversized file is detectable.
            raw = handle.read(MAX_MANIFEST_BYTES + 1)
    except FileNotFoundError:
        return FolderProbe(ProbeStatus.NO_MANIFEST)
    except OSError:
        log.warning("The version file in a candidate folder could not be read")
        return FolderProbe(ProbeStatus.INVALID_MANIFEST)
    try:
        return FolderProbe(ProbeStatus.OK, parse_manifest(raw))
    except UpdateManifestInvalidError:
        return FolderProbe(ProbeStatus.INVALID_MANIFEST)


def is_directory(folder: Path) -> bool:
    return folder.is_dir()


def detect_network_drives() -> list[str]:
    """Roots of every drive letter Windows reports as a network drive (``Z:\\``).

    ``GetLogicalDrives`` + ``GetDriveTypeW == DRIVE_REMOTE`` through ``ctypes``; on any
    other platform there are no drive letters to search.
    """
    if sys.platform != "win32":
        return []
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetLogicalDrives.restype = ctypes.c_uint32
    kernel32.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
    kernel32.GetDriveTypeW.restype = ctypes.c_uint
    mask = int(kernel32.GetLogicalDrives())
    roots: list[str] = []
    for index, letter in enumerate(string.ascii_uppercase):
        if not mask & (1 << index):
            continue
        root = f"{letter}:\\"
        if int(kernel32.GetDriveTypeW(root)) == DRIVE_REMOTE:
            roots.append(root)
    return roots


@dataclass(frozen=True)
class LocatedManifest:
    folder: Path
    manifest: UpdateManifest


class UpdateLocator:
    """Finds the update folder — environment variable, then UNC, then network drives."""

    def __init__(
        self,
        env_dir: str = "",
        unc_folder: str | None = None,
        network_drives: Callable[[], Sequence[str]] | None = None,
        relative_folder: str = RELATIVE_UPDATE_FOLDER,
        timeout: float = PROBE_TIMEOUT_S,
        folder_probe: Callable[[Path], FolderProbe] = probe_folder,
    ) -> None:
        # Module globals are read here, not bound as defaults at import time, so the test
        # suite can divert them once for every test and never touch the real share.
        self._env_dir = env_dir.strip()
        self._unc_folder = UNC_UPDATE_FOLDER if unc_folder is None else unc_folder
        self._network_drives = detect_network_drives if network_drives is None else network_drives
        self._relative = relative_folder
        self._timeout = timeout
        self._probe = folder_probe

    @property
    def timeout(self) -> float:
        return self._timeout

    def locate(self) -> LocatedManifest:
        """The first candidate folder with a valid ``latest.json``.

        Raises :class:`UpdateFolderUnreachableError` when no folder answered,
        :class:`UpdateManifestInvalidError` when at least one had a broken version file,
        and :class:`UpdateManifestMissingError` when folders answered without one.
        """
        reachable = False
        invalid = False
        for folder, outcome in self._outcomes(self._probe):
            if outcome is None or outcome.status is ProbeStatus.UNREACHABLE:
                continue
            reachable = True
            if outcome.status is ProbeStatus.NO_MANIFEST:
                log.info("Update folder candidate without %s: %s", MANIFEST_NAME, folder)
                continue
            if outcome.status is ProbeStatus.INVALID_MANIFEST or outcome.manifest is None:
                log.info("Update folder candidate with an invalid %s: %s", MANIFEST_NAME, folder)
                invalid = True
                continue
            log.info("Update folder found: %s", folder)
            return LocatedManifest(folder, outcome.manifest)
        if invalid:
            raise UpdateManifestInvalidError()
        if reachable:
            raise UpdateManifestMissingError()
        log.info("No update folder candidate was reachable")
        raise UpdateFolderUnreachableError()

    def find_reachable_folder(self) -> Path:
        """The first candidate that exists at all — what ``release.py`` publishes into."""
        for folder, exists in self._outcomes(is_directory):
            if exists:
                return folder
        raise UpdateFolderUnreachableError()

    def run(self, function: Callable[[], _T], name: str) -> _T:
        """Any further share access, under the same time limit as a probe."""
        return run_with_timeout(function, self._timeout, name)

    # -- internals -------------------------------------------------------------------

    def _outcomes(self, probe: Callable[[Path], _T]) -> Iterator[tuple[Path, _T | None]]:
        """Probe every candidate in parallel; yield the outcomes in priority order.

        ``None`` stands for "did not answer in time" or "failed". All fixed candidates and
        the drive detection start at once, so a hanging candidate costs at most one time
        limit — no matter how many of them hang.
        """
        seen: set[str] = set()
        started = time.monotonic()
        fixed = [
            (folder, self._start(probe, folder, started))
            for folder in self._unique(self._fixed_candidates(), seen)
        ]
        drives: _Job[Sequence[str]] = _Job(self._network_drives, "umwelt-drive-detection")
        drives.deadline = started + self._timeout

        for folder, job in fixed:
            yield folder, self._collect(folder, job)

        try:
            roots = list(drives.result(drives.deadline))
        except _TimedOut:
            log.warning("The network drive detection did not answer within the time limit")
            roots = []
        except Exception as exc:
            log.warning("The network drive detection failed")
            log.debug("Drive detection error", exc_info=exc)
            roots = []

        drive_started = time.monotonic()
        candidates = [Path(root) / self._relative for root in roots]
        drive_jobs = [
            (folder, self._start(probe, folder, drive_started))
            for folder in self._unique(candidates, seen)
        ]
        for folder, job in drive_jobs:
            yield folder, self._collect(folder, job)

    def _fixed_candidates(self) -> list[Path]:
        candidates: list[Path] = []
        if self._env_dir:
            candidates.append(Path(self._env_dir))
        if self._unc_folder:
            candidates.append(Path(self._unc_folder))
        return candidates

    def _start(self, probe: Callable[[Path], _T], folder: Path, started: float) -> _Job[_T]:
        job: _Job[_T] = _Job(lambda: probe(folder), "umwelt-update-probe")
        job.deadline = started + self._timeout
        return job

    @staticmethod
    def _unique(folders: Sequence[Path], seen: set[str]) -> list[Path]:
        result: list[Path] = []
        for folder in folders:
            key = os.path.normcase(str(folder))
            if key in seen:
                continue
            seen.add(key)
            result.append(folder)
        return result

    def _collect(self, folder: Path, job: _Job[_T]) -> _T | None:
        try:
            return job.result(job.deadline)
        except _TimedOut:
            log.warning(
                "Update folder candidate did not answer within %.1f s: %s", self._timeout, folder
            )
        except Exception as exc:
            log.info("Update folder candidate could not be probed: %s", folder)
            log.debug("Probe error", exc_info=exc)
        return None


# -- data the UI gets ------------------------------------------------------------------


@dataclass(frozen=True)
class AvailableUpdate:
    """A newer version in the update folder, ready to be copied."""

    version: str
    installer_name: str
    installer_path: Path
    installer_size: int
    sha256: str
    published_on: str
    notes: str
    folder: Path


@dataclass(frozen=True)
class UpdateCheckResult:
    """What a check found. ``update`` is ``None`` when nothing newer is there."""

    installed_version: str
    latest_version: str
    folder: Path
    update: AvailableUpdate | None

    @property
    def update_available(self) -> bool:
        return self.update is not None


# -- the service -----------------------------------------------------------------------


class UpdateService:
    """Compares versions, copies the installer, and starts it. Nothing starts by itself."""

    def __init__(self, locator: UpdateLocator, installed_version: str = __version__) -> None:
        self._locator = locator
        self._installed = installed_version

    @property
    def installed_version(self) -> str:
        return self._installed

    # -- check -----------------------------------------------------------------------

    def check_for_update(self) -> UpdateCheckResult:
        """Find the update folder, read ``latest.json`` and compare it with what runs.

        Blocks for up to a few probe time limits — call it from a worker thread.
        """
        installed = parse_version(self._installed)
        if installed is None:  # pragma: no cover - __version__ is validated at build time
            raise UpdateError(f"Die installierte Version „{self._installed}“ ist nicht lesbar.")

        located = self._locator.locate()
        manifest = located.manifest
        latest = parse_version(manifest.version)
        if latest is None:  # pragma: no cover - parse_manifest already guarantees this
            raise UpdateManifestInvalidError()
        log.info("Newest version in the update folder: %s (installed: %s)", latest, installed)
        if not latest.is_newer_than(installed):
            return UpdateCheckResult(self._installed, manifest.version, located.folder, None)

        path, size = self._locator.run(
            lambda: resolve_installer(located.folder, manifest), "umwelt-installer-lookup"
        )
        update = AvailableUpdate(
            version=manifest.version,
            installer_name=manifest.installer,
            installer_path=path,
            installer_size=size,
            sha256=manifest.sha256,
            published_on=manifest.published_on,
            notes=manifest.notes,
            folder=located.folder,
        )
        return UpdateCheckResult(self._installed, manifest.version, located.folder, update)

    # -- copy ------------------------------------------------------------------------

    def copy_installer(
        self,
        update: AvailableUpdate,
        directory: Path,
        progress: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Path:
        """Copy the installer into ``directory``, hashing every byte on the way.

        Only a copy whose SHA-256 matches ``latest.json`` comes back. A cancelled,
        truncated or mismatching copy is removed before the error travels on, so no
        half or foreign installer can ever be started.
        """
        if not is_valid_installer_name(update.installer_name, update.version):
            log.error("Refused to copy an installer with an unexpected name")
            raise UpdateManifestInvalidError()
        report = progress if progress is not None else _ignore_progress
        cancelled = is_cancelled if is_cancelled is not None else _never_cancelled

        target_dir = _prepare_directory(directory)
        target = target_dir / update.installer_name
        partial = target_dir / (update.installer_name + ".partial")
        try:
            digest = _copy_hashing(update, partial, report, cancelled)
            if digest != update.sha256.lower():
                log.error(
                    "The copied installer for %s does not match the SHA-256 of the version "
                    "file — the copy is deleted and not started",
                    update.version,
                )
                raise ChecksumMismatchError()
            os.replace(partial, target)
        except BaseException:
            _remove_quietly(partial)
            raise
        log.info("Installer for version %s copied and verified", update.version)
        return target

    def launch_installer(self, path: Path) -> None:
        """Start the verified installer. The caller closes the application afterwards.

        Windows cannot replace a running executable, so this hand-over is the only way an
        update can happen at all.
        """
        if path.suffix.lower() != ".exe" or not path.is_file():
            raise UpdateError(
                "Die kopierte Datei ist kein ausführbarer Installer und wurde nicht gestartet."
            )
        try:
            # A fixed argument list, never a shell string.
            subprocess.Popen([str(path)], close_fds=True)
        except OSError:
            log.exception("The installer could not be started")
            raise UpdateError(
                "Der Installer konnte nicht gestartet werden.\n\n"
                f"Bitte führen Sie die Datei „{path}“ von Hand aus."
            ) from None
        log.info("Installer started; the application is shutting down for the update")


def resolve_installer(folder: Path, manifest: UpdateManifest) -> tuple[Path, int]:
    """The installer named by ``manifest``, proven to lie inside ``folder``."""
    if not is_valid_installer_name(manifest.installer, manifest.version):
        raise UpdateManifestInvalidError()
    candidate = folder / manifest.installer
    try:
        resolved = candidate.resolve(strict=True)
        home = folder.resolve(strict=True)
    except FileNotFoundError:
        log.warning("The installer named in the version file is missing")
        raise InstallerMissingError(manifest.installer) from None
    except OSError:
        log.warning("The installer named in the version file could not be resolved")
        raise InstallerMissingError(manifest.installer) from None
    if os.path.normcase(str(resolved.parent)) != os.path.normcase(str(home)):
        log.error("The installer named in the version file resolves outside the update folder")
        raise UpdateManifestInvalidError()
    if not resolved.is_file():
        raise InstallerMissingError(manifest.installer)
    size = resolved.stat().st_size
    if size <= 0 or size > MAX_INSTALLER_BYTES:
        log.warning("The installer in the update folder has an implausible size (%d bytes)", size)
        raise UpdateManifestInvalidError()
    return resolved, size


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(COPY_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_hashing(
    update: AvailableUpdate,
    destination: Path,
    progress: Callable[[int, int], None],
    is_cancelled: Callable[[], bool],
) -> str:
    """Copy chunk by chunk, checking for cancellation at every chunk boundary."""
    digest = hashlib.sha256()
    copied = 0
    total = update.installer_size
    try:
        with update.installer_path.open("rb") as source, destination.open("wb") as target:
            while True:
                if is_cancelled():
                    raise CopyCancelledError()
                chunk = source.read(COPY_CHUNK_BYTES)
                if not chunk:
                    break
                copied += len(chunk)
                if copied > MAX_INSTALLER_BYTES:
                    raise CopyFailedError()
                digest.update(chunk)
                target.write(chunk)
                progress(copied, total)
    except FileNotFoundError:
        log.warning("The installer disappeared from the update folder")
        raise InstallerMissingError(update.installer_name) from None
    except OSError:
        log.exception("The installer could not be copied")
        raise CopyFailedError() from None
    if copied == 0:
        raise CopyFailedError()
    return digest.hexdigest()


def _prepare_directory(directory: Path) -> Path:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / f".umwelt-update-write-test-{os.getpid()}"
        probe.write_bytes(b"")
        probe.unlink()
    except OSError:
        log.warning("The temporary directory is not writable")
        raise TempDirectoryError(directory) from None
    return directory


def _remove_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:  # pragma: no cover - a locked temp file is not worth an error
        log.warning("A partial installer copy could not be removed")


def _ignore_progress(copied: int, total: int) -> None:
    del copied, total


def _never_cancelled() -> bool:
    return False


def default_copy_directory() -> Path:
    """A per-user temporary directory — never the read-only installation directory."""
    return Path(tempfile.gettempdir()) / "umwelt-panel-update"


def build_update_locator(update_dir: str | None = None) -> UpdateLocator:
    """The production search: ``UMWELT_UPDATE_DIR`` → UNC path → every network drive."""
    if update_dir is None:
        from umwelt_panel.config import update_dir_override

        update_dir = update_dir_override()
    return UpdateLocator(
        env_dir=update_dir,
        unc_folder=UNC_UPDATE_FOLDER,
        network_drives=detect_network_drives,
    )


def build_update_service() -> UpdateService:
    """The production wiring. Cheap: nothing is read until a check actually runs."""
    return UpdateService(build_update_locator())


__all__ = (
    "MANIFEST_NAME",
    "PROBE_TIMEOUT_S",
    "RELATIVE_UPDATE_FOLDER",
    "UNC_UPDATE_FOLDER",
    "AvailableUpdate",
    "FolderProbe",
    "LocatedManifest",
    "ProbeStatus",
    "UpdateCheckResult",
    "UpdateLocator",
    "UpdateManifest",
    "UpdateService",
    "Version",
    "build_manifest",
    "build_update_locator",
    "build_update_service",
    "default_copy_directory",
    "detect_network_drives",
    "installer_file_name",
    "is_valid_installer_name",
    "parse_manifest",
    "parse_version",
    "probe_folder",
    "resolve_installer",
    "run_with_timeout",
    "serialize_manifest",
    "sha256_of_file",
)
