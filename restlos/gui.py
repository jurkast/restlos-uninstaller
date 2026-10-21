from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from . import APP_ID, APP_NAME, APP_TAGLINE, PROJECT_URL, __version__
from .analyzer import RemovalAnalyzer
from .backup import BackupManager
from .i18n import LanguageSettings, display_text, translate as _
from .locations import LocationResolver, LocationResult, folder_for_path
from .models import AppRecord, Confidence, RecoveryRecord, RemovalPlan, RemovalResult, RestoreResult, SourceKind
from .recovery import RecoveryManager
from .remover import RemovalExecutor
from .scanners import ApplicationScanner
from .updater import CHECK_INTERVAL_SECONDS, FIRST_CHECK_DELAY_SECONDS, Updater, UpdateError, UpdateStatus
from .utils import format_size


ICON_PATH = Path(__file__).with_name("icon.svg")

# Restlos-Designsprache (wie Restlos Bewerbung): dunkle Petrol-Navigation, helle Karten,
# Mint-Akzent, dunkles Hero-Feld und Hinweise unten rechts. GTK 4.6 kennt keine CSS-Variablen,
# daher stehen die Farben je Modus in eigenen Blöcken.
CSS = """
window.restlos-root, window.restlos-root > contents { background-image: none; }
headerbar.restlos-header {
  min-height: 46px;
  background-image: none;
  background-color: #112c38;
  color: #d9e8ec;
  border-bottom: 1px solid #0b222c;
  box-shadow: none;
}
headerbar.restlos-header button { color: #d9e8ec; background-color: transparent; border-color: transparent; }
headerbar.restlos-header button:hover { background-color: #244652; }
headerbar.restlos-header .header-title { font-weight: 700; }
headerbar.restlos-header windowcontrols button { color: #d9e8ec; }

/* Navigation */
.nav-sidebar { background-color: #112c38; color: #d9e8ec; padding: 26px 18px 18px 18px; }
.brand-name { font-size: 1.25em; font-weight: 800; letter-spacing: -0.4px; color: #ffffff; }
.brand-sub { font-size: 0.72em; letter-spacing: 2px; color: #8faeb9; font-weight: 700; }
.side-title { font-size: 0.70em; letter-spacing: 2px; color: #7e9ba7; font-weight: 700; margin: 22px 12px 6px 12px; }
button.nav {
  background-image: none; background-color: transparent; color: #c0d2d9;
  border: none; border-radius: 9px; padding: 10px 12px; box-shadow: none; font-weight: 600;
}
button.nav:hover { background-color: #1b3b48; color: #e8f4f6; }
button.nav.active { background-color: #244652; color: #9bf1dc; }
.nav-count { font-size: 0.80em; color: #8faeb9; }
button.nav.active .nav-count { color: #9bf1dc; }
.side-bottom { border-top: 1px solid #34505a; padding-top: 16px; color: #92b8bc; font-size: 0.86em; }
.side-bottom .local { color: #6ce0c3; font-weight: 700; }
.side-bottom button {
  background-image: none; background-color: transparent; color: #c8dce0;
  border: 1px solid #34505a; border-radius: 9px; padding: 6px 10px; box-shadow: none;
}
.side-bottom button:hover { background-color: #1b3b48; }
.side-version { color: #7e9ba7; font-size: 0.86em; }

/* Grundelemente */
.eyebrow { font-size: 0.72em; font-weight: 800; letter-spacing: 2px; }
.page-title { font-size: 1.95em; font-weight: 800; letter-spacing: -0.8px; }
.section-title { font-size: 1.15em; font-weight: 750; }
.hero-title { font-size: 1.55em; font-weight: 750; letter-spacing: -0.4px; }
.empty-title { font-size: 1.40em; font-weight: 750; }
.app-name { font-weight: 700; }
.app-source { font-size: 0.86em; }
.card, .stat-tile, .safety-card, .warning-card, .info-card, .list-card, .detail-hero {
  border-radius: 15px; border: 1px solid; padding: 18px;
}
.list-card { padding: 14px; }
.stat-tile { border-radius: 12px; padding: 13px 15px; }
.stat-heading { font-size: 0.72em; font-weight: 800; letter-spacing: 1.6px; }
.stat-value { font-size: 1.35em; font-weight: 800; }
.hero {
  border-radius: 17px; padding: 26px 30px; background-color: #183c48; color: #ffffff;
}
.hero .hero-text { color: #b7d0d8; }
.hero .hero-number { font-size: 3.2em; font-weight: 800; color: #8ee6cf; }
.hero .hero-number-label { color: #b7d0d8; font-size: 0.86em; }
.hero .hero-version { font-size: 2.3em; }
window.restlos-light .hero .hero-eyebrow, window.restlos-dark .hero .hero-eyebrow { color: #8ee6cf; }
.pill { border-radius: 999px; padding: 5px 11px; font-size: 0.82em; font-weight: 700; }
.source-badge { border-radius: 999px; padding: 4px 10px; font-size: 0.84em; font-weight: 700; }
.info-icon { border-radius: 12px; padding: 12px; }
.scan-card { border-radius: 10px; padding: 9px 11px; }
.app-list { background-color: transparent; }
.app-list row { border-radius: 10px; margin: 2px 0; }
.target-row { border-bottom: 1px solid; padding: 9px 4px; }
.warning-row { padding: 2px 0; }
.action-bar { padding-top: 12px; border-top: 1px solid; }
.danger-note { font-weight: 700; }
.status-line { border-radius: 8px; padding: 11px 13px; }
.status-line.good { border-left: 3px solid #2b9a7e; }
.status-line.warn { border-left: 3px solid #cb9336; }
.status-line.bad { border-left: 3px solid #c0533f; }
button.warning-more { min-width: 28px; min-height: 28px; padding: 0 7px; background-image: none; background-color: transparent; font-weight: 800; }

button, menubutton > button, dropdown > button {
  background-image: none; border: 1px solid; border-radius: 9px; padding: 8px 14px; box-shadow: none; text-shadow: none;
}
entry, searchentry, dropdown > button { border: 1px solid; border-radius: 8px; }
button.primary, button.suggested-action {
  color: #ffffff; background-color: #167c77; border-color: #167c77; font-weight: 700;
}
button.primary:hover, button.suggested-action:hover { background-color: #1b8f89; }
button.destructive-action { color: #fff6f2; background-color: #b0473a; border-color: #b0473a; font-weight: 700; }
button.destructive-action:hover { background-color: #c25244; }
button:focus-visible, entry:focus-within, dropdown > button:focus-visible { outline: 2px solid #50b9ae; outline-offset: 1px; }
checkbutton check { border: 1px solid; border-radius: 5px; }
checkbutton check:checked, switch:checked { background-color: #167c77; border-color: #167c77; color: #ffffff; }
progressbar trough { border-radius: 999px; min-height: 8px; }
progressbar progress { background-color: #167c77; border-radius: 999px; min-height: 8px; }
scrollbar slider { border-radius: 999px; }
popover contents { border-radius: 10px; }
paned > separator { min-width: 8px; background-image: none; background-color: transparent; border: none; }

/* Hinweis unten rechts (wie „notice“ in Restlos Bewerbung) */
.notice {
  background-color: #123c46; color: #ffffff; border-radius: 12px; padding: 14px 18px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.30);
}
.notice button { background-image: none; color: #ffffff; background-color: transparent; border-color: #3d6670; }
.notice button:hover { background-color: #1d4f5a; }
.notice button.primary { background-color: #6ce0c3; color: #103945; border-color: #6ce0c3; }
.notice button.primary:hover { background-color: #8ee6cf; }

/* Hell */
window.restlos-light { background-color: #f1f4f5; color: #203441; }
window.restlos-light .main-area, window.restlos-light.dialog-surface { background-color: #f1f4f5; }
window.restlos-light .muted, window.restlos-light .app-source { color: #667d89; }
window.restlos-light .eyebrow, window.restlos-light .stat-heading { color: #167c77; }
window.restlos-light .card, window.restlos-light .stat-tile, window.restlos-light .safety-card,
window.restlos-light .info-card, window.restlos-light .list-card, window.restlos-light .detail-hero {
  background-color: #ffffff; border-color: #dce5e7; color: #203441;
}
window.restlos-light .warning-card { background-color: #fff6e3; border-color: #e7cf98; color: #6a4a0e; }
window.restlos-light button.warning-more { color: #6a4a0e; border-color: #d9bb72; }
window.restlos-light .pill, window.restlos-light .source-badge { background-color: #dff3ed; color: #126b63; }
window.restlos-light .info-icon { background-color: #e1f1ec; color: #167c77; }
window.restlos-light .scan-card, window.restlos-light .status-line { background-color: #f8fafb; }
window.restlos-light .app-list row, window.restlos-light list row { color: #203441; }
window.restlos-light .app-list row:hover { background-color: #f1f6f7; }
window.restlos-light .app-list row:selected { background-color: #dff3ed; color: #12352f; }
window.restlos-light .target-row, window.restlos-light .action-bar { border-color: #e3eaec; }
window.restlos-light button, window.restlos-light menubutton > button, window.restlos-light dropdown > button {
  background-color: #ffffff; color: #203441; border-color: #dce5e7;
}
window.restlos-light button:hover, window.restlos-light dropdown > button:hover { border-color: #167c77; }
window.restlos-light button:disabled { color: #9aabb3; background-color: #f4f7f8; }
window.restlos-light entry, window.restlos-light searchentry { background-color: #f8fafb; color: #203441; border-color: #dce5e7; }
window.restlos-light checkbutton check { background-color: #ffffff; border-color: #a9bcc3; }
window.restlos-light progressbar trough { background-color: #dce5e7; }
window.restlos-light separator { background-color: #dce5e7; }
window.restlos-light paned > separator, window.restlos-dark paned > separator { background-color: transparent; }
window.restlos-light popover contents { background-color: #ffffff; color: #203441; border: 1px solid #dce5e7; }
window.restlos-light .confidence-certain { color: #147a60; }
window.restlos-light .confidence-high { color: #246cb0; }
window.restlos-light .confidence-possible { color: #9a6400; }
window.restlos-light .danger-note { color: #b52d25; }

/* Dunkel */
window.restlos-dark { background-color: #15232e; color: #e3edef; }
window.restlos-dark .main-area, window.restlos-dark.dialog-surface { background-color: #15232e; }
window.restlos-dark .muted, window.restlos-dark .app-source { color: #a6bbc5; }
window.restlos-dark .eyebrow, window.restlos-dark .stat-heading { color: #6ce0c3; }
window.restlos-dark .card, window.restlos-dark .stat-tile, window.restlos-dark .safety-card,
window.restlos-dark .info-card, window.restlos-dark .list-card, window.restlos-dark .detail-hero {
  background-color: #20323e; border-color: #3a505c; color: #e3edef;
}
window.restlos-dark .warning-card { background-color: #3a2f1f; border-color: #6f563b; color: #f2d0a8; }
window.restlos-dark button.warning-more { color: #f2d0a8; border-color: #6f563b; }
window.restlos-dark .pill, window.restlos-dark .source-badge { background-color: #244652; color: #9bf1dc; }
window.restlos-dark .info-icon { background-color: #244652; color: #9bf1dc; }
window.restlos-dark .scan-card, window.restlos-dark .status-line { background-color: #172a35; }
window.restlos-dark .app-list row, window.restlos-dark list row { color: #e3edef; }
window.restlos-dark .app-list row:hover { background-color: #263b48; }
window.restlos-dark .app-list row:selected { background-color: #244652; color: #e3edef; }
window.restlos-dark .target-row, window.restlos-dark .action-bar { border-color: #31464f; }
window.restlos-dark button, window.restlos-dark menubutton > button, window.restlos-dark dropdown > button {
  background-color: #20323e; color: #e3edef; border-color: #3a505c;
}
window.restlos-dark button:hover, window.restlos-dark dropdown > button:hover { border-color: #6ce0c3; }
window.restlos-dark button:disabled { color: #6f8590; background-color: #1b2b36; }
window.restlos-dark entry, window.restlos-dark searchentry { background-color: #172a35; color: #e3edef; border-color: #3a505c; }
window.restlos-dark checkbutton check { background-color: #172a35; border-color: #58717a; }
window.restlos-dark progressbar trough { background-color: #2b404b; }
window.restlos-dark separator { background-color: #3a505c; }
window.restlos-dark popover contents { background-color: #20323e; color: #e3edef; border: 1px solid #3a505c; }
window.restlos-dark .confidence-certain { color: #84dfc5; }
window.restlos-dark .confidence-high { color: #8fc9ff; }
window.restlos-dark .confidence-possible { color: #f2ba79; }
window.restlos-dark .danger-note { color: #ff9284; }

/* Semantische Schaltflächen behalten ihre Farbe in beiden Modi. */
window.restlos-light button.primary, window.restlos-dark button.primary,
window.restlos-light button.suggested-action, window.restlos-dark button.suggested-action {
  color: #ffffff; background-color: #167c77; border-color: #167c77;
}
window.restlos-light button.destructive-action, window.restlos-dark button.destructive-action {
  color: #fff6f2; background-color: #b0473a; border-color: #b0473a;
}
window.restlos-light button.destructive-action:disabled, window.restlos-dark button.destructive-action:disabled,
window.restlos-light button.primary:disabled, window.restlos-dark button.primary:disabled {
  color: #c9d3d7; background-color: #8fa2aa; border-color: #8fa2aa;
}
window.restlos-light .nav-sidebar button.nav, window.restlos-dark .nav-sidebar button.nav {
  background-color: transparent; color: #c0d2d9; border-color: transparent;
}
window.restlos-light .nav-sidebar button.nav:hover, window.restlos-dark .nav-sidebar button.nav:hover { background-color: #1b3b48; }
window.restlos-light .nav-sidebar button.nav.active, window.restlos-dark .nav-sidebar button.nav.active {
  background-color: #244652; color: #9bf1dc;
}
window.restlos-light .side-bottom button, window.restlos-dark .side-bottom button {
  background-color: transparent; color: #c8dce0; border-color: #34505a;
}
window.restlos-light .notice button, window.restlos-dark .notice button { background-color: transparent; color: #ffffff; border-color: #3d6670; }
window.restlos-light .notice button.primary, window.restlos-dark .notice button.primary {
  background-color: #6ce0c3; color: #103945; border-color: #6ce0c3;
}
window.restlos-light headerbar.restlos-header button, window.restlos-dark headerbar.restlos-header button {
  background-color: transparent; color: #d9e8ec; border-color: transparent;
}
"""


def _clear_box(container: Gtk.Widget) -> None:
    child = container.get_first_child()
    while child is not None:
        next_child = child.get_next_sibling()
        if isinstance(container, Gtk.ListBox):
            container.remove(child)
        elif isinstance(container, Gtk.Box):
            container.remove(child)
        child = next_child


def _apply_appearance(widget: Gtk.Widget, dark: bool) -> None:
    widget.remove_css_class("restlos-light")
    widget.remove_css_class("restlos-dark")
    widget.add_css_class("restlos-dark" if dark else "restlos-light")
    widget.add_css_class("dialog-surface")


def _icon_widget(icon: str, size: int = 40) -> Gtk.Image:
    path = Path(icon)
    if path.is_absolute() and path.exists():
        image = Gtk.Image.new_from_file(str(path))
    else:
        image = Gtk.Image.new_from_icon_name(icon or "application-x-executable")
    image.set_pixel_size(size)
    return image


def _label(text: str = "", *css: str, xalign: float = 0.0, wrap: bool = False, ellipsize: bool = False) -> Gtk.Label:
    label = Gtk.Label(label=text, xalign=xalign)
    for name in css:
        label.add_css_class(name)
    if wrap:
        label.set_wrap(True)
        label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    if ellipsize:
        label.set_ellipsize(Pango.EllipsizeMode.END)
    return label


def _margins(widget: Gtk.Widget, top: int, end: int | None = None, bottom: int | None = None, start: int | None = None) -> None:
    widget.set_margin_top(top)
    widget.set_margin_end(top if end is None else end)
    widget.set_margin_bottom(top if bottom is None else bottom)
    widget.set_margin_start((top if end is None else end) if start is None else start)


def _wrapping_check_button(label: str) -> Gtk.CheckButton:
    # Gtk.CheckButton.set_child() is only available in newer GTK 4 releases.
    # Ubuntu 22.04 ships GTK 4.6, whose built-in label is still reachable
    # through the normal widget tree and can be configured for wrapping.
    check = Gtk.CheckButton(label=label)
    child = check.get_first_child()
    while child is not None:
        if isinstance(child, Gtk.Label):
            child.set_hexpand(True)
            child.set_xalign(0)
            child.set_wrap(True)
            child.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            break
        child = child.get_next_sibling()
    return check


def refresh_desktop_icon(data_home: Path | None = None) -> bool:
    """Neues Programmsymbol auch über In-App-Updates ausliefern.

    Ersetzt nur Symbole, die bereits für Restlos angelegt wurden (install.sh legt ein Pixmap an)
    oder ein veraltetes Systemsymbol per Benutzersymbol überdeckt. Gibt True zurück, wenn
    sich etwas geändert hat.
    """
    try:
        source = ICON_PATH.read_bytes()
    except OSError:
        return False
    base = data_home or Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    name = f"{APP_ID}.svg"
    user_icon = base / "icons/hicolor/scalable/apps" / name
    system_icon = Path("/usr/share/icons/hicolor/scalable/apps") / name
    targets: list[Path] = []
    pixmap = base / "pixmaps" / name
    if pixmap.is_file() and not pixmap.is_symlink():
        targets.append(pixmap)
    try:
        system_outdated = system_icon.is_file() and system_icon.read_bytes() != source
    except OSError:
        system_outdated = False
    if (user_icon.is_file() and not user_icon.is_symlink()) or system_outdated:
        targets.append(user_icon)
    changed = False
    for target in targets:
        try:
            if target.is_file() and target.read_bytes() == source:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.tmp")
            temporary.write_bytes(source)
            temporary.chmod(0o644)
            temporary.replace(target)
            changed = True
        except OSError:
            continue
    return changed


class ApplicationRow(Gtk.ListBoxRow):
    def __init__(self, record: AppRecord) -> None:
        super().__init__()
        self.record = record
        self.set_activatable(True)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=11)
        box.set_margin_top(9)
        box.set_margin_bottom(9)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.append(_icon_widget(record.icon, 34))

        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        labels.set_hexpand(True)
        name = Gtk.Label(label=record.name, xalign=0)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        name.set_tooltip_text(record.name)
        name.add_css_class("app-name")
        labels.append(name)
        source = Gtk.Label(label=f"{display_text(record.source.value)} · {record.package_id}", xalign=0)
        source.set_ellipsize(Pango.EllipsizeMode.END)
        source.set_tooltip_text(f"{display_text(record.source.value)} · {record.package_id}")
        source.add_css_class("app-source")
        labels.append(source)
        box.append(labels)
        self.set_child(box)


class WarningRow(Gtk.Box):
    def __init__(self, message: str) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.message = message
        self.expanded = False
        self.add_css_class("warning-row")

        icon = Gtk.Label(label="⚠")
        icon.set_valign(Gtk.Align.START)
        self.append(icon)

        self.label = Gtk.Label(label=message, xalign=0)
        self.label.set_hexpand(True)
        self.label.set_single_line_mode(True)
        self.label.set_ellipsize(Pango.EllipsizeMode.END)
        self.label.set_tooltip_text(message)
        self.append(self.label)

        self.more_button = Gtk.Button(label="…")
        self.more_button.set_valign(Gtk.Align.START)
        self.more_button.add_css_class("warning-more")
        self.more_button.set_tooltip_text(_("Vollständigen Hinweis anzeigen"))
        self.more_button.connect("clicked", self._toggle)
        self.append(self.more_button)

    def _toggle(self, _button: Gtk.Button) -> None:
        self.expanded = not self.expanded
        self.label.set_single_line_mode(not self.expanded)
        self.label.set_wrap(self.expanded)
        self.label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.label.set_ellipsize(
            Pango.EllipsizeMode.NONE if self.expanded else Pango.EllipsizeMode.END
        )
        self.more_button.set_label("−" if self.expanded else "…")
        self.more_button.set_tooltip_text(
            _("Hinweis einklappen") if self.expanded else _("Vollständigen Hinweis anzeigen")
        )


class TargetRow(Gtk.ListBoxRow):
    def __init__(self, target, changed_callback, open_callback) -> None:
        super().__init__()
        self.target = target
        self.set_selectable(False)
        self.add_css_class("target-row")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        check = Gtk.CheckButton()
        check.set_active(target.selected and not target.shared_with)
        check.set_sensitive(not target.shared_with)
        check.set_valign(Gtk.Align.CENTER)
        check.connect("toggled", self._on_toggled, changed_callback)
        box.append(check)

        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        labels.set_hexpand(True)
        path_label = Gtk.Label(label=str(target.path), xalign=0)
        path_label.set_selectable(True)
        path_label.set_ellipsize(Pango.EllipsizeMode.END)
        path_label.set_tooltip_text(str(target.path))
        labels.append(path_label)
        reason = Gtk.Label(label=display_text(target.reason), xalign=0)
        reason.set_wrap(True)
        reason.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        reason.add_css_class("muted")
        labels.append(reason)
        if target.shared_with:
            shared = Gtk.Expander(label=_("Geschützt – wer braucht diese Daten noch?"))
            references = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            for use in target.shared_with:
                note = Gtk.Label(
                    label=_("{name} ({source})\n{evidence}: {path}", name=use.app_name,
                            source=display_text(use.source), evidence=display_text(use.evidence), path=use.reference_path),
                    xalign=0,
                )
                note.set_wrap(True)
                note.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                note.set_max_width_chars(45)
                note.set_selectable(True)
                references.append(note)
            shared.set_child(references)
            labels.append(shared)
        box.append(labels)

        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        side.set_valign(Gtk.Align.CENTER)
        size = Gtk.Label(label=format_size(target.size), xalign=1)
        side.append(size)
        confidence = Gtk.Label(label=_("Geschützt") if target.shared_with else display_text(target.confidence.value), xalign=1)
        confidence.add_css_class(
            {
                Confidence.CERTAIN: "confidence-certain",
                Confidence.HIGH: "confidence-high",
                Confidence.POSSIBLE: "confidence-possible",
            }[target.confidence]
        )
        side.append(confidence)
        box.append(side)
        open_button = Gtk.Button.new_from_icon_name("folder-open-symbolic")
        open_button.set_valign(Gtk.Align.CENTER)
        open_button.set_tooltip_text(_("Ordner öffnen: {path}", path=target.path))
        open_button.connect("clicked", lambda _button: open_callback(target.path))
        box.append(open_button)
        self.set_child(box)

    def _on_toggled(self, check: Gtk.CheckButton, callback) -> None:
        self.target.selected = check.get_active() and not self.target.shared_with
        if self.target.shared_with and check.get_active():
            check.set_active(False)
        callback()


class MainWindow(Gtk.ApplicationWindow):
    PAGES = ("apps", "recovery", "updates")

    def __init__(self, application: Gtk.Application) -> None:
        super().__init__(application=application, title=APP_NAME)
        self.set_default_size(1240, 800)
        self.set_size_request(900, 600)
        self.set_icon_name(APP_ID)
        self.add_css_class("restlos-root")
        self._settings = LanguageSettings()
        self._appearance = self._settings.value("appearance", "system")
        self._gtk_settings = Gtk.Settings.get_default()
        self._desktop_settings: Gio.Settings | None = None
        self._desktop_has_color_scheme = False
        self._desktop_has_gtk_theme = False
        if self._gtk_settings is not None:
            self._gtk_settings.connect("notify::gtk-theme-name", self._sync_theme)
            self._gtk_settings.connect("notify::gtk-application-prefer-dark-theme", self._sync_theme)
        schema_source = Gio.SettingsSchemaSource.get_default()
        schema = (
            schema_source.lookup("org.gnome.desktop.interface", True)
            if schema_source is not None
            else None
        )
        if schema is not None:
            self._desktop_settings = Gio.Settings.new_full(schema, None, None)
            self._desktop_has_color_scheme = schema.has_key("color-scheme")
            self._desktop_has_gtk_theme = schema.has_key("gtk-theme")
            if self._desktop_has_color_scheme:
                self._desktop_settings.connect("changed::color-scheme", self._sync_theme)
            if self._desktop_has_gtk_theme:
                self._desktop_settings.connect("changed::gtk-theme", self._sync_theme)
        self._sync_theme()
        self.apps: list[AppRecord] = []
        self.current_app: AppRecord | None = None
        self.current_plan: RemovalPlan | None = None
        self._legacy_folder_dialog: Gtk.FileChooserNative | None = None
        self._recovery_loading = False
        self._locations_dialog: Gtk.Dialog | None = None
        self._notice_timeout = 0
        self._pending_selection: AppRecord | None = None
        self.busy = False

        self._build_header()
        self._build_shell()
        self._load_applications()

    # ----- Darstellung ---------------------------------------------------------------------
    def _system_prefers_dark(self) -> bool:
        theme_name = ""
        prefer_dark = False
        if self._gtk_settings is not None:
            theme_name = str(self._gtk_settings.get_property("gtk-theme-name") or "")
            prefer_dark = bool(self._gtk_settings.get_property("gtk-application-prefer-dark-theme"))
        environment_theme = os.environ.get("GTK_THEME", "")
        desktop_scheme = ""
        desktop_theme = ""
        if self._desktop_settings is not None:
            if self._desktop_has_color_scheme:
                desktop_scheme = self._desktop_settings.get_string("color-scheme")
            if self._desktop_has_gtk_theme:
                desktop_theme = self._desktop_settings.get_string("gtk-theme")
        if environment_theme:
            return "dark" in environment_theme.casefold()
        return (
            prefer_dark
            or "dark" in theme_name.casefold()
            or "dark" in desktop_theme.casefold()
            or desktop_scheme.casefold() == "prefer-dark"
        )

    def _sync_theme(self, *_args) -> None:
        if self._appearance == "dark":
            dark = True
        elif self._appearance == "light":
            dark = False
        else:
            dark = self._system_prefers_dark()
        self._dark_mode = dark
        self.remove_css_class("restlos-light")
        self.remove_css_class("restlos-dark")
        self.add_css_class("restlos-dark" if dark else "restlos-light")
        application = self.get_application()
        windows = Gtk.Window.get_toplevels()
        for index in range(windows.get_n_items()):
            window = windows.get_item(index)
            if isinstance(window, Gtk.Window) and window is not self and (
                application is not None and window.get_application() is application
            ):
                _apply_appearance(window, dark)
        if hasattr(self, "theme_button"):
            self.theme_button.set_label(_("Hell / Dunkel"))

    def _toggle_theme(self, _button: Gtk.Button) -> None:
        self._appearance = "light" if self._dark_mode else "dark"
        try:
            self._settings.update(appearance=self._appearance)
        except (OSError, ValueError):
            pass
        self._sync_theme()

    def follow_system_theme(self) -> None:
        self._appearance = "system"
        try:
            self._settings.update(appearance="system")
        except (OSError, ValueError):
            pass
        self._sync_theme()

    def _style_dialog(self, dialog: Gtk.Widget) -> None:
        _apply_appearance(dialog, self._dark_mode)

    # ----- Rahmen --------------------------------------------------------------------------
    def _build_header(self) -> None:
        header = Gtk.HeaderBar()
        header.add_css_class("restlos-header")
        title = _label(APP_NAME, "header-title", xalign=0.5)
        header.set_title_widget(title)

        self.refresh_button = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        self.refresh_button.set_tooltip_text(_("Programmliste neu einlesen"))
        self.refresh_button.connect("clicked", lambda _button: self._load_applications())
        header.pack_end(self.refresh_button)

        menu = Gio.Menu()
        menu.append(_("Ordner prüfen …"), "win.choose-folder")
        menu.append(_("Protokollordner öffnen"), "app.open-history")
        menu.append(_("Nach Updates suchen …"), "app.check-updates")
        menu.append(_("Automatisch nach Updates suchen"), "app.automatic-updates")
        menu.append(_("Darstellung wie System"), "win.system-theme")
        language_menu = Gio.Menu()
        for label, language in (
            (_("Systemsprache"), "system"),
            (_("Deutsch"), "de"),
            (_("Englisch"), "en"),
        ):
            item = Gio.MenuItem.new(label, None)
            item.set_action_and_target_value("app.language", GLib.Variant.new_string(language))
            language_menu.append_item(item)
        menu.append_submenu(_("Sprache"), language_menu)
        menu.append(_("Über Restlos Uninstaller"), "app.about")
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        menu_button.set_tooltip_text(_("Menü"))
        header.pack_end(menu_button)
        self.set_titlebar(header)

        for name, callback in (
            ("choose-folder", lambda *_args: self._choose_folder(None)),
            ("system-theme", lambda *_args: self.follow_system_theme()),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

    def _build_shell(self) -> None:
        shell = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_child(shell)
        shell.append(self._build_navigation())

        overlay = Gtk.Overlay()
        overlay.set_hexpand(True)
        overlay.add_css_class("main-area")
        shell.append(overlay)
        self.page_stack = Gtk.Stack()
        self.page_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.page_stack.set_transition_duration(120)
        self.page_stack.add_named(self._apps_page(), "apps")
        self.page_stack.add_named(self._recovery_page(), "recovery")
        self.page_stack.add_named(self._updates_page(), "updates")
        overlay.set_child(self.page_stack)
        overlay.add_overlay(self._build_notice())
        self.navigate("apps")

    def _build_navigation(self) -> Gtk.Widget:
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        sidebar.add_css_class("nav-sidebar")
        sidebar.set_size_request(238, -1)

        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=11)
        mark = Gtk.Image.new_from_file(str(ICON_PATH)) if ICON_PATH.is_file() else Gtk.Image.new_from_icon_name(APP_ID)
        mark.set_pixel_size(42)
        brand.append(mark)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        names.set_valign(Gtk.Align.CENTER)
        names.append(_label("Restlos", "brand-name"))
        names.append(_label("UNINSTALLER", "brand-sub"))
        brand.append(names)
        sidebar.append(brand)

        sidebar.append(_label(_("ARBEITSPLATZ"), "side-title"))
        self.nav_buttons: dict[str, Gtk.Button] = {}
        self.nav_counts: dict[str, Gtk.Label] = {}
        for page, symbol, text in (
            ("apps", "▤", _("Programme entfernen")),
            ("recovery", "↺", _("Wiederherstellung")),
            ("updates", "↻", _("Updates & Startcheck")),
        ):
            button = Gtk.Button()
            button.add_css_class("nav")
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.append(_label(symbol))
            text_label = _label(text, ellipsize=True)
            text_label.set_hexpand(True)
            row.append(text_label)
            count = _label("", "nav-count", xalign=1)
            row.append(count)
            button.set_child(row)
            button.connect("clicked", lambda _button, name=page: self.navigate(name))
            sidebar.append(button)
            self.nav_buttons[page] = button
            self.nav_counts[page] = count

        sidebar.append(_label(_("WERKZEUGE"), "side-title"))
        for symbol, text, tooltip, callback in (
            ("＋", _("Ordner prüfen …"), _("Einen nicht erkannten Programm- oder Spieleordner manuell analysieren"),
             lambda _button: self._choose_folder(None)),
            ("☰", _("Protokolle"), _("Protokollordner öffnen"),
             lambda _button: self.get_application().activate_action("open-history", None)),
        ):
            button = Gtk.Button()
            button.add_css_class("nav")
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.append(_label(symbol))
            row.append(_label(text, ellipsize=True))
            button.set_child(row)
            button.set_tooltip_text(tooltip)
            button.connect("clicked", callback)
            sidebar.append(button)

        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        sidebar.append(spacer)

        bottom = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        bottom.add_css_class("side-bottom")
        bottom.append(_label(_("● Lokal auf deinem Computer"), "local"))
        bottom.append(_label(_("Kein Konto, keine Cloud. Löschplan vor jeder Entfernung."), wrap=True))
        self.theme_button = Gtk.Button(label=_("Hell / Dunkel"))
        self.theme_button.set_halign(Gtk.Align.START)
        self.theme_button.set_tooltip_text(_("Zwischen heller und dunkler Darstellung wechseln"))
        self.theme_button.connect("clicked", self._toggle_theme)
        bottom.append(self.theme_button)
        version = ".".join(__version__.split(".")[:2])
        bottom.append(_label(_("Version {version} · Dein Deinstaller", version=version), "side-version"))
        sidebar.append(bottom)
        return sidebar

    def navigate(self, page: str) -> None:
        if page not in self.PAGES:
            return
        self.page_stack.set_visible_child_name(page)
        for name, button in self.nav_buttons.items():
            if name == page:
                button.add_css_class("active")
            else:
                button.remove_css_class("active")
        if page == "recovery":
            self._load_recovery_records()
        elif page == "updates":
            application = self.get_application()
            if isinstance(application, RestlosApplication):
                self.show_update_status(application.update_status())

    @staticmethod
    def _page_scroll(content: Gtk.Widget) -> Gtk.ScrolledWindow:
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.set_child(content)
        return scroll

    @staticmethod
    def _page_top(eyebrow: str, title: str, trailing: Gtk.Widget | None = None) -> Gtk.Widget:
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        labels.set_hexpand(True)
        labels.append(_label(eyebrow, "eyebrow"))
        labels.append(_label(title, "page-title", ellipsize=True))
        top.append(labels)
        if trailing is not None:
            trailing.set_valign(Gtk.Align.END)
            top.append(trailing)
        return top

    # ----- Hinweis unten rechts --------------------------------------------------------------
    def _build_notice(self) -> Gtk.Widget:
        self.notice = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.notice.add_css_class("notice")
        self.notice.set_halign(Gtk.Align.END)
        self.notice.set_valign(Gtk.Align.END)
        _margins(self.notice, 0, 24, 24, 0)
        self.notice.set_size_request(320, -1)
        self.notice_label = _label("", wrap=True)
        self.notice_label.set_max_width_chars(46)
        self.notice.append(self.notice_label)
        self.notice_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.notice_actions.set_halign(Gtk.Align.END)
        self.notice.append(self.notice_actions)
        self.notice.set_visible(False)
        return self.notice

    def show_notice(
        self,
        text: str,
        *,
        action_label: str = "",
        action: object = None,
        seconds: int = 6,
    ) -> None:
        if self._notice_timeout:
            GLib.source_remove(self._notice_timeout)
            self._notice_timeout = 0
        self.notice_label.set_text(text)
        _clear_box(self.notice_actions)
        if action_label and callable(action):
            primary = Gtk.Button(label=action_label)
            primary.add_css_class("primary")
            primary.connect("clicked", lambda _button: (self.hide_notice(), action()))
            self.notice_actions.append(primary)
        close = Gtk.Button(label=_("Später") if action_label else _("OK"))
        close.connect("clicked", lambda _button: self.hide_notice())
        self.notice_actions.append(close)
        self.notice.set_visible(True)
        if seconds > 0:
            self._notice_timeout = GLib.timeout_add_seconds(seconds, self._notice_expired)

    def _notice_expired(self) -> bool:
        self._notice_timeout = 0
        self.hide_notice()
        return False

    def hide_notice(self) -> None:
        if self._notice_timeout:
            GLib.source_remove(self._notice_timeout)
            self._notice_timeout = 0
        self.notice.set_visible(False)

    # ----- Seite: Programme --------------------------------------------------------------------
    def _apps_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        _margins(page, 26, 30, 22, 30)
        self.count_pill = _label(_("Wird eingelesen …"), "pill")
        page.append(self._page_top(_("SICHER DEINSTALLIEREN"), _("Programme & Spiele"), self.count_pill))

        paned = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        paned.set_vexpand(True)
        paned.set_position(360)
        paned.set_wide_handle(False)
        paned.set_shrink_start_child(False)
        paned.set_shrink_end_child(False)
        page.append(paned)

        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        sidebar.add_css_class("list-card")
        sidebar.set_size_request(300, -1)
        sidebar.set_margin_end(10)
        sidebar.append(_label(_("INSTALLIERTE APPS & SPIELE"), "eyebrow"))

        self.search = Gtk.SearchEntry()
        # The property predates the setter method, which requires GTK 4.10.
        self.search.set_property("placeholder-text", _("Programme durchsuchen …"))
        self.search.connect("search-changed", self._on_search_changed)
        sidebar.append(self.search)

        sources = [_("Alle Quellen"), *(display_text(source.value) for source in SourceKind)]
        self.source_filter = Gtk.DropDown.new_from_strings(sources)
        self.source_filter.set_hexpand(True)
        self.source_filter.set_tooltip_text(_("Nach Installationsquelle filtern"))
        self.source_filter.connect("notify::selected", lambda *_args: self.app_list.invalidate_filter())
        sidebar.append(self.source_filter)

        self.scan_status = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.scan_spinner = Gtk.Spinner()
        self.scan_status_label = _label(_("Programme werden eingelesen …"), "muted", ellipsize=True)
        self.scan_status_label.set_hexpand(True)
        self.scan_status.append(self.scan_spinner)
        self.scan_status.append(self.scan_status_label)
        self.scan_status.add_css_class("scan-card")
        sidebar.append(self.scan_status)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        self.app_list = Gtk.ListBox()
        self.app_list.add_css_class("app-list")
        self.app_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.app_list.set_filter_func(self._filter_application)
        self.app_list.connect("row-selected", self._on_app_selected)
        placeholder = _label(_("Keine passenden Programme gefunden"), "muted", xalign=0.5)
        placeholder.set_margin_top(28)
        self.app_list.set_placeholder(placeholder)
        scroll.set_child(self.app_list)
        sidebar.append(scroll)
        paned.set_start_child(sidebar)

        self.detail_stack = Gtk.Stack()
        self.detail_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.detail_stack.set_margin_start(10)
        self.detail_stack.add_named(self._empty_page(), "empty")
        self.detail_stack.add_named(self._detail_page(), "detail")
        self.detail_stack.add_named(self._progress_page(), "progress")
        self.detail_stack.set_visible_child_name("empty")
        paned.set_end_child(self.detail_stack)
        return page

    def _empty_page(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        hero = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        hero.add_css_class("hero")
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        text.set_hexpand(True)
        text.append(_label(_("Programm auswählen"), "hero-title", wrap=True))
        text.append(_label(
            _("Restlos erstellt zuerst einen überprüfbaren Löschplan. Erst nach deiner Bestätigung wird entfernt – "
              "Benutzerdaten landen standardmäßig im Papierkorb."),
            "hero-text", wrap=True,
        ))
        hero.append(text)
        numbers = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        numbers.set_valign(Gtk.Align.CENTER)
        self.hero_count = _label("—", "hero-number", xalign=1)
        numbers.append(self.hero_count)
        numbers.append(_label(_("Anwendungen erkannt"), "hero-number-label", xalign=1))
        hero.append(numbers)
        box.append(hero)

        grid = Gtk.Grid(column_spacing=14, row_spacing=14)
        grid.set_column_homogeneous(True)
        for column, (symbol, title, text_value) in enumerate((
            ("▤", _("Löschplan"), _("Paketaktionen, Programmordner und Restdaten – jeder Pfad mit Begründung und Größe.")),
            ("↺", _("Papierkorb"), _("Benutzerdaten bleiben wiederherstellbar, bis du den Papierkorb leerst.")),
            ("◆", _("Safety Backup"), _("Vor endgültigem Löschen werden Einstellungen und Spielstände gesichert.")),
        )):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            card.add_css_class("info-card")
            icon = _label(symbol, "info-icon", xalign=0.5)
            icon.set_halign(Gtk.Align.START)
            card.append(icon)
            card.append(_label(title, "section-title", wrap=True))
            card.append(_label(text_value, "muted", wrap=True))
            grid.attach(card, column, 0, 1, 1)
        box.append(grid)
        return self._page_scroll(box)

    def _detail_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        page_scroll = Gtk.ScrolledWindow()
        page_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        page_scroll.set_vexpand(True)
        page.append(page_scroll)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        outer.set_margin_bottom(18)
        outer.set_margin_end(4)
        page_scroll.set_child(outer)

        eyebrow = Gtk.Label(label=_("AUSGEWÄHLTE ANWENDUNG"), xalign=0)
        eyebrow.add_css_class("eyebrow")
        outer.append(eyebrow)

        hero = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
        hero.add_css_class("detail-hero")
        self.detail_icon_box = Gtk.Box()
        hero.append(self.detail_icon_box)
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        labels.set_hexpand(True)
        self.detail_name = Gtk.Label(xalign=0)
        self.detail_name.set_ellipsize(Pango.EllipsizeMode.END)
        self.detail_name.add_css_class("hero-title")
        labels.append(self.detail_name)
        self.detail_description = Gtk.Label(xalign=0)
        self.detail_description.set_wrap(True)
        self.detail_description.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.detail_description.add_css_class("muted")
        labels.append(self.detail_description)
        meta = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.detail_source = Gtk.Label()
        self.detail_source.set_ellipsize(Pango.EllipsizeMode.END)
        self.detail_source.set_max_width_chars(24)
        self.detail_source.add_css_class("source-badge")
        meta.append(self.detail_source)
        self.detail_id = Gtk.Label(xalign=0)
        self.detail_id.set_hexpand(True)
        self.detail_id.set_ellipsize(Pango.EllipsizeMode.END)
        self.detail_id.set_selectable(True)
        self.detail_id.add_css_class("muted")
        meta.append(self.detail_id)
        labels.append(meta)
        hero.append(labels)
        hero_actions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        hero_actions.set_valign(Gtk.Align.START)
        self.locations_button = Gtk.Button(label=_("Speicherorte …"))
        self.locations_button.add_css_class("accent-button")
        self.locations_button.set_tooltip_text(_("Programmdateien und zugehörige Daten vor dem Löschen ansehen"))
        self.locations_button.connect("clicked", self._show_locations)
        hero_actions.append(self.locations_button)
        self.analyze_button = Gtk.Button(label=_("Erneut analysieren"))
        self.analyze_button.connect("clicked", lambda _button: self._analyze_current())
        hero_actions.append(self.analyze_button)
        hero.append(hero_actions)
        outer.append(hero)

        self.warning_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.warning_box.add_css_class("warning-card")
        self.warning_box.set_visible(False)
        outer.append(self.warning_box)

        section = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        section_title = Gtk.Label(label=_("Löschplan"), xalign=0)
        section_title.add_css_class("section-title")
        section_title.set_hexpand(True)
        section.append(section_title)
        self.plan_summary = Gtk.Label(xalign=1)
        self.plan_summary.set_ellipsize(Pango.EllipsizeMode.END)
        self.plan_summary.set_max_width_chars(38)
        self.plan_summary.add_css_class("muted")
        section.append(self.plan_summary)
        outer.append(section)

        stats = Gtk.Grid(column_spacing=12, row_spacing=12)
        stats.set_column_homogeneous(True)
        self.action_stat_value = self._summary_tile(stats, 0, _("PAKETAKTIONEN"))
        self.path_stat_value = self._summary_tile(stats, 1, _("AUSGEWÄHLTE PFADE"))
        self.size_stat_value = self._summary_tile(stats, 2, _("FREIGEGEBENER SPEICHER"))
        outer.append(stats)

        plan_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.action_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.action_card.add_css_class("card")
        plan_box.append(self.action_card)
        self.target_list = Gtk.ListBox()
        self.target_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.target_list.add_css_class("card")
        plan_box.append(self.target_list)
        outer.append(plan_box)

        safety_heading = Gtk.Label(label=_("SICHERHEIT & WIEDERHERSTELLUNG"), xalign=0)
        safety_heading.add_css_class("eyebrow")
        outer.append(safety_heading)

        options = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        options.add_css_class("safety-card")
        self.permanent_check = _wrapping_check_button(
            _("Benutzerdaten endgültig löschen (keine Papierkorb-Wiederherstellung)")
        )
        self.permanent_check.set_active(False)
        self.permanent_check.connect("toggled", self._permanent_mode_changed)
        options.append(self.permanent_check)
        self.backup_check = _wrapping_check_button(_("Safety Backup vor endgültigem Löschen erstellen"))
        self.backup_check.set_active(True)
        self.backup_check.set_sensitive(False)
        self.backup_check.set_tooltip_text(
            _("Sichert Einstellungen und Spielstände; Cache und Programmdateien werden ausgelassen.")
        )
        options.append(self.backup_check)
        self.process_check = _wrapping_check_button(_("Zugehörige laufende Prozesse automatisch beenden"))
        self.process_check.set_active(True)
        options.append(self.process_check)
        outer.append(options)

        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        bottom.add_css_class("action-bar")
        bottom.set_margin_end(4)
        self.delete_note = Gtk.Label(label=_("Vor dem Löschen erscheint eine letzte Zusammenfassung."), xalign=0)
        self.delete_note.set_hexpand(True)
        self.delete_note.set_wrap(True)
        self.delete_note.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.delete_note.add_css_class("muted")
        bottom.append(self.delete_note)
        self.remove_button = Gtk.Button(label=_("Restlos entfernen"))
        self.remove_button.set_valign(Gtk.Align.CENTER)
        self.remove_button.add_css_class("destructive-action")
        self.remove_button.connect("clicked", self._confirm_removal)
        bottom.append(self.remove_button)
        page.append(bottom)
        return page

    @staticmethod
    def _summary_tile(grid: Gtk.Grid, column: int, heading: str) -> Gtk.Label:
        tile = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        tile.add_css_class("stat-tile")
        title = Gtk.Label(label=heading, xalign=0)
        title.add_css_class("stat-heading")
        title.set_wrap(True)
        title.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        title.set_max_width_chars(18)
        tile.append(title)
        value = Gtk.Label(label="—", xalign=0)
        value.add_css_class("stat-value")
        tile.append(value)
        grid.attach(tile, column, 0, 1, 1)
        return value

    def _progress_page(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        box.set_size_request(500, -1)
        self.progress_spinner = Gtk.Spinner()
        self.progress_spinner.set_size_request(48, 48)
        box.append(self.progress_spinner)
        self.progress_title = Gtk.Label(label=_("Entfernung wird vorbereitet …"))
        self.progress_title.add_css_class("empty-title")
        self.progress_title.set_wrap(True)
        self.progress_title.set_max_width_chars(58)
        box.append(self.progress_title)
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_size_request(480, -1)
        box.append(self.progress_bar)
        note = Gtk.Label(label=_("Dieses Fenster nicht schließen, solange Paketaktionen laufen."))
        note.add_css_class("muted")
        box.append(note)
        return box

    def _load_applications(self) -> None:
        if self.busy:
            return
        self.busy = True
        self.refresh_button.set_sensitive(False)
        self.scan_status.set_visible(True)
        self.scan_spinner.start()
        self.count_pill.set_text(_("Wird eingelesen …"))
        self.scan_status_label.set_text(_("Pakete, Spielebibliotheken, Wine und portable Ordner werden eingelesen …"))

        def worker() -> None:
            try:
                apps = ApplicationScanner().scan()
                GLib.idle_add(self._applications_loaded, apps, None)
            except Exception as error:  # defensive boundary for the GUI worker
                GLib.idle_add(self._applications_loaded, [], str(error))

        threading.Thread(target=worker, daemon=True).start()

    def _applications_loaded(self, apps: list[AppRecord], error: str | None) -> bool:
        self.busy = False
        self.refresh_button.set_sensitive(True)
        self.scan_spinner.stop()
        if error:
            self.scan_status_label.set_text(_("Einlesen fehlgeschlagen: {error}", error=error))
            return False
        self.apps = apps
        self._pending_selection = None
        _clear_box(self.app_list)
        for app in apps:
            self.app_list.append(ApplicationRow(app))
        self.scan_status_label.set_text(_("{count} Anwendungen erkannt", count=len(apps)))
        self.scan_status.set_visible(False)
        self._show_app_count()
        self.app_list.invalidate_filter()
        return False

    def _show_app_count(self) -> None:
        count = len(self.apps)
        self.count_pill.set_text(_("{count} Anwendungen erkannt", count=count))
        self.hero_count.set_text(str(count))
        self.nav_counts["apps"].set_text(str(count))

    def _filter_application(self, row: Gtk.ListBoxRow) -> bool:
        if not isinstance(row, ApplicationRow):
            return True
        query = self.search.get_text().strip().casefold()
        app = row.record
        selected_index = self.source_filter.get_selected()
        source_matches = (
            selected_index == 0
            or selected_index > len(SourceKind)
            or app.source == list(SourceKind)[selected_index - 1]
        )
        query_matches = not query or query in f"{app.name} {app.package_id} {app.source.value}".casefold()
        return source_matches and query_matches

    def _on_search_changed(self, _entry: Gtk.SearchEntry) -> None:
        self.app_list.invalidate_filter()

    def _choose_folder(self, _button: Gtk.Button) -> None:
        if hasattr(Gtk, "FileDialog"):
            dialog = Gtk.FileDialog(title=_("Programm- oder Spieleordner auswählen"))
            dialog.select_folder(self, None, self._folder_selected)
            return
        dialog = Gtk.FileChooserNative(
            title=_("Programm- oder Spieleordner auswählen"),
            transient_for=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            accept_label=_("Auswählen"),
            cancel_label=_("Abbrechen"),
        )
        self._legacy_folder_dialog = dialog
        dialog.connect("response", self._legacy_folder_selected)
        dialog.show()

    def _folder_selected(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        path_value = folder.get_path()
        if not path_value:
            self.scan_status_label.set_text(_("Dieser Ordner ist nicht als lokaler Pfad verfügbar."))
            return
        self._add_manual_folder(Path(path_value).absolute())

    def _legacy_folder_selected(self, dialog: Gtk.FileChooserNative, response: int) -> None:
        file = dialog.get_file() if response == Gtk.ResponseType.ACCEPT else None
        dialog.destroy()
        self._legacy_folder_dialog = None
        if file is None or not file.get_path():
            return
        self._add_manual_folder(Path(file.get_path()).absolute())

    def _add_manual_folder(self, path: Path) -> None:
        owned = json.dumps(
            [{"path": str(path), "reason": "Manuell gewählter Programm-/Datenordner"}],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        trusted = json.dumps([str(path)], ensure_ascii=False, separators=(",", ":"))
        app = AppRecord(
            key=f"portable:{path}",
            name=path.name or str(path),
            source=SourceKind.PORTABLE,
            package_id=path.name or "manueller-ordner",
            description=_("Manuell ausgewählter Ordner; Inhalt und Größe werden vor dem Entfernen angezeigt"),
            icon="folder-symbolic",
            scope=_("Manuelle Auswahl"),
            metadata={
                "manager": "portable",
                "owned_paths": owned,
                "trusted_paths": trusted,
                "install_root": str(path),
            },
        )
        self.navigate("apps")
        existing = next((item for item in self.apps if item.key == app.key), None)
        if existing is not None:
            app = existing
        else:
            self.apps.append(app)
            self.app_list.append(ApplicationRow(app))
            self._show_app_count()
            self.scan_status_label.set_text(
                _("{count} Anwendungen erkannt · manueller Ordner hinzugefügt", count=len(self.apps))
            )
        self.search.set_text("")
        self.source_filter.set_selected(0)
        self.app_list.invalidate_filter()
        child = self.app_list.get_first_child()
        while child is not None:
            if isinstance(child, ApplicationRow) and child.record.key == app.key:
                self.app_list.select_row(child)
                break
            child = child.get_next_sibling()

    def _on_app_selected(self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        if not isinstance(row, ApplicationRow):
            return
        if self.busy:
            # Markierung und Löschplan dürfen nie auseinanderlaufen: die Auswahl wird nach der
            # laufenden Aktion übernommen, bis dahin ist „Entfernen“ gesperrt.
            self._pending_selection = row.record
            self.remove_button.set_sensitive(False)
            return
        self._pending_selection = None
        self.current_app = row.record
        self._show_app_header(row.record)
        self._analyze_current()

    def _show_app_header(self, app: AppRecord) -> None:
        _clear_box(self.detail_icon_box)
        self.detail_icon_box.append(_icon_widget(app.icon, 64))
        self.detail_name.set_text(app.name)
        self.detail_name.set_tooltip_text(app.name)
        self.detail_description.set_text(display_text(app.description) or _("Keine Beschreibung verfügbar"))
        source_text = f"{display_text(app.source.value)} · {display_text(app.scope)}"
        self.detail_source.set_text(source_text)
        self.detail_source.set_tooltip_text(source_text)
        self.detail_id.set_text(app.package_id)
        self.detail_id.set_tooltip_text(app.package_id)
        self.detail_stack.set_visible_child_name("detail")

    def _analyze_current(self) -> None:
        if self.current_app is None or self.busy:
            return
        self.busy = True
        self.analyze_button.set_sensitive(False)
        self.locations_button.set_sensitive(False)
        self.remove_button.set_sensitive(False)
        self.current_plan = None
        _clear_box(self.target_list)
        _clear_box(self.action_card)
        self.warning_box.set_visible(False)
        self.plan_summary.set_text(_("Analyse läuft …"))
        self.action_stat_value.set_text("—")
        self.path_stat_value.set_text("—")
        self.size_stat_value.set_text("—")
        app = self.current_app

        def worker() -> None:
            try:
                plan = RemovalAnalyzer().analyze(app)
                GLib.idle_add(self._analysis_loaded, plan, None)
            except Exception as error:
                GLib.idle_add(self._analysis_loaded, None, str(error))

        threading.Thread(target=worker, daemon=True).start()

    def _take_pending_selection(self) -> bool:
        """Eine während der Analyse angeklickte Anwendung jetzt analysieren."""
        pending, self._pending_selection = self._pending_selection, None
        if pending is None or self.busy or (self.current_app is not None and pending.key == self.current_app.key):
            return False
        self.current_app = pending
        self._show_app_header(pending)
        self._analyze_current()
        return True

    def _analysis_loaded(self, plan: RemovalPlan | None, error: str | None) -> bool:
        self.busy = False
        self.analyze_button.set_sensitive(True)
        self.locations_button.set_sensitive(True)
        if self._take_pending_selection():
            return False
        if error or plan is None:
            self.plan_summary.set_text(
                _("Analyse fehlgeschlagen: {error}", error=error or _("unbekannter Fehler"))
            )
            return False
        if self.current_app is None or plan.app.key != self.current_app.key:
            return False
        self.current_plan = plan
        self.current_app = plan.app
        self._show_app_header(plan.app)
        _clear_box(self.action_card)
        _clear_box(self.target_list)
        _clear_box(self.warning_box)

        if plan.actions:
            action_title = Gtk.Label(label=_("Paketverwaltung"), xalign=0)
            action_title.add_css_class("section-title")
            self.action_card.append(action_title)
            for action in plan.actions:
                line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                icon = Gtk.Image.new_from_icon_name("system-software-install-symbolic")
                line.append(icon)
                label = Gtk.Label(label=display_text(action.label), xalign=0)
                label.set_hexpand(True)
                label.set_wrap(True)
                label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                line.append(label)
                self.action_card.append(line)
            self.action_card.set_visible(True)
        else:
            self.action_card.set_visible(False)

        for target in plan.targets:
            self.target_list.append(TargetRow(target, self._update_plan_summary, self._open_folder))
        if not plan.targets:
            label = Gtk.Label(label=_("Keine zusätzlichen Benutzerdaten gefunden"))
            label.set_margin_top(18)
            label.set_margin_bottom(18)
            label.add_css_class("muted")
            self.target_list.append(label)

        warnings = [*plan.warnings, *([plan.safety_error] if plan.safety_error else [])]
        for warning in warnings:
            self.warning_box.append(WarningRow(display_text(warning)))
        self.warning_box.set_visible(bool(warnings))
        self._update_plan_summary()
        return False

    def _open_folder(self, path: Path, parent: Gtk.Window | None = None) -> None:
        try:
            folder = folder_for_path(path)
            # Select a directory handler explicitly. Never launch the target
            # file's MIME handler (it might be an executable or .desktop file).
            manager = Gio.AppInfo.get_default_for_type("inode/directory", False)
            if manager is None:
                raise OSError(_("Es ist kein Dateimanager für Ordner eingerichtet."))
            if not manager.launch([Gio.File.new_for_path(str(folder))], None):
                raise OSError(_("Der Dateimanager konnte nicht gestartet werden."))
        except (OSError, ValueError, RuntimeError, GLib.Error) as error:
            dialog = Gtk.MessageDialog(
                transient_for=parent or self,
                modal=True,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.CLOSE,
                text=_("Ordner konnte nicht geöffnet werden"),
            )
            self._style_dialog(dialog)
            dialog.set_property("secondary-text", _("Pfad: {path}\n\n{error}", path=path, error=error))
            dialog.connect("response", lambda item, _response: item.destroy())
            dialog.present()

    def _show_locations(self, _button: Gtk.Button) -> None:
        if self.current_app is None or self.busy:
            return
        if self._locations_dialog is not None:
            self._locations_dialog.present()
            return
        app = self.current_app
        plan = self.current_plan
        dialog = Gtk.Dialog(title=_("Speicherorte – {name}", name=app.name), transient_for=self, modal=True)
        self._style_dialog(dialog)
        dialog.set_default_size(800, 560)
        dialog.add_button(_("Schließen"), Gtk.ResponseType.CLOSE)
        dialog.connect("response", self._close_locations)
        dialog.connect("close-request", self._locations_close_requested)
        self._locations_dialog = dialog
        content = dialog.get_content_area()
        content.set_spacing(12)
        for edge in ("top", "bottom", "start", "end"):
            getattr(content, f"set_margin_{edge}")(16)
        note = Gtk.Label(
            label=_("Programme können mehrere Speicherorte haben. Geöffnet wird nur der Ordner, niemals die Programmdatei. Die Lösch-Auswahl bleibt unverändert. Gemeinsame Systemordner können auch Dateien anderer Programme enthalten."),
            xalign=0,
        )
        note.set_wrap(True)
        note.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        content.append(note)
        status = Gtk.Label(label=_("Speicherorte werden ermittelt …"), xalign=0)
        status.set_wrap(True)
        status.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        status.add_css_class("muted")
        content.append(status)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        locations = Gtk.ListBox()
        locations.set_selection_mode(Gtk.SelectionMode.NONE)
        scroll.set_child(locations)
        content.append(scroll)
        dialog.present()

        def worker() -> None:
            try:
                result = LocationResolver().inspect(app, plan)
                GLib.idle_add(self._locations_loaded, dialog, locations, status, result, None)
            except Exception as error:
                GLib.idle_add(self._locations_loaded, dialog, locations, status, None, str(error))

        threading.Thread(target=worker, daemon=True).start()

    def _close_locations(self, dialog: Gtk.Dialog, _response: int) -> None:
        if self._locations_dialog is dialog:
            self._locations_dialog = None
        dialog.destroy()

    def _locations_close_requested(self, dialog: Gtk.Dialog) -> bool:
        self._close_locations(dialog, Gtk.ResponseType.CLOSE)
        return True

    def _locations_loaded(
        self, dialog: Gtk.Dialog, locations: Gtk.ListBox, status: Gtk.Label,
        result: LocationResult | None, error: str | None,
    ) -> bool:
        if self._locations_dialog is not dialog:
            return False
        if error or result is None:
            status.set_text(_("Speicherorte konnten nicht ermittelt werden: {error}", error=error or _("unbekannter Fehler")))
            return False
        summary = (_("{count} Speicherort(e) gefunden", count=len(result.locations)) if result.locations
                   else _("Keine vorhandenen lokalen Speicherorte gefunden."))
        status.set_text("\n".join([summary, *result.warnings]))
        for location in result.locations:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.add_css_class("target-row")
            labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            labels.set_hexpand(True)
            path = Gtk.Label(label=str(location.path), xalign=0)
            path.set_selectable(True)
            path.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            path.set_tooltip_text(str(location.path))
            labels.append(path)
            reason = Gtk.Label(label=display_text(location.reason), xalign=0)
            reason.set_wrap(True)
            reason.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            reason.add_css_class("muted")
            labels.append(reason)
            row.append(labels)
            button = Gtk.Button(label=_("Ordner öffnen"))
            button.set_valign(Gtk.Align.CENTER)
            button.connect("clicked", lambda _button, value=location.path: self._open_folder(value, dialog))
            row.append(button)
            locations.append(row)
        return False

    def _update_plan_summary(self) -> None:
        if self.current_plan is None:
            self.remove_button.set_sensitive(False)
            return
        count = len(self.current_plan.selected_targets)
        action_count = len(self.current_plan.actions)
        self.plan_summary.set_text(_("Auswahl vor dem Entfernen prüfen"))
        self.action_stat_value.set_text(str(action_count))
        self.path_stat_value.set_text(str(count))
        self.size_stat_value.set_text(format_size(self.current_plan.total_size))
        self.remove_button.set_sensitive(
            bool(action_count or count) and not self.busy
            and self.current_plan.snapshot is not None and not self.current_plan.safety_error
        )

    def _permanent_mode_changed(self, check: Gtk.CheckButton) -> None:
        self.backup_check.set_sensitive(check.get_active())

    def _confirm_removal(self, _button: Gtk.Button) -> None:
        plan = self.current_plan
        if plan is None or self.busy or plan.safety_error or plan.snapshot is None:
            return
        permanent = self.permanent_check.get_active()
        create_backup = permanent and self.backup_check.get_active()
        backup_targets = BackupManager().candidates(plan.selected_targets) if create_backup else []
        processes = RemovalExecutor().related_processes(plan)
        process_note = ""
        if processes:
            names = ", ".join(f"{name} (PID {pid})" for pid, name in processes[:5])
            process_note = _("\n\nLaufende Prozesse: {names}", names=names)
        mode = _("dauerhaft gelöscht") if permanent else _("wiederherstellbar in den Papierkorb verschoben")
        recovery_note = ""
        if not permanent and plan.actions:
            recovery_note = (
                "\n\n" + _(
                    "Hinweis: Paket-Deinstallationen und Änderungen an Launcher-Bibliotheken sind nicht automatisch "
                    "wiederherstellbar; nur die ausgewählten Dateipfade werden in den Papierkorb verschoben."
                )
            )
        backup_note = ""
        if create_backup:
            backup_note = _(
                "\n\nSafety Backup: {count} geeignete Datenpfade mit {size} werden vor der Entfernung gesichert.",
                count=len(backup_targets),
                size=format_size(sum(target.size for target in backup_targets)),
            )
        secondary = (
            _(
                "{actions} Paketaktion(en) und {paths} ausgewählte Pfade mit {size} werden verarbeitet. "
                "Benutzerdaten werden {mode}.",
                actions=len(plan.actions),
                paths=len(plan.selected_targets),
                size=format_size(plan.total_size),
                mode=mode,
            )
            + backup_note + recovery_note + process_note
        )
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text=_("„{name}“ wirklich restlos entfernen?", name=plan.app.name),
            secondary_text=secondary,
        )
        self._style_dialog(dialog)
        dialog.add_button(_("Abbrechen"), Gtk.ResponseType.CANCEL)
        confirm = dialog.add_button(_("Endgültig entfernen") if permanent else _("Entfernen"), Gtk.ResponseType.ACCEPT)
        confirm.add_css_class("destructive-action")
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        dialog.connect("response", self._on_confirm_response)
        dialog.present()

    def _on_confirm_response(self, dialog: Gtk.MessageDialog, response: int) -> None:
        dialog.destroy()
        if response != Gtk.ResponseType.ACCEPT or self.current_plan is None:
            return
        self._start_removal(self.current_plan)

    def _start_removal(self, plan: RemovalPlan) -> None:
        self.busy = True
        permanent = self.permanent_check.get_active()
        stop_processes = self.process_check.get_active()
        create_backup = permanent and self.backup_check.get_active()
        self.detail_stack.set_visible_child_name("progress")
        self.progress_spinner.start()
        self.progress_bar.set_fraction(0.0)
        self.progress_title.set_text(_("„{name}“ wird entfernt …", name=plan.app.name))

        def update(message: str, fraction: float) -> None:
            GLib.idle_add(self._set_progress, message, fraction)

        def worker() -> None:
            executor = RemovalExecutor()
            result = executor.execute(
                plan,
                permanent=permanent,
                stop_processes=stop_processes,
                create_backup=create_backup,
                progress=update,
            )
            GLib.idle_add(self._removal_finished, plan, result)

        threading.Thread(target=worker, daemon=True).start()

    def _set_progress(self, message: str, fraction: float) -> bool:
        self.progress_title.set_text(display_text(message))
        self.progress_bar.set_fraction(max(0.0, min(fraction, 1.0)))
        return False

    def _removal_finished(self, plan: RemovalPlan, result: RemovalResult) -> bool:
        self.busy = False
        self.progress_spinner.stop()
        self.progress_bar.set_fraction(1.0)
        if result.success:
            title = (
                _("„{name}“ wurde entfernt", name=plan.app.name)
                if not result.residual_paths
                else _("„{name}“ wurde entfernt – Restdaten gefunden", name=plan.app.name)
            )
            detail_parts = [_('{count} Pfade wurden verarbeitet.', count=len(result.removed_paths))]
            if result.recovery_items:
                detail_parts.append(
                    _(
                        "{count} Pfade können im Wiederherstellungszentrum zurückgeholt werden.",
                        count=len(result.recovery_items),
                    )
                )
            if result.backup_items:
                detail_parts.append(
                    _(
                        "Safety Backup: {count} Datenpfade wurden vor dem Löschen gesichert.",
                        count=len(result.backup_items),
                    )
                )
            if result.residual_paths:
                preview = "\n".join(result.residual_paths[:6])
                suffix = "\n…" if len(result.residual_paths) > 6 else ""
                detail_parts.append(
                    _(
                        "Der Kontrollscan fand {count} weitere mögliche Restpfade:\n{preview}{suffix}",
                        count=len(result.residual_paths),
                        preview=preview,
                        suffix=suffix,
                    )
                )
            elif result.verification_error:
                detail_parts.append(
                    _(
                        "Der Kontrollscan konnte nicht abgeschlossen werden: {error}",
                        error=result.verification_error,
                    )
                )
            else:
                detail_parts.append(_("Kontrollscan: keine weiteren zuordenbaren Restpfade gefunden."))
            if result.kept_paths:
                detail_parts.append(
                    _(
                        "{count} nicht ausgewählte Pfade wurden wie gewünscht beibehalten.",
                        count=len(result.kept_paths),
                    )
                )
            detail_parts.append(
                _(
                    "Protokoll: {path}",
                    path=result.receipt_path or _("konnte nicht geschrieben werden"),
                )
            )
            details = "\n\n".join(detail_parts)
            message_type = Gtk.MessageType.WARNING if result.residual_paths else Gtk.MessageType.INFO
        else:
            title = _("Neue Analyse erforderlich") if result.review_required else _("Entfernung nicht vollständig")
            detail_parts = [
                "\n".join(display_text(error) for error in result.errors[:8])
                or _("Ein unbekannter Fehler ist aufgetreten.")
            ]
            if result.recovery_items:
                detail_parts.append(
                    _(
                        "{count} bereits verschobene Pfade sind im Wiederherstellungszentrum verfügbar.",
                        count=len(result.recovery_items),
                    )
                )
            if result.backup_items:
                detail_parts.append(
                    _(
                        "Das Safety Backup mit {count} Datenpfaden ist im Wiederherstellungszentrum verfügbar.",
                        count=len(result.backup_items),
                    )
                )
            details = "\n\n".join(detail_parts)
            message_type = Gtk.MessageType.ERROR
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=message_type,
            buttons=Gtk.ButtonsType.NONE,
            text=title,
            secondary_text=details,
        )
        self._style_dialog(dialog)
        dialog.add_button(_("Schließen"), Gtk.ResponseType.CLOSE)
        if result.review_required:
            self.current_plan = None
            self.remove_button.set_sensitive(False)
            self.plan_summary.set_text(_("Löschplan ungültig – bitte erneut analysieren"))
            dialog.add_button(_("Erneut analysieren"), Gtk.ResponseType.APPLY)
        if result.recovery_items or result.backup_items:
            dialog.add_button(_("Wiederherstellungszentrum"), Gtk.ResponseType.HELP)
        dialog.connect("response", self._after_result_dialog, result)
        dialog.present()
        return False

    def _after_result_dialog(self, dialog: Gtk.MessageDialog, response: int, result: RemovalResult) -> None:
        dialog.destroy()
        if result.success:
            self.current_app = None
            self.current_plan = None
            self.detail_stack.set_visible_child_name("empty")
            self._load_applications()
        else:
            self.detail_stack.set_visible_child_name("detail")
            self._update_plan_summary()
            if result.review_required and response == Gtk.ResponseType.APPLY:
                self._analyze_current()
        if response == Gtk.ResponseType.HELP:
            self.show_recovery_center()

    # ----- Seite: Wiederherstellung --------------------------------------------------------------
    def _recovery_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        _margins(page, 26, 30, 22, 30)
        reload_button = Gtk.Button(label=_("Neu prüfen"))
        reload_button.connect("clicked", lambda _button: self._load_recovery_records(force=True))
        page.append(self._page_top(_("WIEDERHERSTELLUNG"), _("Daten zurückholen"), reload_button))
        note = _label(
            _(
                "Hier kannst du Papierkorbdaten und Safety Backups an ihren ursprünglichen Ort zurückholen. "
                "Paket-Deinstallationen und Änderungen an Spielebibliotheken werden dabei nicht rückgängig gemacht."
            ),
            "muted", wrap=True,
        )
        page.append(note)
        self.recovery_list = Gtk.ListBox()
        self.recovery_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.recovery_list.add_css_class("card")
        self.recovery_list.set_valign(Gtk.Align.START)
        scroll = self._page_scroll(self.recovery_list)
        page.append(scroll)
        return page

    def show_recovery_center(self) -> None:
        self.navigate("recovery")

    def _load_recovery_records(self, *, force: bool = False) -> None:
        if self._recovery_loading and not force:
            return
        self._recovery_loading = True
        _clear_box(self.recovery_list)
        loading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        loading.set_halign(Gtk.Align.CENTER)
        _margins(loading, 36, 12)
        spinner = Gtk.Spinner()
        spinner.start()
        loading.append(spinner)
        loading.append(_label(_("Papierkorb, Safety Backups und Restlos-Protokolle werden geprüft …"), wrap=True))
        self.recovery_list.append(loading)

        def worker() -> None:
            try:
                records = RecoveryManager().list_records()
                GLib.idle_add(self._recovery_records_loaded, records, None)
            except Exception as error:  # defensive boundary for the GUI worker
                GLib.idle_add(self._recovery_records_loaded, [], str(error))

        threading.Thread(target=worker, daemon=True).start()

    def _recovery_records_loaded(self, records: list[RecoveryRecord], error: str | None) -> bool:
        self._recovery_loading = False
        _clear_box(self.recovery_list)
        self.nav_counts["recovery"].set_text(str(len(records)) if records else "")
        if error:
            empty_text = _("Wiederherstellungsdaten konnten nicht gelesen werden: {error}", error=error)
        elif not records:
            empty_text = _("Keine wiederherstellbaren Restlos-Vorgänge gefunden.")
        else:
            empty_text = ""
            for record in records:
                self.recovery_list.append(self._recovery_row(record))
        if empty_text:
            empty = _label(empty_text, "muted", xalign=0.5, wrap=True)
            _margins(empty, 36, 12)
            self.recovery_list.append(empty)
        return False

    def _recovery_row(self, record: RecoveryRecord) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.set_selectable(False)
        row.add_css_class("target-row")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        _margins(box, 10, 8)

        icon = _label("↺", "info-icon", xalign=0.5)
        icon.set_valign(Gtk.Align.CENTER)
        box.append(icon)
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        labels.set_hexpand(True)
        name = _label(record.app_name, "app-name", ellipsize=True)
        name.set_tooltip_text(record.app_name)
        labels.append(name)
        timestamp = record.timestamp.replace("T", " ").replace("Z", " UTC")
        details = _label(
            _(
                "{timestamp} · {count} Pfad(e) · {size} · {source}",
                timestamp=timestamp,
                count=len(record.available_items),
                size=format_size(record.available_size),
                source=display_text(record.source),
            ),
            "muted", ellipsize=True,
        )
        details.set_tooltip_text(details.get_text())
        labels.append(details)
        if record.actions:
            labels.append(_label(
                _("Paket- oder Bibliotheksaktionen müssen bei Bedarf separat rückgängig gemacht werden."),
                "muted", wrap=True,
            ))
        box.append(labels)
        restore = Gtk.Button(label=_("Wiederherstellen"))
        restore.set_valign(Gtk.Align.CENTER)
        restore.add_css_class("primary")
        restore.connect("clicked", self._confirm_restore, record)
        box.append(restore)
        row.set_child(box)
        return row

    def _confirm_restore(self, _button: Gtk.Button, record: RecoveryRecord) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text=_("Daten von „{name}“ wiederherstellen?", name=record.app_name),
            secondary_text=_(
                "{count} Pfad(e) mit {size} werden an ihre ursprünglichen Orte zurückgeholt. Vorhandene Dateien "
                "werden nicht überschrieben. Ein deinstalliertes Programmpaket wird dadurch nicht erneut installiert.",
                count=len(record.available_items),
                size=format_size(record.available_size),
            ),
        )
        self._style_dialog(dialog)
        dialog.add_button(_("Abbrechen"), Gtk.ResponseType.CANCEL)
        confirm = dialog.add_button(_("Wiederherstellen"), Gtk.ResponseType.ACCEPT)
        confirm.add_css_class("suggested-action")
        dialog.set_default_response(Gtk.ResponseType.ACCEPT)
        dialog.connect("response", self._on_restore_confirmed, record.recovery_id)
        dialog.present()

    def _on_restore_confirmed(self, dialog: Gtk.MessageDialog, response: int, recovery_id: str) -> None:
        dialog.destroy()
        if response != Gtk.ResponseType.ACCEPT:
            return
        progress = Gtk.Dialog(transient_for=self, modal=True, title=_("Daten wiederherstellen"))
        self._style_dialog(progress)
        progress.set_deletable(False)
        area = progress.get_content_area()
        area.set_spacing(14)
        _margins(area, 24, 28)
        spinner = Gtk.Spinner()
        spinner.set_size_request(42, 42)
        spinner.set_halign(Gtk.Align.CENTER)
        spinner.start()
        area.append(spinner)
        area.append(_label(_("Daten werden an ihre ursprünglichen Orte zurückgeholt …"), wrap=True))
        progress.present()

        def worker() -> None:
            result = RecoveryManager().restore(recovery_id)
            GLib.idle_add(self._restore_finished, progress, result)

        threading.Thread(target=worker, daemon=True).start()

    def _restore_finished(self, progress: Gtk.Dialog, result: RestoreResult) -> bool:
        progress.destroy()
        if result.success:
            title = _("Wiederherstellung abgeschlossen")
            details = _(
                "{count} Pfad(e) wurden zurückgeholt. Falls das Programmpaket entfernt wurde, muss es separat "
                "neu installiert werden.",
                count=len(result.restored_paths),
            )
            message_type = Gtk.MessageType.INFO
        else:
            title = _("Wiederherstellung nicht vollständig")
            restored = (
                _("{count} Pfad(e) wurden bereits wiederhergestellt.\n\n", count=len(result.restored_paths))
                if result.restored_paths
                else ""
            )
            details = restored + (
                "\n".join(display_text(error) for error in result.errors[:8])
                or _("Ein unbekannter Fehler ist aufgetreten.")
            )
            message_type = Gtk.MessageType.ERROR
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=message_type,
            buttons=Gtk.ButtonsType.CLOSE,
            text=title,
            secondary_text=details,
        )
        self._style_dialog(dialog)
        dialog.connect("response", lambda item, _response: item.destroy())
        dialog.present()
        self._load_recovery_records(force=True)
        if not self.busy:
            self._load_applications()
        return False

    # ----- Seite: Updates & Startcheck ---------------------------------------------------------
    def _updates_page(self) -> Gtk.Widget:
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        _margins(content, 26, 30, 22, 30)
        content.append(self._page_top(_("PROGRAMMUPDATES"), _("Updates & Startcheck")))

        hero = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        hero.add_css_class("hero")
        hero_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        hero_text.set_hexpand(True)
        hero_text.append(_label(_("RESTLOS BLEIBT BEI DIR"), "eyebrow", "hero-eyebrow"))
        hero_text.append(_label(_("Neue Funktionen. Deine Daten bleiben lokal."), "hero-title", wrap=True))
        hero_text.append(_label(
            _("GitHub liefert ausschließlich Programmupdates. Löschprotokolle, Wiederherstellungsdaten "
              "und Einstellungen werden nicht hochgeladen."),
            "hero-text", wrap=True,
        ))
        hero.append(hero_text)
        hero_numbers = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        hero_numbers.set_valign(Gtk.Align.CENTER)
        self.update_hero_version = _label(__version__, "hero-number", "hero-version", xalign=1)
        hero_numbers.append(self.update_hero_version)
        hero_numbers.append(_label(_("Aktive Version"), "hero-number-label", xalign=1))
        hero.append(hero_numbers)
        content.append(hero)

        grid = Gtk.Grid(column_spacing=18, row_spacing=18)
        grid.set_column_homogeneous(True)
        content.append(grid)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.add_css_class("card")
        card.append(_label(_("Programmupdates"), "section-title"))
        self.update_version_label = _label("", "muted", wrap=True)
        card.append(self.update_version_label)
        self.update_status_line = _label("", "status-line", wrap=True)
        card.append(self.update_status_line)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.update_restart_button = Gtk.Button(label=_("Jetzt neu starten und aktualisieren"))
        self.update_restart_button.add_css_class("primary")
        self.update_restart_button.connect("clicked", lambda _button: self._application_call("restart_for_update"))
        buttons.append(self.update_restart_button)
        self.update_check_button = Gtk.Button(label=_("Jetzt prüfen"))
        self.update_check_button.connect("clicked", lambda _button: self._application_call("check_updates_now"))
        buttons.append(self.update_check_button)
        card.append(buttons)
        self.update_automatic = _wrapping_check_button(_("Automatisch stündlich prüfen und im Hintergrund vorbereiten"))
        self.update_automatic.connect("toggled", self._automatic_toggled)
        card.append(self.update_automatic)
        self.update_rollback_button = Gtk.Button(label=_("Zur vorherigen Version zurückschalten"))
        self.update_rollback_button.set_halign(Gtk.Align.START)
        self.update_rollback_button.connect("clicked", lambda _button: self._application_call("rollback_update"))
        card.append(self.update_rollback_button)
        grid.attach(card, 0, 0, 1, 1)

        how = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        how.add_css_class("card")
        how.append(_label(_("So funktioniert das Update"), "section-title"))
        for line in (
            _("Restlos prüft stündlich das neueste GitHub-Release und lädt es im Hintergrund."),
            _("Jedes Update ist mit Ed25519 signiert; Prüfsumme und Größe werden kontrolliert."),
            _("Die neue Version liegt nur in deinem Benutzerordner – kein Passwort, kein Systemeingriff."),
            _("Startet eine neue Version nicht, schaltet Restlos automatisch zurück."),
            _("Protokolle, Wiederherstellungsdaten und Einstellungen bleiben unverändert."),
        ):
            how.append(_label("✓  " + line, wrap=True))
        repository_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.update_repository = Gtk.Entry()
        self.update_repository.set_hexpand(True)
        self.update_repository.set_tooltip_text(_("GitHub-Benutzer/Repository der Updatequelle"))
        repository_row.append(self.update_repository)
        save = Gtk.Button(label=_("Speichern"))
        save.connect("clicked", self._repository_saved)
        repository_row.append(save)
        how.append(_label(_("UPDATEQUELLE"), "stat-heading"))
        how.append(repository_row)
        grid.attach(how, 1, 0, 1, 1)

        check = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        check.add_css_class("card")
        check.append(_label(_("Startcheck"), "section-title"))
        check.append(_label(_("Was Restlos auf diesem Computer vorfindet:"), "muted", wrap=True))
        self.startcheck_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        check.append(self.startcheck_box)
        content.append(check)
        self._fill_startcheck()
        return self._page_scroll(content)

    def _application_call(self, name: str) -> None:
        application = self.get_application()
        method = getattr(application, name, None)
        if callable(method):
            method()

    def _automatic_toggled(self, check: Gtk.CheckButton) -> None:
        if getattr(self, "_updating_status", False):
            return
        application = self.get_application()
        if isinstance(application, RestlosApplication):
            application.set_automatic_updates(check.get_active())

    def _repository_saved(self, _button: Gtk.Button) -> None:
        application = self.get_application()
        if isinstance(application, RestlosApplication):
            application.save_update_repository(self.update_repository.get_text())

    def show_update_status(self, status: UpdateStatus | None, *, checking: bool = False) -> None:
        if status is None:
            return
        self._updating_status = True
        try:
            self.update_version_label.set_text(_("Installiert: Version {version}", version=status.running))
            self.update_hero_version.set_text(status.running)
            for name in ("good", "warn", "bad"):
                self.update_status_line.remove_css_class(name)
            if checking:
                text, tone = _("Updates werden geprüft und gegebenenfalls im Hintergrund vorbereitet …"), "warn"
            else:
                text, tone = describe_update_status(status)
            self.update_status_line.set_text(text)
            self.update_status_line.add_css_class(tone)
            self.update_restart_button.set_visible(status.restart_ready)
            self.update_check_button.set_sensitive(not checking)
            self.update_automatic.set_active(status.automatic)
            application = self.get_application()
            running_staged = bool(getattr(application, "running_staged", False))
            self.update_rollback_button.set_visible(bool(status.pending) or running_staged)
            if not self.update_repository.has_focus():
                self.update_repository.set_text(status.repository)
            self.nav_counts["updates"].set_text("1" if status.restart_ready else "")
        finally:
            self._updating_status = False

    def _fill_startcheck(self) -> None:
        _clear_box(self.startcheck_box)
        gtk_version = f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}"
        python_version = ".".join(str(part) for part in sys.version_info[:3])
        managers = [name for name in ("apt-get", "dnf", "pacman", "zypper", "flatpak", "snap") if shutil.which(name)]
        entries = (
            (True, _("GTK {gtk} · Python {python}", gtk=gtk_version, python=python_version)),
            (shutil.which("pkexec") is not None,
             _("Administratorrechte über PolicyKit (pkexec) verfügbar") if shutil.which("pkexec")
             else _("pkexec fehlt – Systempakete können nicht entfernt werden")),
            (shutil.which("openssl") is not None,
             _("OpenSSL für signierte Updates vorhanden") if shutil.which("openssl")
             else _("OpenSSL fehlt – Updates können nicht geprüft werden")),
            (bool(managers),
             _("Paketquellen: {names}", names=", ".join(managers)) if managers
             else _("Keine bekannte Paketverwaltung gefunden")),
        )
        for ok, text in entries:
            line = _label(("✓  " if ok else "!  ") + text, "status-line", "good" if ok else "warn", wrap=True)
            self.startcheck_box.append(line)


def describe_update_status(status: UpdateStatus) -> tuple[str, str]:
    """Statustext und Tonalität (good/warn/bad) für die Update-Seite."""
    checked = ""
    if status.checked is not None:
        checked = " · " + _("geprüft {time}", time=time.strftime("%d.%m.%Y %H:%M", time.localtime(status.checked)))
    if status.restart_ready:
        return _("Version {version} ist geprüft und bereit. Sie startet beim nächsten Öffnen – oder sofort per Neustart.",
                 version=status.pending) + checked, "good"
    match status.kind:
        case "current":
            return _("Restlos ist auf dem aktuellen Stand.") + checked, "good"
        case "ready":
            return _("Restlos ist auf dem aktuellen Stand.") + checked, "good"
        case "blocked":
            return _("Version {version} wird übersprungen, weil sie nicht starten konnte. Die nächste Version kommt "
                     "wieder automatisch.", version=status.version) + checked, "warn"
        case "rolled-back":
            return _("Zur vorherigen Version zurückgeschaltet. Version {version} wird übersprungen.",
                     version=status.version) + checked, "warn"
        case "error":
            return display_text(status.detail or _("Ein unbekannter Fehler ist aufgetreten.")) + checked, "bad"
    if not status.automatic:
        return _("Automatische Updates sind ausgeschaltet."), "warn"
    return _("Noch nicht geprüft. Die erste Prüfung startet kurz nach dem Öffnen."), "warn"


class RestlosApplication(Gtk.Application):
    def __init__(self) -> None:
        # DEFAULT_FLAGS was only named in GLib 2.74; zero also supports 2.72.
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags(0))
        self.updater = Updater()
        self.running_staged = self.updater.root != self.updater.base
        self.restart_requested = False
        self._update_check_running = False
        self._update_timer = 0
        self._announced_version = ""
        self.connect("activate", self._activate)
        self._add_actions()

    def _activate(self, _application: Gtk.Application) -> None:
        window = self.props.active_window
        first_start = window is None
        if window is None:
            window = MainWindow(self)
        window.present()
        if not first_start:
            return
        # Fenster steht: erfolgreichen Start einer vorbereiteten Version bestätigen.
        GLib.idle_add(self._confirm_started)
        if self._update_timer == 0:
            self._update_timer = GLib.timeout_add_seconds(CHECK_INTERVAL_SECONDS, self._periodic_check)
            if self.updater.config()["automatic"]:
                GLib.timeout_add_seconds(FIRST_CHECK_DELAY_SECONDS, self._first_check)

    def _confirm_started(self) -> bool:
        try:
            self.updater.startup_ready()
        except (OSError, UpdateError):
            pass
        refresh_desktop_icon()
        status = self.update_status()
        window = self._main_window()
        if window is not None and status is not None:
            window.show_update_status(status)
            if status.kind == "rolled-back":
                window.show_notice(
                    _("Das letzte Update konnte nicht starten. Restlos verwendet wieder die vorherige Version."),
                    seconds=12,
                )
            elif status.restart_ready:
                self._announce(status)
        return False

    def _first_check(self) -> bool:
        self.check_updates_now(automatic=True)
        return False

    def _periodic_check(self) -> bool:
        if self.updater.config()["automatic"]:
            self.check_updates_now(automatic=True)
        return True

    def _main_window(self) -> MainWindow | None:
        for window in self.get_windows():
            if isinstance(window, MainWindow):
                return window
        return None

    def _style_dialog(self, dialog: Gtk.Widget) -> None:
        main = self._main_window()
        _apply_appearance(dialog, bool(main is not None and main.has_css_class("restlos-dark")))

    def _add_actions(self) -> None:
        for name, callback in (
            ("about", self._show_about),
            ("recovery", self._show_recovery_center),
            ("open-history", self._open_history),
            ("check-updates", lambda *_args: self.check_updates_now()),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)
        automatic = Gio.SimpleAction.new_stateful(
            "automatic-updates",
            None,
            GLib.Variant.new_boolean(self.updater.config()["automatic"]),
        )
        automatic.connect("change-state", self._change_automatic_updates)
        self.add_action(automatic)
        language = Gio.SimpleAction.new_stateful(
            "language",
            GLib.VariantType.new("s"),
            GLib.Variant.new_string(LanguageSettings().selected()),
        )
        language.connect("change-state", self._change_language)
        self.add_action(language)

    def _show_about(self, _action, _parameter) -> None:
        dialog = Gtk.AboutDialog(
            transient_for=self.props.active_window,
            modal=True,
            program_name=APP_NAME,
            version=__version__,
            comments=APP_TAGLINE,
            copyright=_("2026 – lokale Open-Source-Ausgabe"),
            license_type=Gtk.License.MIT_X11,
            logo_icon_name=APP_ID,
        )
        self._style_dialog(dialog)
        dialog.set_website(PROJECT_URL)
        dialog.set_website_label(_("Projektseite auf GitHub"))
        dialog.present()

    def _show_recovery_center(self, _action, _parameter) -> None:
        window = self._main_window()
        if window is not None:
            window.show_recovery_center()

    def _open_history(self, *_args) -> None:
        state_home = os.environ.get("XDG_STATE_HOME")
        path = (Path(state_home) if state_home else Path.home() / ".local/state") / "restlos/history"
        try:
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            Gio.AppInfo.launch_default_for_uri(path.as_uri(), None)
        except (OSError, GLib.Error) as error:
            self._show_message(_("Ordner konnte nicht geöffnet werden"), _("Pfad: {path}\n\n{error}", path=path, error=error),
                               Gtk.MessageType.ERROR)

    # ----- Updates -------------------------------------------------------------------------
    def update_status(self) -> UpdateStatus | None:
        try:
            return self.updater.status()
        except (OSError, UpdateError):
            return None

    def check_updates_now(self, *, automatic: bool = False) -> None:
        if self._update_check_running:
            return
        self._update_check_running = True
        window = self._main_window()
        if window is not None:
            window.show_update_status(self.update_status(), checking=True)
        action = self.lookup_action("check-updates")
        if isinstance(action, Gio.SimpleAction):
            action.set_enabled(False)

        def worker() -> None:
            try:
                status = self.updater.check()
            except Exception:  # defensive boundary for the background worker
                status = self.update_status()
            GLib.idle_add(self._update_check_finished, status, automatic)

        threading.Thread(target=worker, daemon=True).start()

    def _update_check_finished(self, status: UpdateStatus | None, automatic: bool) -> bool:
        self._update_check_running = False
        action = self.lookup_action("check-updates")
        if isinstance(action, Gio.SimpleAction):
            action.set_enabled(True)
        window = self._main_window()
        if window is None or status is None:
            return False
        window.show_update_status(status)
        if status.restart_ready:
            self._announce(status, force=not automatic)
        elif not automatic:
            text, _tone = describe_update_status(status)
            window.show_notice(text, seconds=8)
        return False

    def _announce(self, status: UpdateStatus, *, force: bool = False) -> None:
        window = self._main_window()
        if window is None or (status.pending == self._announced_version and not force):
            return
        self._announced_version = status.pending
        window.show_notice(
            _("Restlos Uninstaller {version} ist geprüft und bereit.", version=status.pending),
            action_label=_("Jetzt neu starten und aktualisieren"),
            action=self.restart_for_update,
            seconds=0,
        )

    def restart_for_update(self) -> None:
        window = self._main_window()
        if window is not None and window.busy:
            window.show_notice(_("Bitte warten, bis die laufende Aktion abgeschlossen ist. Danach neu starten."))
            return
        status = self.update_status()
        if status is None or not status.restart_ready:
            if window is not None:
                window.show_notice(_("Es ist kein vorbereitetes Update vorhanden."))
            return
        self.restart_requested = True
        self.quit()

    def rollback_update(self) -> None:
        try:
            self.updater.rollback()
        except (OSError, UpdateError) as error:
            self._show_message(_("Zurückschalten fehlgeschlagen"), display_text(str(error)), Gtk.MessageType.ERROR)
            return
        window = self._main_window()
        if window is not None:
            window.show_update_status(self.update_status())
            window.show_notice(_("Beim nächsten Start verwendet Restlos wieder die vorherige Version."), seconds=10)

    def set_automatic_updates(self, enabled: bool) -> None:
        try:
            self.updater.save_config(automatic=enabled)
        except (OSError, UpdateError) as error:
            self._show_message(_("Einstellung nicht gespeichert"), display_text(str(error)), Gtk.MessageType.ERROR)
            return
        action = self.lookup_action("automatic-updates")
        if isinstance(action, Gio.SimpleAction):
            action.set_state(GLib.Variant.new_boolean(enabled))
        window = self._main_window()
        if window is not None:
            window.show_update_status(self.update_status())
        if enabled:
            self.check_updates_now(automatic=True)

    def save_update_repository(self, repository: str) -> None:
        try:
            self.updater.save_config(repository=repository)
        except (OSError, UpdateError) as error:
            self._show_message(_("Einstellung nicht gespeichert"), display_text(str(error)), Gtk.MessageType.ERROR)
            return
        window = self._main_window()
        if window is not None:
            window.show_notice(_("Update-Einstellungen gespeichert."))
            window.show_update_status(self.update_status())

    def _change_automatic_updates(self, action: Gio.SimpleAction, value: GLib.Variant) -> None:
        self.set_automatic_updates(value.get_boolean())

    def _change_language(self, action: Gio.SimpleAction, value: GLib.Variant) -> None:
        selected = value.get_string()
        try:
            LanguageSettings().set(selected)
        except (OSError, ValueError) as error:
            self._show_message(_("Sprache konnte nicht gespeichert werden"), str(error), Gtk.MessageType.ERROR)
            return
        action.set_state(value)
        self._show_message(
            _("Sprache gespeichert"),
            _("Starte Restlos Uninstaller neu, damit die neue Sprache vollständig verwendet wird."),
            Gtk.MessageType.INFO,
        )

    def _show_message(self, title: str, details: str, message_type: Gtk.MessageType) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self.props.active_window,
            modal=True,
            message_type=message_type,
            buttons=Gtk.ButtonsType.CLOSE,
            text=title,
            secondary_text=details,
        )
        self._style_dialog(dialog)
        dialog.connect("response", lambda item, _response: item.destroy())
        dialog.present()


def _restart(base: Path) -> None:
    # Die Basisversion wählt beim Neustart erneut (geprüfte neue Version oder Rückfall).
    environment = dict(os.environ)
    environment.pop("RESTLOS_LAUNCH_CHOSEN", None)
    environment.pop("RESTLOS_BASE_DIR", None)
    script = base / "run_restlos.py"
    os.execve(sys.executable, [sys.executable, "-I", "-B", str(script)], environment)


def run_gui() -> int:
    # Gtk.init() wirft ohne grafische Sitzung (SSH, TTY) eine Ausnahme; init_check meldet es sauber.
    display = Gdk.Display.get_default() if Gtk.init_check() else None
    if display is None:
        print(_("Keine grafische Sitzung gefunden. Verwende `restlos list` oder `restlos analyze NAME`."))
        return 1
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS.encode("utf-8"))
    Gtk.StyleContext.add_provider_for_display(
        display,
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
    Gtk.Window.set_default_icon_name(APP_ID)
    application = RestlosApplication()
    result = application.run(None)
    if application.restart_requested:
        try:
            _restart(application.updater.base)
        except OSError as error:
            print(_("Neustart fehlgeschlagen: {error}", error=error), file=sys.stderr)
    return result
