"""Updater UI (PROJ-9): notice, dialogs, controller, main-window wiring — offscreen Qt."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt  # noqa: E402

from umwelt_ctl.device import DeviceDisconnected  # noqa: E402
from umwelt_panel.core.services.log_service import MeasurementLog  # noqa: E402
from umwelt_panel.core.services.settings_service import SettingsService  # noqa: E402
from umwelt_panel.core.services.update_service import (  # noqa: E402
    MANIFEST_NAME,
    AvailableUpdate,
    UpdateLocator,
    UpdateService,
    build_manifest,
    installer_file_name,
    serialize_manifest,
    sha256_of_file,
)
from umwelt_panel.data.db import Database  # noqa: E402
from umwelt_panel.ui import dialogs  # noqa: E402
from umwelt_panel.ui import update_controller as uc_mod  # noqa: E402
from umwelt_panel.ui.device_controller import DeviceController  # noqa: E402
from umwelt_panel.ui.main_window import MainWindow  # noqa: E402
from umwelt_panel.ui.update_controller import UpdateController  # noqa: E402
from umwelt_panel.ui.update_dialogs import CopyProgressDialog, UpdateAvailableDialog  # noqa: E402
from umwelt_panel.ui.widgets.update_notice import UpdateNotice  # noqa: E402

pytestmark = pytest.mark.gui

WAIT = 5000
PAYLOAD = b"MZ installer " * 5000


def publish(folder: Path, version: str, *, sha256: str | None = None) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    installer = folder / installer_file_name(version)
    installer.write_bytes(PAYLOAD)
    manifest = build_manifest(version=version, installer=installer.name,
                              sha256=sha256 or sha256_of_file(installer),
                              published=dt.datetime(2026, 10, 2, 12, tzinfo=dt.UTC),
                              notes="- Updater eingebaut\n- <b>kein HTML</b>")
    (folder / MANIFEST_NAME).write_bytes(serialize_manifest(manifest))


def make_service(folder: Path, installed: str = "0.1.0") -> UpdateService:
    return UpdateService(UpdateLocator(env_dir=str(folder), unc_folder="",
                                       network_drives=lambda: [], timeout=2.0),
                         installed_version=installed)


def sample_update(tmp_path: Path) -> AvailableUpdate:
    return AvailableUpdate(version="0.2.0", installer_name=installer_file_name("0.2.0"),
                           installer_path=tmp_path / installer_file_name("0.2.0"),
                           installer_size=3 * 1024 * 1024, sha256="a" * 64,
                           published_on="02.10.2026", notes="- Neu", folder=tmp_path)


@pytest.fixture
def shown(monkeypatch):
    """Record every message box instead of opening one."""
    seen: list[tuple[str, str, str]] = []
    monkeypatch.setattr(dialogs, "show_error", lambda _p, t, m: seen.append(("error", t, m)))
    monkeypatch.setattr(dialogs, "show_info", lambda _p, t, m: seen.append(("info", t, m)))
    return seen


class Launches:
    def __init__(self, monkeypatch, tmp_path: Path):
        self.paths: list[Path] = []
        self.copy_dir = tmp_path / "temp-kopie"
        monkeypatch.setattr(uc_mod, "default_download_directory", lambda: self.copy_dir)
        monkeypatch.setattr(UpdateService, "launch_installer",
                            lambda _self, path: self.paths.append(path))


# --------------------------------------------------------------------------- widgets


def test_notice_shows_version_and_buttons(qtbot, tmp_path):
    notice = UpdateNotice("0.1.0")
    qtbot.addWidget(notice)
    assert notice.isHidden()
    update = sample_update(tmp_path)
    notice.show_update(update)
    assert not notice.isHidden()
    assert "Version 0.2.0 ist verfügbar (installiert: 0.1.0)" in notice.message()
    assert notice.install_button().text() == "Jetzt &aktualisieren"
    with qtbot.waitSignal(notice.install_requested, timeout=WAIT) as sig:
        qtbot.mouseClick(notice.install_button(), Qt.MouseButton.LeftButton)
    assert sig.args == [update]
    with qtbot.waitSignal(notice.dismissed, timeout=WAIT):
        qtbot.mouseClick(notice.later_button(), Qt.MouseButton.LeftButton)
    assert notice.isHidden()


def test_available_dialog_texts(qtbot, tmp_path):
    dlg = UpdateAvailableDialog("0.1.0", sample_update(tmp_path))
    qtbot.addWidget(dlg)
    assert dlg.windowTitle() == "Aktualisierung verfügbar"
    assert dlg.versions_text() == "Installiert: 0.1.0     Verfügbar: 0.2.0"
    assert dlg.published_text() == "Veröffentlicht am 02.10.2026"
    assert dlg.notes_text() == "- Neu"
    assert "UmgebungssensorenPanel-Setup-0.2.0.exe (3 MB)" in dlg.size_text()
    assert dlg.later_button().isDefault()  # „Später" is the safe default
    assert dlg.update_button().text() == "&Jetzt aktualisieren"


def test_progress_dialog_shows_progress_and_cancels(qtbot):
    dlg = CopyProgressDialog("UmgebungssensorenPanel-Setup-0.2.0.exe")
    qtbot.addWidget(dlg)
    dlg.show_progress(1024 * 1024, 4 * 1024 * 1024)
    assert dlg.status_text() == "1.0 von 4.0 MB kopiert"
    assert dlg.progress_bar().maximum() == 4096 and dlg.progress_bar().value() == 1024
    dlg.reject()
    assert dlg.is_cancelled() and not dlg.cancel_button().isEnabled()


# --------------------------------------------------------------------------- controller


def test_manual_check_up_to_date(qtbot, tmp_path, shown):
    publish(tmp_path / "upd", "0.1.0")
    ctl = UpdateController(make_service(tmp_path / "upd"))
    with qtbot.waitSignal(ctl.finished, timeout=WAIT):
        ctl.check_for_updates()
    assert shown == [("info", "Keine Aktualisierung nötig",
                      "Sie verwenden bereits die neueste Version (0.1.0). Es wurde nichts "
                      "kopiert.")]


def test_manual_check_share_unreachable(qtbot, tmp_path, shown):
    ctl = UpdateController(make_service(tmp_path / "nicht-da"))
    with qtbot.waitSignal(ctl.finished, timeout=WAIT):
        ctl.check_for_updates()
    assert len(shown) == 1
    kind, title, text = shown[0]
    assert (kind, title) == ("error", "Update-Laufwerk nicht erreichbar")
    assert "VPN" in text


def test_manual_check_broken_manifest(qtbot, tmp_path, shown):
    (tmp_path / "upd").mkdir()
    (tmp_path / "upd" / MANIFEST_NAME).write_text("{kaputt", encoding="utf-8")
    ctl = UpdateController(make_service(tmp_path / "upd"))
    with qtbot.waitSignal(ctl.finished, timeout=WAIT):
        ctl.check_for_updates()
    assert shown[0][:2] == ("error", "Update nicht möglich")
    assert "latest.json" in shown[0][2]


def test_background_check_is_silent_on_errors(qtbot, tmp_path, shown):
    ctl = UpdateController(make_service(tmp_path / "nicht-da"))
    found: list[object] = []
    ctl.update_found.connect(found.append)
    with qtbot.waitSignal(ctl.finished, timeout=WAIT):
        ctl.check_in_background()
    assert shown == [] and found == []


def test_manual_check_install_copies_verifies_and_quits(qtbot, tmp_path, shown, monkeypatch):
    publish(tmp_path / "upd", "0.2.0")
    launches = Launches(monkeypatch, tmp_path)
    ctl = UpdateController(make_service(tmp_path / "upd"))
    monkeypatch.setattr(ctl, "_ask_to_install", lambda _installed, _update: True)
    with qtbot.waitSignal(ctl.application_should_quit, timeout=WAIT):
        ctl.check_for_updates()
    copy = launches.copy_dir / "UmgebungssensorenPanel-Setup-0.2.0.exe"
    assert launches.paths == [copy] and copy.read_bytes() == PAYLOAD
    assert shown == []


def test_wrong_checksum_never_starts_the_installer(qtbot, tmp_path, shown, monkeypatch):
    publish(tmp_path / "upd", "0.2.0", sha256="0" * 64)
    launches = Launches(monkeypatch, tmp_path)
    ctl = UpdateController(make_service(tmp_path / "upd"))
    quits: list[bool] = []
    ctl.application_should_quit.connect(lambda: quits.append(True))
    monkeypatch.setattr(ctl, "_ask_to_install", lambda _installed, _update: True)
    with qtbot.waitSignal(ctl.finished, timeout=WAIT):
        ctl.check_for_updates()
    assert launches.paths == [] and quits == []
    assert shown[0][1] == "Update nicht möglich" and "Prüfsumme" in shown[0][2]
    assert list(launches.copy_dir.iterdir()) == []


def test_declining_the_dialog_copies_nothing(qtbot, tmp_path, shown, monkeypatch):
    publish(tmp_path / "upd", "0.2.0")
    launches = Launches(monkeypatch, tmp_path)
    ctl = UpdateController(make_service(tmp_path / "upd"))
    monkeypatch.setattr(ctl, "_ask_to_install", lambda _installed, _update: False)
    with qtbot.waitSignal(ctl.finished, timeout=WAIT):
        ctl.check_for_updates()
    assert launches.paths == [] and not launches.copy_dir.exists()


# --------------------------------------------------------------------------- main window


class Window:
    def __init__(self, qtbot, tmp_path: Path, service: UpdateService):
        self.db = Database(tmp_path / "messwerte.db")
        self.db.open()
        log = MeasurementLog(self.db)

        def no_device(_port):
            raise DeviceDisconnected("Kein Arduino (USB-VID 0x2341) gefunden.")

        controller = DeviceController(log, open_device=no_device, scan_ports=lambda: [])
        self.window = MainWindow(controller, log, SettingsService(self.db), updates=service)
        qtbot.addWidget(self.window)
        self.window.show()


def test_menu_bar_has_update_entry(qtbot, tmp_path, shown):
    w = Window(qtbot, tmp_path, make_service(tmp_path / "upd")).window
    titles = [a.text() for a in w.menuBar().actions()]
    assert titles == ["&Datei", "&Gerät", "Nach &Updates suchen", "&Hilfe"]
    assert w.update_action.objectName() == "updateMenuAction"
    assert w.update_notice.isHidden()


def test_startup_check_shows_notice_without_blocking(qtbot, tmp_path, shown, monkeypatch):
    publish(tmp_path / "upd", "0.2.0")
    launches = Launches(monkeypatch, tmp_path)
    w = Window(qtbot, tmp_path, make_service(tmp_path / "upd")).window
    w.schedule_update_check(0)
    qtbot.waitUntil(lambda: w.update_notice.isVisible(), timeout=WAIT)
    assert "Version 0.2.0 ist verfügbar" in w.update_notice.message()
    assert shown == []  # never a modal dialog from the silent check
    # „Jetzt aktualisieren" in the notice copies, verifies, starts and closes the window.
    qtbot.mouseClick(w.update_notice.install_button(), Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: launches.paths != [] and not w.isVisible(), timeout=WAIT)
    assert w.update_notice.isHidden()


def test_startup_check_stays_quiet_without_share(qtbot, tmp_path, shown):
    w = Window(qtbot, tmp_path, make_service(tmp_path / "nicht-da")).window
    with qtbot.waitSignal(w.update_controller.finished, timeout=WAIT):
        w.schedule_update_check(0)
    assert shown == [] and w.update_notice.isHidden()


def test_menu_entry_answers_out_loud(qtbot, tmp_path, shown):
    w = Window(qtbot, tmp_path, make_service(tmp_path / "nicht-da")).window
    with qtbot.waitSignal(w.update_controller.finished, timeout=WAIT):
        w.update_action.trigger()
    assert shown and shown[0][1] == "Update-Laufwerk nicht erreichbar"
