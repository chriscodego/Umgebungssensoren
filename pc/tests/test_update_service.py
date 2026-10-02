"""Update service (PROJ-9) — Qt-free, against a temporary folder. Never touches the share."""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import pytest

from umwelt_panel import config
from umwelt_panel.core.errors import (
    ChecksumMismatchError,
    CopyCancelledError,
    InstallerMissingError,
    UpdateError,
    UpdateFolderUnreachableError,
    UpdateManifestInvalidError,
    UpdateManifestMissingError,
)
from umwelt_panel.core.services import update_service as us
from umwelt_panel.core.services.update_service import (
    MANIFEST_NAME,
    FolderProbe,
    ProbeStatus,
    UpdateLocator,
    UpdateService,
    build_manifest,
    installer_file_name,
    is_valid_installer_name,
    parse_manifest,
    parse_version,
    serialize_manifest,
    sha256_of_file,
)

PUBLISHED = dt.datetime(2026, 10, 2, 12, 0, tzinfo=dt.UTC)
PAYLOAD = b"MZ fake installer " * 1000


def publish(folder: Path, version: str, payload: bytes = PAYLOAD, *,
            sha256: str | None = None, notes: str = "- Neu: Updater") -> Path:
    """Put an installer and a matching latest.json into ``folder`` (what release.py does)."""
    folder.mkdir(parents=True, exist_ok=True)
    installer = folder / installer_file_name(version)
    installer.write_bytes(payload)
    manifest = build_manifest(version=version, installer=installer.name,
                              sha256=sha256 or sha256_of_file(installer),
                              published=PUBLISHED, notes=notes)
    (folder / MANIFEST_NAME).write_bytes(serialize_manifest(manifest))
    return installer


def locator(folder: Path | str = "", *, drives=(), relative: str = "x",
            timeout: float = 2.0, probe=us.probe_folder) -> UpdateLocator:
    return UpdateLocator(env_dir=str(folder), unc_folder="", network_drives=lambda: list(drives),
                         relative_folder=relative, timeout=timeout, folder_probe=probe)


def service(folder: Path, installed: str = "0.1.0") -> UpdateService:
    return UpdateService(locator(folder), installed_version=installed)


# --------------------------------------------------------------------------- versions


@pytest.mark.parametrize("newer, older", [
    ("0.2.0", "0.1.0"), ("0.1.1", "0.1.0"), ("1.0.0", "0.99.99"), ("0.10.0", "0.9.0"),
    ("0.2.0", "0.2.0-rc.1"), ("0.2.0-rc.2", "0.2.0-rc.1"), ("0.2.0-beta", "0.2.0-alpha"),
])
def test_version_order(newer, older):
    assert parse_version(newer).is_newer_than(parse_version(older))
    assert not parse_version(older).is_newer_than(parse_version(newer))


def test_version_parsing():
    assert str(parse_version("v1.2.3")) == "1.2.3"
    assert not parse_version("0.1.0").is_newer_than(parse_version("0.1.0"))
    for bad in ("", None, "1.2", "eins.zwei.drei", "1.2.3.4", "1.2.3 extra"):
        assert parse_version(bad) is None


def test_installer_name_rules():
    assert installer_file_name("0.2.0") == "UmgebungssensorenPanel-Setup-0.2.0.exe"
    assert is_valid_installer_name("UmgebungssensorenPanel-Setup-0.2.0.exe", "0.2.0")
    name = "UmgebungssensorenPanel-Setup-0.2.0.exe"
    for bad in (installer_file_name("0.3.0"), "..\\" + name, "C:" + name, "sub/" + name,
                "RFBControlPanel-Setup-0.2.0.exe", name + ".bat", ""):
        assert not is_valid_installer_name(bad, "0.2.0"), bad


# --------------------------------------------------------------------------- latest.json


def test_manifest_round_trip_with_bom_and_unknown_fields():
    data = build_manifest(version="0.2.0", installer=installer_file_name("0.2.0"),
                          sha256="AB" * 32, published=PUBLISHED, notes="Änderungen")
    assert data["sha256"] == "ab" * 32 and data["published"] == "2026-10-02T12:00:00Z"
    raw = json.dumps({**data, "zukunft": 1}, ensure_ascii=False).encode("utf-8-sig")
    m = parse_manifest(raw)
    assert (m.version, m.notes, m.published_on) == ("0.2.0", "Änderungen", "02.10.2026")


def _manifest(**overrides) -> bytes:
    data = {"version": "0.2.0", "installer": installer_file_name("0.2.0"), "sha256": "a" * 64,
            "published": "2026-10-02T12:00:00Z", "notes": ""}
    data.update(overrides)
    return json.dumps({k: v for k, v in data.items() if v is not ...}).encode("utf-8")


@pytest.mark.parametrize("raw", [
    b"", b"{kaputt", b"[1, 2]", "\udcff".encode("utf-8", "surrogatepass"),
    _manifest(version=...), _manifest(sha256=...), _manifest(version=2),
    _manifest(version="0.2"), _manifest(sha256="xyz"), _manifest(published="gestern"),
    _manifest(installer="..\\UmgebungssensorenPanel-Setup-0.2.0.exe"),
    _manifest(installer=installer_file_name("0.3.0")),
    _manifest(notes="x" * (us.MAX_MANIFEST_BYTES + 1)),
], ids=["leer", "kein-json", "kein-objekt", "kein-utf8", "ohne-version", "ohne-sha",
        "version-zahl", "version-kurz", "sha-kaputt", "zeit-kaputt", "pfad-im-namen",
        "name-andere-version", "zu-gross"])
def test_broken_manifest_is_rejected(raw):
    with pytest.raises(UpdateManifestInvalidError):
        parse_manifest(raw)


# --------------------------------------------------------------------------- folder search


def test_check_finds_newer_version(tmp_path):
    installer = publish(tmp_path / "upd", "0.2.0")
    result = service(tmp_path / "upd").check_for_update()
    assert result.update_available and result.latest_version == "0.2.0"
    update = result.update
    assert update.installer_path == installer.resolve()
    assert update.installer_size == len(PAYLOAD)
    assert update.published_on == "02.10.2026" and update.notes == "- Neu: Updater"


@pytest.mark.parametrize("installed", ["0.2.0", "0.3.0"])
def test_same_or_older_version_is_no_update(tmp_path, installed):
    publish(tmp_path / "upd", "0.2.0")
    result = service(tmp_path / "upd", installed).check_for_update()
    assert not result.update_available
    assert result.installed_version == installed and result.latest_version == "0.2.0"


def test_missing_manifest(tmp_path):
    (tmp_path / "upd").mkdir()
    with pytest.raises(UpdateManifestMissingError):
        service(tmp_path / "upd").check_for_update()


def test_broken_manifest_in_folder(tmp_path):
    (tmp_path / "upd").mkdir()
    (tmp_path / "upd" / MANIFEST_NAME).write_text("{nicht json", encoding="utf-8")
    with pytest.raises(UpdateManifestInvalidError):
        service(tmp_path / "upd").check_for_update()


def test_unreachable_folder(tmp_path):
    with pytest.raises(UpdateFolderUnreachableError) as exc:
        service(tmp_path / "gibt-es-nicht").check_for_update()
    assert "nicht erreichbar" in str(exc.value)
    assert "05_Software\\Umgebungssensoren" in str(exc.value)


def test_hanging_share_costs_at_most_the_time_limit(tmp_path):
    release = threading.Event()

    def hanging(_folder: Path) -> FolderProbe:
        release.wait(10)
        return FolderProbe(ProbeStatus.UNREACHABLE)

    started = time.monotonic()
    try:
        with pytest.raises(UpdateFolderUnreachableError):
            UpdateService(locator(tmp_path, timeout=0.3, probe=hanging)).check_for_update()
    finally:
        release.set()
    assert time.monotonic() - started < 2.0


def test_installer_named_in_manifest_is_missing(tmp_path):
    installer = publish(tmp_path / "upd", "0.2.0")
    installer.unlink()
    with pytest.raises(InstallerMissingError):
        service(tmp_path / "upd").check_for_update()


def test_network_drive_fallback_and_priority(tmp_path):
    publish(tmp_path / "laufwerk" / "rel", "0.3.0")
    found = locator("", drives=[str(tmp_path / "laufwerk")], relative="rel").locate()
    assert found.manifest.version == "0.3.0"
    # The environment variable wins over every drive.
    publish(tmp_path / "env", "0.2.0")
    found = locator(tmp_path / "env", drives=[str(tmp_path / "laufwerk")],
                    relative="rel").locate()
    assert found.manifest.version == "0.2.0"
    assert locator("", drives=[str(tmp_path / "laufwerk")],
                   relative="rel").find_reachable_folder() == tmp_path / "laufwerk" / "rel"


def test_update_dir_env_override(tmp_path, monkeypatch):
    publish(tmp_path / "env", "0.5.0")
    monkeypatch.setenv(config.UPDATE_DIR_ENV, str(tmp_path / "env"))
    assert config.update_dir_override() == str(tmp_path / "env")
    result = UpdateService(us.build_update_locator(), installed_version="0.1.0").check_for_update()
    assert result.latest_version == "0.5.0" and result.folder == tmp_path / "env"


def test_default_search_never_reaches_the_real_share_in_tests():
    # conftest diverts the UNC path and the drive list; without UMWELT_UPDATE_DIR the
    # search finds nothing (and fast).
    with pytest.raises(UpdateFolderUnreachableError):
        us.build_update_service().check_for_update()


# --------------------------------------------------------------------------- copy + checksum


def test_copy_verifies_checksum_and_reports_progress(tmp_path):
    publish(tmp_path / "upd", "0.2.0")
    svc = service(tmp_path / "upd")
    update = svc.check_for_update().update
    progress: list[tuple[int, int]] = []
    path = svc.copy_installer(update, tmp_path / "temp",
                              progress=lambda c, t: progress.append((c, t)))
    assert path == tmp_path / "temp" / "UmgebungssensorenPanel-Setup-0.2.0.exe"
    assert path.read_bytes() == PAYLOAD
    assert progress[-1] == (len(PAYLOAD), len(PAYLOAD))
    assert [p.name for p in (tmp_path / "temp").iterdir()] == [path.name]
    # The update folder was only read.
    assert sorted(p.name for p in (tmp_path / "upd").iterdir()) == [
        "UmgebungssensorenPanel-Setup-0.2.0.exe", MANIFEST_NAME]


def test_wrong_checksum_deletes_the_copy(tmp_path):
    publish(tmp_path / "upd", "0.2.0", sha256="0" * 64)
    svc = service(tmp_path / "upd")
    update = svc.check_for_update().update
    with pytest.raises(ChecksumMismatchError) as exc:
        svc.copy_installer(update, tmp_path / "temp")
    assert "NICHT gestartet" in str(exc.value)
    assert list((tmp_path / "temp").iterdir()) == []


def test_cancelled_copy_leaves_nothing(tmp_path):
    publish(tmp_path / "upd", "0.2.0")
    svc = service(tmp_path / "upd")
    update = svc.check_for_update().update
    with pytest.raises(CopyCancelledError):
        svc.copy_installer(update, tmp_path / "temp", is_cancelled=lambda: True)
    assert list((tmp_path / "temp").iterdir()) == []


def test_installer_vanishing_during_copy(tmp_path):
    installer = publish(tmp_path / "upd", "0.2.0")
    svc = service(tmp_path / "upd")
    update = svc.check_for_update().update
    installer.unlink()
    with pytest.raises(InstallerMissingError):
        svc.copy_installer(update, tmp_path / "temp")


def test_launch_uses_an_argument_list(tmp_path, monkeypatch):
    exe = tmp_path / "UmgebungssensorenPanel-Setup-0.2.0.exe"
    exe.write_bytes(b"MZ")
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: calls.append((args, kw)))
    UpdateService(locator(tmp_path)).launch_installer(exe)
    assert calls == [([str(exe)], {"close_fds": True})]


def test_launch_refuses_non_executables(tmp_path):
    other = tmp_path / "latest.json"
    other.write_text("{}", encoding="utf-8")
    with pytest.raises(UpdateError):
        UpdateService(locator(tmp_path)).launch_installer(other)
    with pytest.raises(UpdateError):
        UpdateService(locator(tmp_path)).launch_installer(tmp_path / "fehlt.exe")


def test_copy_directory_is_in_temp_not_install_dir():
    target = us.default_copy_directory()
    assert target.parent == Path(tempfile.gettempdir())
    assert target.name == "umwelt-panel-update"


def test_constants_match_the_agreed_update_folder():
    assert us.RELATIVE_UPDATE_FOLDER == r"01_Interna\05_Software\Umgebungssensoren"
    assert us.UNC_SHARE + "\\" + us.RELATIVE_UPDATE_FOLDER == (
        r"\\131.234.237.14\Gutmann\01_Interna\05_Software\Umgebungssensoren")
    assert us.PROBE_TIMEOUT_S == 5.0
