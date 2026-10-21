"""GUI wiring checks; skip on systems without GTK or a display."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from restlos.locations import AppLocation, LocationResult
from restlos.models import AppRecord, Confidence, RemovalPlan, RemovalResult, RemovalTarget, SharedUse, SourceKind

try:
    from restlos.gui import Gio, Gtk, MainWindow, Pango, RestlosApplication, TargetRow, WarningRow
    GTK_AVAILABLE = Gtk.init_check()
except (ImportError, ValueError):
    GTK_AVAILABLE = False


@unittest.skipUnless(GTK_AVAILABLE, "GTK 4 and a display are required")
class LocationGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = Gtk.Application(
            application_id="io.github.jurkast.Restlos.LocationTests",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        cls.application.register(None)

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        with patch.object(MainWindow, "_load_applications"):
            self.window = MainWindow(self.application)
        self.addCleanup(self.window.destroy)

    def test_application_initialization_supports_baseline_gtk_and_glib(self) -> None:
        with patch("restlos.gui.Updater") as updater, patch("restlos.gui.LanguageSettings") as settings:
            updater.return_value.config.return_value = {"automatic": False, "repository": "x/y", "blocked": ""}
            settings.return_value.selected.return_value = "system"
            application = RestlosApplication()
        self.assertEqual(application.get_flags(), Gio.ApplicationFlags(0))
        self.assertIsNotNone(application.lookup_action("check-updates"))
        self.assertTrue(self.window.search.get_property("placeholder-text"))
        self.assertNotEqual(
            self.window.has_css_class("restlos-light"),
            self.window.has_css_class("restlos-dark"),
        )

    def test_air_appearance_switches_between_light_and_dark_system_themes(self) -> None:
        self.window._gtk_settings = None
        self.window._desktop_settings = None
        with patch.dict("restlos.gui.os.environ", {"GTK_THEME": "Restlos-Dark"}):
            self.window._sync_theme()
        self.assertTrue(self.window.has_css_class("restlos-dark"))
        self.assertFalse(self.window.has_css_class("restlos-light"))

        with patch.dict("restlos.gui.os.environ", {"GTK_THEME": "Restlos-Light"}):
            self.window._sync_theme()
        self.assertTrue(self.window.has_css_class("restlos-light"))
        self.assertFalse(self.window.has_css_class("restlos-dark"))

    def test_air_appearance_is_applied_to_dialogs(self) -> None:
        dialog = Gtk.Dialog(transient_for=self.window)
        self.addCleanup(dialog.destroy)
        self.window._dark_mode = True
        self.window._style_dialog(dialog)
        self.assertTrue(dialog.has_css_class("restlos-dark"))

        self.window._dark_mode = False
        self.window._style_dialog(dialog)
        self.assertTrue(dialog.has_css_class("restlos-light"))
        self.assertFalse(dialog.has_css_class("restlos-dark"))

    def test_target_folder_button_leaves_selection_unchanged(self) -> None:
        target = RemovalTarget(self.root, "Data", 0, Confidence.HIGH, False)
        changed, opened = Mock(), Mock()
        row = TargetRow(target, changed, opened)
        row.get_child().get_last_child().emit("clicked")
        opened.assert_called_once_with(self.root)
        changed.assert_not_called()
        self.assertFalse(target.selected)

    def test_shared_row_locks_checkbox_but_keeps_folder_button(self) -> None:
        target = RemovalTarget(self.root, "Data", 0, Confidence.HIGH, False,
                               [SharedUse("beta", "Beta", "Lutris", str(self.root), "Wine prefix")])
        changed, opened = Mock(), Mock()
        row = TargetRow(target, changed, opened)
        checkbox = row.get_child().get_first_child()
        self.assertFalse(checkbox.get_sensitive())
        checkbox.set_active(True)
        self.assertFalse(target.selected)
        row.get_child().get_last_child().emit("clicked")
        opened.assert_called_once_with(self.root)

    def test_unreviewed_plan_cannot_enable_removal(self) -> None:
        app = AppRecord("portable:test", "Test", SourceKind.PORTABLE, "test")
        self.window.current_plan = RemovalPlan(app, [RemovalTarget(self.root, "Data", 0, Confidence.HIGH)])
        self.window._update_plan_summary()
        self.assertFalse(self.window.remove_button.get_sensitive())

    def test_plan_summary_updates_visual_status_tiles(self) -> None:
        app = AppRecord("portable:test", "Test", SourceKind.PORTABLE, "test")
        self.window.current_plan = RemovalPlan(
            app,
            [RemovalTarget(self.root, "Data", 2048, Confidence.HIGH)],
        )
        self.window._update_plan_summary()
        self.assertEqual(self.window.action_stat_value.get_text(), "0")
        self.assertEqual(self.window.path_stat_value.get_text(), "1")
        self.assertEqual(self.window.size_stat_value.get_text(), "2.0 KiB")

    def test_long_detail_and_safety_texts_are_constrained(self) -> None:
        self.assertEqual(self.window.detail_name.get_ellipsize(), Pango.EllipsizeMode.END)
        self.assertEqual(self.window.detail_id.get_ellipsize(), Pango.EllipsizeMode.END)
        for check in (self.window.permanent_check, self.window.backup_check, self.window.process_check):
            label = check.get_first_child()
            while label is not None and not isinstance(label, Gtk.Label):
                label = label.get_next_sibling()
            self.assertIsInstance(label, Gtk.Label)
            self.assertTrue(label.get_wrap())

    def test_warning_row_expands_from_ellipsis_and_collapses_again(self) -> None:
        row = WarningRow("A deliberately long warning that must not leave its card")
        self.assertEqual(row.label.get_ellipsize(), Pango.EllipsizeMode.END)
        self.assertFalse(row.label.get_wrap())
        self.assertEqual(row.more_button.get_label(), "…")

        row.more_button.emit("clicked")
        self.assertEqual(row.label.get_ellipsize(), Pango.EllipsizeMode.NONE)
        self.assertTrue(row.label.get_wrap())
        self.assertEqual(row.more_button.get_label(), "−")

        row.more_button.emit("clicked")
        self.assertEqual(row.label.get_ellipsize(), Pango.EllipsizeMode.END)
        self.assertFalse(row.label.get_wrap())

    @patch("restlos.gui.Gtk.MessageDialog")
    def test_invalidated_plan_requires_reanalysis_not_automatic_retry(self, message) -> None:
        app = AppRecord("portable:test", "Test", SourceKind.PORTABLE, "test")
        plan = RemovalPlan(app)
        self.window.current_app = app
        self.window.current_plan = plan
        result = RemovalResult(False, review_required=True)
        self.window._removal_finished(plan, result)
        self.assertIsNone(self.window.current_plan)
        self.assertFalse(self.window.remove_button.get_sensitive())
        with patch.object(self.window, "_analyze_current") as analyze, \
             patch.object(self.window, "_start_removal") as remove:
            self.window._after_result_dialog(message.return_value, Gtk.ResponseType.APPLY, result)
            analyze.assert_called_once()
            remove.assert_not_called()

    @patch("restlos.gui.Gio.AppInfo.get_default_for_type")
    def test_desktop_file_is_passed_to_directory_handler_as_parent(self, get_manager) -> None:
        desktop = self.root / "run.desktop"
        desktop.write_text("[Desktop Entry]\nExec=must-not-run\n", encoding="utf-8")
        self.window._open_folder(desktop)
        get_manager.assert_called_once_with("inode/directory", False)
        args = get_manager.return_value.launch.call_args.args
        self.assertEqual(args[0][0].get_path(), str(self.root))

    @patch("restlos.gui.Gtk.MessageDialog")
    @patch("restlos.gui.Gio.AppInfo.get_default_for_type")
    def test_missing_file_does_not_launch_anything(self, get_manager, message) -> None:
        self.window._open_folder(self.root / "missing")
        get_manager.assert_not_called()
        message.return_value.present.assert_called_once()

    @patch("restlos.gui.Gtk.MessageDialog")
    @patch("restlos.gui.Gio.AppInfo.get_default_for_type", return_value=None)
    def test_missing_file_manager_shows_error(self, get_manager, message) -> None:
        self.window._open_folder(self.root)
        message.return_value.present.assert_called_once()

    def test_closed_dialog_ignores_late_results(self) -> None:
        dialog, rows, status = Mock(), Mock(), Mock()
        self.window._locations_dialog = None
        self.assertFalse(self.window._locations_loaded(dialog, rows, status, LocationResult(), None))
        rows.append.assert_not_called()
        status.set_text.assert_not_called()

    def test_location_buttons_use_their_own_paths(self) -> None:
        second = self.root / "second"
        second.mkdir()
        dialog = Gtk.Dialog(transient_for=self.window)
        self.addCleanup(dialog.destroy)
        self.window._locations_dialog = dialog
        rows, status = Gtk.ListBox(), Gtk.Label()
        result = LocationResult([AppLocation(self.root, "Data"), AppLocation(second, "Data")])
        self.window._locations_loaded(dialog, rows, status, result, None)
        with patch.object(self.window, "_open_folder") as opened:
            for n, path in enumerate((self.root, second)):
                rows.get_row_at_index(n).get_child().get_last_child().emit("clicked")
                opened.assert_called_with(path, dialog)

    def test_failed_analysis_cannot_leave_previous_apps_plan_active(self) -> None:
        app = AppRecord("portable:test", "Test", SourceKind.PORTABLE, "test")
        self.window.current_app = app
        self.window.current_plan = RemovalPlan(app)
        with patch("restlos.gui.threading.Thread"):
            self.window._analyze_current()
        self.assertIsNone(self.window.current_plan)
        self.assertFalse(self.window.remove_button.get_sensitive())
        self.window._analysis_loaded(None, "test error")
        self.assertTrue(self.window.locations_button.get_sensitive())
        self.assertFalse(self.window.remove_button.get_sensitive())

    def test_selection_during_analysis_is_analyzed_afterwards(self) -> None:
        first = AppRecord("portable:a", "Erstes", SourceKind.PORTABLE, "a")
        second = AppRecord("portable:b", "Zweites", SourceKind.PORTABLE, "b")
        self.window._applications_loaded([first, second], None)
        rows = [self.window.app_list.get_row_at_index(index) for index in (0, 1)]
        with patch("restlos.gui.threading.Thread"):
            self.window.app_list.select_row(rows[0])
            self.assertTrue(self.window.busy)
            # Klick auf eine andere Anwendung, während die erste noch analysiert wird.
            self.window.app_list.select_row(rows[1])
            self.assertEqual(self.window.current_app.key, first.key)
            self.assertFalse(self.window.remove_button.get_sensitive())
            stale = RemovalPlan(first)
            self.window._analysis_loaded(stale, None)
        # Der alte Plan wird nicht übernommen, die markierte Anwendung wird analysiert.
        self.assertEqual(self.window.current_app.key, second.key)
        self.assertIsNone(self.window.current_plan)
        self.assertTrue(self.window.busy)
        self.assertEqual(self.window.detail_name.get_text(), "Zweites")

    def test_old_desktop_icon_is_replaced_once(self) -> None:
        from restlos.gui import ICON_PATH, refresh_desktop_icon
        pixmap = self.root / "pixmaps/io.github.jurkast.Restlos.svg"
        pixmap.parent.mkdir(parents=True)
        pixmap.write_text("<svg>alt</svg>", encoding="utf-8")
        self.assertTrue(refresh_desktop_icon(self.root))
        self.assertEqual(pixmap.read_bytes(), ICON_PATH.read_bytes())
        self.assertFalse(refresh_desktop_icon(self.root))
        self.assertFalse((self.root / "icons").exists())

    def test_leftovers_page_lists_findings_and_opens_review(self) -> None:
        from restlos.leftovers import Leftover
        folder = self.root / "OldGame"
        folder.mkdir()
        self.window._leftovers_loaded([Leftover(folder, "Kein installiertes Programm gefunden – bitte prüfen", 2048, 0.0)], None)
        self.assertEqual(self.window.nav_counts["leftovers"].get_text(), "1")
        self.assertEqual(self.window.leftovers_size.get_text(), "2.0 KiB")
        with patch("restlos.gui.threading.Thread"):
            self.window._review_leftover(folder)
        self.assertEqual(self.window.page_stack.get_visible_child_name(), "apps")
        self.assertEqual(self.window.current_app.key, f"portable:{folder}")

    def test_navigation_contains_leftovers_page(self) -> None:
        self.assertIn("leftovers", self.window.nav_buttons)
        with patch.object(self.window, "_load_leftovers") as load:
            self.window.navigate("leftovers")
        load.assert_called_once()

    def test_updates_page_shows_active_version_in_hero(self) -> None:
        from restlos.updater import UpdateStatus
        status = UpdateStatus(running="2.1.3", pending="", automatic=True, repository="jurkast/restlos-uninstaller",
                              kind="current", version="2.1.3", detail="", checked=None)
        self.window.show_update_status(status)
        self.assertEqual(self.window.update_hero_version.get_text(), "2.1.3")
        self.assertFalse(self.window.update_restart_button.get_visible())


if __name__ == "__main__":
    unittest.main()
