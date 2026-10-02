"""Publish one Control Panel release to the institute file share: check, build, copy, tag.

The update function (PROJ-9, port of PROJ-10 of the sibling project "RFB Controll
Panel") reads ``latest.json`` from the update folder on the institute share and compares
its version against the running ``__version__``. That only
works if version, installer file name, checksum and Git tag can never drift apart, so
this script derives all of them from the same source and refuses to run when anything
disagrees.

Order matters:

1. Preconditions — versions agree, clean working tree, tag free (locally, and on
   origin with ``--push-tag``), update folder reachable (found with *the same search the application
   uses*), and no installer of this version in the folder yet. Nothing is ever
   overwritten.
2. The quality gates (``ruff check pc``, ``pytest pc/tests``), then
   ``packaging/build.py`` (bundle + installer).
3. The installer is copied to ``<name>.partial``, its SHA-256 compared with the
   original, then renamed to its final name.
4. **Only then** ``latest.json`` is written — via ``latest.json.partial`` and an atomic
   rename. A lab PC therefore never sees a version file pointing at an
   installer that is not completely there. If the copy fails, ``latest.json`` still
   points at the previous, complete version.
5. ``git tag -a panel-v<version>`` (local). Pushing it needs ``--push-tag`` — the
   project rule is: never push without explicit user approval.

The tag is ``panel-v<version>``, not ``v<version>``: plain ``vX.Y.Z`` tags belong to the
combined firmware + PC release of the ``/release`` workflow.

Usage::

    python packaging/release.py --dry-run          # check everything, change nothing
    python packaging/release.py                    # build, copy, write latest.json, tag
    python packaging/release.py --push-tag         # … and push the tag to origin
    python packaging/release.py --notes "…"        # own change notes instead of git log
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

PACKAGING = Path(__file__).resolve().parent
ROOT = PACKAGING.parent
sys.path.insert(0, str(PACKAGING))
# The application's own folder search is reused, so release and app can never disagree
# about where the update folder is. core/ is Qt-free, so this import needs no display.
sys.path.insert(0, str(ROOT / "pc" / "src"))

from build import use_utf8_console  # noqa: E402
from version_source import read_version, version_mismatch  # noqa: E402

from umwelt_panel.core.errors import UpdateError  # noqa: E402
from umwelt_panel.core.services.update_service import (  # noqa: E402
    MANIFEST_NAME,
    build_manifest,
    build_update_locator,
    installer_file_name,
    parse_manifest,
    parse_version,
    serialize_manifest,
    sha256_of_file,
)

INSTALLER_DIR = ROOT / "dist" / "installer"
PARTIAL_SUFFIX = ".partial"

#: Change notes from ``git log``: at most this many subjects, each cut to this length.
MAX_NOTE_LINES = 30
MAX_NOTE_LINE_CHARS = 120

#: Quality gates. A release is never cut from code that does not pass them.
GATES: tuple[tuple[str, list[str]], ...] = (
    ("ruff check", [sys.executable, "-m", "ruff", "check", "pc"]),
    ("pytest", [sys.executable, "-m", "pytest", "pc/tests", "-q"]),
)


class ReleaseError(RuntimeError):
    """A precondition or a step failed. The message is meant for the person at the terminal."""


def log(message: str) -> None:
    print(message, flush=True)


def capture(command: list[str], *, check: bool = True) -> str:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, check=False,
                            encoding="utf-8", errors="replace")  # git speaks UTF-8
    if check and result.returncode != 0:
        raise ReleaseError(
            f"Befehl fehlgeschlagen: {' '.join(command)}\n{result.stdout}{result.stderr}".strip()
        )
    return (result.stdout or "").strip()


def run(command: list[str]) -> None:
    log(f"→ {' '.join(command)}")
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode != 0:
        raise ReleaseError(f"Befehl fehlgeschlagen: {' '.join(command)}")


# -- checks ---------------------------------------------------------------------------


def resolve_version() -> str:
    """``__version__`` decides; pyproject.toml has to agree, or nothing happens."""
    problem = version_mismatch(ROOT)
    if problem is not None:
        raise ReleaseError(problem)
    return read_version(ROOT)


def check_clean_tree() -> None:
    """A release must be reproducible from the commit it claims to be built from."""
    dirty = capture(["git", "status", "--porcelain"])
    if dirty:
        raise ReleaseError(
            "Das Arbeitsverzeichnis ist nicht sauber. Ein Release muss aus einem "
            "committeten Stand entstehen, sonst lässt es sich später nicht "
            f"nachvollziehen.\n\n{dirty}"
        )


def check_tag_free(tag: str, *, check_origin: bool) -> None:
    if capture(["git", "tag", "--list", tag]):
        raise ReleaseError(
            f"Das Tag {tag} existiert bereits lokal. Version in pc/src/umwelt_panel/"
            "__init__.py, pc/src/umwelt_ctl/__init__.py und pc/pyproject.toml erhöhen."
        )
    if not check_origin:
        return
    result = subprocess.run(
        ["git", "ls-remote", "--tags", "origin", tag],
        cwd=ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        # The tag is pushed at the very end. Finding out then that origin is unreachable
        # would leave a published version without its tag.
        raise ReleaseError(
            "origin ist nicht erreichbar — ob das Tag dort schon existiert, lässt sich "
            f"nicht prüfen.\n{result.stderr.strip()}"
        )
    if result.stdout.strip():
        raise ReleaseError(f"Das Tag {tag} existiert bereits auf origin.")


def find_update_folder(update_dir: str | None = None) -> Path:
    """The update folder, found exactly the way the application finds it.

    ``UMWELT_UPDATE_DIR`` → UNC path → every network drive. For a release the folder only
    has to exist — before the very first release there is no ``latest.json`` yet.
    """
    try:
        return build_update_locator(update_dir).find_reachable_folder()
    except UpdateError as exc:
        raise ReleaseError(str(exc)) from None


def check_not_yet_published(folder: Path, version: str) -> None:
    """Never overwrite: an installer of this version must not be in the folder yet."""
    name = installer_file_name(version)
    for candidate in (folder / name, folder / (name + PARTIAL_SUFFIX)):
        if candidate.exists():
            raise ReleaseError(
                f"Im Update-Ordner liegt bereits „{candidate.name}“. Eine veröffentlichte "
                "Version wird nie überschrieben — bitte die Versionsnummer erhöhen."
            )


def check_no_downgrade(folder: Path, version: str) -> str | None:
    """The current ``latest.json`` must not point at the same or a newer version.

    Returns the version it currently points at, or ``None`` when there is none (yet).
    """
    manifest_path = folder / MANIFEST_NAME
    if not manifest_path.is_file():
        return None
    try:
        current = parse_manifest(manifest_path.read_bytes())
    except (UpdateError, OSError):
        log(f"Warnung: Die vorhandene {MANIFEST_NAME} ist ungültig und wird ersetzt.")
        return None
    new = parse_version(version)
    old = parse_version(current.version)
    if new is None or old is None or not new.is_newer_than(old):
        raise ReleaseError(
            f"{MANIFEST_NAME} zeigt bereits auf Version {current.version}. Version {version} "
            "ist nicht neuer — bitte die Versionsnummer erhöhen."
        )
    return current.version


def release_notes(explicit: str | None = None) -> str:
    """Commit subjects since the last tag (or the last few commits), shortened."""
    if explicit is not None and explicit.strip():
        return explicit.strip()
    previous = capture(["git", "describe", "--tags", "--abbrev=0"], check=False)
    revision_range = f"{previous}..HEAD" if previous else "HEAD"
    subjects = capture(
        [
            "git",
            "log",
            "--no-merges",
            f"--max-count={MAX_NOTE_LINES}",
            "--pretty=format:%s",
            revision_range,
        ]
    )
    return format_notes(subjects.splitlines())


def format_notes(subjects: list[str]) -> str:
    lines: list[str] = []
    for subject in subjects[:MAX_NOTE_LINES]:
        text = subject.strip()
        if not text:
            continue
        if len(text) > MAX_NOTE_LINE_CHARS:
            text = text[: MAX_NOTE_LINE_CHARS - 1].rstrip() + "…"
        lines.append(f"- {text}")
    return "\n".join(lines)


def run_gates() -> None:
    for name, command in GATES:
        log(f"Prüfe: {name}")
        run(command)


# -- actions --------------------------------------------------------------------------


def build(version: str) -> Path:
    run([sys.executable, str(PACKAGING / "build.py")])
    installer = INSTALLER_DIR / installer_file_name(version)
    if not installer.is_file():
        raise ReleaseError(f"Der Build meldete Erfolg, aber {installer} fehlt.")
    return installer


def copy_installer(installer: Path, folder: Path, version: str) -> tuple[Path, str]:
    """Copy under an intermediate name, verify, then rename. Never overwrites.

    The copy is verified *before* it gets its final name, so the final name only ever
    holds a complete, checked installer. Any failure removes the intermediate file.
    Returns the final path and the SHA-256 of the original.
    """
    name = installer_file_name(version)
    if installer.name != name:
        raise ReleaseError(f"Der Installer heißt „{installer.name}“, erwartet war „{name}“.")
    final = folder / name
    partial = folder / (name + PARTIAL_SUFFIX)
    check_not_yet_published(folder, version)

    original_sha = sha256_of_file(installer)
    try:
        log(f"Kopiere {name} → {partial}")
        shutil.copyfile(installer, partial)
        copy_sha = sha256_of_file(partial)
        if copy_sha != original_sha:
            raise ReleaseError(
                "Die Prüfsumme der Kopie auf dem Laufwerk stimmt nicht mit dem Original "
                "überein. Die Kopie wurde gelöscht; latest.json ist unverändert."
            )
        if final.exists():  # someone else was faster — still never overwrite
            raise ReleaseError(f"„{name}“ ist während des Kopierens aufgetaucht.")
        os.replace(partial, final)
    except BaseException:
        _remove_quietly(partial)
        raise
    log(f"Installer liegt geprüft auf dem Laufwerk: {final}")
    return final, original_sha


def write_latest_json(folder: Path, manifest: dict[str, str]) -> Path:
    """Write ``latest.json`` atomically: intermediate file, then rename over the old one."""
    target = folder / MANIFEST_NAME
    partial = folder / (MANIFEST_NAME + PARTIAL_SUFFIX)
    try:
        partial.write_bytes(serialize_manifest(manifest))
        os.replace(partial, target)
    except BaseException:
        _remove_quietly(partial)
        raise
    return target


def publish_to_folder(
    installer: Path,
    folder: Path,
    version: str,
    notes: str,
    published: datetime | None = None,
) -> dict[str, str]:
    """Copy the installer, verify it, and only then point ``latest.json`` at it."""
    final, sha256 = copy_installer(installer, folder, version)
    manifest = build_manifest(
        version=version,
        installer=final.name,
        sha256=sha256,
        published=published if published is not None else datetime.now(UTC),
        notes=notes,
    )
    write_latest_json(folder, manifest)
    log(f"{MANIFEST_NAME} zeigt jetzt auf Version {version}.")
    return manifest


def tag_and_push(tag: str, version: str, *, push: bool) -> None:
    run(["git", "tag", "-a", tag, "-m", f"Control Panel release {version}"])
    if push:
        run(["git", "push", "origin", tag])
    else:
        log(f"Tag {tag} nur lokal gesetzt. Hochladen nach Freigabe: git push origin {tag}")


def _remove_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        log(f"Warnung: „{path}“ konnte nicht entfernt werden — bitte von Hand löschen.")


# -- entry point ----------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Baut den Installer des Umgebungssensoren Control Panels und stellt "
        "ihn im Update-Ordner auf dem Institutslaufwerk bereit."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur prüfen und den Plan anzeigen — nichts bauen, kopieren oder taggen.",
    )
    parser.add_argument(
        "--skip-checks",
        action="store_true",
        help="Die Quality Gates (ruff, pytest) überspringen. Nur für Notfälle.",
    )
    parser.add_argument(
        "--push-tag",
        action="store_true",
        help="Das Tag am Ende auch nach origin hochladen (nur mit Freigabe).",
    )
    parser.add_argument(
        "--notes",
        default=None,
        help="Eigene Änderungsnotizen statt der Commit-Betreffzeilen seit dem letzten Tag.",
    )
    args = parser.parse_args(argv)
    use_utf8_console()

    try:
        version = resolve_version()
        tag = f"panel-v{version}"
        name = installer_file_name(version)

        log(f"Version: {version}   Tag: {tag}")
        check_clean_tree()
        check_tag_free(tag, check_origin=args.push_tag)
        log("Suche den Update-Ordner (dieselbe Suche wie die Anwendung) …")
        folder = find_update_folder()
        log(f"Update-Ordner: {folder}")
        check_not_yet_published(folder, version)
        previous = check_no_downgrade(folder, version)
        notes = release_notes(args.notes)
        log("Alle Vorbedingungen erfüllt.")
        log("")
        log("Änderungsnotizen:")
        log(notes or "  (keine)")

        if args.dry_run:
            log("")
            log("Testlauf — es wurde nichts verändert. Ohne --dry-run würde passieren:")
            if not args.skip_checks:
                log("  1. ruff check pc, pytest pc/tests")
            log("  2. packaging/build.py (Bundle + Installer)")
            log(f"  3. {name} → {folder / (name + PARTIAL_SUFFIX)}, Prüfsumme vergleichen,")
            log(f"     dann umbenennen in {folder / name}")
            log(
                f"  4. zuletzt {folder / MANIFEST_NAME} schreiben "
                f"(bisher: {previous or 'keine Versionsdatei'})"
            )
            push = f" und git push origin {tag}" if args.push_tag else " (nur lokal)"
            log(f"  5. git tag -a {tag}{push}")
            return 0

        if not args.skip_checks:
            run_gates()
        installer = build(version)
        log(f"Installer gebaut: {installer}")
        publish_to_folder(installer, folder, version, notes)
        try:
            tag_and_push(tag, version, push=args.push_tag)
        except ReleaseError as exc:
            raise ReleaseError(
                f"Version {version} liegt bereits im Update-Ordner, aber das Tag konnte "
                f"nicht gesetzt oder gepusht werden:\n{exc}\n\nBitte von Hand nachholen: "
                f"git tag -a {tag} -m 'Control Panel release {version}'"
            ) from None

        log("")
        log(f"Version {version} ist veröffentlicht. Die Rechner im Institutsnetz finden sie.")
        return 0
    except ReleaseError as exc:
        log("")
        log(f"Abgebrochen: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
