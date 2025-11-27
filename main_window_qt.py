# main_window_qt.py
# Version 09.20.00.00 dated 20251105
# Added PhotoDeletionService with comprehensive delete functionality
# Enhanced repositories with utility methods for future migrations
# Current LOC: ~2,640 (added photo deletion feature)

# [ Tree View  ]
#     │
#     ▼
#  photo_folders  ⇨  loads folder → retrieves photos
#     │
#     ▼
#  photo_metadata → thumbnail grid, details panel
#
#
# 🧭 3. Suggested Database Schema
#  🗃️ photo_folders
#  id	parent_id	path	name
#  1	NULL	/repo/2022	2022
#  2	1	/repo/2022/family	family
#  3	1	/repo/2022/vacation	vacation
#  🗃️ photo_metadata
#  path	folder_id	size_kb	modified	width	height	embedding	date_taken	tags
#  /repo/2022/family/img1.jpg	2	3200	2024-12-05 12:34	4000	3000	… blob …	2024-05-04	family,baby
#
#  👉 folder_id gives fast tree navigation
#  👉 tags, embedding, and date_taken allow smart sorting later.
#
#  🧭 2. Recommended Directory Scanning Strategy
#  👉 We don't want to re-scan the entire repository every time.
#  👉 We should scan once and index the structure in the database.
#
#  🧰 Step-by-step:
#  Recursive scan using os.walk() or pathlib.Path.rglob('*')
#
#  For each file:
#  Check file type (image formats: .jpg, .png, .heic, .webp, .tif, etc.)
#  Get basic metadata (size, modified date, dimensions if needed)
#  Save to photo_metadata table
#  For each folder:
#  Save a reference to photo_folders table (for tree view)
#  Mark parent–child relationship for UI navigation
#  Store a hash or last_modified so we can incrementally update later.

from splash_qt import SplashScreen, StartupWorker
import os, platform, traceback, time as _time, logging
from thumb_cache_db import get_cache

from db_writer import DBWriter
from typing import Iterable, Optional, Dict, Tuple

# ✅ NEW: Import service-based ScanWorker
from services.scan_worker_adapter import ScanWorkerAdapter as ScanWorker

# Add imports near top if not present:

from PySide6.QtCore import Qt, QThread, QSize, QThreadPool, Signal, QObject, QRunnable, QEvent, QTimer, QProcess, QItemSelectionModel, QRect

from PySide6.QtGui import QPixmap, QImage, QImageReader, QAction, QActionGroup, QIcon, QTransform, QPalette, QColor, QGuiApplication

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QSplitter,
    QHBoxLayout, QVBoxLayout, QLabel,
    QComboBox, QSizePolicy, QToolBar, QMessageBox,
    QDialog, QPushButton, QFileDialog, QScrollArea,
    QCheckBox, QComboBox as QSortComboBox,
    QProgressDialog, QProgressBar, QApplication, QStyle,
    QDialogButtonBox, QMenu, QGroupBox, QFrame,
    QSlider, QFormLayout, QTextEdit, QButtonGroup, QLineEdit
)


from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from collections import deque


from PIL import Image, ImageEnhance, ImageQt, ImageOps, ExifTags
# Optional HEIF/HEIC support (non-fatal)
try:
    import pillow_heif  # if installed, Pillow can open HEIC/HEIF
    print("[Startup] pillow_heif available — HEIC/HEIF support enabled.")
except Exception:
    # fine if missing; HEIC files will be skipped unless plugin installed
    pass

from sidebar_qt import SidebarQt

from thumbnail_grid_qt import ThumbnailGridQt

# 🎬 Phase 4.4: Video player support
from video_player_qt import VideoPlayerPanel
from thumbnail_grid_qt import is_video_file

# Layout system for UI/UX switching
from layouts.layout_manager import LayoutManager

# Phase 1 Refactoring: Extracted UI panels
from ui.panels.details_panel import DetailsPanel
from ui.panels.backfill_status_panel import BackfillStatusPanel

# Phase 1 Refactoring: Extracted controllers
from controllers import ScanController, SidebarController, ProjectController

# Phase 2 Refactoring: Extracted UI widgets
from ui.widgets.breadcrumb_navigation import BreadcrumbNavigation
from ui.widgets.backfill_indicator import CompactBackfillIndicator
from ui.widgets.selection_toolbar import SelectionToolbar

# Phase 2 Refactoring: Extracted services
from services.thumbnail_manager import ThumbnailManager

from app_services import (
    list_projects, get_default_project_id, 
    scan_signals, scan_repository, 
    clear_thumbnail_cache
)

from reference_db import ReferenceDB
from reference_db import (
    # NOTE: ensure_created_date_fields no longer needed - handled by migration system
    count_missing_created_fields,
    single_pass_backfill_created_fields,
)

from settings_manager_qt import SettingsManager
# --- Apply decoder warning policy early ---
from settings_manager_qt import apply_decoder_warning_policy
apply_decoder_warning_policy()

from preview_panel_qt import LightboxDialog

# --- Search UI imports ---
from search_widget_qt import SearchBarWidget, AdvancedSearchDialog

# --- Video backfill dialog ---
from video_backfill_dialog import VideoBackfillDialog

# --- Preferences dialog (new version with i18n and sidebar navigation) ---
from preferences_dialog import PreferencesDialog
from translation_manager import get_translation_manager, tr

# --- Backfill / process management imports ---
import subprocess, shlex, sys
from pathlib import Path
from threading import Thread, Event

# When double-clicking a thumbnail:
def _on_thumb_double_click(self, path):
    dlg = LightboxDialog(path, self)
    dlg.exec()


# --- Simple file logger for debugging frozen builds ---
def safe_log(msg: str):
    """Append a message to app_log.txt (UTF-8)."""
    try:
        log_path = os.path.join(os.getcwd(), "app_log.txt")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception as e:
        # In worst case, just print if file writing fails
        print(f"[LOGGING ERROR] {e}: {msg}")

# Small helper: clamp integer percent
def _clamp_pct(v):
    try:
        return max(0, min(100, int(v or 0)))
    except Exception:
        return 0


def _get_default_ignore_folders():
    """
    Get platform-specific default ignore folders for scanning.
    Returns a list of folder names to skip during repository scans.
    """
    common = ["__pycache__", "node_modules", ".git", ".svn", ".hg",
              "venv", ".venv", "env", ".env"]

    if platform.system() == "Windows":
        return common + [
            "AppData", "Program Files", "Program Files (x86)", "Windows",
            "$Recycle.Bin", "System Volume Information", "Temp", "Cache",
            "Microsoft", "Installer", "Recovery", "Logs",
            "ThumbCache", "ActionCenterCache"
        ]
    elif platform.system() == "Darwin":  # macOS
        return common + ["Library", ".Trash", "Caches", "Logs",
                        "Application Support"]
    else:  # Linux and others
        return common + [".cache", ".local/share/Trash", "tmp"]


# ---------------------------
# Note: Old embedded ScanWorker class removed - now using services/photo_scan_service.py


# === Phase 1, Step 1.3: Controllers Extracted ================================
# NOTE: ScanController, SidebarController, and ProjectController have been
#       extracted to controllers/ package for better modularity.
#       See: controllers/scan_controller.py
#            controllers/sidebar_controller.py
#            controllers/project_controller.py
#
# Reduction: ~600 LOC moved to separate controller files


#======================================

# === Phase 2, Step 2.4: ThumbnailManager Extracted (Pipeline A) =============
# NOTE: ThumbnailManager and related classes (_ThumbLoaded, _ThumbTask) have been
#       extracted to services/thumbnail_manager.py for better modularity.
#       See: services/thumbnail_manager.py
#
# This is Pipeline A - used for zoom integration in MainWindow.
# Pipeline C (ThumbWorker in thumbnail_grid_qt.py) is the preferred pipeline
# for viewport-based lazy loading in the Current Layout.
#
# Reduction: ~164 LOC moved to separate service file
# =============================================================================



# === Phase 3 UIBuilder =======================================================

class UIBuilder:
    """
    Helper for building toolbars, menus, and controls with less boilerplate.
    Used by MainWindow during __init__ to reduce clutter.
    """
    def __init__(self, main):
        self.main = main
        self.tb = None

    def make_toolbar(self, name="Tools"):
        tb = QToolBar(name, self.main)
        self.main.addToolBar(tb)
        self.tb = tb
        return tb

    def action(self, text, icon=None, shortcut=None, tooltip=None, checkable=False, handler=None):
        act = QAction(text, self.main)
        if icon:
            act.setIcon(QIcon.fromTheme(icon))
        if shortcut:
            try:
                act.setShortcut(shortcut)
            except Exception:
                pass
        if tooltip:
            act.setToolTip(tooltip)
        act.setCheckable(checkable)
        if handler:
            act.triggered.connect(handler)
        if self.tb:
            self.tb.addAction(act)
        return act

    def separator(self):
        if self.tb:
            self.tb.addSeparator()

    def menu(self, title, icon=None):
        m = self.main.menuBar().addMenu(title)
        return m

    def menu_action(self, menu, text, shortcut=None, tooltip=None, checkable=False, handler=None):
        act = QAction(text, self.main)
        if shortcut:
            try:
                act.setShortcut(shortcut)
            except Exception:
                pass
        if tooltip:
            act.setToolTip(tooltip)
        act.setCheckable(checkable)
        if handler:
            act.triggered.connect(handler)
        menu.addAction(act)
        return act

    def combo_sort(self, label_text, options, on_change):
        self.tb.addWidget(QLabel(label_text))
        combo = QSortComboBox()
        combo.addItems(options)
        combo.currentIndexChanged.connect(lambda *_: on_change())
        self.tb.addWidget(combo)
        return combo

    def checkbox(self, text, checked=True):
        chk = QCheckBox(text)
        chk.setChecked(checked)
        if self.tb:
            self.tb.addWidget(chk)
        return chk


# ======================================================
# OLD PREFERENCES DIALOG REMOVED
# The old PreferencesDialog class has been replaced with preferences_dialog.py
# New features: Left sidebar navigation, i18n support, 900x600 layout
# ======================================================

# ======================================================


# =============================================================================
# REFACTORING NOTE (Phase 1, Step 1.2 - Thumbnail Consolidation):
#
# Pipeline B (ThumbnailTask/ThumbnailResult) REMOVED - Dead code!
# - Was defined but never used anywhere in the codebase
# - Removed 54 lines of unused code
#
# Thumbnail handling now uses:
# - Pipeline A (ThumbnailManager below) - for MainWindow integration
# - Pipeline C (thumbnail_grid_qt.py: ThumbWorker) - for Current Layout grid
#   ↳ This is the proven, stable pipeline with viewport-based lazy loading
# =============================================================================


# =============================================================================
# REFACTORING NOTE (Phase 1, Step 1.1 - UI Panel Extraction):
#
# DetailsPanel class EXTRACTED to ui/panels/details_panel.py (1,006 lines)
# - Rich metadata display for photos and videos
# - EXIF parsing, GPS reverse geocoding, thumbnail preview
# - Now imported from ui/panels/details_panel.py
#
# See: ui/panels/details_panel.py for implementation
# =============================================================================

# === Phase 2, Step 2.1: BreadcrumbNavigation Extracted =======================
# NOTE: BreadcrumbNavigation widget has been extracted to ui/widgets/ package
#       for better modularity.
#       See: ui/widgets/breadcrumb_navigation.py
#
# Reduction: ~248 LOC moved to separate widget file
# =============================================================================

# === Phase 2, Step 2.3: SelectionToolbar Extracted ==========================
# NOTE: SelectionToolbar widget has been extracted to ui/widgets/ package
#       for better modularity.
#       See: ui/widgets/selection_toolbar.py
#
# Reduction: ~126 LOC moved to separate widget file
# =============================================================================

# === Phase 2, Step 2.2: CompactBackfillIndicator Extracted ==================
# NOTE: CompactBackfillIndicator widget has been extracted to ui/widgets/ package
#       for better modularity.
#       See: ui/widgets/backfill_indicator.py
#
# Reduction: ~228 LOC moved to separate widget file
# =============================================================================

# =============================================================================
# REFACTORING NOTE (Phase 1, Step 1.1 - UI Panel Extraction):
#
# BackfillStatusPanel class EXTRACTED to ui/panels/backfill_status_panel.py (149 lines)
# - Metadata backfill status display and control
# - Background/foreground worker management
# - Now imported from ui/panels/backfill_status_panel.py
#
# See: ui/panels/backfill_status_panel.py for implementation
# =============================================================================



class MainWindow(QMainWindow):
    PROGRESS_DIALOG_THRESHOLD = 10  # 👈 only show dialog if photo count >= X
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MemoryMate - PhotoFlow")
        
        # keep rest of initializer logic, but ensure some attributes exist
        # keep rest of initializer logic, but ensure some attributes exist
        self.settings = SettingsManager()
        self._committed_total = 0
        self._scan_result = (0, 0)  # folders, photos

        # CRITICAL FIX: Load language from settings and apply to TranslationManager
        # This ensures the entire app (not just preferences dialog) uses the selected language
        saved_language = self.settings.get("language", "en")
        tm = get_translation_manager()
        tm.set_language(saved_language)
        print(f"[MainWindow] Language loaded from settings: {saved_language}")

        # Initialize layout manager (for UI/UX layout switching)
        self.layout_manager = LayoutManager(self)
        print("[MainWindow] Layout manager initialized")

        self.setAttribute(Qt.WA_AcceptTouchEvents, True)
        QApplication.instance().setAttribute(Qt.AA_SynthesizeMouseForUnhandledTouchEvents, True)
        QApplication.instance().setAttribute(Qt.AA_SynthesizeTouchForUnhandledMouseEvents, True)
        QApplication.instance().setAttribute(Qt.AA_CompressTabletEvents, False)

        # Get the available geometry of the primary screen
        screen = QGuiApplication.primaryScreen().availableGeometry()

        # Set the main window to fit the available screen (without hiding under taskbar)

        # Optional: add a margin if you want some breathing room
        margin = 50
        self.setGeometry(screen.adjusted(margin, margin, -margin, -margin))

        # Move to top-left of available area  
        self.move(screen.center() - self.rect().center())

        
        if not self.settings.get("show_decoder_warnings", False):
            print("🔇 Qt/Pillow decoder warnings silenced (per user settings).")
        else:
            print("⚠️ Decoder warnings ENABLED (verbose mode).")
        
        self.active_tag_filter = "all"

        # === Toolbar & Menus via UIBuilder ===
        ui = UIBuilder(self)
        tb = ui.make_toolbar("Tools")
        # Defer connecting handlers until grid exists
        act_select_all = ui.action(tr('toolbar.select_all'))
        act_clear_sel = ui.action(tr('toolbar.clear'))
        act_open = ui.action(tr('toolbar.open'))
        act_delete = ui.action(tr('toolbar.delete'))
        ui.separator()

        folded = bool(self.settings.get("sidebar_folded", False))

        # Create action early — connect it later when sidebar exists
        self.act_fold_unfold = ui.action(
            tr('toolbar.fold_unfold_sidebar'),
            shortcut="Ctrl+Shift+F",
            tooltip="Toggle collapse/expand of the sidebar (Ctrl+Shift+F)",
            checkable=True
        )
        self.act_fold_unfold.setChecked(folded)
        ui.separator()

        # === Menu Bar ===
        # === Phase 3: Enhanced Menus (Modern Structure) ===
        menu_bar = self.menuBar()

        # ========== FILE MENU ==========
        menu_file = menu_bar.addMenu(tr("menu.file"))

        act_scan_repo_menu = QAction(tr("menu.file_scan"), self)
        act_scan_repo_menu.setShortcut("Ctrl+O")
        act_scan_repo_menu.setToolTip("Scan a directory to add photos to the current project")
        menu_file.addAction(act_scan_repo_menu)

        menu_file.addSeparator()

        act_preferences = QAction(tr("menu.file_preferences"), self)
        act_preferences.setShortcut("Ctrl+,")
        act_preferences.setIcon(QIcon.fromTheme("preferences-system"))
        menu_file.addAction(act_preferences)
        act_preferences.triggered.connect(self._open_preferences)

        # ========== VIEW MENU ==========
        menu_view = menu_bar.addMenu(tr("menu.view"))

        # Zoom controls
        act_zoom_in = QAction(tr("menu.view_zoom_in"), self)
        act_zoom_in.setShortcut("Ctrl++")
        act_zoom_in.setToolTip("Increase thumbnail size")
        menu_view.addAction(act_zoom_in)

        act_zoom_out = QAction(tr("menu.view_zoom_out"), self)
        act_zoom_out.setShortcut("Ctrl+-")
        act_zoom_out.setToolTip("Decrease thumbnail size")
        menu_view.addAction(act_zoom_out)

        menu_view.addSeparator()

        # Grid Size submenu
        menu_grid_size = menu_view.addMenu(tr("menu.view_grid_size"))

        act_grid_small_menu = QAction(tr("menu.view_grid_small"), self)
        act_grid_small_menu.setCheckable(True)
        menu_grid_size.addAction(act_grid_small_menu)

        act_grid_medium_menu = QAction(tr("menu.view_grid_medium"), self)
        act_grid_medium_menu.setCheckable(True)
        act_grid_medium_menu.setChecked(True)  # Default
        menu_grid_size.addAction(act_grid_medium_menu)

        act_grid_large_menu = QAction(tr("menu.view_grid_large"), self)
        act_grid_large_menu.setCheckable(True)
        menu_grid_size.addAction(act_grid_large_menu)

        act_grid_xl_menu = QAction(tr("menu.view_grid_xl"), self)
        act_grid_xl_menu.setCheckable(True)
        menu_grid_size.addAction(act_grid_xl_menu)

        # Group grid size actions for exclusive selection
        self.grid_size_menu_group = QActionGroup(self)
        self.grid_size_menu_group.addAction(act_grid_small_menu)
        self.grid_size_menu_group.addAction(act_grid_medium_menu)
        self.grid_size_menu_group.addAction(act_grid_large_menu)
        self.grid_size_menu_group.addAction(act_grid_xl_menu)

        menu_view.addSeparator()

        # Sort By submenu
        menu_sort = menu_view.addMenu(tr("menu.view_sort"))

        act_sort_date = QAction(tr("menu.view_sort_date"), self)
        act_sort_date.setCheckable(True)
        menu_sort.addAction(act_sort_date)

        act_sort_filename = QAction(tr("menu.view_sort_filename"), self)
        act_sort_filename.setCheckable(True)
        act_sort_filename.setChecked(True)  # Default
        menu_sort.addAction(act_sort_filename)

        act_sort_size = QAction(tr("menu.view_sort_size"), self)
        act_sort_size.setCheckable(True)
        menu_sort.addAction(act_sort_size)

        # Group sort actions for exclusive selection
        self.sort_menu_group = QActionGroup(self)
        self.sort_menu_group.addAction(act_sort_date)
        self.sort_menu_group.addAction(act_sort_filename)
        self.sort_menu_group.addAction(act_sort_size)

        menu_view.addSeparator()

        # Sidebar submenu
        menu_sidebar = menu_view.addMenu(tr("menu.view_sidebar"))

        act_toggle_sidebar = QAction(tr("menu.view_sidebar"), self)
        act_toggle_sidebar.setShortcut("Ctrl+B")
        act_toggle_sidebar.setCheckable(True)
        act_toggle_sidebar.setChecked(True)  # Default visible
        menu_sidebar.addAction(act_toggle_sidebar)

        act_toggle_sidebar_mode = QAction(tr("menu.view_sidebar_mode"), self)
        act_toggle_sidebar_mode.setShortcut("Ctrl+Alt+S")
        act_toggle_sidebar_mode.setToolTip("Toggle Sidebar between List and Tabs (Ctrl+Alt+S)")
        menu_sidebar.addAction(act_toggle_sidebar_mode)

        menu_view.addSeparator()

        # Layout submenu (UI/UX switching)
        menu_layout = menu_view.addMenu("Layout")
        menu_layout.setToolTip("Switch between different UI layouts")

        # Create action group for exclusive layout selection
        self.layout_action_group = QActionGroup(self)
        self.layout_action_group.setExclusive(True)

        # Get available layouts from manager and create menu actions
        available_layouts = self.layout_manager.get_available_layouts()
        for layout_id, layout_name in available_layouts.items():
            action = QAction(layout_name, self)
            action.setCheckable(True)
            action.setData(layout_id)

            # Set Current Layout as checked by default
            if layout_id == "current":
                action.setChecked(True)

            # Connect to layout switching handler
            action.triggered.connect(lambda checked, lid=layout_id: self._switch_layout(lid))

            self.layout_action_group.addAction(action)
            menu_layout.addAction(action)

        # ========== FILTERS MENU ==========
        menu_filters = menu_bar.addMenu("Filters")

        self.btn_all = QAction(tr("sidebar.all_photos"), self)
        self.btn_all.setCheckable(True)
        self.btn_all.setChecked(True)
        menu_filters.addAction(self.btn_all)

        self.btn_fav = QAction(tr("sidebar.favorites"), self)
        self.btn_fav.setCheckable(True)
        menu_filters.addAction(self.btn_fav)

        self.btn_faces = QAction(tr("sidebar.people"), self)
        self.btn_faces.setCheckable(True)
        menu_filters.addAction(self.btn_faces)

        # Group filter actions for exclusive selection
        self.filter_menu_group = QActionGroup(self)
        self.filter_menu_group.addAction(self.btn_all)
        self.filter_menu_group.addAction(self.btn_fav)
        self.filter_menu_group.addAction(self.btn_faces)

        # ========== TOOLS MENU ==========
        menu_tools = menu_bar.addMenu(tr("menu.tools"))

        act_scan_repo_tools = QAction(tr("menu.tools_scan_repo"), self)
        act_scan_repo_tools.setToolTip("Scan a directory to add photos to the current project")
        menu_tools.addAction(act_scan_repo_tools)

        menu_tools.addSeparator()

        # Metadata Backfill submenu
        menu_backfill = menu_tools.addMenu("Metadata Backfill")

        act_meta_start = menu_backfill.addAction("Start Background Backfill (Photos)")
        act_meta_single = menu_backfill.addAction("Run Foreground Backfill (Photos)")
        menu_backfill.addSeparator()
        act_video_backfill = menu_backfill.addAction("🎬 Video Metadata Backfill...")
        act_video_backfill.setToolTip("Re-extract metadata (dates, duration, resolution) for all videos")
        menu_backfill.addSeparator()
        act_meta_auto = menu_backfill.addAction("Auto-run after scan (Photos & Videos)")
        act_meta_auto.setCheckable(True)
        act_meta_auto.setChecked(self.settings.get("auto_run_backfill_after_scan", False))
        act_meta_auto.setToolTip("Automatically backfill metadata for both photos and videos after scanning")

        act_clear_cache = QAction(tr("menu.tools_clear_cache"), self)
        menu_tools.addAction(act_clear_cache)
        act_clear_cache.triggered.connect(self._on_clear_thumbnail_cache)

        menu_tools.addSeparator()

        # Database submenu (advanced operations)
        menu_db = menu_tools.addMenu(tr("menu.tools_database"))

        act_db_fresh = QAction(tr("menu.tools_db_fresh"), self)
        menu_db.addAction(act_db_fresh)

        act_db_check = QAction(tr("menu.tools_db_check"), self)
        menu_db.addAction(act_db_check)

        menu_db.addSeparator()

        act_db_rebuild_dates = QAction(tr("menu.tools_db_rebuild_dates"), self)
        menu_db.addAction(act_db_rebuild_dates)

        act_migrate = QAction(tr("menu.tools_db_migrate"), self)
        menu_db.addAction(act_migrate)

        act_optimize = QAction(tr("menu.tools_db_optimize"), self)
        menu_db.addAction(act_optimize)

        # ========== HELP MENU ==========
        menu_help = menu_bar.addMenu(tr("menu.help"))

        act_about = QAction(tr("menu.help_about"), self)
        menu_help.addAction(act_about)

        act_shortcuts = QAction(tr("menu.help_shortcuts"), self)
        act_shortcuts.setShortcut("F1")
        menu_help.addAction(act_shortcuts)

        menu_help.addSeparator()

        act_report_bug = QAction("Report Bug…", self)
        menu_help.addAction(act_report_bug)

        # ========== MENU ACTION CONNECTIONS ==========

        # File menu connections
        act_scan_repo_menu.triggered.connect(lambda: self._on_scan_repository() if hasattr(self, '_on_scan_repository') else None)

        # View menu connections
        act_zoom_in.triggered.connect(self._on_zoom_in)
        act_zoom_out.triggered.connect(self._on_zoom_out)

        act_grid_small_menu.triggered.connect(lambda: self._set_grid_preset("small"))
        act_grid_medium_menu.triggered.connect(lambda: self._set_grid_preset("medium"))
        act_grid_large_menu.triggered.connect(lambda: self._set_grid_preset("large"))
        act_grid_xl_menu.triggered.connect(lambda: self._set_grid_preset("xl"))

        act_sort_date.triggered.connect(lambda: self._apply_menu_sort("Date"))
        act_sort_filename.triggered.connect(lambda: self._apply_menu_sort("Filename"))
        act_sort_size.triggered.connect(lambda: self._apply_menu_sort("Size"))

        act_toggle_sidebar.toggled.connect(self._on_toggle_sidebar_visibility)
        # act_toggle_sidebar_mode connection happens later (line ~2430)

        # Filter menu connections
        self.btn_all.triggered.connect(lambda: self._apply_tag_filter("all"))
        self.btn_fav.triggered.connect(lambda: self._apply_tag_filter("favorite"))
        self.btn_faces.triggered.connect(lambda: self._apply_tag_filter("face"))

        # Tools menu connections
        act_scan_repo_tools.triggered.connect(lambda: self._on_scan_repository() if hasattr(self, '_on_scan_repository') else None)

        act_meta_start.triggered.connect(lambda: self.backfill_panel._on_start_background())
        act_meta_single.triggered.connect(lambda: self.backfill_panel._on_run_foreground())
        act_video_backfill.triggered.connect(self._on_video_backfill)
        act_meta_auto.toggled.connect(lambda v: self.settings.set("auto_run_backfill_after_scan", bool(v)))

        act_db_fresh.triggered.connect(self._db_fresh_start)
        act_db_check.triggered.connect(self._db_self_check)
        act_db_rebuild_dates.triggered.connect(self._db_rebuild_date_index)
        act_migrate.triggered.connect(self._run_date_migration)

        def _optimize_db():
            try:
                ReferenceDB().optimize_indexes()
                QMessageBox.information(self, tr('message_boxes.database_title'), tr('message_boxes.database_success_message'))
            except Exception as e:
                QMessageBox.critical(self, tr('message_boxes.database_error_title'), str(e))

        act_optimize.triggered.connect(_optimize_db)

        # Help menu connections
        act_about.triggered.connect(lambda: QMessageBox.information(self, "About", "MemoryMate PhotoFlow (Alpha)\n© 2025"))
        act_shortcuts.triggered.connect(self._show_keyboard_shortcuts)
        act_report_bug.triggered.connect(lambda: self._open_url("https://github.com/anthropics/memorymate-photoflow/issues"))    

        # 📂 Scan Repository Action
        act_scan_repo = tb.addAction(tr('toolbar.scan_repository'))
        # Phase 1: Promote Scan Repository with a primary button
        self.btn_scan_primary = QPushButton(tr('toolbar.scan_repository'))
        self.btn_scan_primary.setCursor(Qt.PointingHandCursor)
        self.btn_scan_primary.setStyleSheet("""
            QPushButton {
                background-color: #4A90E2;
                color: white;
                border: 1px solid #3A7BC8;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #357ABD;
            }
        """)
        self.btn_scan_primary.clicked.connect(self._on_scan_repository)
        tb.addWidget(self.btn_scan_primary)

        # Toggle action: show/hide the BackfillStatusPanel
        self.act_toggle_backfill = QAction(QIcon.fromTheme("view-sidebar"), tr('toolbar.backfill_panel'), self)
        self.act_toggle_backfill.setCheckable(True)
        
        # read persisted preference (fallback True)
        _visible_default = bool(self.settings.get("show_backfill_panel", True))
        
        self.act_toggle_backfill.setChecked(_visible_default)
        self.act_toggle_backfill.setToolTip("Show / hide Metadata Backfill status panel")
        
        tb.addAction(self.act_toggle_backfill)

        # Connect toggle signal to a handler that safely creates/shows/hides the panel and persists the choice
        self.act_toggle_backfill.toggled.connect(self._on_toggle_backfill_panel)

        # Ensure panel initial visibility matches saved preference (if panel already created)
        try:
            if hasattr(self, "backfill_panel") and self.backfill_panel is not None:
                self.backfill_panel.setVisible(_visible_default)
        except Exception:
            pass

        # 🛑 Cancel Scan button (programmatic cancel trigger)
        self.act_cancel_scan = ui.action(
            tr('toolbar.cancel_scan'),
            icon="process-stop",
            tooltip="Abort an ongoing repository scan immediately",
            handler=self._on_cancel_scan_clicked
        )
        self.act_cancel_scan.setEnabled(False)

        # Incremental vs full scan
        self.chk_incremental = ui.checkbox(tr('toolbar.incremental'), checked=True)
        ui.separator()

        # 🔍 Search Bar
        self.search_bar = SearchBarWidget(self)
        self.search_bar.searchTriggered.connect(self._on_quick_search)
        self.search_bar.advancedSearchRequested.connect(self._on_advanced_search)
        tb.addWidget(self.search_bar)
        ui.separator()

        # 🔽 Sorting and filtering controls
        self.sort_combo = ui.combo_sort(tr('toolbar.sort'), ["Filename", "Date", "Size"], self._apply_sort_filter)
        self.sort_order_combo = QSortComboBox()
        self.sort_order_combo.addItems([tr('toolbar.ascending'), tr('toolbar.descending')])
        self.sort_order_combo.currentIndexChanged.connect(lambda *_: self._apply_sort_filter())
        tb.addWidget(self.sort_order_combo)
        ui.separator()

        # Phase 2.3: Grid Size Presets (Google Photos style)
        # Quick resize buttons: Small / Medium / Large / XL
        tb.addWidget(QLabel(tr('toolbar.grid')))

        # Create button group for exclusive selection
        self.grid_size_group = QButtonGroup(self)

        # Small preset
        self.btn_grid_small = QPushButton("S")
        self.btn_grid_small.setFixedSize(28, 28)
        self.btn_grid_small.setCheckable(True)
        self.btn_grid_small.setToolTip("Small thumbnails (90px)")
        self.btn_grid_small.setStyleSheet("font-weight: bold;")
        self.btn_grid_small.clicked.connect(lambda: self._set_grid_preset("small"))
        self.grid_size_group.addButton(self.btn_grid_small, 0)
        tb.addWidget(self.btn_grid_small)

        # Medium preset
        self.btn_grid_medium = QPushButton("M")
        self.btn_grid_medium.setFixedSize(28, 28)
        self.btn_grid_medium.setCheckable(True)
        self.btn_grid_medium.setChecked(True)  # Default
        self.btn_grid_medium.setToolTip("Medium thumbnails (120px)")
        self.btn_grid_medium.setStyleSheet("font-weight: bold;")
        self.btn_grid_medium.clicked.connect(lambda: self._set_grid_preset("medium"))
        self.grid_size_group.addButton(self.btn_grid_medium, 1)
        tb.addWidget(self.btn_grid_medium)

        # Large preset
        self.btn_grid_large = QPushButton("L")
        self.btn_grid_large.setFixedSize(28, 28)
        self.btn_grid_large.setCheckable(True)
        self.btn_grid_large.setToolTip("Large thumbnails (200px)")
        self.btn_grid_large.setStyleSheet("font-weight: bold;")
        self.btn_grid_large.clicked.connect(lambda: self._set_grid_preset("large"))
        self.grid_size_group.addButton(self.btn_grid_large, 2)
        tb.addWidget(self.btn_grid_large)

        # XL preset
        self.btn_grid_xl = QPushButton("XL")
        self.btn_grid_xl.setFixedSize(32, 28)
        self.btn_grid_xl.setCheckable(True)
        self.btn_grid_xl.setToolTip("Extra large thumbnails (280px)")
        self.btn_grid_xl.setStyleSheet("font-weight: bold;")
        self.btn_grid_xl.clicked.connect(lambda: self._set_grid_preset("xl"))
        self.grid_size_group.addButton(self.btn_grid_xl, 3)
        tb.addWidget(self.btn_grid_xl)

        # --- Central container
        container = QWidget()
        self.setCentralWidget(container)
        main_layout = QVBoxLayout(container)

        # Phase 2.3: Removed huge BackfillStatusPanel (120-240px)
        # Replaced with compact indicator in top bar

        # --- Top bar (with breadcrumb navigation + compact backfill indicator)
        topbar = QWidget()
        top_layout = QHBoxLayout(topbar)
        top_layout.setContentsMargins(6, 6, 6, 6)

        # Phase 2 (High Impact): Breadcrumb Navigation replaces project dropdown
        self.breadcrumb_nav = BreadcrumbNavigation(self)
        top_layout.addWidget(self.breadcrumb_nav, 1)

        # Keep project data for backwards compatibility
        self._projects = list_projects()

        # Phase 2.3: Add compact backfill indicator (right-aligned)
        try:
            self.backfill_indicator = CompactBackfillIndicator(self)
            top_layout.addWidget(self.backfill_indicator)
            # Keep reference to old panel for compatibility with menu actions
            self.backfill_panel = self.backfill_indicator
        except Exception as e:
            print(f"[MainWindow] Could not create backfill indicator: {e}")

        main_layout.addWidget(topbar)

        # --- Main layout (Sidebar + Grid + Details)
        self.splitter = QSplitter(Qt.Horizontal)

        default_pid = get_default_project_id()
        if default_pid is None and self._projects:
            default_pid = self._projects[0]["id"]

        self.sidebar = SidebarQt(project_id=default_pid)
        

        # === Lazy wiring for sidebar actions (now sidebar exists) ===
        def _on_fold_toggle(checked):
            try:
                if hasattr(self, "sidebar") and self.sidebar:
                    self.sidebar.toggle_fold(bool(checked))
                self.settings.set("sidebar_folded", bool(checked))
            except Exception as e:
                print(f"[MainWindow] fold toggle failed: {e}")

        self.act_fold_unfold.toggled.connect(_on_fold_toggle)
        try:
            self.sidebar.toggle_fold(folded)
        except Exception:
            pass

        def _on_toggle_sidebar_mode():
            try:
                current = self.sidebar._effective_display_mode()
                new_mode = "tabs" if current == "list" else "list"
                self.sidebar.switch_display_mode(new_mode)
                self.settings.set("sidebar_mode", new_mode)
            except Exception as e:
                print(f"[MainWindow] toggle sidebar mode failed: {e}")

        act_toggle_sidebar_mode.triggered.connect(_on_toggle_sidebar_mode)

        # === Controllers ===
        self.scan_controller = ScanController(self)
        self.sidebar_controller = SidebarController(self)
        self.project_controller = ProjectController(self)

        self.sidebar.on_branch_selected = self.sidebar_controller.on_branch_selected
        self.sidebar.folderSelected.connect(self.sidebar_controller.on_folder_selected)
        # 🎬 Phase 4: Videos support
        if hasattr(self.sidebar, 'selectVideos'):
            self.sidebar.selectVideos.connect(self.sidebar_controller.on_videos_selected)

        self.splitter.addWidget(self.sidebar)

        # Phase 2.3: Grid container with selection toolbar
        self.grid_container = QWidget()
        grid_layout = QVBoxLayout(self.grid_container)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(4)

        # Chip filter bar
        chip_bar = QWidget()
        chip_layout = QHBoxLayout(chip_bar)
        chip_layout.setContentsMargins(8, 6, 8, 6)
        chip_layout.setSpacing(8)
        def make_chip(text, cb):
            b = QPushButton(text)
            b.setStyleSheet("QPushButton{border:1px solid #ccc; border-radius:14px; padding:4px 10px; background:#f7f7f7;} QPushButton:hover{background:#eaeaea;}")
            if cb: b.clicked.connect(cb)
            return b
        chip_layout.addWidget(make_chip(tr('toolbar.favorites'), lambda: self._apply_tag_filter("favorite")))
        chip_layout.addWidget(make_chip(tr('toolbar.people'), lambda: self._apply_tag_filter("face")))
        chip_layout.addWidget(make_chip(tr('toolbar.videos'), lambda: self.grid.set_context("videos", None)))
        chip_layout.addSpacing(12)
        chip_layout.addWidget(make_chip(tr('toolbar.today'), lambda: self.grid.set_context("date", "today")))
        chip_layout.addWidget(make_chip(tr('toolbar.this_week'), lambda: self.grid.set_context("date", "this-week")))
        chip_layout.addWidget(make_chip(tr('toolbar.this_month'), lambda: self.grid.set_context("date", "this-month")))
        chip_layout.addStretch()
        grid_layout.addWidget(chip_bar)

        # Selection toolbar (hidden by default, shows when items selected)
        self.selection_toolbar = SelectionToolbar(self)
        grid_layout.addWidget(self.selection_toolbar)

        # Thumbnail grid
        self.grid = ThumbnailGridQt(project_id=default_pid)
        grid_layout.addWidget(self.grid)

        # 🎬 Phase 4.4: Video player panel (hidden by default)
        self.video_player = VideoPlayerPanel(self)
        self.video_player.hide()
        self.video_player.closed.connect(self._on_video_player_closed)
        grid_layout.addWidget(self.video_player)

        self.splitter.addWidget(self.grid_container)

        # 🔗 Now that grid exists — connect toolbar actions safely
        act_select_all.triggered.connect(self.grid.list_view.selectAll)
        act_clear_sel.triggered.connect(self.grid.list_view.clearSelection)
        act_open.triggered.connect(lambda: self._open_lightbox_from_selection())
        act_delete.triggered.connect(lambda: self._request_delete_from_selection())

       # === Thumbnail Manager wiring ===
        self.thumb_cache = {}
        try:
            self.thumbnails = ThumbnailManager(
                grid=self.grid,
                cache=self.thumb_cache,
                log=getattr(self, "gui_log", None),
                initial_size=160
            )
        except Exception as e:
            print("[MainWindow] ⚠️ ThumbnailManager init failed:", e)
            self.thumbnails = None

        # Hook zoom slider to ThumbnailManager if available
        if hasattr(self.grid, "zoom_slider"):
            self.grid.zoom_slider.valueChanged.connect(
                lambda val: self.thumbnails.update_zoom(val) if self.thumbnails else None
            )

        # --- Details panel on the right
        self.details = DetailsPanel(self)
        self.splitter.addWidget(self.details)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)

        # Phase 3: Set initial splitter sizes for better usability
        # Sidebar: 250px, Grid: takes remaining, Details: 300px
        self.splitter.setSizes([250, 1000, 300])
        # Make splitter handle more visible and easier to grab
        self.splitter.setHandleWidth(3)

        main_layout.addWidget(self.splitter, 1)

        # --- Wire toolbar actions
        act_select_all.triggered.connect(self.grid.list_view.selectAll)
        act_clear_sel.triggered.connect(self.grid.list_view.clearSelection)
        act_open.triggered.connect(lambda: self._open_lightbox_from_selection())
        act_delete.triggered.connect(lambda: self._request_delete_from_selection())

        act_scan_repo.triggered.connect(self._on_scan_repository)

        self.sort_combo.currentIndexChanged.connect(lambda *_: self._apply_sort_filter())
        self.sort_order_combo.currentIndexChanged.connect(lambda *_: self._apply_sort_filter())

        # --- Grid signals
        # Phase 2.3: Use rich status bar instead of simple message
        self.grid.selectionChanged.connect(lambda n: self._update_status_bar(selection_count=n))
        self.grid.openRequested.connect(lambda p: self._open_lightbox(p))
        self.grid.deleteRequested.connect(lambda paths: self._confirm_delete(paths))
        # Phase 2.3: Update status bar when grid data is reloaded
        self.grid.gridReloaded.connect(lambda: self._update_status_bar())
        # Phase 2: Update breadcrumb navigation when grid changes
        self.grid.gridReloaded.connect(lambda: self._update_breadcrumb())
        # Phase 2.3: Update selection toolbar when selection changes
        self.grid.selectionChanged.connect(lambda n: self.selection_toolbar.update_selection(n))

        # --- Wire selection toolbar buttons
        self.selection_toolbar.btn_favorite.clicked.connect(self._toggle_favorite_selection)
        self.selection_toolbar.btn_delete.clicked.connect(self._request_delete_from_selection)
        self.selection_toolbar.btn_export.clicked.connect(self._export_selection_to_folder)
        self.selection_toolbar.btn_move.clicked.connect(self._move_selection_to_folder)
        self.selection_toolbar.btn_tag.clicked.connect(self._add_tag_to_selection)
        self.selection_toolbar.btn_clear.clicked.connect(self.grid.list_view.clearSelection)

        # --- Phase 8: Wire face grouping buttons (moved to grid toolbar)
        if hasattr(self.grid, "btn_detect_and_group"):
            self.grid.btn_detect_and_group.clicked.connect(self._on_detect_and_group_faces)
        if hasattr(self.grid, "btn_recluster"):
            self.grid.btn_recluster.clicked.connect(self._on_recluster_faces)

        # --- Auto-update details panel on selection change
        self._selection_tag_cache = {}
        self._details_update_timer = QTimer(self)
        self._details_update_timer.setSingleShot(True)
        def _update_details_from_selection():
            paths = self.grid.get_selected_paths()
            # 📜 ENHANCEMENT: Show placeholder when no selection or empty grid click
            if paths:
                try:
                    from services.tag_service import get_tag_service
                    svc = get_tag_service()
                    # Batch fetch tags for selection and cache
                    pid = self.grid.project_id
                    tag_map = svc.get_tags_for_paths(paths, pid) if pid is not None else {}
                    self._selection_tag_cache = tag_map or {}
                except Exception:
                    self._selection_tag_cache = {}
                self.details.update_path(paths[-1])
            else:
                # Clear and show elegant placeholder
                self.details.clear()
                self.details.thumb.setMinimumHeight(220)
                self.details.thumb.setToolTip('')
                self.details.thumb.setText("🖼️")
                self.details.thumb.setStyleSheet("""
                    QLabel {
                        color: #999;
                        font-size: 64px;
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                   stop:0 #f5f5f5, stop:1 #e8e8e8);
                        border: 2px dashed #ccc;
                        border-radius: 8px;
                    }
                """)
                self.details.meta.setText("""
                    <div style='text-align:center; padding:20px; color:#999;'>
                        <p style='font-size:14pt; font-weight:600;'>No Selection</p>
                        <p style='font-size:10pt;'>Select a photo or video to view details</p>
                    </div>
                """)
        self.grid.selectionChanged.connect(lambda *_: self._details_update_timer.start(100))
        self._details_update_timer.timeout.connect(_update_details_from_selection)
        
        # 🏷️ ENHANCEMENT: Refresh details panel when tags change
        # This ensures tag overlay updates in real-time
        if hasattr(self.grid, 'tagsChanged'):
            self.grid.tagsChanged.connect(lambda *_: _update_details_from_selection())
        
        # 📜 Initialize details panel with placeholder on startup
        QTimer.singleShot(100, _update_details_from_selection)
        
        # === Initialize periodic progress pollers (for detached workers) ===
        try:
            self.app_root = os.getcwd()  # base path for 'status/' folder
            status_dir = os.path.join(self.app_root, "status")

            # More defensive directory creation (fixes WinError 183 on Windows)
            if not os.path.exists(status_dir):
                os.makedirs(status_dir)
            elif not os.path.isdir(status_dir):
                raise ValueError(f"'status' exists but is not a directory: {status_dir}")

            self._init_progress_pollers()
        except Exception as e:
            print(f"[MainWindow] ⚠️ Progress pollers init failed: {e}")

        # Phase 2: Initialize breadcrumb navigation
        QTimer.singleShot(100, self._update_breadcrumb)

        # === Initialize default layout (UI/UX system) ===
        # Load user's preferred layout or default to "current"
        # This must happen after all UI components are created
        try:
            self.layout_manager.initialize_default_layout()
            print("[Startup] Layout system initialized successfully")
        except Exception as e:
            print(f"[Startup] ⚠️ Layout initialization failed: {e}")
            import traceback
            traceback.print_exc()

        # === Initialize database schema at startup ===
        try:
            from repository.base_repository import DatabaseConnection
            db_conn = DatabaseConnection("reference_data.db", auto_init=True)
            print("[Startup] Database schema initialized successfully")
        except Exception as e:
            print(f"[Startup] ⚠️ Database initialization failed: {e}")
            import traceback
            traceback.print_exc()


# =========================
    def _init_db_and_sidebar(self):
        """
        Initialize database schema, ensure created_* date fields, backfill if needed,
        optimize indexes, and reload the sidebar date tree.

        Runs on app startup to make sure the date navigation works immediately.
        """
        from reference_db import ReferenceDB
        self.db = ReferenceDB()

        # NOTE: Schema creation and migrations are now handled automatically
        # by repository layer during ReferenceDB initialization.
        # created_* columns are added via migration system (v1.5.0 migration).

        # 🕰 Backfill if needed (populate data in existing columns)
        try:
            updated_rows = self.db.single_pass_backfill_created_fields()
            if updated_rows:
                print(f"[DB] Backfilled {updated_rows} legacy rows with created_* fields.")
        except Exception as e:
            print(f"[DB] Backfill failed (possibly empty DB): {e}")

        # ⚡ Optimize indexes (important for large photo libraries)
        try:
            self.db.optimize_indexes()
        except Exception as e:
            print(f"[DB] optimize_indexes failed: {e}")

        # 🌳 Reload sidebar date tree
        try:
            self.sidebar.reload_date_tree()
            print("[Sidebar] Date tree reloaded.")
        except Exception as e:
            print(f"[Sidebar] Failed to reload date tree: {e}")
  
    # ============================================================
    # 🏷️ Tag filter handler
    # ============================================================
    def _apply_tag_filter(self, tag: str | None):
        """
        Apply or clear a tag filter without changing navigation context.
        """
        if not hasattr(self, "grid"):
            return

        if tag in (None, "", "all"):
            self.grid.apply_tag_filter(None)
            print("[TAG FILTER] Cleared.")
        else:
            self.grid.apply_tag_filter(tag)
            print(f"[TAG FILTER] Applied: {tag}")

        # Phase 2.3: Update rich status bar after filter change
        self._update_status_bar()


    def _clear_tag_filter(self):
        """Clear active tag overlay and restore previous grid navigation mode."""
        if getattr(self, "active_tag_filter", None):
            print("[TAG FILTER] Cleared by navigation.")
        self.active_tag_filter = None
        self.grid.active_tag_filter = None

        # ✅ Restore the last navigation mode and key
        prev_mode = getattr(self, "last_nav_mode", "branch")
        if self.grid.load_mode == "tag":
            self.grid.load_mode = prev_mode

            # Restore keys based on last mode
            if prev_mode == "branch":
                self.grid.branch_key = getattr(self, "last_nav_key", None)
            elif prev_mode == "folder":
                self.grid.current_folder_id = getattr(self, "last_nav_key", None)
            elif prev_mode == "date":
                self.grid.date_key = getattr(self, "last_nav_key", None)

        # Force refresh
        if hasattr(self.grid, "reload"):
            self.grid.reload()

    # ============================================================
    # 🔍 Search handlers
    # ============================================================
    def _on_quick_search(self, query: str):
        """Handle quick search from search bar."""
        try:
            from services import SearchService
            search_service = SearchService()
            paths = search_service.quick_search(query, limit=100)

            # Display results in grid
            if paths:
                self.grid.load_paths(paths)
                self.statusBar().showMessage(f"🔍 Found {len(paths)} photos matching '{query}'")
                print(f"[SEARCH] Quick search found {len(paths)} results for '{query}'")
            else:
                self.statusBar().showMessage(f"🔍 No photos found matching '{query}'")
                QMessageBox.information(self, tr('search.error_title'), tr('search.no_results').format(query=query))
        except Exception as e:
            logging.getLogger(__name__).error(f"Quick search failed: {e}")
            QMessageBox.critical(self, tr('search.error_title'), tr('search.error_message').format(error=e))

    def _on_advanced_search(self):
        """Show advanced search dialog."""
        try:
            dialog = AdvancedSearchDialog(self)
            if dialog.exec() == QDialog.Accepted:
                criteria = dialog.get_search_criteria()

                from services import SearchService
                search_service = SearchService()
                result = search_service.search(criteria)

                if result.paths:
                    self.grid.load_paths(result.paths)
                    self.statusBar().showMessage(
                        f"🔍 Found {result.filtered_count} photos in {result.execution_time_ms:.1f}ms"
                    )
                    print(f"[SEARCH] Advanced search found {result.filtered_count} results in {result.execution_time_ms:.1f}ms")
                else:
                    QMessageBox.information(self, tr('search.error_title'), tr('search.no_results_criteria'))
        except Exception as e:
            logging.getLogger(__name__).error(f"Advanced search failed: {e}")
            QMessageBox.critical(self, tr('search.error_title'), tr('search.error_message').format(error=e))


    def _on_video_backfill(self):
        """Open the video metadata backfill dialog."""
        try:
            # Get project_id from grid or sidebar
            project_id = None
            if hasattr(self, 'grid') and hasattr(self.grid, 'project_id'):
                project_id = self.grid.project_id
            elif hasattr(self, 'sidebar') and hasattr(self.sidebar, 'project_id'):
                project_id = self.sidebar.project_id

            # Fallback to default project if not found
            if project_id is None:
                from app_services import get_default_project_id
                project_id = get_default_project_id()

            if project_id is None:
                QMessageBox.warning(
                    self,
                    "No Project",
                    "No project is currently active.\n"
                    "Please create a project or scan a folder first."
                )
                return

            dialog = VideoBackfillDialog(self, project_id=project_id)
            result = dialog.exec()

            # If backfill completed successfully, refresh sidebar to update video counts
            if result == QDialog.Accepted and dialog.stats:
                if dialog.stats.get('updated', 0) > 0:
                    print(f"✓ Video backfill completed: {dialog.stats['updated']} videos updated")
                    # Refresh sidebar to show updated video date counts
                    if hasattr(self, 'sidebar') and hasattr(self.sidebar, 'refresh_sidebar'):
                        self.sidebar.refresh_sidebar()
                        print("✓ Sidebar refreshed with new video metadata")
        except Exception as e:
            QMessageBox.critical(
                self,
                "Video Backfill Error",
                f"Failed to open video backfill dialog:\n{str(e)}"
            )
            print(f"✗ Video backfill error: {e}")
            import traceback
            traceback.print_exc()

    def _on_clear_thumbnail_cache(self):
        if QMessageBox.question(
            self,
            "Clear Thumbnail Cache",
            "This will delete all generated thumbnail cache files.\n"
            "They will be rebuilt automatically as needed.\n\nProceed?",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            ok = clear_thumbnail_cache()
            if ok:
                QMessageBox.information(self, tr('message_boxes.cache_cleared_title'), tr('message_boxes.cache_cleared_message'))
            else:
                QMessageBox.warning(self, tr('message_boxes.cache_title'), tr('message_boxes.cache_not_found'))


    def _open_preferences(self):
        dlg = PreferencesDialog(self.settings, self)
        if dlg.exec() == QDialog.Accepted:
            # Apply live UI updates if needed
            if self.settings.get("dark_mode", False):
                self._apply_dark_mode()
            else:
                self._apply_light_mode()


    def _switch_layout(self, layout_id: str):
        """
        Switch to a different UI layout.

        Args:
            layout_id: ID of the layout to switch to (e.g., "current", "google", "apple")
        """
        try:
            success = self.layout_manager.switch_layout(layout_id)
            if success:
                print(f"[MainWindow] ✓ Switched to layout: {layout_id}")
            else:
                print(f"[MainWindow] ✗ Failed to switch to layout: {layout_id}")
                QMessageBox.warning(
                    self,
                    "Layout Switch Failed",
                    f"Could not switch to layout: {layout_id}"
                )
        except Exception as e:
            print(f"[MainWindow] ✗ Error switching layout: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(
                self,
                "Layout Error",
                f"An error occurred while switching layouts:\n{e}"
            )


    def _apply_dark_mode(self):
        """Switch the app palette to dark mode (safe for PySide6)."""
        app = QApplication.instance()
        dark = QPalette()
        dark.setColor(QPalette.Window, QColor(30, 30, 30))
        dark.setColor(QPalette.WindowText, Qt.white)
        dark.setColor(QPalette.Base, QColor(25, 25, 25))
        dark.setColor(QPalette.AlternateBase, QColor(35, 35, 35))
        dark.setColor(QPalette.ToolTipBase, Qt.white)
        dark.setColor(QPalette.ToolTipText, Qt.white)
        dark.setColor(QPalette.Text, Qt.white)
        dark.setColor(QPalette.Button, QColor(45, 45, 45))
        dark.setColor(QPalette.ButtonText, Qt.white)
        dark.setColor(QPalette.BrightText, Qt.red)
        dark.setColor(QPalette.Link, QColor(42, 130, 218))
        dark.setColor(QPalette.Highlight, QColor(42, 130, 218))
        dark.setColor(QPalette.HighlightedText, Qt.black)
        app.setPalette(dark)


    def _run_date_migration(self):
        """
        Manual, idempotent migration:
          1) Ensure created_* columns + indexes
          2) Backfill in chunks with progress dialog
        """
        # Step 1: Get database reference
        # NOTE: Schema columns are automatically created via migration system
        db = ReferenceDB()

        # Step 2: how much to do? (check for data to backfill)
        total = db.count_missing_created_fields()
        if total == 0:
            QMessageBox.information(self, tr('message_boxes.migration_title'), tr('message_boxes.migration_nothing'))
            return

        progress = QProgressDialog("Backfilling created_* fields…", "Cancel", 0, total, self)
        progress.setWindowTitle("Database Migration")
        progress.setWindowModality(Qt.WindowModal)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.show()

        processed = 0
        CHUNK = 1000
        while processed < total:
            if progress.wasCanceled():
                break
            n = db.single_pass_backfill_created_fields(CHUNK)
            if n <= 0:
                break
            processed += n
            progress.setValue(min(processed, total))
            QApplication.processEvents()

        progress.setValue(total)
        progress.close()
        # Optional: refresh sidebar, in case you already render date branches
        try:
            self.sidebar.reload()
        except Exception:
            pass
        QMessageBox.information(self, "Migration", f"Completed. Updated ~{processed} rows.")


    def _db_fresh_start(self):
        """
        Delete/backup the current DB file and recreate an empty schema.
        Then clear UI and let the user run a new scan.
        """
        ret = QMessageBox.warning(
            self,
            "Fresh Start (delete DB)",
            "This will erase the current database (a backup .bak_YYYYMMDD_HHMMSS will be created if possible).\n\n"
            "Are you sure you want to continue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if ret != QMessageBox.Yes:
            return

        try:
            # --- 🛑 Stop anything that might hold the DB ---
            if hasattr(self, "thumb_grid"):
                self.thumb_grid.shutdown_threads()  # stop background loaders

            if hasattr(self, "sidebar"):
                self.sidebar.db = None  # release ReferenceDB handle

            # --- 🧹 Reset DB ---
            db = ReferenceDB()
            db.fresh_reset()

            # --- 🧼 Clear UI ---
            if hasattr(self, "grid"):
                self.grid.clear()

            if hasattr(self, "sidebar"):
                # rebind fresh DB after reset
                self.sidebar.db = ReferenceDB()
                self.sidebar.reload()

            QMessageBox.information(
                self,
                "Database Reset",
                "✅ A fresh empty database was created.\n\nNow run: 📂 Scan Repository…"
            )

        except Exception as e:
            QMessageBox.critical(self, "Reset Failed", f"❌ {e}")


    def _db_self_check(self):
        """
        Run integrity PRAGMA and show basic counts to confirm a healthy scan.
        """
        try:
            db = ReferenceDB()
            rep = db.integrity_report()
            counts = rep.get("counts", {})
            ok = rep.get("ok", False)
            errors = rep.get("errors", [])
            msg = []
            msg.append("Integrity: " + ("OK ✅" if ok else "FAIL ❌"))
            msg.append("")
            msg.append("Counts:")
            msg.append(f"  • photo_folders:   {counts.get('photo_folders', 0)}")
            msg.append(f"  • photo_metadata:  {counts.get('photo_metadata', 0)}")
            msg.append(f"  • projects:        {counts.get('projects', 0)}")
            msg.append(f"  • branches:        {counts.get('branches', 0)}")
            msg.append(f"  • project_images:  {counts.get('project_images', 0)}")
            if errors:
                msg.append("")
                msg.append("Warnings/Errors:")
                for e in errors:
                    msg.append(f"  - {e}")
            QMessageBox.information(self, "DB Self-Check", "\n".join(msg))
        except Exception as e:
            QMessageBox.critical(self, "Self-Check Failed", str(e))


    def _db_rebuild_date_index(self):
        """
        Optional hook: if you implemented a date index builder (e.g., build_date_index_by_day),
        call it here. Otherwise, show a friendly message.
        """
        try:
            db = ReferenceDB()
            # If you already added: db.build_date_index_by_day()
            if hasattr(db, "build_date_index_by_day"):
                n = db.build_date_index_by_day()  # hypothetical return: rows added/updated
                QMessageBox.information(self, "Date Index", f"Date index rebuilt.\nUpdated rows: {n}")
            else:
                QMessageBox.information(
                    self, "Date Index",
                    "Date index not implemented yet in ReferenceDB.\n"
                    "You can safely ignore this or wire it later."
                )
        except Exception as e:
            QMessageBox.critical(self, "Date Index Failed", str(e))


    def _exif_to_dict(self, path: str) -> dict:
        """Read EXIF using PIL. Return a flat dict of tag_name -> value (best-effort)."""
        try:
            from PIL import Image, ExifTags
            with Image.open(path) as img:
                raw = img.getexif() or {}
                tagmap = {ExifTags.TAGS.get(k, k): raw.get(k) for k in raw.keys()}
                # Flatten MakerNote garbage
                if "MakerNote" in tagmap:
                    tagmap.pop("MakerNote", None)
                return tagmap
        except Exception:
            return {}

    def _fmt_rational(self, v):
        """Handle PIL rational/tuples (e.g., (1, 125)) → float or friendly str."""
        try:
            # fractions
            if hasattr(v, "numerator") and hasattr(v, "denominator"):
                return float(v.numerator) / float(v.denominator) if v.denominator else 0.0
            # (num, den) tuple
            if isinstance(v, (tuple, list)) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v):
                return float(v[0]) / float(v[1]) if v[1] else 0.0
            return v
        except Exception:
            return v

    def _parse_exif_exposure(self, exif: dict) -> dict:
        """Return prettified ISO / shutter / aperture / focal."""
        out = {}
        # ISO
        iso = exif.get("ISOSpeedRatings") or exif.get("PhotographicSensitivity")
        if isinstance(iso, (list, tuple)):
            iso = iso[0] if iso else None
        if iso:
            out["ISO"] = f"{iso}"
        # Shutter
        shutter = exif.get("ExposureTime")
        if shutter:
            r = self._fmt_rational(shutter)
            if isinstance(r, (int, float)) and r > 0:
                # pretty as 1/xxx for small values
                out["Shutter"] = f"1/{int(round(1 / r))}" if r < 1 else f"{r:.2f}s"
            else:
                out["Shutter"] = f"{shutter}"
        # Aperture
        fnum = exif.get("FNumber")
        if fnum:
            f = self._fmt_rational(fnum)
            out["Aperture"] = f"f/{f:.1f}" if isinstance(f, (int, float)) else f"f/{f}"
        # Focal length
        fl = exif.get("FocalLength")
        if fl:
            f = self._fmt_rational(fl)
            out["Focal Length"] = f"{f:.0f} mm" if isinstance(f, (int, float)) else f"{f} mm"
        return out

    def _gps_to_degrees(self, gps):
        """Convert GPS IFD to (lat, lon) in decimal degrees if possible."""
        try:
            def _conv(ref, vals):
                def _rat(x):
                    if hasattr(x, "numerator") and hasattr(x, "denominator"):
                        return float(x.numerator) / float(x.denominator) if x.denominator else 0.0
                    if isinstance(x, (tuple, list)) and len(x) == 2:
                        return float(x[0]) / float(x[1]) if x[1] else 0.0
                    return float(x)
                d, m, s = (_rat(vals[0]), _rat(vals[1]), _rat(vals[2]))
                deg = d + m/60.0 + s/3600.0
                if ref in ("S", "W"):
                    deg = -deg
                return deg

            lat = lon = None
            gps_lat = gps.get("GPSLatitude")
            gps_lat_ref = gps.get("GPSLatitudeRef")
            gps_lon = gps.get("GPSLongitude")
            gps_lon_ref = gps.get("GPSLongitudeRef")
            if gps_lat and gps_lat_ref and gps_lon and gps_lon_ref:
                lat = _conv(gps_lat_ref, gps_lat)
                lon = _conv(gps_lon_ref, gps_lon)
            return (lat, lon)
        except Exception:
            return (None, None)

    def _build_meta_table(self, rows: list[tuple[str, str]]) -> str:
        safe = []
        for k, v in rows:
            val = "-" if v is None or v == "" else str(v)
            safe.append(f"<tr><td><b>{k}</b></td><td>{val}</td></tr>")
        return "<table cellspacing='2' cellpadding='2'>" + "".join(safe) + "</table>"


    def _apply_light_mode(self):
        """Revert to the default (light) palette."""
        app = QApplication.instance()
        app.setPalette(QApplication.style().standardPalette())


    def _on_toggle_backfill_panel(self, visible: bool):
        """
        Handler for the toolbar toggle action. Ensures the BackfillStatusPanel exists,
        inserts it into the main layout if necessary, toggles visibility and persists the choice.
        """
        try:
            # Ensure we have a BackfillStatusPanel instance (lazy-create if necessary)
            if not hasattr(self, "backfill_panel") or self.backfill_panel is None:
                try:
                    # Try to create and insert at the top of the central layout
                    self.backfill_panel = BackfillStatusPanel(self)
                    # Insert at top if possible
                    try:
                        container = self.centralWidget()
                        if container is not None:
                            layout = container.layout()
                            if layout is not None:
                                layout.insertWidget(0, self.backfill_panel)
                    except Exception:
                        # If insertion fails, fallback to adding to layout end (best-effort)
                        try:
                            main_layout = getattr(self, "main_layout", None)
                            if main_layout is not None and hasattr(main_layout, "addWidget"):
                                main_layout.addWidget(self.backfill_panel)
                        except Exception:
                            pass
                except Exception as e:
                    print(f"[MainWindow] Failed to create BackfillStatusPanel dynamically: {e}")
                    return

            # Apply requested visibility
            try:
                self.backfill_panel.setVisible(bool(visible))
            except Exception as e:
                print(f"[MainWindow] Could not set BackfillStatusPanel visibility: {e}")

            # Persist the choice
            try:
                self.settings.set("show_backfill_panel", bool(visible))
            except Exception:
                pass

        except Exception as e:
            print(f"[MainWindow] _on_toggle_backfill_panel error: {e}")

    def _on_project_changed(self, idx: int):
        self.project_controller.on_project_changed(idx)

    def _on_project_changed_by_id(self, project_id: int):
        """
        Phase 2: Switch to a project by ID (used by breadcrumb navigation).
        Updates the sidebar and grid to show the selected project.
        """
        print(f"\n[MainWindow] ========== _on_project_changed_by_id({project_id}) STARTED ==========")
        try:
            # CRITICAL: Check if already on this project to prevent redundant reloads and crashes
            current_project_id = getattr(self.grid, 'project_id', None) if hasattr(self, 'grid') else None
            print(f"[MainWindow] Current project_id: {current_project_id}")
            
            if current_project_id == project_id:
                print(f"[MainWindow] Already on project {project_id}, skipping switch")
                return

            print(f"[MainWindow] Step 1: Updating grid.project_id...")
            # CRITICAL ORDER: Update grid FIRST before sidebar to prevent race condition
            # Sidebar.set_project() triggers callbacks that reload grid, so grid.project_id
            # must be set BEFORE those callbacks fire
            if hasattr(self, "grid") and self.grid:
                self.grid.project_id = project_id
                print(f"[MainWindow] Step 1: ✓ Set grid.project_id = {project_id}")
            else:
                print(f"[MainWindow] Step 1: ✗ Grid not available!")

            print(f"[MainWindow] Step 2: Updating sidebar...")
            # Now update sidebar (this triggers reload which will use the new grid.project_id)
            if hasattr(self, "sidebar") and self.sidebar:
                self.sidebar.set_project(project_id)
                print(f"[MainWindow] Step 2: ✓ Sidebar.set_project({project_id}) completed")
            else:
                print(f"[MainWindow] Step 2: ✗ Sidebar not available!")

            print(f"[MainWindow] Step 3: Reloading grid to 'all' branch...")
            # Finally, explicitly reload grid to show all photos
            if hasattr(self, "grid") and self.grid:
                self.grid.set_branch("all")  # Reset to show all photos
                print(f"[MainWindow] Step 3: ✓ Grid.set_branch('all') completed")
            else:
                print(f"[MainWindow] Step 3: ✗ Grid not available for set_branch!")

            # CRITICAL FIX: Removed duplicate breadcrumb update!
            # The gridReloaded signal (line 3392) already triggers _update_breadcrumb()
            # Scheduling a second update here causes a race condition crash!
            print(f"[MainWindow] Step 4: Breadcrumb will auto-update via gridReloaded signal")

            print(f"[MainWindow] Step 5: ✓✓✓ Switched to project ID: {project_id}")
            print(f"[MainWindow] ========== _on_project_changed_by_id({project_id}) COMPLETED ==========\n")
        except Exception as e:
            print(f"[MainWindow] ✗✗✗ ERROR switching project: {e}")
            import traceback
            traceback.print_exc()
            print(f"[MainWindow] ========== _on_project_changed_by_id({project_id}) FAILED ==========\n")

    def _refresh_project_list(self):
        """
        Phase 2: Refresh the project list (called after creating a new project).
        Updates the cached project list for breadcrumb navigation.
        """
        try:
            from app_services import list_projects
            self._projects = list_projects()
            print(f"[MainWindow] Refreshed project list: {len(self._projects)} projects")
        except Exception as e:
            print(f"[MainWindow] Error refreshing project list: {e}")

    def _on_folder_selected(self, folder_id: int):
        # DELEGATED to SidebarController (legacy stub kept for compatibility)
        self.sidebar_controller.on_folder_selected(folder_id)


    def _on_branch_selected(self, branch_key: str):
        # DELEGATED to SidebarController (legacy stub kept for compatibility)
        self.sidebar_controller.on_branch_selected(branch_key)


    def _on_scan_repository(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Photo Repository")
        if not folder:
            return
        incremental = self.chk_incremental.isChecked()
        self.scan_controller.start_scan(folder, incremental)

    # 👇 Optional: keep cancel button behavior simple
    def _on_cancel_scan_clicked(self):
        self.scan_controller.cancel()

    def _apply_sort_filter(self):
        """
        Apply sorting/filtering to the grid based on toolbar combo boxes.
        """
        sort_field = self.sort_combo.currentText().lower()
        descending = self.sort_order_combo.currentText() == "Descending"
        self.grid.apply_sorting(sort_field, descending)

        # Phase 2.3: Update rich status bar after sorting
        self._update_status_bar()

    def _set_grid_preset(self, size: str):
        """
        Phase 2.3: Set grid thumbnail size using preset (Google Photos style).
        Instantly resizes grid to Small (90px), Medium (120px), Large (200px), or XL (280px).

        Args:
            size: One of "small", "medium", "large", "xl"
        """
        if not hasattr(self, "grid") or not self.grid:
            return

        # Map presets to zoom factors
        # Formula: zoom_factor = target_height / _thumb_base (where _thumb_base = 120)
        presets = {
            "small": 0.75,    # 90px
            "medium": 1.0,    # 120px (default)
            "large": 1.67,    # 200px
            "xl": 2.33        # 280px
        }

        zoom_factor = presets.get(size, 1.0)

        # Apply zoom with animation
        if hasattr(self.grid, "_animate_zoom_to"):
            self.grid._animate_zoom_to(zoom_factor, duration=150)
        elif hasattr(self.grid, "_set_zoom_factor"):
            self.grid._set_zoom_factor(zoom_factor)

        print(f"[Grid Preset] Set to {size} (zoom: {zoom_factor})")

    # === Phase 3: Enhanced Menu Handlers ===

    def _on_zoom_in(self):
        """Phase 3: Zoom in (increase thumbnail size)."""
        if not hasattr(self, "grid") or not self.grid:
            return

        current_zoom = getattr(self.grid, "_zoom_factor", 1.0)
        new_zoom = min(current_zoom + 0.25, 3.0)  # Max zoom 3.0

        if hasattr(self.grid, "_animate_zoom_to"):
            self.grid._animate_zoom_to(new_zoom, duration=150)
        elif hasattr(self.grid, "_set_zoom_factor"):
            self.grid._set_zoom_factor(new_zoom)

        print(f"[Menu Zoom] Zoom In: {current_zoom:.2f} → {new_zoom:.2f}")

    def _on_zoom_out(self):
        """Phase 3: Zoom out (decrease thumbnail size)."""
        if not hasattr(self, "grid") or not self.grid:
            return

        current_zoom = getattr(self.grid, "_zoom_factor", 1.0)
        new_zoom = max(current_zoom - 0.25, 0.5)  # Min zoom 0.5

        if hasattr(self.grid, "_animate_zoom_to"):
            self.grid._animate_zoom_to(new_zoom, duration=150)
        elif hasattr(self.grid, "_set_zoom_factor"):
            self.grid._set_zoom_factor(new_zoom)

        print(f"[Menu Zoom] Zoom Out: {current_zoom:.2f} → {new_zoom:.2f}")

    def _apply_menu_sort(self, sort_type: str):
        """Phase 3: Apply sorting from View menu."""
        if not hasattr(self, "sort_combo"):
            return

        # Map menu sort type to combo box index
        sort_map = {
            "Filename": 0,
            "Date": 1,
            "Size": 2
        }

        index = sort_map.get(sort_type, 0)
        self.sort_combo.setCurrentIndex(index)
        self._apply_sort_filter()

        print(f"[Menu Sort] Applied: {sort_type}")

    def _on_toggle_sidebar_visibility(self, checked: bool):
        """Phase 3: Show/hide sidebar from View menu."""
        if hasattr(self, "sidebar") and self.sidebar:
            self.sidebar.setVisible(checked)
            print(f"[Menu Sidebar] Visibility: {checked}")

    def _show_keyboard_shortcuts(self):
        """Phase 3: Show keyboard shortcuts help dialog."""
        shortcuts_text = """
<h2>Keyboard Shortcuts</h2>

<h3>Navigation</h3>
<table>
<tr><td><b>Arrow Keys</b></td><td>Navigate grid</td></tr>
<tr><td><b>Space / Enter</b></td><td>Open lightbox</td></tr>
<tr><td><b>Escape</b></td><td>Clear selection / Close lightbox</td></tr>
</table>

<h3>Selection</h3>
<table>
<tr><td><b>Ctrl+Click</b></td><td>Toggle selection</td></tr>
<tr><td><b>Shift+Click</b></td><td>Range selection</td></tr>
<tr><td><b>Ctrl+A</b></td><td>Select all</td></tr>
</table>

<h3>View</h3>
<table>
<tr><td><b>Ctrl++</b></td><td>Zoom in</td></tr>
<tr><td><b>Ctrl+-</b></td><td>Zoom out</td></tr>
<tr><td><b>Ctrl+B</b></td><td>Toggle sidebar</td></tr>
<tr><td><b>Ctrl+Alt+S</b></td><td>Toggle sidebar mode (List/Tabs)</td></tr>
</table>

<h3>Actions</h3>
<table>
<tr><td><b>Ctrl+O</b></td><td>Scan repository</td></tr>
<tr><td><b>Ctrl+,</b></td><td>Preferences</td></tr>
<tr><td><b>F1</b></td><td>Show keyboard shortcuts</td></tr>
</table>
        """

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Keyboard Shortcuts")
        msg_box.setTextFormat(Qt.TextFormat.RichText)
        msg_box.setText(shortcuts_text)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

    def _open_url(self, url: str):
        """Phase 3: Open URL in default browser."""
        try:
            import webbrowser
            webbrowser.open(url)
            print(f"[Menu] Opened URL: {url}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not open URL:\n{url}\n\nError: {e}")

    def _open_lightbox_from_selection(self):
        """Open the last selected image in lightbox."""
        paths = self.grid.get_selected_paths()
        print(f"[MAIN_open_lightbox_from_selection] paths: {paths}")
        if paths:
            self._open_lightbox(paths[-1])

    def _toggle_favorite_selection(self):
        """
        Phase 2.3: Toggle favorite tag for all selected photos.
        Called from selection toolbar.
        """
        paths = self.grid.get_selected_paths()
        if not paths:
            return

        # Check if any photo is already favorited
        db = ReferenceDB()
        has_favorite = False
        for path in paths:
            tags = db.get_tags_for_paths([path], self.grid.project_id).get(path, [])
            if "favorite" in tags:
                has_favorite = True
                break

        # Toggle: if any is favorite, unfavorite all; otherwise favorite all
        if has_favorite:
            # Unfavorite all
            for path in paths:
                db.remove_tag(path, "favorite", self.grid.project_id)
            msg = f"Removed favorite from {len(paths)} photo(s)"
        else:
            # Favorite all
            for path in paths:
                db.add_tag(path, "favorite", self.grid.project_id)
            msg = f"Added {len(paths)} photo(s) to favorites"

        # Refresh grid to show updated tag icons
        if hasattr(self.grid, "_refresh_tags_for_paths"):
            self.grid._refresh_tags_for_paths(paths)
        if hasattr(self.grid, 'tagsChanged'):
            self.grid.tagsChanged.emit()

        self.statusBar().showMessage(msg, 3000)
        print(f"[Favorite] {msg}")

    def _add_tag_to_selection(self):
        """Prompt for a tag name and assign to selected photos."""
        paths = self.grid.get_selected_paths()
        if not paths:
            return
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Add Tag", "Tag name:")
        if ok and name.strip():
            try:
                from services.tag_service import get_tag_service
                svc = get_tag_service()
                svc.assign_tags_bulk(paths, name.strip(), self.grid.project_id)
                # Update grid tags overlay without full reload
                if hasattr(self.grid, '_refresh_tags_for_paths'):
                    self.grid._refresh_tags_for_paths(paths)
                if hasattr(self.grid, 'tagsChanged'):
                    self.grid.tagsChanged.emit()
                self.statusBar().showMessage(f"Tagged {len(paths)} photo(s) with '{name.strip()}'", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Tag Failed", str(e))

    def _export_selection_to_folder(self):
        """Export selected photos to a chosen folder (copies)."""
        paths = self.grid.get_selected_paths()
        if not paths:
            return
        folder = QFileDialog.getExistingDirectory(self, "Export to Folder")
        if not folder:
            return
        import shutil, os
        ok, fail = 0, 0
        for p in paths:
            try:
                shutil.copy2(p, os.path.join(folder, os.path.basename(p)))
                ok += 1
            except Exception:
                fail += 1
        self.statusBar().showMessage(f"Exported {ok}, failed {fail}", 5000)

    def _move_selection_to_folder(self):
        """Assign selected photos to a folder (by folder_id)."""
        paths = self.grid.get_selected_paths()
        if not paths:
            return
        from PySide6.QtWidgets import QInputDialog
        folder_id, ok = QInputDialog.getInt(self, "Move to Folder", "Folder ID:", 0, 0)
        if not ok:
            return
        try:
            db = ReferenceDB()
            for p in paths:
                db.set_folder_for_image(p, folder_id)
            self.grid.reload()
            self.statusBar().showMessage(f"Moved {len(paths)} photo(s) to folder {folder_id}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Move Failed", str(e))

    # ============================================================
    # Phase 8: Face Grouping Handlers (moved from People tab)
    # ============================================================

    def _on_detect_and_group_faces(self):
        """
        Launch automatic face grouping pipeline.

        Pipeline: Detection → Clustering → UI Refresh
        - Detection: Scans photos, detects faces, generates embeddings
        - Clustering: Groups similar faces using DBSCAN
        - Refresh: Auto-updates People tab with results

        User sees: Single button click → Automatic results ✅
        """
        try:
            from PySide6.QtCore import QThreadPool
            from PySide6.QtWidgets import QMessageBox, QProgressBar, QVBoxLayout, QDialog, QLabel, QPushButton
            from workers.face_detection_worker import FaceDetectionWorker
            from workers.face_cluster_worker import FaceClusterWorker

            # Get current project ID
            project_id = getattr(self.grid, "project_id", None)
            if not project_id:
                QMessageBox.warning(
                    self,
                    "No Project",
                    "Please select a project first."
                )
                return

            # Confirm action
            reply = QMessageBox.question(
                self,
                "Detect & Group Faces",
                f"This will automatically:\n"
                f"1. Detect faces in all photos\n"
                f"2. Group similar faces into person albums\n"
                f"3. Show results in the People tab\n\n"
                f"This may take 10-20 minutes for large photo collections.\n\n"
                f"Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply != QMessageBox.Yes:
                return

            print(f"[MainWindow] Launching automatic face grouping pipeline for project {project_id}")

            # Create progress dialog
            progress_dialog = QDialog(self)
            progress_dialog.setWindowTitle("Grouping Faces")
            progress_dialog.setModal(True)
            progress_dialog.setMinimumWidth(500)

            layout = QVBoxLayout()
            status_label = QLabel("Starting face detection...")
            progress_bar = QProgressBar()
            progress_bar.setRange(0, 100)
            progress_bar.setValue(0)

            cancel_btn = QPushButton("Cancel")
            cancel_btn.setStyleSheet("QPushButton{padding:5px 15px;}")

            layout.addWidget(status_label)
            layout.addWidget(progress_bar)
            layout.addWidget(cancel_btn)
            progress_dialog.setLayout(layout)

            # Worker references (for cancellation)
            current_detection_worker = None
            current_cluster_worker = None

            def cancel_pipeline():
                """Cancel the entire pipeline."""
                if current_detection_worker:
                    current_detection_worker.cancel()
                if current_cluster_worker:
                    current_cluster_worker.cancel()
                progress_dialog.close()
                print("[MainWindow] Face grouping pipeline cancelled by user")

            cancel_btn.clicked.connect(cancel_pipeline)

            # Step 1: Start detection worker
            detection_worker = FaceDetectionWorker(project_id=project_id)
            current_detection_worker = detection_worker

            def on_detection_progress(current, total, message):
                """Update progress during detection (0-50%)."""
                pct = int((current / total) * 50) if total > 0 else 0
                progress_bar.setValue(pct)
                status_label.setText(f"[1/2] {message}")
                print(f"[FaceDetection] [{current}/{total}] {message}")

            def on_detection_finished(success, failed, total_faces):
                """Detection complete → Auto-start clustering."""
                print(f"[FaceDetection] Complete: {success} photos, {total_faces} faces detected")

                if total_faces == 0:
                    progress_dialog.close()
                    QMessageBox.information(
                        self,
                        "No Faces Found",
                        f"No faces detected in {success} photos.\n\n"
                        f"Try photos with clear, front-facing faces for best results."
                    )
                    return

                # Step 2: Auto-start clustering worker
                nonlocal current_cluster_worker
                cluster_worker = FaceClusterWorker(project_id=project_id)
                current_cluster_worker = cluster_worker

                def on_cluster_progress(current, total, message):
                    """Update progress during clustering (50-100%)."""
                    pct = int(50 + (current / total) * 50) if total > 0 else 50
                    progress_bar.setValue(pct)
                    status_label.setText(f"[2/2] {message}")
                    print(f"[FaceCluster] {message}")

                def on_cluster_finished(cluster_count, total_clustered):
                    """Clustering complete → Auto-refresh UI."""
                    progress_dialog.close()
                    print(f"[FaceCluster] Complete: {cluster_count} person groups created")

                    # Refresh the sidebar to show new People clusters
                    if hasattr(self, "sidebar"):
                        self.sidebar.reload()

                    # Show success notification
                    QMessageBox.information(
                        self,
                        "Face Grouping Complete",
                        f"✅ Found {cluster_count} people in your photos!\n\n"
                        f"Grouped {total_clustered} faces from {success} photos.\n\n"
                        f"View results in the People section of the sidebar."
                    )

                def on_cluster_error(error_msg):
                    """Handle clustering errors."""
                    progress_dialog.close()
                    QMessageBox.warning(
                        self,
                        "Clustering Failed",
                        f"Face detection succeeded ({total_faces} faces found),\n"
                        f"but clustering failed:\n\n{error_msg}\n\n"
                        f"Try clicking 🔁 Re-Cluster to retry."
                    )

                cluster_worker.signals.progress.connect(on_cluster_progress)
                cluster_worker.signals.finished.connect(on_cluster_finished)
                cluster_worker.signals.error.connect(on_cluster_error)

                QThreadPool.globalInstance().start(cluster_worker)

            detection_worker.signals.progress.connect(on_detection_progress)
            detection_worker.signals.finished.connect(on_detection_finished)

            # Start detection worker
            QThreadPool.globalInstance().start(detection_worker)

            # Show progress dialog
            progress_dialog.show()

        except ImportError as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(
                self,
                "Missing Library",
                f"InsightFace library not installed.\n\n"
                f"Install with:\npip install insightface onnxruntime\n\n"
                f"Error: {e}"
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Face Grouping Failed", str(e))

    def _on_recluster_faces(self):
        """
        Manually re-run clustering on existing face detections.

        Use case: User wants to re-group faces without re-detecting
        (e.g., after adjusting clustering parameters, or if auto-clustering failed)
        """
        try:
            from PySide6.QtCore import QThreadPool
            from PySide6.QtWidgets import QMessageBox, QProgressDialog
            from workers.face_cluster_worker import FaceClusterWorker
            from reference_db import ReferenceDB

            # Get current project ID
            project_id = getattr(self.grid, "project_id", None)
            if not project_id:
                QMessageBox.warning(
                    self,
                    "No Project",
                    "Please select a project first."
                )
                return

            # Check if faces exist
            db = ReferenceDB()
            with db._connect() as conn:
                cur = conn.execute("SELECT COUNT(*) FROM face_crops WHERE project_id = ?", (project_id,))
                face_count = cur.fetchone()[0]

            if face_count == 0:
                QMessageBox.warning(
                    self,
                    "No Faces Detected",
                    "No faces have been detected yet.\n\n"
                    f"Click ⚡ Detect & Group Faces first to scan your photos."
                )
                return

            print(f"[MainWindow] Launching clustering worker for {face_count} detected faces")

            # Create progress dialog
            progress = QProgressDialog("Grouping faces...", "Cancel", 0, 100, self)
            progress.setWindowTitle("Re-Clustering Faces")
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setValue(0)

            # Create worker
            worker = FaceClusterWorker(project_id=project_id)

            def on_progress(current, total, message):
                progress.setLabelText(message)
                progress.setValue(current)
                print(f"[FaceCluster] {message}")

            def on_finished(cluster_count, total_faces):
                progress.close()
                print(f"[FaceCluster] Complete: {cluster_count} person groups created")

                # Refresh sidebar to show new clusters
                if hasattr(self, "sidebar"):
                    self.sidebar.reload()

                QMessageBox.information(
                    self,
                    "Clustering Complete",
                    f"✅ Grouped {total_faces} faces into {cluster_count} person albums.\n\n"
                    f"View results in the People section of the sidebar."
                )

            def on_error(error_msg):
                progress.close()
                QMessageBox.critical(
                    self,
                    "Clustering Failed",
                    f"Failed to cluster faces:\n\n{error_msg}"
                )

            def on_cancel():
                worker.cancel()

            worker.signals.progress.connect(on_progress)
            worker.signals.finished.connect(on_finished)
            worker.signals.error.connect(on_error)
            progress.canceled.connect(on_cancel)

            # Start worker
            QThreadPool.globalInstance().start(worker)

        except Exception as e:
            import traceback
            traceback.print_exc()
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Re-Cluster Failed", str(e))

    def _request_delete_from_selection(self):
        paths = []
        try:
            if hasattr(self, 'grid') and hasattr(self.grid, 'get_selected_paths'):
                paths = self.grid.get_selected_paths() or []
        except Exception:
            paths = []
        if not paths:
            return
        self._confirm_delete(paths)

    def _confirm_delete(self, paths: list[str]):
        """Delete photos from database (and optionally from disk)."""
        if not paths:
            return

        # Ask user about deletion scope
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Question)
        msg.setWindowTitle("Delete Photos")
        msg.setText(f"Delete {len(paths)} photo(s)?")
        msg.setInformativeText("Choose deletion scope:")

        # Add custom buttons
        db_only_btn = msg.addButton("Database Only", QMessageBox.ActionRole)
        db_and_files_btn = msg.addButton("Database && Files", QMessageBox.DestructiveRole)
        cancel_btn = msg.addButton(QMessageBox.Cancel)

        msg.setDefaultButton(db_only_btn)
        msg.exec()

        clicked = msg.clickedButton()

        if clicked == cancel_btn or clicked is None:
            return

        delete_files = (clicked == db_and_files_btn)

        # Import and use deletion service
        from services import PhotoDeletionService
        deletion_service = PhotoDeletionService()

        try:
            result = deletion_service.delete_photos(
                paths=paths,
                delete_files=delete_files,
                invalidate_cache=True
            )

            # Show result summary
            summary = f"Deleted {result.photos_deleted_from_db} photos from database"
            if delete_files:
                summary += f"\nDeleted {result.files_deleted_from_disk} files from disk"
                if result.files_not_found > 0:
                    summary += f"\n{result.files_not_found} files not found"

            if result.errors:
                summary += f"\n\nErrors:\n" + "\n".join(result.errors[:5])
                QMessageBox.warning(self, "Deletion Completed with Errors", summary)
            else:
                QMessageBox.information(self, "Deletion Successful", summary)

            # Reload grid to reflect changes
            self.grid.reload()

        except Exception as e:
            QMessageBox.critical(
                self,
                "Deletion Failed",
                f"Failed to delete photos: {e}"
            )

    def _open_lightbox(self, path: str):
        """
        Open the LightboxDialog for the clicked path, and pass the full list of
        paths based on the current navigation context (folder / branch / date).
        """
        if not path:
            return

        from reference_db import ReferenceDB
        db = ReferenceDB()

        # 1) Build the "context paths" in this priority:
        #    folder -> branch -> date -> visible paths -> just [path]
        paths = []
        context = "unknown"

        # Folder context
        folder_id = getattr(self.grid, "current_folder_id", None)
        print(f"[open_lightbox] self.grid={self.grid}")
        print(f"[open_lightbox] folder_id={folder_id}")
        if folder_id is not None:
            try:
                project_id = getattr(self.grid, "project_id", None)
                paths = db.get_images_by_folder(folder_id, project_id=project_id)
                context = f"folder({folder_id})"
                
            except Exception as e:
                print(f"[open_lightbox] folder fetch failed: {e}")
        
        
        # Branch context (if no folder result)
        print(f"[open_lightbox] paths={paths}")
        branch_key = getattr(self.grid, "branch_key", None)
        if not paths and branch_key:
            try:
                paths = db.get_images_by_branch(self.grid.project_id, branch_key)
                context = f"branch({branch_key})"
            except Exception as e:
                print(f"[open_lightbox] branch fetch failed: {e}")
        print(f"[open_lightbox] branch_key={branch_key}")
        
        # Date context (if no folder/branch result)
        date_key = getattr(self.grid, "date_key", None)
        if not paths and date_key:           
            try:
                if len(date_key) == 4 and date_key.isdigit():
                    paths = db.get_images_by_year(int(date_key))
                    context = f"year({date_key})"
                elif len(date_key) == 7 and date_key[4] == "-" and date_key[5:7].isdigit():
                    # format "YYYY-MM"
                    paths = db.get_images_by_month_str(date_key)
                    context = f"month({date_key})"
                elif len(date_key) == 10 and date_key[4] == "-" and date_key[7] == "-":
                    # format "YYYY-MM-DD"
                    # SURGICAL FIX C: Load both photos and videos for date nodes
                    paths = db.get_media_by_date(date_key, project_id=self.db_handler.project_id)
                    context = f"day({date_key})"
            except Exception as e:
                print(f"[open_lightbox] date fetch failed: {e}")
        print(f"[open_lightbox] date_key={date_key}")
        print(f"[open_lightbox] paths={paths}")
        
        # --- Fallback 1: what's visible on the grid right now?
        if not paths and hasattr(self.grid, "get_visible_paths"):
            try:
                paths = self.grid.get_visible_paths()
                context = "visible_paths"
            except Exception as e:
                print(f"[open_lightbox] get_visible_paths() failed: {e}")

        # --- Fallback 2: internal loaded model (even if view isn't built yet)
        if not paths and hasattr(self.grid, "get_all_paths"):
            try:
                paths = self.grid.get_all_paths()
                context = "all_paths"
            except Exception as e:
                print(f"[open_lightbox] get_all_paths() failed: {e}")

        # --- Final fallback: this single image only
        if not paths:
            paths = [path]
            context = "single"

        # Locate index of the clicked photo in `paths`
        try:
            idx = paths.index(path)
        except ValueError:
            # Different path normalization? try os.path.normcase/normpath
            try:
                norm = lambda p: os.path.normcase(os.path.normpath(p))
                idx = [norm(p) for p in paths].index(norm(path))
            except Exception:
                idx = 0

        print(f"[open_lightbox] context={context}, total={len(paths)}")
        print(f"[open_lightbox] paths={paths}")
        print(f"[open_lightbox] path={path}")

        # 🎬 UNIFIED MEDIA PREVIEW: Open LightboxDialog for BOTH photos AND videos
        # The LightboxDialog now handles both media types with adaptive controls
        print(f"[UnifiedPreview] Opening media in unified dialog: {path}")
        print(f"[UnifiedPreview] Media type: {'video' if is_video_file(path) else 'photo'}")

        # No filtering - pass ALL media paths (mixed photos and videos)
        # LightboxDialog will detect media type and show appropriate controls
        dlg = LightboxDialog(path, self)
        dlg.set_image_list(paths, idx)  # Pass full mixed media list
        dlg.resize(1200, 800)  # Larger default size for video viewing
        dlg.exec()

    def _open_video_player(self, video_path: str, video_list: list = None, start_index: int = 0):
        """
        Open video player for the given video path with navigation support.
        🎬 Phase 4.4: Video playback support
        🎬 Enhanced: Added video list and navigation support

        Args:
            video_path: Path to the video file
            video_list: List of video paths for navigation (optional)
            start_index: Index of current video in the list (optional)
        """
        if not video_path:
            return

        # Get video metadata from database
        metadata = None
        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()
            project_id = getattr(self.grid, 'project_id', None)
            if project_id:
                metadata = db.get_video_by_path(video_path, project_id)
        except Exception as e:
            print(f"[VideoPlayer] Failed to load metadata: {e}")

        # Hide grid, show video player
        self.grid.hide()
        self.video_player.show()

        # Load and play video with navigation support
        # BUG FIX #5: Pass project_id explicitly to support tagging
        self.video_player.load_video(video_path, metadata, project_id=project_id)

        # BUG FIX: Set video list for next/previous navigation
        if video_list:
            self.video_player.set_video_list(video_list, start_index)
            print(f"[VideoPlayer] Opened: {video_path} ({start_index+1}/{len(video_list)})")
        else:
            print(f"[VideoPlayer] Opened: {video_path}")

    def _on_video_player_closed(self):
        """
        Handle video player close event.
        🎬 Phase 4.4: Return to grid view when player closes
        """
        self.video_player.hide()
        self.grid.show()
        print("[VideoPlayer] Closed, returning to grid")

    def resizeEvent(self, event):
        """
        Clamp the main window to the primary screen available geometry so that layout
        changes (triggered by sidebar clicks or widget reflows) won't push parts of the
        window off-screen (bottom clipped).
        """
        try:
            super().resizeEvent(event)
        except Exception:
            pass

        try:
            avail = QGuiApplication.primaryScreen().availableGeometry()
            geo = self.geometry()
            tx = geo.x()
            ty = geo.y()
            tw = geo.width()
            th = geo.height()

            # Ensure window does not extend below the available bottom
            if geo.bottom() > avail.bottom():
                ty = max(avail.top(), avail.bottom() - th)
            # Ensure window does not extend above top
            if ty < avail.top():
                ty = avail.top()
            # Ensure window does not extend right of available area
            if geo.right() > avail.right():
                tx = max(avail.left(), avail.right() - tw)
            if tx < avail.left():
                tx = avail.left()

            # move if changed
            if (tx, ty) != (geo.x(), geo.y()):
                try:
                    self.move(tx, ty)
                except Exception:
                    pass
        except Exception:
            pass


    def closeEvent(self, event):
        """Ensure thumbnail threads and caches are closed before app exit."""
        try:
            if hasattr(self, "grid") and hasattr(self.grid, "shutdown_threads"):
                self.grid.shutdown_threads()
                print("[Shutdown] Grid threads shut down.")
        except Exception as e:
            print(f"[Shutdown] Grid thread error: {e}")

        try:
            if hasattr(self, "thumbnails") and hasattr(self.thumbnails, "shutdown_threads"):
                self.thumbnails.shutdown_threads()
                print("[Shutdown] ThumbnailManager threads shut down.")
        except Exception as e:
            print(f"[Shutdown] ThumbnailManager shutdown error: {e}")

        try:
            if hasattr(self, "thumb_cache"):
                self.thumb_cache.clear()
                print("[Shutdown] Thumbnail cache cleared.")
        except Exception as e:
            print(f"[Shutdown] Thumb cache clear error: {e}")

        super().closeEvent(event)

    def _update_breadcrumb(self):
        """
        Phase 2 (High Impact): Update breadcrumb navigation based on current grid state.
        Shows: Project > Folder/Date/Branch path
        """
        print(f"\n[Breadcrumb] _update_breadcrumb() CALLED")
        try:
            if not hasattr(self, "breadcrumb_nav") or not hasattr(self, "grid"):
                print(f"[Breadcrumb] Missing breadcrumb_nav or grid, aborting")
                return

            print(f"[Breadcrumb] Grid state: navigation_mode={getattr(self.grid, 'navigation_mode', 'None')}, project_id={getattr(self.grid, 'project_id', 'None')}")

            segments = []

            # CRITICAL FIX: Get CURRENT project name from grid.project_id, NOT default project!
            project_name = "My Photos"
            if hasattr(self, "_projects") and self._projects and hasattr(self.grid, 'project_id'):
                current_pid = self.grid.project_id  # ← Use ACTUAL current project, not default!
                print(f"[Breadcrumb] Looking for CURRENT project_id={current_pid} in {len(self._projects)} projects")
                for p in self._projects:
                    if p.get("id") == current_pid:
                        project_name = p.get("name", "My Photos")
                        print(f"[Breadcrumb] Found CURRENT project name: {project_name}")
                        break
                else:
                    # If current project not found in list (shouldn't happen), log warning
                    print(f"[Breadcrumb] ⚠️ WARNING: Current project_id={current_pid} not found in project list!")

            # Always start with project
            segments.append((project_name, None))  # No callback for current project
            print(f"[Breadcrumb] Added project segment: {project_name}")

            # Add navigation context
            if self.grid.navigation_mode == "folder" and hasattr(self.grid, "navigation_key"):
                # For folder mode, show folder path
                folder_id = self.grid.navigation_key
                # Get folder name from DB
                folder_name = f"Folder #{folder_id}"  # Fallback
                try:
                    with self.db._connect() as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT name FROM photo_folders WHERE id = ?", (folder_id,))
                        row = cur.fetchone()
                        if row:
                            folder_name = row[0]
                except Exception as e:
                    self.logger.warning(f"Failed to get folder name for ID {folder_id}: {e}")

                # CRITICAL FIX: Use functools.partial instead of lambda to avoid closure issues
                from functools import partial
                segments.append(("Folder View", partial(self.grid.set_branch, "all")))
                segments.append((folder_name, None))
                print(f"[Breadcrumb] Added folder segments: Folder View > {folder_name}")
            elif self.grid.navigation_mode == "date" and hasattr(self.grid, "navigation_key"):
                # For date mode, show date path
                date_key = str(self.grid.navigation_key)
                from functools import partial
                segments.append(("Timeline", partial(self.grid.set_branch, "all")))
                segments.append((date_key, None))
                print(f"[Breadcrumb] Added date segments: Timeline > {date_key}")
            elif self.grid.navigation_mode == "branch":
                # For branch mode, show "All Photos"
                segments.append(("All Photos", None))
                print(f"[Breadcrumb] Added branch segment: All Photos")
            elif hasattr(self.grid, "active_tag_filter") and self.grid.active_tag_filter:
                # Tag filter mode
                tag = self.grid.active_tag_filter
                from functools import partial
                segments.append(("Tags", partial(self._apply_tag_filter, "all")))
                if tag == "favorite":
                    segments.append(("Favorites", None))
                elif tag == "face":
                    segments.append(("Faces", None))
                else:
                    segments.append((tag, None))
                print(f"[Breadcrumb] Added tag segments: Tags > {tag}")
            else:
                segments.append(("All Photos", None))
                print(f"[Breadcrumb] Added fallback segment: All Photos")

            print(f"[Breadcrumb] Calling set_path() with {len(segments)} segments")
            self.breadcrumb_nav.set_path(segments)
            print(f"[Breadcrumb] set_path() completed successfully")
            print(f"[Breadcrumb] _update_breadcrumb() COMPLETED\n")
        except Exception as e:
            print(f"[Breadcrumb] ✗✗✗ ERROR in _update_breadcrumb(): {e}")
            import traceback
            traceback.print_exc()
            print(f"[Breadcrumb] _update_breadcrumb() FAILED\n")

    def _update_status_bar(self, selection_count=None):
        """
        Phase 2.3: Rich status bar with context-aware information.

        Shows: Total photos | Current view | Selection count | Zoom level | Filter status

        Similar to Google Photos / iPhone Photos status bars.
        """
        try:
            parts = []

            # 1. Total photo count
            if hasattr(self, "grid") and self.grid:
                total = self.grid.model.rowCount() if hasattr(self.grid, "model") else 0
                parts.append(f"📸 {total:,} photo{'' if total == 1 else 's'}")

            # 2. Current view/context
            current_view = None
            if hasattr(self, "grid") and self.grid:
                # Determine what's being shown
                if hasattr(self.grid, "navigation_mode") and self.grid.navigation_mode:
                    mode = self.grid.navigation_mode
                    if mode == "folder":
                        current_view = "Folder view"
                    elif mode == "date":
                        key = getattr(self.grid, "navigation_key", None)
                        current_view = f"📅 {key}" if key else "Date view"
                    elif mode == "branch":
                        current_view = "All Photos"
                elif hasattr(self.grid, "active_tag_filter") and self.grid.active_tag_filter:
                    tag = self.grid.active_tag_filter
                    if tag == "favorite":
                        current_view = "⭐ Favorites"
                    elif tag == "face":
                        current_view = "👥 Faces"
                    else:
                        current_view = f"🏷️ {tag}"
                else:
                    current_view = "All Photos"

            if current_view:
                parts.append(current_view)

            # 3. Selection count (only if > 0)
            if selection_count is not None and selection_count > 0:
                parts.append(f"Selected: {selection_count}")

            # 4. Zoom level (if grid has zoom info)
            if hasattr(self, "grid") and hasattr(self.grid, "thumb_height"):
                height = self.grid.thumb_height
                if height <= 100:
                    zoom = "Small"
                elif height <= 160:
                    zoom = "Medium"
                elif height <= 220:
                    zoom = "Large"
                else:
                    zoom = "XL"
                parts.append(f"Zoom: {zoom}")

            # Combine all parts with separator
            message = " • ".join(parts) if parts else "Ready"
            self.statusBar().showMessage(message)

        except Exception as e:
            print(f"[MainWindow] _update_status_bar error: {e}")
            # Fallback to simple message
            self.statusBar().showMessage(tr('status_messages.ready'))


    def _init_progress_pollers(self):
        self.cluster_timer = QTimer(self)
        self.cluster_timer.timeout.connect(self._poll_cluster_status)
        self.cluster_timer.start(2000)  # every 2 seconds

        self.backfill_timer = QTimer(self)
        self.backfill_timer.timeout.connect(self._poll_backfill_status)
        self.backfill_timer.start(2000)

    def _poll_cluster_status(self):
        path = os.path.join(self.app_root, "status", "cluster_status.json")
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            phase = data.get("phase")
            pct = data.get("percent", 0)
            
#            self.status_bar.showMessage(f"👥 Clustering {pct:.1f}% ({phase})")
            self.statusBar().showMessage(f"👥 Clustering {pct:.1f}% ({phase})")

            if phase == "done":
                self.statusBar().showMessage(tr('status_messages.clustering_complete'))
                os.remove(path)
        except Exception as e:
            print(f"[Status] cluster poll failed: {e}")

    def _poll_backfill_status(self):
        path = os.path.join(self.app_root, "status", "backfill_status.json")
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            pct = data.get("percent", 0)
            
#            self.status_bar.showMessage(f"📸 Backfill {pct:.1f}%")
            phase = data.get("phase", "")
            self.statusBar().showMessage(f"📸 Backfill {pct:.1f}% ({phase})")
#            self.statusBar().showMessage(f"👥 Clustering {pct:.1f}% ({phase})")

            if data.get("phase") == "done":
#                self.status_bar.showMessage("✅ Metadata backfill complete")
                self.statusBar().showMessage(tr('status_messages.backfill_complete'))                
                os.remove(path)
        except Exception as e:
            print(f"[Status] backfill poll failed: {e}")
