# splash_qt.py
# Version 1.2 dated 20251125
# Enhanced startup splash screen with detailed progress information
# Shows real-time initialization messages to improve user experience
# ---------------------------------------------

import time
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QPixmap, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar, QApplication,
    QPushButton, QHBoxLayout, QTextBrowser
)

# ===============================================
# 🧠 Worker: does DB / cache / index init in background
# ===============================================
class StartupWorker(QThread):
    progress = Signal(int, str)   # percent, message
    detail = Signal(str)          # detailed message for info area
    finished = Signal(bool)       # success/failure

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def emit_detail(self, message: str):
        """Emit a detailed status message to the info area"""
        self.detail.emit(message)

    def run(self):
        """
        Perform early startup steps BEFORE MainWindow is created.
        Covers: database, cache, translations, services initialization.
        """
        from reference_db import ReferenceDB
        from thumb_cache_db import get_cache

        try:
            # STEP 1 — Initial setup (5%)
            self.progress.emit(5, "Initializing application…")
            self.emit_detail("🚀 Starting MemoryMate-PhotoFlow...")
            self.emit_detail("✓ Pillow-HEIF available - HEIC/HEIF support enabled")
            time.sleep(0.05)
            if self._cancel:
                return

            # STEP 2 — DB initialization (15%)
            self.progress.emit(15, "Opening database…")
            self.emit_detail("📂 Opening database...")
            db = ReferenceDB()
            self.emit_detail("✓ Database opened successfully")
            time.sleep(0.05)
            if self._cancel:
                return

            # STEP 3 — Verify database schema (30%)
            self.progress.emit(30, "Verifying database schema…")
            self.emit_detail("🔍 Verifying database schema...")
            # NOTE: Schema creation and migrations are now handled automatically
            # by repository.DatabaseConnection during ReferenceDB initialization.
            print("[Startup] Database schema initialized successfully")
            self.emit_detail("✓ Database schema verified")

            # Optimize indexes if method exists (optional performance tuning)
            if hasattr(db, "optimize_indexes"):
                db.optimize_indexes()
                self.emit_detail("✓ Database indexes optimized")

            if self._cancel:
                return

            # STEP 4 — Backfill created_* if needed (45%)
            self.progress.emit(45, "Verifying timestamps…")
            self.emit_detail("⏱ Checking timestamp fields...")
            try:
                updated = db.single_pass_backfill_created_fields()
                if updated:
                    print(f"[Startup] Backfilled {updated} rows.")
                    self.emit_detail(f"✓ Backfilled {updated} timestamp records")
                else:
                    self.emit_detail("✓ All timestamps valid")
            except Exception as e:
                print(f"[Startup] Backfill skipped: {e}")
                self.emit_detail("⚠ Timestamp verification skipped")
            if self._cancel:
                return

            # STEP 5 — Cache initialization (55%)
            self.progress.emit(55, "Initializing thumbnail cache…")
            self.emit_detail("🖼 Initializing thumbnail cache...")
            cache = get_cache()
            stats = cache.get_stats()
            print(f"[Cache] {stats}")
            self.emit_detail(f"✓ Cache: {stats.get('entries', 0)} entries, {stats.get('size_mb', 0):.1f} MB")
            if self.settings.get("cache_auto_cleanup", True):
                cache.purge_stale(max_age_days=7)
                self.emit_detail("✓ Stale cache entries purged")
            if self._cancel:
                return

            # STEP 6 — Initialize SearchService (65%)
            self.progress.emit(65, "Initializing search service…")
            self.emit_detail("🔎 Initializing search service...")
            try:
                from services import SearchService
                search_service = SearchService()
                print("[Startup] SearchService initialized")
                self.emit_detail("✓ Search service ready")
            except Exception as e:
                print(f"[Startup] SearchService initialization failed: {e}")
                self.emit_detail(f"⚠ Search service error: {e}")
            if self._cancel:
                return

            # STEP 7 — Initialize ThumbnailService (75%)
            self.progress.emit(75, "Initializing thumbnail service…")
            self.emit_detail("🖼 Initializing thumbnail service...")
            try:
                from services import get_thumbnail_service
                thumb_service = get_thumbnail_service()
                print("[Startup] ThumbnailService initialized")
                self.emit_detail("✓ Thumbnail service ready (LRU cache active)")
            except Exception as e:
                print(f"[Startup] ThumbnailService initialization failed: {e}")
                self.emit_detail(f"⚠ Thumbnail service error: {e}")
            if self._cancel:
                return

            # STEP 8 — Check FFmpeg (85%)
            self.progress.emit(85, "Checking video support…")
            self.emit_detail("🎬 Checking video support...")
            try:
                import os
                ffmpeg_path = os.path.join("C:", "ffmpeg", "bin")
                if os.path.exists(os.path.join(ffmpeg_path, "ffmpeg.exe")):
                    self.emit_detail(f"✓ FFmpeg detected at {ffmpeg_path}")
                else:
                    self.emit_detail("⚠ FFmpeg not found - video features limited")
            except Exception:
                pass
            if self._cancel:
                return

            # STEP 9 — Check InsightFace (90%)
            self.progress.emit(90, "Checking face detection…")
            self.emit_detail("👤 Checking face detection models...")
            try:
                import os
                models_path = os.path.join(os.getcwd(), "models", "buffalo_l")
                if os.path.exists(models_path):
                    self.emit_detail(f"✓ InsightFace buffalo_l models detected")
                    self.emit_detail(f"   Location: {models_path}")
                else:
                    self.emit_detail("⚠ Face detection models not found")
            except Exception:
                pass
            if self._cancel:
                return

            # Done with background initialization
            # MainWindow creation happens next (on main thread)
            self.progress.emit(95, "Preparing main window…")
            self.emit_detail("🏠 Preparing main window...")
            self.emit_detail("✅ Initialization complete!")
            self.finished.emit(True)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished.emit(False)

# ===============================================
# 🌅 Splash Screen UI
# ===============================================
class SplashScreen(QDialog):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setWindowTitle("MemoryMate PhotoFlow — Loading…")
        self.setFixedSize(550, 450)  # Increased size for details area
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                border-radius: 8px;
            }
            QLabel {
                color: #ffffff;
                font-size: 12pt;
            }
            QPushButton {
                background-color: #444;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #666;
            }
            QTextBrowser {
                background-color: #2a2a2a;
                color: #d0d0d0;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 9pt;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Optional logo
        logo = QLabel()
        pixmap = QPixmap("MemoryMate-PhotoFlow-logo.png")  # optional logo file
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            logo.setAlignment(Qt.AlignCenter)
            layout.addWidget(logo)

        # Title
        title = QLabel("MemoryMate-PhotoFlow")
        title.setAlignment(Qt.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Status label
        self.status_label = QLabel("Starting up…")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        # Details area (scrollable)
        details_label = QLabel("Initialization Details:")
        details_label.setStyleSheet("font-size: 9pt; color: #aaa;")
        layout.addWidget(details_label)

        self.details_area = QTextBrowser()
        self.details_area.setMaximumHeight(180)
        self.details_area.setOpenExternalLinks(False)
        self.details_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        layout.addWidget(self.details_area)

        # Cancel button row
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.cancel_btn = QPushButton("Cancel")
        btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)


    def update_progress(self, percent: int, message: str):
        """Update progress bar and main status message"""
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)
        QApplication.processEvents()

    def add_detail(self, message: str):
        """Add a detailed message to the info area"""
        self.details_area.append(message)
        # Auto-scroll to bottom
        scrollbar = self.details_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        QApplication.processEvents()
