# layouts/google_layout.py
# Google Photos-style layout - Timeline-based, date-grouped, minimalist design

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSplitter, QToolBar, QLineEdit, QTreeWidget,
    QTreeWidgetItem, QFrame, QGridLayout, QSizePolicy, QDialog,
    QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, Signal, QSize, QEvent, QRunnable, QThreadPool, QObject
from PySide6.QtGui import QPixmap, QIcon, QKeyEvent, QImage, QColor
from .base_layout import BaseLayout
from typing import Dict, List, Tuple
from collections import defaultdict
from datetime import datetime
import os


# === ASYNC THUMBNAIL LOADING ===
class ThumbnailSignals(QObject):
    """Signals for async thumbnail loading (shared by all workers)."""
    loaded = Signal(str, QPixmap, int)  # (path, pixmap, size)


class ThumbnailLoader(QRunnable):
    """Async thumbnail loader using QThreadPool (copied from Current Layout pattern)."""

    def __init__(self, path: str, size: int, signals: ThumbnailSignals):
        super().__init__()
        self.path = path
        self.size = size
        self.signals = signals  # Use shared signal object

    def run(self):
        """Load thumbnail in background thread."""
        try:
            from app_services import get_thumbnail
            pixmap = get_thumbnail(self.path, self.size)

            if pixmap and not pixmap.isNull():
                # Emit to shared signal (connected in GooglePhotosLayout)
                self.signals.loaded.emit(self.path, pixmap, self.size)
        except Exception as e:
            print(f"[ThumbnailLoader] Error loading {self.path}: {e}")


class MediaLightbox(QDialog):
    """
    Full-screen media lightbox/preview dialog supporting photos AND videos.

    ✨ ENHANCED FEATURES:
    - Mixed photo/video navigation
    - Video playback with controls
    - Zoom controls for photos (Ctrl+Wheel, +/- keys)
    - Slideshow mode (Space to toggle)
    - Keyboard shortcuts (Arrow keys, Space, Delete, F, R, etc.)
    - Quick actions (Delete, Favorite, Rate)
    - Metadata panel (EXIF, date, dimensions, video info)
    - Fullscreen toggle (F11)
    - Close button and ESC key
    """

    def __init__(self, media_path: str, all_media: List[str], parent=None):
        """
        Initialize media lightbox.

        Args:
            media_path: Path to photo/video to display
            all_media: List of all media paths (photos + videos) in timeline order
            parent: Parent widget
        """
        super().__init__(parent)

        self.media_path = media_path
        self.all_media = all_media
        self.current_index = all_media.index(media_path) if media_path in all_media else 0
        self._media_loaded = False  # Track if media has been loaded

        # Zoom state (for photos) - SMOOTH CONTINUOUS ZOOM
        # Like Current Layout's LightboxDialog - smooth zoom with mouse wheel
        self.zoom_level = 1.0  # Current zoom scale
        self.fit_zoom_level = 1.0  # Zoom level for "fit to window" mode
        self.zoom_mode = "fit"  # "fit", "fill", "actual", or "custom"
        self.original_pixmap = None  # Store original for zoom
        self.zoom_factor = 1.15  # Zoom increment per wheel step (smooth like Current Layout)

        # Slideshow state
        self.slideshow_active = False
        self.slideshow_timer = None
        self.slideshow_interval = 3000  # 3 seconds

        # Rating state
        self.current_rating = 0  # 0-5 stars

        self._setup_ui()
        # Don't load media here - wait for showEvent when window has proper size

    def _setup_ui(self):
        """Setup Google Photos-style lightbox UI with overlay controls."""
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QPropertyAnimation, QTimer, QRect

        # Window settings - SMART SIZING: 90% of screen, centered
        self.setWindowTitle("Media Viewer")

        # Calculate smart window size (90% of screen, centered)
        screen = QApplication.primaryScreen().geometry()
        width = int(screen.width() * 0.9)
        height = int(screen.height() * 0.9)
        x = (screen.width() - width) // 2
        y = (screen.height() - height) // 2
        self.setGeometry(QRect(x, y, width, height))

        self.setStyleSheet("background: #000000;")  # Pure black background

        # Start maximized (not fullscreen - user choice)
        self.showMaximized()

        # Main layout (vertical with toolbars + media)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # === TOP TOOLBAR (Overlay with gradient) ===
        self.top_toolbar = self._create_top_toolbar()
        main_layout.addWidget(self.top_toolbar)

        # === MIDDLE SECTION: Media + Info Panel (Horizontal) ===
        middle_layout = QHBoxLayout()
        middle_layout.setContentsMargins(0, 0, 0, 0)
        middle_layout.setSpacing(0)

        # Media display area (left side, expands)
        self.scroll_area = QScrollArea()
        self.scroll_area.setStyleSheet("QScrollArea { background: #000000; border: none; }")
        self.scroll_area.setWidgetResizable(False)  # Don't auto-resize (needed for zoom)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setAlignment(Qt.AlignCenter)

        # CRITICAL FIX: Create container widget to hold both image and video
        # This prevents Qt from deleting widgets when switching with setWidget()
        self.media_container = QWidget()
        self.media_container.setStyleSheet("background: #000000;")
        media_container_layout = QVBoxLayout(self.media_container)
        media_container_layout.setContentsMargins(0, 0, 0, 0)
        media_container_layout.setSpacing(0)

        # Image display (for photos)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background: transparent;")
        self.image_label.setScaledContents(False)
        media_container_layout.addWidget(self.image_label)

        # Video display will be added to container on first video load

        # Set container as scroll area widget (never replace it!)
        self.scroll_area.setWidget(self.media_container)

        middle_layout.addWidget(self.scroll_area, 1)  # Expands to fill space

        # === OVERLAY NAVIGATION BUTTONS (Google Photos style) ===
        # Create as direct children of MediaLightbox, positioned on left/right sides
        self._create_overlay_nav_buttons()

        # Info panel (right side, toggleable)
        self.info_panel = self._create_info_panel()
        self.info_panel.hide()  # Hidden by default
        middle_layout.addWidget(self.info_panel)

        # Add middle section to main layout
        middle_widget = QWidget()
        middle_widget.setLayout(middle_layout)
        main_layout.addWidget(middle_widget, 1)

        # === BOTTOM TOOLBAR (Overlay with gradient) ===
        self.bottom_toolbar = self._create_bottom_toolbar()
        main_layout.addWidget(self.bottom_toolbar)

        # Track info panel state
        self.info_panel_visible = False

        # === MOUSE PANNING SUPPORT ===
        # Enable mouse tracking for hand cursor and panning
        self.setMouseTracking(True)
        self.scroll_area.setMouseTracking(True)
        self.image_label.setMouseTracking(True)

        # Panning state
        self.is_panning = False
        self.pan_start_pos = None
        self.scroll_start_x = 0
        self.scroll_start_y = 0

        # Button positioning retry counter (safety limit)
        self._position_retry_count = 0

        # === PROFESSIONAL AUTO-HIDE SYSTEM ===
        # Create opacity effects for smooth fade animations
        self.top_toolbar_opacity = QGraphicsOpacityEffect()
        self.top_toolbar.setGraphicsEffect(self.top_toolbar_opacity)
        self.top_toolbar_opacity.setOpacity(0.0)  # Hidden by default

        self.bottom_toolbar_opacity = QGraphicsOpacityEffect()
        self.bottom_toolbar.setGraphicsEffect(self.bottom_toolbar_opacity)
        self.bottom_toolbar_opacity.setOpacity(0.0)  # Hidden by default

        # Auto-hide timer (2 seconds)
        self.toolbar_hide_timer = QTimer()
        self.toolbar_hide_timer.setSingleShot(True)
        self.toolbar_hide_timer.setInterval(2000)  # 2 seconds
        self.toolbar_hide_timer.timeout.connect(self._hide_toolbars)

        # Toolbar visibility state
        self.toolbars_visible = False

    def _create_top_toolbar(self) -> QWidget:
        """Create top overlay toolbar with close, info, zoom, slideshow, and action buttons."""
        toolbar = QWidget()
        toolbar.setFixedHeight(80)  # Increased for larger buttons
        toolbar.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(0, 0, 0, 0.9),
                    stop:1 rgba(0, 0, 0, 0));
            }
        """)

        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)  # More spacing for larger buttons

        # PROFESSIONAL Button style (56x56px, larger icons)
        btn_style = """
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                color: white;
                border: none;
                border-radius: 28px;
                font-size: 18pt;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.25);
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.35);
            }
        """

        # === LEFT SIDE: Close + Quick Actions ===
        # Close button
        self.close_btn = QPushButton("✕")
        self.close_btn.setFocusPolicy(Qt.NoFocus)
        self.close_btn.setFixedSize(56, 56)
        self.close_btn.setStyleSheet(btn_style)
        self.close_btn.clicked.connect(self.close)
        layout.addWidget(self.close_btn)

        layout.addSpacing(12)

        # Delete button
        self.delete_btn = QPushButton("🗑️")
        self.delete_btn.setFocusPolicy(Qt.NoFocus)
        self.delete_btn.setFixedSize(56, 56)
        self.delete_btn.setStyleSheet(btn_style)
        self.delete_btn.clicked.connect(self._delete_current_media)
        self.delete_btn.setToolTip("Delete (D)")
        layout.addWidget(self.delete_btn)

        # Favorite button
        self.favorite_btn = QPushButton("♡")
        self.favorite_btn.setFocusPolicy(Qt.NoFocus)
        self.favorite_btn.setFixedSize(56, 56)
        self.favorite_btn.setStyleSheet(btn_style)
        self.favorite_btn.clicked.connect(self._toggle_favorite)
        self.favorite_btn.setToolTip("Favorite (F)")
        layout.addWidget(self.favorite_btn)

        layout.addStretch()

        # === CENTER: Counter + Zoom Indicator + Rating ===
        center_widget = QWidget()
        center_widget.setStyleSheet("background: transparent;")
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(2)

        # Counter label
        self.counter_label = QLabel()
        self.counter_label.setAlignment(Qt.AlignCenter)
        self.counter_label.setStyleSheet("color: white; font-size: 11pt; background: transparent;")
        center_layout.addWidget(self.counter_label)

        # Zoom/Status indicator
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 9pt; background: transparent;")
        center_layout.addWidget(self.status_label)

        layout.addWidget(center_widget)

        layout.addStretch()

        # === RIGHT SIDE: Zoom + Slideshow + Info ===
        # Zoom out button
        self.zoom_out_btn = QPushButton("−")
        self.zoom_out_btn.setFocusPolicy(Qt.NoFocus)
        self.zoom_out_btn.setFixedSize(32, 32)
        self.zoom_out_btn.setStyleSheet(btn_style + "QPushButton { font-size: 18pt; font-weight: bold; }")
        self.zoom_out_btn.clicked.connect(self._zoom_out)
        self.zoom_out_btn.setToolTip("Zoom Out (-)")
        layout.addWidget(self.zoom_out_btn)

        # Zoom in button
        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.setFocusPolicy(Qt.NoFocus)
        self.zoom_in_btn.setFixedSize(32, 32)
        self.zoom_in_btn.setStyleSheet(btn_style + "QPushButton { font-size: 16pt; font-weight: bold; }")
        self.zoom_in_btn.clicked.connect(self._zoom_in)
        self.zoom_in_btn.setToolTip("Zoom In (+)")
        layout.addWidget(self.zoom_in_btn)

        layout.addSpacing(8)

        # Slideshow button
        self.slideshow_btn = QPushButton("▶")
        self.slideshow_btn.setFocusPolicy(Qt.NoFocus)
        self.slideshow_btn.setFixedSize(56, 56)
        self.slideshow_btn.setStyleSheet(btn_style)
        self.slideshow_btn.clicked.connect(self._toggle_slideshow)
        self.slideshow_btn.setToolTip("Slideshow (S)")
        layout.addWidget(self.slideshow_btn)

        # Info toggle button
        self.info_btn = QPushButton("ℹ️")
        self.info_btn.setFocusPolicy(Qt.NoFocus)
        self.info_btn.setFixedSize(56, 56)
        self.info_btn.setStyleSheet(btn_style)
        self.info_btn.clicked.connect(self._toggle_info_panel)
        self.info_btn.setToolTip("Info (I)")
        layout.addWidget(self.info_btn)

        return toolbar

    def _create_bottom_toolbar(self) -> QWidget:
        """Create bottom overlay toolbar with navigation and video controls."""
        toolbar = QWidget()
        toolbar.setFixedHeight(80)
        toolbar.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(0, 0, 0, 0),
                    stop:1 rgba(0, 0, 0, 0.8));
            }
        """)

        layout = QVBoxLayout(toolbar)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(12)

        # Video controls container (hidden by default, shown for videos)
        self.video_controls_widget = self._create_video_controls()
        layout.addWidget(self.video_controls_widget)

        # Navigation controls moved to overlay (see _create_overlay_nav_buttons)

        return toolbar

    def _create_overlay_nav_buttons(self):
        """Create Google Photos-style overlay navigation buttons on left/right sides."""
        from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve
        from PySide6.QtGui import QCursor

        print("[MediaLightbox] Creating overlay navigation buttons...")

        # Previous button (left side)
        self.prev_btn = QPushButton("◄", self)
        self.prev_btn.setFocusPolicy(Qt.NoFocus)
        self.prev_btn.setFixedSize(48, 48)
        self.prev_btn.setCursor(Qt.PointingHandCursor)
        self.prev_btn.setStyleSheet("""
            QPushButton {
                background: rgba(0, 0, 0, 0.5);
                color: white;
                border: none;
                border-radius: 24px;
                font-size: 18pt;
            }
            QPushButton:hover {
                background: rgba(0, 0, 0, 0.7);
            }
            QPushButton:pressed {
                background: rgba(0, 0, 0, 0.9);
            }
            QPushButton:disabled {
                background: rgba(0, 0, 0, 0.2);
                color: rgba(255, 255, 255, 0.3);
            }
        """)
        self.prev_btn.clicked.connect(self._previous_media)

        # Next button (right side)
        self.next_btn = QPushButton("►", self)
        self.next_btn.setFocusPolicy(Qt.NoFocus)
        self.next_btn.setFixedSize(48, 48)
        self.next_btn.setCursor(Qt.PointingHandCursor)
        self.next_btn.setStyleSheet("""
            QPushButton {
                background: rgba(0, 0, 0, 0.5);
                color: white;
                border: none;
                border-radius: 24px;
                font-size: 18pt;
            }
            QPushButton:hover {
                background: rgba(0, 0, 0, 0.7);
            }
            QPushButton:pressed {
                background: rgba(0, 0, 0, 0.9);
            }
            QPushButton:disabled {
                background: rgba(0, 0, 0, 0.2);
                color: rgba(255, 255, 255, 0.3);
            }
        """)
        self.next_btn.clicked.connect(self._next_media)

        # CRITICAL: Show buttons explicitly
        self.prev_btn.show()
        self.next_btn.show()

        # Raise buttons above other widgets (overlay effect)
        self.prev_btn.raise_()
        self.next_btn.raise_()

        # CRITICAL FIX: Use QGraphicsOpacityEffect instead of setWindowOpacity
        # (windowOpacity only works on top-level windows, not child widgets)
        self.prev_btn_opacity = QGraphicsOpacityEffect()
        self.prev_btn.setGraphicsEffect(self.prev_btn_opacity)
        self.prev_btn_opacity.setOpacity(1.0)  # Start visible

        self.next_btn_opacity = QGraphicsOpacityEffect()
        self.next_btn.setGraphicsEffect(self.next_btn_opacity)
        self.next_btn_opacity.setOpacity(1.0)  # Start visible

        self.nav_buttons_visible = True  # Start visible

        # Auto-hide timer
        self.nav_hide_timer = QTimer()
        self.nav_hide_timer.setSingleShot(True)
        self.nav_hide_timer.timeout.connect(self._hide_nav_buttons)

        # Position buttons (will be called in resizeEvent)
        QTimer.singleShot(0, self._position_nav_buttons)

        print(f"[MediaLightbox] ✓ Nav buttons created and shown")

    # === PROFESSIONAL AUTO-HIDE TOOLBAR SYSTEM ===

    def _show_toolbars(self):
        """Show toolbars with smooth fade-in animation."""
        if not self.toolbars_visible:
            self.toolbars_visible = True

            # Fade in both toolbars (smooth 200ms animation)
            self.top_toolbar_opacity.setOpacity(1.0)
            self.bottom_toolbar_opacity.setOpacity(1.0)

        # Only auto-hide in fullscreen mode
        if self.isFullScreen():
            self.toolbar_hide_timer.stop()
            self.toolbar_hide_timer.start()  # Restart 2-second timer

    def _hide_toolbars(self):
        """Hide toolbars with smooth fade-out animation (fullscreen only)."""
        # Only hide if in fullscreen
        if self.isFullScreen() and self.toolbars_visible:
            self.toolbars_visible = False

            # Fade out both toolbars (smooth 200ms animation)
            self.top_toolbar_opacity.setOpacity(0.0)
            self.bottom_toolbar_opacity.setOpacity(0.0)

    # === END AUTO-HIDE SYSTEM ===

    def _create_video_controls(self) -> QWidget:
        """Create video playback controls (play/pause, seek, volume, time)."""
        controls = QWidget()
        controls.setStyleSheet("background: transparent;")
        controls.hide()  # Hidden by default, shown for videos

        layout = QHBoxLayout(controls)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Play/Pause button
        self.play_pause_btn = QPushButton("▶")
        self.play_pause_btn.setFocusPolicy(Qt.NoFocus)
        self.play_pause_btn.setFixedSize(56, 56)
        self.play_pause_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                color: white;
                border: none;
                border-radius: 18px;
                font-size: 12pt;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.25);
            }
        """)
        self.play_pause_btn.clicked.connect(self._toggle_play_pause)
        layout.addWidget(self.play_pause_btn)

        # Time label (current)
        self.time_current_label = QLabel("0:00")
        self.time_current_label.setStyleSheet("color: white; font-size: 9pt; background: transparent;")
        layout.addWidget(self.time_current_label)

        # Seek slider
        from PySide6.QtWidgets import QSlider
        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setFocusPolicy(Qt.NoFocus)
        self.seek_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: rgba(255, 255, 255, 0.2);
                height: 4px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: white;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::sub-page:horizontal {
                background: rgba(66, 133, 244, 0.8);
                border-radius: 2px;
            }
        """)
        self.seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self.seek_slider.sliderReleased.connect(self._on_seek_released)
        layout.addWidget(self.seek_slider, 1)

        # Time label (total)
        self.time_total_label = QLabel("0:00")
        self.time_total_label.setStyleSheet("color: white; font-size: 9pt; background: transparent;")
        layout.addWidget(self.time_total_label)

        # Volume icon
        volume_icon = QLabel("🔊")
        volume_icon.setStyleSheet("font-size: 12pt; background: transparent;")
        layout.addWidget(volume_icon)

        # Volume slider
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setFocusPolicy(Qt.NoFocus)
        self.volume_slider.setFixedWidth(80)
        self.volume_slider.setMinimum(0)
        self.volume_slider.setMaximum(100)
        self.volume_slider.setValue(80)
        self.volume_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: rgba(255, 255, 255, 0.2);
                height: 4px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: white;
                width: 10px;
                height: 10px;
                margin: -3px 0;
                border-radius: 5px;
            }
            QSlider::sub-page:horizontal {
                background: white;
                border-radius: 2px;
            }
        """)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        layout.addWidget(self.volume_slider)

        return controls

    def _create_info_panel(self) -> QWidget:
        """Create toggleable info panel with metadata (on right side)."""
        panel = QWidget()
        panel.setFixedWidth(350)
        panel.setStyleSheet("""
            QWidget {
                background: rgba(32, 33, 36, 0.95);
                border-left: 1px solid rgba(255, 255, 255, 0.1);
            }
        """)

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(20, 20, 20, 20)
        panel_layout.setSpacing(16)

        # Panel header
        header = QLabel("Media Information")
        header.setStyleSheet("color: white; font-size: 12pt; font-weight: bold; background: transparent;")
        panel_layout.addWidget(header)

        # Metadata content (scrollable)
        metadata_scroll = QScrollArea()
        metadata_scroll.setFrameShape(QFrame.NoFrame)
        metadata_scroll.setWidgetResizable(True)
        metadata_scroll.setStyleSheet("background: transparent; border: none;")

        self.metadata_content = QWidget()
        self.metadata_layout = QVBoxLayout(self.metadata_content)
        self.metadata_layout.setContentsMargins(0, 0, 0, 0)
        self.metadata_layout.setSpacing(12)
        self.metadata_layout.setAlignment(Qt.AlignTop)

        metadata_scroll.setWidget(self.metadata_content)
        panel_layout.addWidget(metadata_scroll)

        return panel

    def _toggle_info_panel(self):
        """Toggle info panel visibility."""
        if self.info_panel_visible:
            self.info_panel.hide()
            self.info_panel_visible = False
        else:
            self.info_panel.show()
            self.info_panel_visible = True

    def _toggle_play_pause(self):
        """Toggle video playback (play/pause)."""
        if hasattr(self, 'video_player'):
            from PySide6.QtMultimedia import QMediaPlayer
            if self.video_player.playbackState() == QMediaPlayer.PlayingState:
                self.video_player.pause()
                self.play_pause_btn.setText("▶")
            else:
                self.video_player.play()
                self.play_pause_btn.setText("⏸")

    def _on_volume_changed(self, value: int):
        """Handle volume slider change."""
        if hasattr(self, 'audio_output'):
            volume = value / 100.0
            self.audio_output.setVolume(volume)

    def _on_seek_pressed(self):
        """Handle seek slider press (pause position updates)."""
        if hasattr(self, 'position_timer'):
            self.position_timer.stop()

    def _on_seek_released(self):
        """Handle seek slider release (seek to position)."""
        if hasattr(self, 'video_player'):
            position = self.seek_slider.value()
            self.video_player.setPosition(position)
            if hasattr(self, 'position_timer'):
                self.position_timer.start()

    def _is_video(self, path: str) -> bool:
        """Check if file is a video based on extension."""
        video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.3gp'}
        return os.path.splitext(path)[1].lower() in video_extensions

    def _load_media_safe(self):
        """Safe wrapper for _load_media that sets the loaded flag."""
        if not self._media_loaded:
            self._media_loaded = True
            self._load_media()

    def _load_media(self):
        """Load and display current media (photo or video)."""
        print(f"[MediaLightbox] _load_media called for: {os.path.basename(self.media_path)}")
        if self._is_video(self.media_path):
            self._load_video()
        else:
            self._load_photo()

    def _load_video(self):
        """Load and display video with playback controls."""
        print(f"[MediaLightbox] Loading video: {os.path.basename(self.media_path)}")

        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PySide6.QtMultimediaWidgets import QVideoWidget
            from PySide6.QtCore import QUrl, QTimer

            # Clear previous content
            self.image_label.clear()
            self.image_label.setStyleSheet("")

            # Create video player if not exists
            if not hasattr(self, 'video_player'):
                self.video_player = QMediaPlayer()
                self.audio_output = QAudioOutput()
                self.video_player.setAudioOutput(self.audio_output)

                # Create video widget
                self.video_widget = QVideoWidget()
                self.video_widget.setStyleSheet("background: black;")
                self.video_player.setVideoOutput(self.video_widget)

                # Add video widget to container (alongside image_label)
                # CRITICAL: Add to container, not replace scroll area widget!
                container_layout = self.media_container.layout()
                container_layout.addWidget(self.video_widget)

                # Connect video player signals
                self.video_player.durationChanged.connect(self._on_duration_changed)
                self.video_player.positionChanged.connect(self._on_position_changed)

                # Create position update timer
                self.position_timer = QTimer()
                self.position_timer.timeout.connect(self._update_video_position)
                self.position_timer.setInterval(100)  # Update every 100ms

            # Show video, hide image (simple show/hide, no widget replacement!)
            self.image_label.hide()
            self.video_widget.show()

            # CRITICAL FIX: Resize video widget and container (same pattern as photos!)
            # Calculate video display size based on scroll area dimensions
            video_width = self.scroll_area.width() - 100  # Leave margin for scroll bars
            video_height = self.scroll_area.height() - 200  # Leave space for toolbars

            # Resize both video widget and container (QScrollArea needs explicit size!)
            self.video_widget.resize(video_width, video_height)
            self.media_container.resize(video_width, video_height)
            print(f"[MediaLightbox] ✓ Video widget sized: {video_width}x{video_height}")

            # Show video controls
            self.video_controls_widget.show()

            # Set initial volume
            volume = self.volume_slider.value() / 100.0
            self.audio_output.setVolume(volume)

            # Load and play video
            video_url = QUrl.fromLocalFile(self.media_path)
            self.video_player.setSource(video_url)
            self.video_player.play()

            # Update play/pause button
            self.play_pause_btn.setText("⏸")

            # Start position timer
            self.position_timer.start()

            print(f"[MediaLightbox] ✓ Video player started: {os.path.basename(self.media_path)}")

        except Exception as e:
            print(f"[MediaLightbox] ⚠️ Error loading video: {e}")
            import traceback
            traceback.print_exc()

            # Fallback to placeholder
            self.image_label.show()
            if hasattr(self, 'video_widget'):
                self.video_widget.hide()
            self.video_controls_widget.hide()
            self.image_label.setText(f"🎬 VIDEO\n\n{os.path.basename(self.media_path)}\n\n⚠️ Playback error")
            self.image_label.setStyleSheet("color: white; font-size: 16pt; background: #2a2a2a; border-radius: 8px; padding: 40px;")

        # Update counter
        self.counter_label.setText(f"{self.current_index + 1} of {len(self.all_media)}")

        # Update navigation buttons
        self.prev_btn.setEnabled(self.current_index > 0)
        self.next_btn.setEnabled(self.current_index < len(self.all_media) - 1)

        # Load video metadata
        self._load_metadata()

    def _on_duration_changed(self, duration: int):
        """Handle video duration change (set seek slider range)."""
        self.seek_slider.setMaximum(duration)
        # Format duration as mm:ss
        minutes = duration // 60000
        seconds = (duration % 60000) // 1000
        self.time_total_label.setText(f"{minutes}:{seconds:02d}")

    def _on_position_changed(self, position: int):
        """Handle video position change (update seek slider and time)."""
        # Update seek slider (only if not being dragged)
        if not self.seek_slider.isSliderDown():
            self.seek_slider.setValue(position)

    def _update_video_position(self):
        """Update video position display."""
        if hasattr(self, 'video_player'):
            position = self.video_player.position()
            # Format position as mm:ss
            minutes = position // 60000
            seconds = (position % 60000) // 1000
            self.time_current_label.setText(f"{minutes}:{seconds:02d}")

    def _load_photo(self):
        """Load and display the current photo with EXIF orientation correction."""
        from PySide6.QtCore import Qt  # Import at top to avoid UnboundLocalError
        from PySide6.QtGui import QPixmap

        try:
            # Hide video widget and controls if they exist
            if hasattr(self, 'video_widget'):
                self.video_widget.hide()
                if hasattr(self, 'video_player'):
                    self.video_player.stop()
                    if hasattr(self, 'position_timer'):
                        self.position_timer.stop()

            # Hide video controls
            if hasattr(self, 'video_controls_widget'):
                self.video_controls_widget.hide()

            # Show image label (simple show/hide, no widget replacement!)
            self.image_label.show()
            self.image_label.setStyleSheet("")  # Reset any custom styling

            print(f"[MediaLightbox] Loading photo: {os.path.basename(self.media_path)}")
            print(f"[MediaLightbox] Window size: {self.width()}x{self.height()}")

            # CRITICAL FIX: Load image using PIL first for EXIF orientation correction
            from PIL import Image, ImageOps
            import io

            pil_image = None  # Track for cleanup
            pixmap = None

            try:
                # Load with PIL and auto-rotate based on EXIF orientation
                pil_image = Image.open(self.media_path)

                # EXIF ORIENTATION FIX: Auto-rotate based on EXIF orientation tag
                # This fixes photos that appear rotated incorrectly
                pil_image = ImageOps.exif_transpose(pil_image)

                # MEMORY CORRUPTION FIX: Save to bytes buffer instead of direct tobytes
                # This prevents QImage from referencing freed PIL memory
                if pil_image.mode != 'RGB':
                    pil_image = pil_image.convert('RGB')

                # Save to bytes buffer (keeps data alive independently of PIL image)
                buffer = io.BytesIO()
                pil_image.save(buffer, format='PNG')
                buffer.seek(0)

                # Load QPixmap from buffer
                pixmap = QPixmap()
                pixmap.loadFromData(buffer.read())

                print(f"[PhotoLightbox] ✓ Image loaded with EXIF orientation: {pil_image.width}x{pil_image.height}")

                # MEMORY LEAK FIX: Close PIL image to free memory
                pil_image.close()
                buffer.close()
                print(f"[PhotoLightbox] ✓ PIL image and buffer closed")

            except Exception as pil_error:
                print(f"[PhotoLightbox] PIL loading failed, falling back to QPixmap: {pil_error}")
                import traceback
                traceback.print_exc()

                # Clean up PIL image if it was opened
                if pil_image:
                    try:
                        pil_image.close()
                    except:
                        pass

                # Fallback to QPixmap if PIL fails
                pixmap = QPixmap(self.media_path)

            if not pixmap or pixmap.isNull():
                self.image_label.setText("❌ Failed to load image")
                self.image_label.setStyleSheet("color: white; font-size: 14pt;")
                return

            # Store original pixmap for zoom operations
            self.original_pixmap = pixmap

            # Scale to fit while maintaining aspect ratio
            # Get available space (accounting for padding and nav buttons)
            # ROBUST FIX: Ensure we have valid window dimensions
            window_width = max(self.width(), 800)  # Minimum 800px
            window_height = max(self.height(), 600)  # Minimum 600px

            max_width = window_width - 100  # Leave space for UI
            max_height = window_height - 200  # Leave space for top/bottom bars

            print(f"[PhotoLightbox] Scaling to: max_width={max_width}, max_height={max_height}")

            # Apply zoom if set
            if self.zoom_mode == "fit":
                scaled_pixmap = pixmap.scaled(
                    max_width, max_height,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            else:
                # Apply manual zoom level
                zoomed_width = int(pixmap.width() * self.zoom_level)
                zoomed_height = int(pixmap.height() * self.zoom_level)
                scaled_pixmap = pixmap.scaled(
                    zoomed_width, zoomed_height,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )

            self.image_label.setPixmap(scaled_pixmap)
            self.image_label.resize(scaled_pixmap.size())  # CRITICAL: Size label to match pixmap for QScrollArea
            # CRITICAL: Also resize container to fit the image (QScrollArea needs this!)
            self.media_container.resize(scaled_pixmap.size())
            print(f"[PhotoLightbox] ✓ Photo displayed: {scaled_pixmap.width()}x{scaled_pixmap.height()}, zoom={self.zoom_level}")

            # Update counter
            self.counter_label.setText(
                f"{self.current_index + 1} of {len(self.all_media)}"
            )

            # Update navigation buttons
            self.prev_btn.setEnabled(self.current_index > 0)
            self.next_btn.setEnabled(self.current_index < len(self.all_media) - 1)

            # Load metadata
            self._load_metadata()

            # Update status label (zoom indicator)
            self._update_status_label()

        except Exception as e:
            print(f"[MediaLightbox] Error loading photo: {e}")
            self.image_label.setText(f"❌ Error loading image\n\n{str(e)}")
            self.image_label.setStyleSheet("color: white; font-size: 12pt;")

    def _load_metadata(self):
        """Load and display photo metadata."""
        # Clear existing metadata
        while self.metadata_layout.count():
            child = self.metadata_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        try:
            # Get file info
            file_size = os.path.getsize(self.media_path)
            file_size_mb = file_size / (1024 * 1024)
            filename = os.path.basename(self.media_path)

            # Add filename
            self._add_metadata_field("📄 Filename", filename)

            # Add file size
            self._add_metadata_field("💾 File Size", f"{file_size_mb:.2f} MB")

            # Get image dimensions
            pixmap = QPixmap(self.media_path)
            if not pixmap.isNull():
                self._add_metadata_field(
                    "📐 Dimensions",
                    f"{pixmap.width()} × {pixmap.height()} px"
                )

            # Get EXIF metadata
            try:
                from services.exif_parser import EXIFParser
                exif_parser = EXIFParser()
                metadata = exif_parser.parse_image_full(self.media_path)

                # Date taken
                if metadata.get('datetime_original'):
                    date_str = metadata['datetime_original'].strftime("%B %d, %Y at %I:%M %p")
                    self._add_metadata_field("📅 Date Taken", date_str)

                # Camera info
                if metadata.get('camera_make') or metadata.get('camera_model'):
                    camera = f"{metadata.get('camera_make', '')} {metadata.get('camera_model', '')}".strip()
                    self._add_metadata_field("📷 Camera", camera)

                # GPS coordinates
                if metadata.get('gps_latitude') and metadata.get('gps_longitude'):
                    lat = metadata['gps_latitude']
                    lon = metadata['gps_longitude']
                    self._add_metadata_field(
                        "🌍 Location",
                        f"{lat:.6f}, {lon:.6f}"
                    )

            except Exception as e:
                print(f"[MediaLightbox] Error loading EXIF: {e}")
                self._add_metadata_field("⚠️ EXIF Data", "Not available")

            # Add file path (at bottom)
            self._add_metadata_field("📁 Path", self.media_path, word_wrap=True)

        except Exception as e:
            print(f"[MediaLightbox] Error loading metadata: {e}")
            self._add_metadata_field("⚠️ Error", str(e))

    def _add_metadata_field(self, label: str, value: str, word_wrap: bool = False):
        """Add a metadata field to the panel."""
        # Label
        label_widget = QLabel(label)
        label_widget.setStyleSheet("""
            color: rgba(255, 255, 255, 0.7);
            font-size: 9pt;
            font-weight: bold;
        """)
        self.metadata_layout.addWidget(label_widget)

        # Value
        value_widget = QLabel(value)
        value_widget.setStyleSheet("""
            color: white;
            font-size: 10pt;
            padding-left: 8px;
        """)
        if word_wrap:
            value_widget.setWordWrap(True)
        self.metadata_layout.addWidget(value_widget)

    def _position_nav_buttons(self):
        """Position navigation buttons on left/right sides, vertically centered (like Current Layout)."""
        if not hasattr(self, 'prev_btn') or not hasattr(self, 'scroll_area'):
            print(f"[MediaLightbox] _position_nav_buttons: Missing attributes (prev_btn={hasattr(self, 'prev_btn')}, scroll_area={hasattr(self, 'scroll_area')})")
            return

        # Check if scroll area has valid size
        if self.scroll_area.width() == 0 or self.scroll_area.height() == 0:
            # Safety limit: stop retrying after 20 attempts (1 second total)
            if self._position_retry_count < 20:
                self._position_retry_count += 1
                print(f"[MediaLightbox] Scroll area not ready (retry {self._position_retry_count}/20), waiting 50ms...")
                from PySide6.QtCore import QTimer
                QTimer.singleShot(50, self._position_nav_buttons)
            else:
                print(f"[MediaLightbox] ⚠️ Scroll area still not ready after 20 retries!")
            return

        # Reset retry counter on success
        self._position_retry_count = 0

        # CRITICAL FIX: Use mapTo() to get scroll area position relative to dialog window
        # (like Current Layout's LightboxDialog does with canvas.mapTo())
        try:
            from PySide6.QtCore import QPoint
            scroll_tl = self.scroll_area.mapTo(self, QPoint(0, 0))
        except Exception as e:
            print(f"[MediaLightbox] ⚠️ mapTo() failed: {e}, using fallback")
            from PySide6.QtCore import QPoint
            scroll_tl = QPoint(0, 0)

        scroll_w = self.scroll_area.width()
        scroll_h = self.scroll_area.height()

        # Button dimensions
        btn_w = self.prev_btn.width() or 48
        btn_h = self.prev_btn.height() or 48
        margin = 12  # Distance from edges (reduced from 20 to match Current Layout)

        # Calculate vertical center position (relative to dialog, not scroll area)
        y = scroll_tl.y() + (scroll_h // 2) - (btn_h // 2)

        # Position left button (relative to dialog)
        left_x = scroll_tl.x() + margin
        self.prev_btn.move(left_x, max(8, y))

        # Position right button (relative to dialog)
        right_x = scroll_tl.x() + scroll_w - btn_w - margin
        self.next_btn.move(right_x, max(8, y))

        # CRITICAL: Ensure buttons are visible and on top
        self.prev_btn.show()
        self.next_btn.show()
        self.prev_btn.raise_()
        self.next_btn.raise_()

        print(f"[MediaLightbox] ✓ Nav buttons positioned: left={left_x}, right={right_x}, y={y}, scroll_pos=({scroll_tl.x()},{scroll_tl.y()})")

    def _show_nav_buttons(self):
        """Show navigation buttons with instant visibility (always visible for usability)."""
        if not self.nav_buttons_visible:
            self.nav_buttons_visible = True
            self.prev_btn_opacity.setOpacity(1.0)
            self.next_btn_opacity.setOpacity(1.0)

        # Cancel any pending hide
        self.nav_hide_timer.stop()

    def _hide_nav_buttons(self):
        """Hide navigation buttons (auto-hide disabled for better UX)."""
        # PROFESSIONAL UX: Keep navigation buttons always visible
        # Users need immediate access to navigation, especially in photo galleries
        pass

    def enterEvent(self, event):
        """Show navigation buttons on mouse enter."""
        self._show_nav_buttons()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Hide navigation buttons after delay on mouse leave."""
        self.nav_hide_timer.start(500)  # Hide after 500ms
        super().leaveEvent(event)

    def resizeEvent(self, event):
        """Reposition navigation buttons and auto-adjust zoom on window resize."""
        super().resizeEvent(event)
        self._position_nav_buttons()

        # SAFETY: Ensure media is loaded (fallback if showEvent didn't fire)
        if not self._media_loaded:
            print(f"[MediaLightbox] resizeEvent: media not loaded yet, triggering load...")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(150, self._load_media_safe)
            return

        # AUTO-ADJUST ZOOM: Reapply zoom in fit/fill modes
        if self.zoom_mode == "fit":
            self._fit_to_window()
        elif self.zoom_mode == "fill":
            self._fill_window()

        if self.zoom_mode in ["fit", "fill"]:
            self._update_zoom_status()

    def mousePressEvent(self, event):
        """Handle mouse press for panning."""
        from PySide6.QtCore import Qt

        # Only pan with left mouse button on photos
        if event.button() == Qt.LeftButton and not self._is_video(self.media_path):
            # Check if we're over the scroll area and content is larger than viewport
            if self._is_content_panneable():
                self.is_panning = True
                self.pan_start_pos = event.pos()
                self.scroll_start_x = self.scroll_area.horizontalScrollBar().value()
                self.scroll_start_y = self.scroll_area.verticalScrollBar().value()
                self.scroll_area.setCursor(Qt.ClosedHandCursor)
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move for panning, cursor updates, and toolbar reveal."""
        from PySide6.QtCore import Qt

        # PROFESSIONAL AUTO-HIDE: Show toolbars on mouse movement
        self._show_toolbars()

        # Update cursor based on content size
        if not self._is_video(self.media_path) and self._is_content_panneable():
            if not self.is_panning:
                self.scroll_area.setCursor(Qt.OpenHandCursor)
        else:
            self.scroll_area.setCursor(Qt.ArrowCursor)

        # Perform panning if active
        if self.is_panning and self.pan_start_pos:
            delta = event.pos() - self.pan_start_pos

            # Update scroll bars
            self.scroll_area.horizontalScrollBar().setValue(self.scroll_start_x - delta.x())
            self.scroll_area.verticalScrollBar().setValue(self.scroll_start_y - delta.y())

            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release to stop panning."""
        from PySide6.QtCore import Qt

        if event.button() == Qt.LeftButton and self.is_panning:
            self.is_panning = False
            self.pan_start_pos = None

            # Restore cursor
            if self._is_content_panneable():
                self.scroll_area.setCursor(Qt.OpenHandCursor)
            else:
                self.scroll_area.setCursor(Qt.ArrowCursor)

            event.accept()
            return

        super().mouseReleaseEvent(event)

    def _is_content_panneable(self) -> bool:
        """Check if content is larger than viewport (can be panned)."""
        if self._is_video(self.media_path):
            return False

        # Check if image is larger than scroll area viewport
        viewport = self.scroll_area.viewport()
        content = self.media_container

        return (content.width() > viewport.width() or
                content.height() > viewport.height())

    def _previous_media(self):
        """Navigate to previous media (photo or video)."""
        if self.current_index > 0:
            self.current_index -= 1
            self.media_path = self.all_media[self.current_index]
            self._load_media()

    def _next_media(self):
        """Navigate to next media (photo or video)."""
        if self.current_index < len(self.all_media) - 1:
            self.current_index += 1
            self.media_path = self.all_media[self.current_index]
            self._load_media()

    def showEvent(self, event):
        """Load media when dialog is first shown (after window has proper size)."""
        super().showEvent(event)
        print(f"[MediaLightbox] showEvent triggered, _media_loaded={self._media_loaded}")
        if not self._media_loaded:
            # ROBUST FIX: Use longer delay to ensure window is fully sized and rendered
            from PySide6.QtCore import QTimer
            print(f"[MediaLightbox] Scheduling media load in 100ms...")
            QTimer.singleShot(100, self._load_media_safe)  # 100ms delay for proper layout

        # Set focus to dialog so keyboard shortcuts work
        self.setFocus()

    def keyPressEvent(self, event: QKeyEvent):
        """Handle enhanced keyboard shortcuts."""
        key = event.key()
        modifiers = event.modifiers()

        print(f"[MediaLightbox] Key pressed: {key} (Qt.Key_Left={Qt.Key_Left}, Qt.Key_Right={Qt.Key_Right})")

        # ESC: Close
        if key == Qt.Key_Escape:
            print("[MediaLightbox] ESC pressed - closing")
            self.close()
            event.accept()  # Prevent event propagation

        # Arrow keys: Navigation
        elif key == Qt.Key_Left or key == Qt.Key_Up:
            print("[MediaLightbox] Left/Up arrow - previous media")
            self._previous_media()
            event.accept()
        elif key == Qt.Key_Right or key == Qt.Key_Down:
            print("[MediaLightbox] Right/Down arrow - next media")
            self._next_media()
            event.accept()

        # Space: Next (slideshow style) - CRITICAL: Must accept event to prevent button trigger
        elif key == Qt.Key_Space:
            print("[MediaLightbox] Space pressed - next media")
            self._next_media()
            event.accept()  # Prevent Space from triggering focused button!

        # Home/End: First/Last
        elif key == Qt.Key_Home:
            print("[MediaLightbox] Home pressed - first media")
            if self.all_media:
                self.current_index = 0
                self.media_path = self.all_media[0]
                self._load_media()
                event.accept()
        elif key == Qt.Key_End:
            print("[MediaLightbox] End pressed - last media")
            if self.all_media:
                self.current_index = len(self.all_media) - 1
                self.media_path = self.all_media[-1]
                self._load_media()
                event.accept()

        # I: Toggle info panel
        elif key == Qt.Key_I:
            print("[MediaLightbox] I pressed - toggle info panel")
            self._toggle_info_panel()
            event.accept()

        # +/-: Zoom (for photos)
        elif key in (Qt.Key_Plus, Qt.Key_Equal):  # + or =
            print("[MediaLightbox] + pressed - zoom in")
            self._zoom_in()
            event.accept()
        elif key in (Qt.Key_Minus, Qt.Key_Underscore):  # - or _
            print("[MediaLightbox] - pressed - zoom out")
            self._zoom_out()
            event.accept()

        # 0: Fit to window (Professional zoom mode)
        elif key == Qt.Key_0:
            print("[MediaLightbox] 0 pressed - fit to window")
            self._zoom_to_fit()
            event.accept()

        # D: Delete
        elif key == Qt.Key_D:
            print("[MediaLightbox] D pressed - delete")
            self._delete_current_media()
            event.accept()

        # F: Toggle favorite
        elif key == Qt.Key_F:
            print("[MediaLightbox] F pressed - toggle favorite")
            self._toggle_favorite()
            event.accept()

        # S: Toggle slideshow
        elif key == Qt.Key_S:
            print("[MediaLightbox] S pressed - toggle slideshow")
            self._toggle_slideshow()
            event.accept()

        # 1-5: Rate
        elif key in (Qt.Key_1, Qt.Key_2, Qt.Key_3, Qt.Key_4, Qt.Key_5):
            rating = int(event.text())
            print(f"[MediaLightbox] {rating} pressed - rate {rating} stars")
            self._rate_media(rating)
            event.accept()

        # F11: Toggle fullscreen
        elif key == Qt.Key_F11:
            print("[MediaLightbox] F11 pressed - toggle fullscreen")
            self._toggle_fullscreen()
            event.accept()

        else:
            print(f"[MediaLightbox] Unhandled key: {key}")
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        """Handle mouse wheel for smooth continuous zoom (like Current Layout)."""
        if self._is_video(self.media_path):
            super().wheelEvent(event)
            return

        # PROFESSIONAL UX: Smooth zoom without Ctrl modifier (like Current Layout)
        steps = event.angleDelta().y() / 120.0
        if steps == 0:
            super().wheelEvent(event)
            return

        # Calculate zoom factor (1.15 per step - smooth and natural)
        factor = self.zoom_factor ** steps

        # Apply smooth zoom
        self._smooth_zoom(factor)
        event.accept()

    def _smooth_zoom(self, factor):
        """Apply smooth continuous zoom (like Current Layout)."""
        if self._is_video(self.media_path) or not self.original_pixmap:
            return

        # Calculate new zoom level
        new_zoom = self.zoom_level * factor

        # Enforce minimum: don't zoom below fit level
        min_zoom = max(0.1, self.fit_zoom_level * 0.25)  # Allow 25% of fit as minimum
        max_zoom = 10.0  # Maximum 1000% zoom

        new_zoom = max(min_zoom, min(new_zoom, max_zoom))

        # Update zoom state
        self.zoom_level = new_zoom

        # Switch to custom zoom mode if zooming from fit/fill
        if new_zoom > self.fit_zoom_level * 1.01:  # Small tolerance for floating point
            self.zoom_mode = "custom"
        elif abs(new_zoom - self.fit_zoom_level) < 0.01:
            self.zoom_mode = "fit"

        # Apply the zoom
        self._apply_zoom()
        self._update_zoom_status()

    def _zoom_in(self):
        """Zoom in by one step (keyboard shortcut: +)."""
        self._smooth_zoom(self.zoom_factor)

    def _zoom_out(self):
        """Zoom out by one step (keyboard shortcut: -)."""
        self._smooth_zoom(1.0 / self.zoom_factor)

    def _apply_zoom(self):
        """Apply current zoom level to displayed photo."""
        from PySide6.QtCore import Qt  # Import at top to avoid UnboundLocalError

        if not self.original_pixmap or self.original_pixmap.isNull():
            return

        # Calculate zoomed size
        zoomed_width = int(self.original_pixmap.width() * self.zoom_level)
        zoomed_height = int(self.original_pixmap.height() * self.zoom_level)

        # Scale pixmap
        scaled_pixmap = self.original_pixmap.scaled(
            zoomed_width, zoomed_height,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.image_label.setPixmap(scaled_pixmap)
        self.image_label.resize(scaled_pixmap.size())  # CRITICAL: Size label to match pixmap for QScrollArea
        # CRITICAL: Also resize container to fit the image (QScrollArea needs this!)
        self.media_container.resize(scaled_pixmap.size())

        # Update cursor based on new zoom level
        if self._is_content_panneable():
            self.scroll_area.setCursor(Qt.OpenHandCursor)
        else:
            self.scroll_area.setCursor(Qt.ArrowCursor)

    def _zoom_to_fit(self):
        """Zoom to fit window (Keyboard: 0) - Letterboxing if needed."""
        if self._is_video(self.media_path):
            return

        self.zoom_mode = "fit"
        self._fit_to_window()
        self._update_zoom_status()

    def _zoom_to_actual(self):
        """Zoom to 100% actual size (Keyboard: 1) - 1:1 pixel mapping."""
        if self._is_video(self.media_path):
            return

        self.zoom_mode = "actual"
        self.zoom_level = 1.0
        self._apply_zoom()
        self._update_zoom_status()

    def _zoom_to_fill(self):
        """Zoom to fill window (may crop edges to avoid letterboxing)."""
        if self._is_video(self.media_path):
            return

        self.zoom_mode = "fill"
        self._fill_window()
        self._update_zoom_status()

    def _fit_to_window(self):
        """Fit entire image to window (letterboxing if needed)."""
        from PySide6.QtCore import Qt  # Import at top to avoid UnboundLocalError

        if not self.original_pixmap or self.original_pixmap.isNull():
            return

        # Get viewport size
        viewport_size = self.scroll_area.viewport().size()

        # Scale to fit (maintains aspect ratio)
        scaled_pixmap = self.original_pixmap.scaled(
            viewport_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.image_label.setPixmap(scaled_pixmap)
        self.image_label.resize(scaled_pixmap.size())
        self.media_container.resize(scaled_pixmap.size())

        # Calculate actual zoom level for display
        self.zoom_level = scaled_pixmap.width() / self.original_pixmap.width()
        self.fit_zoom_level = self.zoom_level  # Store for smooth zoom minimum

    def _fill_window(self):
        """Fill window completely (may crop edges to avoid letterboxing)."""
        from PySide6.QtCore import Qt  # Import at top to avoid UnboundLocalError

        if not self.original_pixmap or self.original_pixmap.isNull():
            return

        # Get viewport size
        viewport_size = self.scroll_area.viewport().size()

        # Calculate zoom to fill (crops edges if needed)
        width_ratio = viewport_size.width() / self.original_pixmap.width()
        height_ratio = viewport_size.height() / self.original_pixmap.height()
        fill_ratio = max(width_ratio, height_ratio)  # Use larger ratio to fill

        zoomed_width = int(self.original_pixmap.width() * fill_ratio)
        zoomed_height = int(self.original_pixmap.height() * fill_ratio)

        scaled_pixmap = self.original_pixmap.scaled(
            zoomed_width, zoomed_height,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.image_label.setPixmap(scaled_pixmap)
        self.image_label.resize(scaled_pixmap.size())
        self.media_container.resize(scaled_pixmap.size())

        self.zoom_level = fill_ratio

    def _update_zoom_status(self):
        """Update status label with professional zoom indicators."""
        status_parts = []

        # Zoom indicator (for photos)
        if not self._is_video(self.media_path):
            if self.zoom_mode == "fit":
                status_parts.append("🔍 Fit to Window")
            elif self.zoom_mode == "fill":
                status_parts.append("🔍 Fill Window")
            elif self.zoom_mode == "actual":
                status_parts.append("🔍 100% (Actual Size)")
            else:
                zoom_pct = int(self.zoom_level * 100)
                status_parts.append(f"🔍 {zoom_pct}%")

        # Slideshow indicator
        if self.slideshow_active:
            status_parts.append("⏵ Slideshow")

        self.status_label.setText(" | ".join(status_parts) if status_parts else "")

    def _update_status_label(self):
        """Update status label with zoom level or slideshow status."""
        status_parts = []

        # Zoom indicator (for photos)
        if not self._is_video(self.media_path):
            zoom_pct = int(self.zoom_level * 100)
            if self.zoom_mode == "fit":
                status_parts.append("Fit")
            elif self.zoom_mode == "fill":
                status_parts.append("Fill")
            else:
                status_parts.append(f"{zoom_pct}%")

        # Slideshow indicator
        if self.slideshow_active:
            status_parts.append("⏵ Slideshow")

        self.status_label.setText(" | ".join(status_parts) if status_parts else "")

    def _toggle_slideshow(self):
        """Toggle slideshow mode."""
        if self.slideshow_active:
            # Stop slideshow
            self.slideshow_active = False
            if self.slideshow_timer:
                self.slideshow_timer.stop()
            self.slideshow_btn.setText("▶")
            self.slideshow_btn.setToolTip("Slideshow (S)")
        else:
            # Start slideshow
            self.slideshow_active = True
            from PySide6.QtCore import QTimer
            if not self.slideshow_timer:
                self.slideshow_timer = QTimer()
                self.slideshow_timer.timeout.connect(self._slideshow_advance)
            self.slideshow_timer.start(self.slideshow_interval)
            self.slideshow_btn.setText("⏸")
            self.slideshow_btn.setToolTip("Pause Slideshow (S)")

        self._update_status_label()

    def _slideshow_advance(self):
        """Advance to next media in slideshow."""
        if self.slideshow_active:
            self._next_media()

    def _delete_current_media(self):
        """Delete current media file."""
        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self,
            "Delete Media",
            f"Are you sure you want to delete this file?\n\n{os.path.basename(self.media_path)}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                import os
                # Remove from database first
                # TODO: Add database deletion logic here

                # Delete file
                os.remove(self.media_path)
                print(f"[MediaLightbox] Deleted: {self.media_path}")

                # Remove from list
                self.all_media.remove(self.media_path)

                # Load next or previous
                if self.all_media:
                    if self.current_index >= len(self.all_media):
                        self.current_index = len(self.all_media) - 1
                    self.media_path = self.all_media[self.current_index]
                    self._load_media()
                else:
                    # No more media, close lightbox
                    self.close()

            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Delete Error",
                    f"Failed to delete file:\n{str(e)}"
                )

    def _toggle_favorite(self):
        """Toggle favorite status of current media."""
        # TODO: Implement favorite in database
        # For now, just toggle button appearance
        if self.favorite_btn.text() == "♡":
            self.favorite_btn.setText("♥")
            self.favorite_btn.setStyleSheet(self.favorite_btn.styleSheet() + "\nQPushButton { color: #ff4444; }")
            print(f"[MediaLightbox] Favorited: {os.path.basename(self.media_path)}")
        else:
            self.favorite_btn.setText("♡")
            self.favorite_btn.setStyleSheet(self.favorite_btn.styleSheet().replace("\nQPushButton { color: #ff4444; }", ""))
            print(f"[MediaLightbox] Unfavorited: {os.path.basename(self.media_path)}")

    def _rate_media(self, rating: int):
        """Rate current media with 1-5 stars."""
        self.current_rating = rating
        stars = "★" * rating + "☆" * (5 - rating)
        print(f"[MediaLightbox] Rated {rating}/5: {os.path.basename(self.media_path)}")
        # TODO: Save to database

        # Update status label to show rating
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "Rating",
            f"Rated {stars} ({rating}/5)",
            QMessageBox.Ok
        )

    def _toggle_fullscreen(self):
        """Toggle fullscreen mode with distraction-free viewing."""
        if self.isFullScreen():
            # Exit fullscreen
            self.showMaximized()

            # Show toolbars again
            self._show_toolbars()
            self.toolbar_hide_timer.stop()  # Don't auto-hide when not fullscreen

            print("[MediaLightbox] Exited fullscreen")
        else:
            # Enter fullscreen
            self.showFullScreen()

            # Hide toolbars for distraction-free viewing
            self._hide_toolbars()

            # Enable auto-hide in fullscreen
            self.toolbar_hide_timer.start()

            print("[MediaLightbox] Entered fullscreen (toolbars auto-hide)")


class GooglePhotosLayout(BaseLayout):
    """
    Google Photos-style layout.

    Structure:
    ┌─────────────────────────────────────────────┐
    │  Toolbar (Scan, Faces, Search, etc.)       │
    ├───────────┬─────────────────────────────────┤
    │ Sidebar   │  Timeline (Date Groups)         │
    │ • Search  │  • December 2024 (15 photos)    │
    │ • Years   │  • November 2024 (32 photos)    │
    │ • Albums  │  • October 2024 (28 photos)     │
    └───────────┴─────────────────────────────────┘

    Features:
    - Timeline-based view (grouped by date)
    - Minimal sidebar (search + timeline navigation)
    - Large zoomable thumbnails
    - Layout-specific toolbar with Scan/Faces
    """

    def get_name(self) -> str:
        return "Google Photos Style"

    def get_id(self) -> str:
        return "google"

    def create_layout(self) -> QWidget:
        """
        Create Google Photos-style layout.
        """
        # Phase 2: Selection tracking
        self.selected_photos = set()  # Set of selected photo paths
        self.selection_mode = False  # Whether selection mode is active
        self.last_selected_path = None  # For Shift range selection
        self.all_displayed_paths = []  # Track all photos in current view for range selection

        # Async thumbnail loading (copied from Current Layout's proven pattern)
        self.thumbnail_thread_pool = QThreadPool()
        self.thumbnail_thread_pool.setMaxThreadCount(4)  # REDUCED: Limit concurrent loads
        self.thumbnail_buttons = {}  # Map path -> button widget for async updates
        self.thumbnail_load_count = 0  # Track how many thumbnails we've queued

        # QUICK WIN #1: Track unloaded thumbnails for scroll-triggered loading
        self.unloaded_thumbnails = {}  # Map path -> (button, size) for lazy loading
        self.initial_load_limit = 50  # Load first 50 immediately (increased from 30)

        # QUICK WIN #3: Virtual scrolling - render only visible date groups
        self.date_groups_metadata = []  # List of {date_str, photos, thumb_size, index}
        self.date_group_widgets = {}  # Map index -> widget (rendered or placeholder)
        self.rendered_date_groups = set()  # Set of indices that are currently rendered
        self.virtual_scroll_enabled = True  # Enable virtual scrolling
        self.initial_render_count = 5  # Render first 5 date groups immediately

        # QUICK WIN #4: Collapsible date groups
        self.date_group_collapsed = {}  # Map date_str -> bool (collapsed state)
        self.date_group_grids = {}  # Map date_str -> grid widget for toggle visibility

        # QUICK WIN #5: Smooth scroll performance (60 FPS)
        self.scroll_debounce_timer = QTimer()
        self.scroll_debounce_timer.setSingleShot(True)
        self.scroll_debounce_timer.timeout.connect(self._on_scroll_debounced)
        self.scroll_debounce_delay = 150  # ms - debounce scroll events

        # CRITICAL FIX: Create ONE shared signal object for ALL workers (like Current Layout)
        # Problem: Each worker was creating its own signal → signals got garbage collected
        # Solution: Share one signal object, connect it once
        self.thumbnail_signals = ThumbnailSignals()
        self.thumbnail_signals.loaded.connect(self._on_thumbnail_loaded)

        # Initialize filter state
        self.current_thumb_size = 200
        self.current_filter_year = None
        self.current_filter_month = None
        self.current_filter_folder = None
        self.current_filter_person = None

        # Get current project ID (CRITICAL: Photos are organized by project)
        from app_services import get_default_project_id, list_projects
        self.project_id = get_default_project_id()

        # Fallback to first project if no default
        if self.project_id is None:
            projects = list_projects()
            if projects:
                self.project_id = projects[0]["id"]
                print(f"[GooglePhotosLayout] Using first project: {self.project_id}")
            else:
                print("[GooglePhotosLayout] ⚠️ WARNING: No projects found! Please create a project first.")
        else:
            print(f"[GooglePhotosLayout] Using default project: {self.project_id}")

        # Main container
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Create toolbar
        toolbar = self._create_toolbar()
        main_layout.addWidget(toolbar)

        # Create horizontal splitter (Sidebar | Timeline)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(3)

        # Create sidebar
        self.sidebar = self._create_sidebar()
        self.splitter.addWidget(self.sidebar)

        # Create timeline
        self.timeline = self._create_timeline()
        self.splitter.addWidget(self.timeline)

        # Set splitter sizes (200px sidebar, rest for timeline)
        self.splitter.setSizes([200, 1000])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)

        main_layout.addWidget(self.splitter)

        # QUICK WIN #6: Create floating selection toolbar (initially hidden)
        self.floating_toolbar = self._create_floating_toolbar(main_widget)
        self.floating_toolbar.hide()

        # Load photos from database
        self._load_photos()

        return main_widget

    def _create_toolbar(self) -> QToolBar:
        """
        Create Google Photos-specific toolbar.
        """
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        toolbar.setStyleSheet("""
            QToolBar {
                background: #f8f9fa;
                border-bottom: 1px solid #dadce0;
                padding: 6px;
                spacing: 8px;
            }
            QPushButton {
                background: white;
                border: 1px solid #dadce0;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11pt;
            }
            QPushButton:hover {
                background: #f1f3f4;
                border-color: #bdc1c6;
            }
            QPushButton:pressed {
                background: #e8eaed;
            }
        """)

        # Primary actions
        self.btn_create_project = QPushButton("➕ New Project")
        self.btn_create_project.setToolTip("Create a new project")
        # CRITICAL FIX: Connect button immediately, not in on_layout_activated
        self.btn_create_project.clicked.connect(self._on_create_project_clicked)
        print("[GooglePhotosLayout] ✅ Create Project button connected in toolbar creation")
        toolbar.addWidget(self.btn_create_project)

        # Project selector
        from PySide6.QtWidgets import QComboBox, QLabel
        project_label = QLabel("Project:")
        project_label.setStyleSheet("padding: 0 8px; font-weight: bold;")
        toolbar.addWidget(project_label)

        self.project_combo = QComboBox()
        self.project_combo.setMinimumWidth(150)
        self.project_combo.setStyleSheet("""
            QComboBox {
                background: white;
                border: 1px solid #dadce0;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11pt;
            }
            QComboBox:hover {
                border-color: #bdc1c6;
            }
            QComboBox::drop-down {
                border: none;
            }
        """)
        self.project_combo.setToolTip("Select project to view")
        toolbar.addWidget(self.project_combo)

        # Populate project selector
        self._populate_project_selector()

        toolbar.addSeparator()

        self.btn_scan = QPushButton("📂 Scan Repository")
        self.btn_scan.setToolTip("Scan folder to add new photos to database")
        toolbar.addWidget(self.btn_scan)

        self.btn_faces = QPushButton("👤 Detect Faces")
        self.btn_faces.setToolTip("Run face detection and clustering on photos")
        toolbar.addWidget(self.btn_faces)

        toolbar.addSeparator()

        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 Search your photos...")
        self.search_box.setMinimumWidth(300)
        self.search_box.setStyleSheet("""
            QLineEdit {
                background: white;
                border: 1px solid #dadce0;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11pt;
            }
            QLineEdit:focus {
                border-color: #1a73e8;
            }
        """)
        # Phase 2: Connect search functionality
        self.search_box.textChanged.connect(self._on_search_text_changed)
        self.search_box.returnPressed.connect(self._perform_search)
        toolbar.addWidget(self.search_box)

        toolbar.addSeparator()

        # Refresh button
        self.btn_refresh = QPushButton("↻ Refresh")
        self.btn_refresh.setToolTip("Reload timeline from database")
        self.btn_refresh.clicked.connect(self._load_photos)
        toolbar.addWidget(self.btn_refresh)

        # Clear Filter button (initially hidden)
        self.btn_clear_filter = QPushButton("✕ Clear Filter")
        self.btn_clear_filter.setToolTip("Show all photos (remove date/folder filters)")
        self.btn_clear_filter.clicked.connect(self._clear_filter)
        self.btn_clear_filter.setVisible(False)
        self.btn_clear_filter.setStyleSheet("""
            QPushButton {
                background: #fff3cd;
                border: 1px solid #ffc107;
                color: #856404;
            }
            QPushButton:hover {
                background: #ffeaa7;
            }
        """)
        toolbar.addWidget(self.btn_clear_filter)

        toolbar.addSeparator()

        # Phase 2: Selection mode toggle
        self.btn_select = QPushButton("☑️ Select")
        self.btn_select.setToolTip("Enable selection mode to select multiple photos")
        self.btn_select.setCheckable(True)
        self.btn_select.clicked.connect(self._toggle_selection_mode)
        toolbar.addWidget(self.btn_select)

        toolbar.addSeparator()

        # Phase 2: Zoom slider for thumbnail size
        from PySide6.QtWidgets import QLabel, QSlider
        zoom_label = QLabel("🔎 Zoom:")
        zoom_label.setStyleSheet("padding: 0 4px;")
        toolbar.addWidget(zoom_label)

        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setMinimum(100)  # 100px thumbnails
        self.zoom_slider.setMaximum(400)  # 400px thumbnails
        self.zoom_slider.setValue(200)    # Default 200px
        self.zoom_slider.setFixedWidth(120)
        self.zoom_slider.setToolTip("Adjust thumbnail size")
        self.zoom_slider.valueChanged.connect(self._on_zoom_changed)
        toolbar.addWidget(self.zoom_slider)

        # Zoom value label
        self.zoom_value_label = QLabel("200px")
        self.zoom_value_label.setFixedWidth(50)
        self.zoom_value_label.setStyleSheet("padding: 0 4px; font-size: 10pt;")
        toolbar.addWidget(self.zoom_value_label)

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        # Selection actions (will show/hide based on selection)
        self.btn_delete = QPushButton("🗑️ Delete")
        self.btn_delete.setToolTip("Delete selected photos")
        self.btn_delete.setVisible(False)
        self.btn_delete.clicked.connect(self._on_delete_selected)
        toolbar.addWidget(self.btn_delete)

        self.btn_favorite = QPushButton("⭐ Favorite")
        self.btn_favorite.setToolTip("Mark selected as favorites")
        self.btn_favorite.setVisible(False)
        self.btn_favorite.clicked.connect(self._on_favorite_selected)
        toolbar.addWidget(self.btn_favorite)

        # Store toolbar reference
        self._toolbar = toolbar

        return toolbar

    def _create_floating_toolbar(self, parent: QWidget) -> QWidget:
        """
        QUICK WIN #6: Create floating selection toolbar (Google Photos style).

        Appears at bottom of screen when photos are selected.
        Shows selection count and action buttons.

        Args:
            parent: Parent widget for positioning

        Returns:
            QWidget: Floating toolbar (initially hidden)
        """
        toolbar = QWidget(parent)
        toolbar.setStyleSheet("""
            QWidget {
                background: #202124;
                border-radius: 8px;
                border: 1px solid #5f6368;
            }
        """)

        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # Selection count label
        self.selection_count_label = QLabel("0 selected")
        self.selection_count_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 11pt;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.selection_count_label)

        layout.addStretch()

        # Action buttons
        # Select All button
        btn_select_all = QPushButton("Select All")
        btn_select_all.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #8ab4f8;
                border: none;
                padding: 6px 12px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background: #3c4043;
                border-radius: 4px;
            }
        """)
        btn_select_all.setCursor(Qt.PointingHandCursor)
        btn_select_all.clicked.connect(self._on_select_all)
        layout.addWidget(btn_select_all)

        # Clear Selection button
        btn_clear = QPushButton("Clear")
        btn_clear.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #8ab4f8;
                border: none;
                padding: 6px 12px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background: #3c4043;
                border-radius: 4px;
            }
        """)
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.clicked.connect(self._on_clear_selection)
        layout.addWidget(btn_clear)

        # Delete button
        btn_delete = QPushButton("🗑️ Delete")
        btn_delete.setStyleSheet("""
            QPushButton {
                background: #d32f2f;
                color: white;
                border: none;
                padding: 6px 16px;
                border-radius: 4px;
                font-size: 10pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #b71c1c;
            }
        """)
        btn_delete.setCursor(Qt.PointingHandCursor)
        btn_delete.clicked.connect(self._on_delete_selected)
        layout.addWidget(btn_delete)

        # Position toolbar at bottom center (will be repositioned on resize)
        toolbar.setFixedHeight(56)
        toolbar.setFixedWidth(400)

        return toolbar

    def _create_sidebar(self) -> QWidget:
        """
        Create minimal sidebar with timeline navigation, folders, and people.
        """
        sidebar = QWidget()
        sidebar.setMinimumWidth(180)
        sidebar.setMaximumWidth(250)
        sidebar.setStyleSheet("""
            QWidget {
                background: white;
                border-right: 1px solid #dadce0;
            }
        """)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # Timeline navigation header (clickable to clear filters)
        timeline_header = QPushButton("📅 Timeline")
        timeline_header.setFlat(True)
        timeline_header.setCursor(Qt.PointingHandCursor)
        timeline_header.setStyleSheet("""
            QPushButton {
                text-align: left;
                font-size: 12pt;
                font-weight: bold;
                color: #202124;
                border: none;
                padding: 4px 0px;
            }
            QPushButton:hover {
                color: #1a73e8;
                background: transparent;
            }
        """)
        timeline_header.clicked.connect(self._on_section_header_clicked)
        layout.addWidget(timeline_header)

        # Timeline tree (Years > Months)
        self.timeline_tree = QTreeWidget()
        self.timeline_tree.setHeaderHidden(True)
        self.timeline_tree.setStyleSheet("""
            QTreeWidget {
                border: none;
                background: transparent;
                font-size: 10pt;
            }
            QTreeWidget::item {
                padding: 4px;
            }
            QTreeWidget::item:hover {
                background: #f1f3f4;
            }
            QTreeWidget::item:selected {
                background: #e8f0fe;
                color: #1a73e8;
            }
        """)
        # Connect click signal to filter handler
        self.timeline_tree.itemClicked.connect(self._on_timeline_item_clicked)
        layout.addWidget(self.timeline_tree)

        # Folders section header (clickable to clear filters)
        folders_header = QPushButton("📁 Folders")
        folders_header.setFlat(True)
        folders_header.setCursor(Qt.PointingHandCursor)
        folders_header.setStyleSheet("""
            QPushButton {
                text-align: left;
                font-size: 12pt;
                font-weight: bold;
                color: #202124;
                border: none;
                padding: 4px 0px;
                margin-top: 12px;
            }
            QPushButton:hover {
                color: #1a73e8;
                background: transparent;
            }
        """)
        folders_header.clicked.connect(self._on_section_header_clicked)
        layout.addWidget(folders_header)

        # Folders tree
        self.folders_tree = QTreeWidget()
        self.folders_tree.setHeaderHidden(True)
        self.folders_tree.setStyleSheet("""
            QTreeWidget {
                border: none;
                background: transparent;
                font-size: 10pt;
            }
            QTreeWidget::item {
                padding: 4px;
            }
            QTreeWidget::item:hover {
                background: #f1f3f4;
            }
            QTreeWidget::item:selected {
                background: #e8f0fe;
                color: #1a73e8;
            }
        """)
        # Connect click signal to filter handler
        self.folders_tree.itemClicked.connect(self._on_folder_item_clicked)
        layout.addWidget(self.folders_tree)

        # People section header (clickable to clear filters)
        people_header = QPushButton("👥 People")
        people_header.setFlat(True)
        people_header.setCursor(Qt.PointingHandCursor)
        people_header.setStyleSheet("""
            QPushButton {
                text-align: left;
                font-size: 12pt;
                font-weight: bold;
                color: #202124;
                border: none;
                padding: 4px 0px;
                margin-top: 12px;
            }
            QPushButton:hover {
                color: #1a73e8;
                background: transparent;
            }
        """)
        people_header.clicked.connect(self._on_section_header_clicked)
        layout.addWidget(people_header)

        # People tree
        self.people_tree = QTreeWidget()
        self.people_tree.setHeaderHidden(True)
        self.people_tree.setStyleSheet("""
            QTreeWidget {
                border: none;
                background: transparent;
                font-size: 10pt;
            }
            QTreeWidget::item {
                padding: 4px;
            }
            QTreeWidget::item:hover {
                background: #f1f3f4;
            }
            QTreeWidget::item:selected {
                background: #e8f0fe;
                color: #1a73e8;
            }
        """)
        # Connect click signal to filter handler
        self.people_tree.itemClicked.connect(self._on_people_item_clicked)
        layout.addWidget(self.people_tree)

        # Videos section header (clickable to show all videos)
        videos_header = QPushButton("🎬 Videos")
        videos_header.setFlat(True)
        videos_header.setCursor(Qt.PointingHandCursor)
        videos_header.setStyleSheet("""
            QPushButton {
                text-align: left;
                font-size: 12pt;
                font-weight: bold;
                color: #202124;
                border: none;
                padding: 4px 0px;
                margin-top: 12px;
            }
            QPushButton:hover {
                color: #1a73e8;
                background: transparent;
            }
        """)
        videos_header.clicked.connect(self._on_videos_header_clicked)
        layout.addWidget(videos_header)

        # Videos tree
        self.videos_tree = QTreeWidget()
        self.videos_tree.setHeaderHidden(True)
        self.videos_tree.setStyleSheet("""
            QTreeWidget {
                border: none;
                background: transparent;
                font-size: 10pt;
            }
            QTreeWidget::item {
                padding: 4px;
            }
            QTreeWidget::item:hover {
                background: #f1f3f4;
            }
            QTreeWidget::item:selected {
                background: #e8f0fe;
                color: #1a73e8;
            }
        """)
        # Connect click signal to filter handler
        self.videos_tree.itemClicked.connect(self._on_videos_item_clicked)
        layout.addWidget(self.videos_tree)

        # Spacer at bottom
        layout.addStretch()

        return sidebar

    def _create_timeline(self) -> QWidget:
        """
        Create timeline scroll area with date groups.
        """
        # Scroll area
        self.timeline_scroll = QScrollArea()  # Store reference for scroll events
        self.timeline_scroll.setWidgetResizable(True)
        self.timeline_scroll.setFrameShape(QFrame.NoFrame)
        self.timeline_scroll.setStyleSheet("""
            QScrollArea {
                background: white;
                border: none;
            }
        """)

        # Timeline container (holds date groups)
        self.timeline_container = QWidget()
        self.timeline_layout = QVBoxLayout(self.timeline_container)
        self.timeline_layout.setContentsMargins(20, 20, 20, 20)
        self.timeline_layout.setSpacing(30)
        self.timeline_layout.setAlignment(Qt.AlignTop)

        self.timeline_scroll.setWidget(self.timeline_container)

        # QUICK WIN #1: Connect scroll event for lazy thumbnail loading
        # This enables ALL photos to load as user scrolls (removes 30-photo limit)
        self.timeline_scroll.verticalScrollBar().valueChanged.connect(
            self._on_timeline_scrolled
        )
        print("[GooglePhotosLayout] ✅ Scroll-triggered lazy loading enabled")

        return self.timeline_scroll

    def _load_photos(self, thumb_size: int = 200, filter_year: int = None, filter_month: int = None, filter_folder: str = None, filter_person: str = None):
        """
        Load photos from database and populate timeline.

        Args:
            thumb_size: Thumbnail size in pixels (default 200)
            filter_year: Optional year filter (e.g., 2024)
            filter_month: Optional month filter (1-12, requires filter_year)
            filter_folder: Optional folder path filter
            filter_person: Optional person/face cluster filter (branch_key)

        CRITICAL: Wrapped in comprehensive error handling to prevent crashes
        during/after scan operations when database might be in inconsistent state.
        """
        # Store current thumbnail size and filters
        self.current_thumb_size = thumb_size
        self.current_filter_year = filter_year
        self.current_filter_month = filter_month
        self.current_filter_folder = filter_folder
        self.current_filter_person = filter_person

        filter_desc = []
        if filter_year:
            filter_desc.append(f"year={filter_year}")
        if filter_month:
            filter_desc.append(f"month={filter_month}")
        if filter_folder:
            filter_desc.append(f"folder={filter_folder}")
        if filter_person:
            filter_desc.append(f"person={filter_person}")

        filter_str = f" [{', '.join(filter_desc)}]" if filter_desc else ""
        print(f"[GooglePhotosLayout] Loading photos from database (thumb size: {thumb_size}px){filter_str}...")

        # Show/hide Clear Filter button based on whether filters are active
        has_filters = filter_year is not None or filter_month is not None or filter_folder is not None or filter_person is not None
        self.btn_clear_filter.setVisible(has_filters)

        # Clear existing timeline and thumbnail cache
        try:
            while self.timeline_layout.count():
                child = self.timeline_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

            # Clear thumbnail button cache and reset load counter
            self.thumbnail_buttons.clear()
            self.thumbnail_load_count = 0  # Reset counter for new photo set

            # CRITICAL FIX: Only clear trees when NOT filtering
            # When filtering, we want to keep the tree structure visible
            # so users can see all available years/months/folders/people and switch between them
            has_filters = filter_year is not None or filter_month is not None or filter_folder is not None or filter_person is not None
            if not has_filters:
                # Clear trees only when showing all photos (no filters)
                self.timeline_tree.clear()
                self.folders_tree.clear()
                self.people_tree.clear()
                self.videos_tree.clear()
        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error clearing timeline: {e}")
            # Continue anyway

        # Get photos from database
        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()

            # CRITICAL: Check if we have a valid project
            if self.project_id is None:
                # No project - show empty state with instructions
                empty_label = QLabel("📂 No project selected\n\nClick '➕ New Project' to create your first project")
                empty_label.setAlignment(Qt.AlignCenter)
                empty_label.setStyleSheet("font-size: 12pt; color: #888; padding: 60px;")
                self.timeline_layout.addWidget(empty_label)
                print("[GooglePhotosLayout] ⚠️ No project selected")
                return

            # Query photos for the current project (join with project_images)
            # CRITICAL FIX: Filter by project_id using project_images table
            # Build query with optional filters
            # CRITICAL FIX: Use created_date instead of date_taken
            # created_date is ALWAYS populated (uses date_taken if available, otherwise file modified date)
            # This matches Current Layout behavior and ensures ALL photos appear
            query_parts = ["""
                SELECT DISTINCT pm.path, pm.created_date as date_taken, pm.width, pm.height
                FROM photo_metadata pm
                JOIN project_images pi ON pm.path = pi.image_path
                WHERE pi.project_id = ?
            """]

            params = [self.project_id]

            # Add year filter (using created_date which is always populated)
            if filter_year is not None:
                query_parts.append("AND strftime('%Y', pm.created_date) = ?")
                params.append(str(filter_year))

            # Add month filter (requires year)
            if filter_month is not None and filter_year is not None:
                query_parts.append("AND strftime('%m', pm.created_date) = ?")
                params.append(f"{filter_month:02d}")

            # Add folder filter
            if filter_folder is not None:
                query_parts.append("AND pm.path LIKE ?")
                params.append(f"{filter_folder}%")

            # Add person/face filter (photos containing this person)
            if filter_person is not None:
                print(f"[GooglePhotosLayout] Filtering by person: {filter_person}")
                query_parts.append("""
                    AND pm.path IN (
                        SELECT DISTINCT image_path
                        FROM face_crops
                        WHERE project_id = ? AND branch_key = ?
                    )
                """)
                params.append(self.project_id)
                params.append(filter_person)

            query_parts.append("ORDER BY pm.date_taken DESC")
            query = "\n".join(query_parts)

            # Debug: Log SQL query and parameters
            print(f"[GooglePhotosLayout] 🔍 SQL Query:\n{query}")
            print(f"[GooglePhotosLayout] 🔍 Parameters: {params}")
            if filter_person is not None:
                print(f"[GooglePhotosLayout] 🔍 Person filter: project_id={self.project_id}, branch_key={filter_person}")

            # Use ReferenceDB's connection pattern with timeout protection
            try:
                with db._connect() as conn:
                    # Set a timeout to prevent blocking if database is locked
                    conn.execute("PRAGMA busy_timeout = 5000")  # 5 second timeout
                    cur = conn.cursor()
                    cur.execute(query, tuple(params))
                    rows = cur.fetchall()

                    # Debug logging
                    print(f"[GooglePhotosLayout] 📊 Loaded {len(rows)} photos from database")

            except Exception as db_error:
                print(f"[GooglePhotosLayout] ⚠️ Database query failed: {db_error}")
                # Show error state but don't crash
                error_label = QLabel(f"⚠️ Error loading photos\n\n{str(db_error)}\n\nTry clicking Refresh")
                error_label.setAlignment(Qt.AlignCenter)
                error_label.setStyleSheet("font-size: 11pt; color: #d32f2f; padding: 60px;")
                self.timeline_layout.addWidget(error_label)
                return

            if not rows:
                # No photos in project - show empty state
                empty_label = QLabel("📷 No photos in this project yet\n\nClick 'Scan Repository' to add photos")
                empty_label.setAlignment(Qt.AlignCenter)
                empty_label.setStyleSheet("font-size: 12pt; color: #888; padding: 60px;")
                self.timeline_layout.addWidget(empty_label)
                print(f"[GooglePhotosLayout] No photos found in project {self.project_id}")
                return

            # Group photos by date
            photos_by_date = self._group_photos_by_date(rows)

            # Build timeline, folders, people, and videos trees (only if not filtering)
            # This shows ALL years/months/folders/people/videos, not just filtered ones
            if filter_year is None and filter_month is None and filter_folder is None and filter_person is None:
                self._build_timeline_tree(photos_by_date)
                self._build_folders_tree(rows)
                self._build_people_tree()
                self._build_videos_tree()

            # Track all displayed paths for Shift+Ctrl multi-selection
            self.all_displayed_paths = [photo[0] for photos_list in photos_by_date.values() for photo in photos_list]
            print(f"[GooglePhotosLayout] Tracking {len(self.all_displayed_paths)} paths for multi-selection")

            # QUICK WIN #3: Virtual scrolling - create date groups with lazy rendering
            self.date_groups_metadata.clear()
            self.date_group_widgets.clear()
            self.rendered_date_groups.clear()

            # Store metadata for all date groups
            for index, (date_str, photos) in enumerate(photos_by_date.items()):
                self.date_groups_metadata.append({
                    'index': index,
                    'date_str': date_str,
                    'photos': photos,
                    'thumb_size': thumb_size
                })

            # Create widgets (placeholders or rendered) for each group
            for metadata in self.date_groups_metadata:
                index = metadata['index']

                # Render first N groups immediately, placeholders for the rest
                if self.virtual_scroll_enabled and index >= self.initial_render_count:
                    # Create placeholder for off-screen groups
                    widget = self._create_date_group_placeholder(metadata)
                else:
                    # Render initial groups
                    widget = self._create_date_group(
                        metadata['date_str'],
                        metadata['photos'],
                        metadata['thumb_size']
                    )
                    self.rendered_date_groups.add(index)

                self.date_group_widgets[index] = widget
                self.timeline_layout.addWidget(widget)

            # Add spacer at bottom
            self.timeline_layout.addStretch()

            if self.virtual_scroll_enabled:
                print(f"[GooglePhotosLayout] 🚀 Virtual scrolling: {len(photos_by_date)} date groups ({len(self.rendered_date_groups)} rendered, {len(photos_by_date) - len(self.rendered_date_groups)} placeholders)")
            else:
                print(f"[GooglePhotosLayout] Loaded {len(rows)} photos in {len(photos_by_date)} date groups")
            print(f"[GooglePhotosLayout] Queued {self.thumbnail_load_count} thumbnails for loading (initial limit: {self.initial_load_limit})")

        except Exception as e:
            # CRITICAL: Catch ALL exceptions to prevent layout crashes
            print(f"[GooglePhotosLayout] ⚠️ CRITICAL ERROR loading photos: {e}")
            import traceback
            traceback.print_exc()

            # Show error state with actionable message
            try:
                error_label = QLabel(
                    f"⚠️ Failed to load photos\n\n"
                    f"Error: {str(e)}\n\n"
                    f"Try:\n"
                    f"• Click Refresh button\n"
                    f"• Switch to Current layout and back\n"
                    f"• Restart the application"
                )
                error_label.setAlignment(Qt.AlignCenter)
                error_label.setStyleSheet("font-size: 11pt; color: #d32f2f; padding: 40px;")
                self.timeline_layout.addWidget(error_label)
            except:
                pass  # Even error display failed - just log it

    def _group_photos_by_date(self, rows) -> Dict[str, List[Tuple]]:
        """
        Group photos by date (YYYY-MM-DD).

        Uses created_date which is ALWAYS populated (never NULL).
        created_date = date_taken if available, otherwise file modified date.

        Returns:
            dict: {date_str: [(path, date_taken, width, height), ...]}
        """
        groups = defaultdict(list)

        for row in rows:
            path, date_taken, width, height = row

            # created_date is always in YYYY-MM-DD format, so we can use it directly
            # No need to parse or handle NULL values
            if date_taken:  # Should always be true since created_date is never NULL
                groups[date_taken].append((path, date_taken, width, height))
            else:
                # Fallback (should never happen with created_date)
                print(f"[GooglePhotosLayout] ⚠️ WARNING: Photo has no created_date: {path}")

        return dict(groups)

    def _build_timeline_tree(self, photos_by_date: Dict[str, List[Tuple]]):
        """
        Build timeline tree in sidebar (Years > Months with counts).

        Uses created_date which is always in YYYY-MM-DD format.
        """
        # Group by year and month
        years_months = defaultdict(lambda: defaultdict(int))

        for date_str in photos_by_date.keys():
            # created_date is always YYYY-MM-DD format, can parse directly
            try:
                date_obj = datetime.fromisoformat(date_str)
                year = date_obj.year
                month = date_obj.month
                count = len(photos_by_date[date_str])
                years_months[year][month] += count
            except Exception as e:
                print(f"[GooglePhotosLayout] ⚠️ Failed to parse date '{date_str}': {e}")
                continue

        # Build tree
        for year in sorted(years_months.keys(), reverse=True):
            year_item = QTreeWidgetItem([f"📅 {year}"])
            year_item.setData(0, Qt.UserRole, {"type": "year", "year": year})
            year_item.setExpanded(True)
            self.timeline_tree.addTopLevelItem(year_item)

            for month in sorted(years_months[year].keys(), reverse=True):
                count = years_months[year][month]
                month_name = datetime(year, month, 1).strftime("%B")
                month_item = QTreeWidgetItem([f"  • {month_name} ({count})"])
                month_item.setData(0, Qt.UserRole, {"type": "month", "year": year, "month": month})
                year_item.addChild(month_item)

    def _build_folders_tree(self, rows):
        """
        Build folders tree in sidebar (folder hierarchy with counts).

        Args:
            rows: List of (path, date_taken, width, height) tuples
        """
        # Group photos by parent folder
        folder_counts = defaultdict(int)

        for row in rows:
            path = row[0]
            parent_folder = os.path.dirname(path)
            folder_counts[parent_folder] += 1

        # Sort folders by count (most photos first)
        sorted_folders = sorted(folder_counts.items(), key=lambda x: x[1], reverse=True)

        # Build tree (show top 10 folders)
        for folder, count in sorted_folders[:10]:
            # Show only folder name, not full path
            folder_name = os.path.basename(folder) if folder else "(Root)"
            if not folder_name:
                folder_name = folder  # Show full path if basename is empty

            folder_item = QTreeWidgetItem([f"📁 {folder_name} ({count})"])
            folder_item.setData(0, Qt.UserRole, {"type": "folder", "path": folder})
            folder_item.setToolTip(0, folder)  # Show full path on hover
            self.folders_tree.addTopLevelItem(folder_item)

    def _on_timeline_item_clicked(self, item: QTreeWidgetItem, column: int):
        """
        Handle timeline tree item click - filter by year or month.

        Args:
            item: Clicked tree item
            column: Column index (always 0)
        """
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        item_type = data.get("type")

        if item_type == "year":
            year = data.get("year")
            print(f"[GooglePhotosLayout] Filtering by year: {year}")
            self._load_photos(
                thumb_size=self.current_thumb_size,
                filter_year=year,
                filter_month=None,
                filter_folder=None,
                filter_person=None
            )
        elif item_type == "month":
            year = data.get("year")
            month = data.get("month")
            month_name = datetime(year, month, 1).strftime("%B %Y")
            print(f"[GooglePhotosLayout] Filtering by month: {month_name}")
            self._load_photos(
                thumb_size=self.current_thumb_size,
                filter_year=year,
                filter_month=month,
                filter_folder=None,
                filter_person=None
            )

    def _on_folder_item_clicked(self, item: QTreeWidgetItem, column: int):
        """
        Handle folder tree item click - filter by folder.

        Args:
            item: Clicked tree item
            column: Column index (always 0)
        """
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        folder_path = data.get("path")
        if folder_path:
            folder_name = os.path.basename(folder_path) if folder_path else "(Root)"
            print(f"[GooglePhotosLayout] Filtering by folder: {folder_name}")
            self._load_photos(
                thumb_size=self.current_thumb_size,
                filter_year=None,
                filter_month=None,
                filter_folder=folder_path,
                filter_person=None
            )

    def _build_people_tree(self):
        """
        Build people tree in sidebar (face clusters with counts).

        Queries face_branch_reps table for detected faces/people.
        """
        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()

            # Query face clusters for current project (with representative image)
            query = """
                SELECT branch_key, label, count, rep_path, rep_thumb_png
                FROM face_branch_reps
                WHERE project_id = ?
                ORDER BY count DESC
                LIMIT 10
            """

            print(f"[GooglePhotosLayout] 👥 Querying face_branch_reps for project_id={self.project_id}")

            with db._connect() as conn:
                conn.execute("PRAGMA busy_timeout = 5000")
                cur = conn.cursor()
                cur.execute(query, (self.project_id,))
                rows = cur.fetchall()

            print(f"[GooglePhotosLayout] 👥 Found {len(rows)} face clusters")
            for branch_key, label, count, rep_path, rep_thumb_png in rows:
                print(f"[GooglePhotosLayout]   - {branch_key}: {label or 'Unnamed'} ({count} photos)")

            if not rows:
                # No face clusters found - show placeholder
                no_faces_item = QTreeWidgetItem(["  (Run face detection first)"])
                no_faces_item.setDisabled(True)
                self.people_tree.addTopLevelItem(no_faces_item)
                return

            # Build tree with thumbnails
            for branch_key, label, count, rep_path, rep_thumb_png in rows:
                # Use label if set, otherwise use "Unnamed Person"
                display_name = label if label else f"Unnamed Person"

                # Create tree item
                person_item = QTreeWidgetItem([f"{display_name} ({count})"])
                person_item.setData(0, Qt.UserRole, {"type": "person", "branch_key": branch_key, "label": label})

                # Load and set face thumbnail as icon
                icon = self._load_face_thumbnail(rep_path, rep_thumb_png)
                if icon:
                    person_item.setIcon(0, icon)
                else:
                    # Fallback to emoji icon if no thumbnail available
                    person_item.setText(0, f"👤 {display_name} ({count})")

                self.people_tree.addTopLevelItem(person_item)

        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error building people tree: {e}")
            import traceback
            traceback.print_exc()

    def _load_face_thumbnail(self, rep_path: str, rep_thumb_png: bytes) -> QIcon:
        """
        Load face thumbnail from rep_path or rep_thumb_png BLOB.

        Args:
            rep_path: Path to representative face crop image
            rep_thumb_png: PNG thumbnail as BLOB data

        Returns:
            QIcon with face thumbnail, or None if unavailable
        """
        try:
            from PIL import Image
            import io

            # Try loading from BLOB first (faster, already in DB)
            if rep_thumb_png:
                try:
                    # Load from BLOB
                    image_data = io.BytesIO(rep_thumb_png)
                    with Image.open(image_data) as img:
                        # Convert to QPixmap
                        img_rgb = img.convert('RGB')
                        data = img_rgb.tobytes('raw', 'RGB')
                        qimg = QImage(data, img.width, img.height, QImage.Format_RGB888)
                        pixmap = QPixmap.fromImage(qimg)

                        # Scale to tree item size (32x32 for better visibility)
                        scaled = pixmap.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        return QIcon(scaled)
                except Exception as blob_error:
                    print(f"[GooglePhotosLayout] Failed to load thumbnail from BLOB: {blob_error}")

            # Fallback: Try loading from file path
            if rep_path and os.path.exists(rep_path):
                try:
                    with Image.open(rep_path) as img:
                        # Convert to QPixmap
                        img_rgb = img.convert('RGB')
                        data = img_rgb.tobytes('raw', 'RGB')
                        qimg = QImage(data, img.width, img.height, QImage.Format_RGB888)
                        pixmap = QPixmap.fromImage(qimg)

                        # Scale to tree item size
                        scaled = pixmap.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        return QIcon(scaled)
                except Exception as file_error:
                    print(f"[GooglePhotosLayout] Failed to load thumbnail from {rep_path}: {file_error}")

            return None

        except Exception as e:
            print(f"[GooglePhotosLayout] Error loading face thumbnail: {e}")
            return None

    def _on_people_item_clicked(self, item: QTreeWidgetItem, column: int):
        """
        Handle people tree item click - filter by person/face cluster.

        Args:
            item: Clicked tree item
            column: Column index (always 0)
        """
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        branch_key = data.get("branch_key")
        if branch_key:
            label = data.get("label") or "Unnamed Person"
            print(f"[GooglePhotosLayout] Filtering by person: {label} (branch_key={branch_key})")
            self._load_photos(
                thumb_size=self.current_thumb_size,
                filter_year=None,
                filter_month=None,
                filter_folder=None,
                filter_person=branch_key
            )

    def _on_section_header_clicked(self):
        """
        Handle section header click - clear all filters and show all photos.

        Based on Google Photos UX: Clicking section headers returns to "All Photos" view.
        """
        print("[GooglePhotosLayout] Section header clicked - clearing all filters")

        # Clear all filters
        self._load_photos(
            thumb_size=self.current_thumb_size,
            filter_year=None,
            filter_month=None,
            filter_folder=None,
            filter_person=None
        )

        # Also clear search box
        if self.search_box.text():
            self.search_box.clear()

    def _build_videos_tree(self):
        """
        Build videos tree in sidebar with filters (copied from Current Layout).

        Features:
        - All Videos
        - By Duration (Short/Medium/Long)
        - By Resolution (SD/HD/FHD/4K)
        - By Date (Year/Month hierarchy)
        """
        try:
            from services.video_service import VideoService
            video_service = VideoService()

            print(f"[GoogleLayout] Loading videos for project_id={self.project_id}")
            videos = video_service.get_videos_by_project(self.project_id) if self.project_id else []
            total_videos = len(videos)
            print(f"[GoogleLayout] Found {total_videos} videos in project {self.project_id}")

            if not videos:
                # No videos - show message
                no_videos_item = QTreeWidgetItem(["  (No videos yet)"])
                no_videos_item.setForeground(0, QColor("#888888"))
                self.videos_tree.addTopLevelItem(no_videos_item)
                return

            # All Videos
            all_item = QTreeWidgetItem([f"All Videos ({total_videos})"])
            all_item.setData(0, Qt.UserRole, {"type": "all_videos"})
            self.videos_tree.addTopLevelItem(all_item)

            # By Duration
            short_videos = [v for v in videos if v.get('duration_seconds') and v['duration_seconds'] < 30]
            medium_videos = [v for v in videos if v.get('duration_seconds') and 30 <= v['duration_seconds'] < 300]
            long_videos = [v for v in videos if v.get('duration_seconds') and v['duration_seconds'] >= 300]

            if short_videos or medium_videos or long_videos:
                duration_parent = QTreeWidgetItem([f"⏱️ By Duration"])
                self.videos_tree.addTopLevelItem(duration_parent)

                if short_videos:
                    short_item = QTreeWidgetItem([f"  Short < 30s ({len(short_videos)})"])
                    short_item.setData(0, Qt.UserRole, {"type": "duration", "key": "short", "videos": short_videos})
                    duration_parent.addChild(short_item)

                if medium_videos:
                    medium_item = QTreeWidgetItem([f"  Medium 30s-5m ({len(medium_videos)})"])
                    medium_item.setData(0, Qt.UserRole, {"type": "duration", "key": "medium", "videos": medium_videos})
                    duration_parent.addChild(medium_item)

                if long_videos:
                    long_item = QTreeWidgetItem([f"  Long > 5m ({len(long_videos)})"])
                    long_item.setData(0, Qt.UserRole, {"type": "duration", "key": "long", "videos": long_videos})
                    duration_parent.addChild(long_item)

            # By Resolution
            sd_videos = [v for v in videos if v.get('width') and v.get('height') and v['height'] < 720]
            hd_videos = [v for v in videos if v.get('width') and v.get('height') and 720 <= v['height'] < 1080]
            fhd_videos = [v for v in videos if v.get('width') and v.get('height') and 1080 <= v['height'] < 2160]
            uhd_videos = [v for v in videos if v.get('width') and v.get('height') and v['height'] >= 2160]

            if sd_videos or hd_videos or fhd_videos or uhd_videos:
                res_parent = QTreeWidgetItem([f"📺 By Resolution"])
                self.videos_tree.addTopLevelItem(res_parent)

                if sd_videos:
                    sd_item = QTreeWidgetItem([f"  SD < 720p ({len(sd_videos)})"])
                    sd_item.setData(0, Qt.UserRole, {"type": "resolution", "key": "sd", "videos": sd_videos})
                    res_parent.addChild(sd_item)

                if hd_videos:
                    hd_item = QTreeWidgetItem([f"  HD 720p ({len(hd_videos)})"])
                    hd_item.setData(0, Qt.UserRole, {"type": "resolution", "key": "hd", "videos": hd_videos})
                    res_parent.addChild(hd_item)

                if fhd_videos:
                    fhd_item = QTreeWidgetItem([f"  Full HD 1080p ({len(fhd_videos)})"])
                    fhd_item.setData(0, Qt.UserRole, {"type": "resolution", "key": "fhd", "videos": fhd_videos})
                    res_parent.addChild(fhd_item)

                if uhd_videos:
                    uhd_item = QTreeWidgetItem([f"  4K 2160p+ ({len(uhd_videos)})"])
                    uhd_item.setData(0, Qt.UserRole, {"type": "resolution", "key": "4k", "videos": uhd_videos})
                    res_parent.addChild(uhd_item)

            # By Date (Year/Month hierarchy)
            try:
                from reference_db import ReferenceDB
                db = ReferenceDB()
                video_hier = db.get_video_date_hierarchy(self.project_id) or {}

                if video_hier:
                    date_parent = QTreeWidgetItem([f"📅 By Date"])
                    self.videos_tree.addTopLevelItem(date_parent)

                    for year in sorted(video_hier.keys(), key=lambda y: int(str(y)), reverse=True):
                        year_count = db.count_videos_for_year(year, self.project_id)
                        year_item = QTreeWidgetItem([f"  {year} ({year_count})"])
                        year_item.setData(0, Qt.UserRole, {"type": "video_year", "year": year})
                        date_parent.addChild(year_item)

                        # Month nodes under year
                        months = video_hier[year]
                        for month in sorted(months.keys(), key=lambda m: int(str(m))):
                            month_label = f"{int(month):02d}"
                            month_count = db.count_videos_for_month(year, month, self.project_id)
                            month_item = QTreeWidgetItem([f"    {month_label} ({month_count})"])
                            month_item.setData(0, Qt.UserRole, {"type": "video_month", "year": year, "month": month_label})
                            year_item.addChild(month_item)
            except Exception as e:
                print(f"[GoogleLayout] Failed to build video date hierarchy: {e}")

            print(f"[GoogleLayout] Built videos tree with {total_videos} videos")

        except Exception as e:
            print(f"[GoogleLayout] ⚠️ Error building videos tree: {e}")
            import traceback
            traceback.print_exc()

    def _on_videos_header_clicked(self):
        """
        Handle videos header click - show all videos in timeline.
        """
        print("[GoogleLayout] Videos header clicked - loading all videos")

        try:
            from services.video_service import VideoService
            video_service = VideoService()

            videos = video_service.get_videos_by_project(self.project_id) if self.project_id else []
            print(f"[GoogleLayout] Loading {len(videos)} videos")

            if not videos:
                print("[GoogleLayout] No videos found")
                return

            # Show videos in timeline (will need to implement video display)
            self._show_videos_in_timeline(videos)

        except Exception as e:
            print(f"[GoogleLayout] ⚠️ Error loading videos: {e}")
            import traceback
            traceback.print_exc()

    def _on_videos_item_clicked(self, item: QTreeWidgetItem, column: int):
        """
        Handle videos tree item click - filter/show videos.

        Args:
            item: Clicked tree item
            column: Column index (always 0)
        """
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        item_type = data.get("type")

        if item_type == "all_videos":
            print("[GoogleLayout] Showing all videos")
            try:
                from services.video_service import VideoService
                video_service = VideoService()
                videos = video_service.get_videos_by_project(self.project_id) if self.project_id else []
                self._show_videos_in_timeline(videos)
            except Exception as e:
                print(f"[GoogleLayout] Error loading all videos: {e}")

        elif item_type in ["duration", "resolution"]:
            videos = data.get("videos", [])
            print(f"[GoogleLayout] Showing {len(videos)} videos filtered by {item_type}")
            self._show_videos_in_timeline(videos)

        elif item_type == "video_year":
            year = data.get("year")
            print(f"[GoogleLayout] Showing videos from year {year}")
            try:
                from reference_db import ReferenceDB
                from services.video_service import VideoService
                db = ReferenceDB()
                video_service = VideoService()

                # Get all videos for this year
                all_videos = video_service.get_videos_by_project(self.project_id)
                year_videos = [v for v in all_videos if v.get('created_date', '').startswith(str(year))]
                self._show_videos_in_timeline(year_videos)
            except Exception as e:
                print(f"[GoogleLayout] Error loading videos for year {year}: {e}")

        elif item_type == "video_month":
            year = data.get("year")
            month = data.get("month")
            print(f"[GoogleLayout] Showing videos from {year}-{month}")
            try:
                from services.video_service import VideoService
                video_service = VideoService()

                all_videos = video_service.get_videos_by_project(self.project_id)
                month_videos = [v for v in all_videos if v.get('created_date', '').startswith(f"{year}-{month}")]
                self._show_videos_in_timeline(month_videos)
            except Exception as e:
                print(f"[GoogleLayout] Error loading videos for {year}-{month}: {e}")

    def _show_videos_in_timeline(self, videos: list):
        """
        Display videos in the timeline (similar to photos).

        Args:
            videos: List of video dictionaries from VideoService
        """
        print(f"[GoogleLayout] Showing {len(videos)} videos in timeline")

        # Clear existing timeline
        try:
            while self.timeline_layout.count():
                child = self.timeline_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
        except Exception as e:
            print(f"[GoogleLayout] Error clearing timeline: {e}")

        if not videos:
            # Show empty state
            empty_label = QLabel("🎬 No videos found")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet("font-size: 12pt; color: #888; padding: 60px;")
            self.timeline_layout.addWidget(empty_label)
            return

        # Group videos by date
        videos_by_date = defaultdict(list)
        for video in videos:
            date = video.get('created_date', 'No Date')
            if date and date != 'No Date':
                # Extract just the date part (YYYY-MM-DD)
                date = date.split(' ')[0] if ' ' in date else date
            videos_by_date[date].append(video)

        # Create date groups for videos
        for date_str in sorted(videos_by_date.keys(), reverse=True):
            date_videos = videos_by_date[date_str]
            date_group = self._create_video_date_group(date_str, date_videos)
            self.timeline_layout.addWidget(date_group)

        # Add spacer at bottom
        self.timeline_layout.addStretch()

    def _create_video_date_group(self, date_str: str, videos: list) -> QWidget:
        """
        Create a date group widget for videos (header + video grid).

        Args:
            date_str: Date string "YYYY-MM-DD"
            videos: List of video dictionaries
        """
        group = QFrame()
        group.setStyleSheet("""
            QFrame {
                background: white;
                border: 1px solid #e8eaed;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(group)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(12)

        # Header
        try:
            date_obj = datetime.fromisoformat(date_str)
            formatted_date = date_obj.strftime("%B %d, %Y (%A)")
        except:
            formatted_date = date_str

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        date_label = QLabel(f"📅 {formatted_date}")
        date_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #202124;")
        header_layout.addWidget(date_label)

        count_label = QLabel(f"({len(videos)} video{'s' if len(videos) != 1 else ''})")
        count_label.setStyleSheet("font-size: 10pt; color: #5f6368; margin-left: 8px;")
        header_layout.addWidget(count_label)

        header_layout.addStretch()
        layout.addWidget(header)

        # Video grid (QUICK WIN #2: Also responsive)
        grid_container = QWidget()
        grid = QGridLayout(grid_container)
        grid.setSpacing(2)  # GOOGLE PHOTOS STYLE: Minimal spacing
        grid.setContentsMargins(0, 0, 0, 0)

        # QUICK WIN #2: Responsive columns for videos too
        columns = self._calculate_responsive_columns(200)  # Use standard 200px thumb size

        for i, video in enumerate(videos):
            row = i // columns
            col = i % columns

            # Create video thumbnail widget
            video_thumb = self._create_video_thumbnail(video)
            grid.addWidget(video_thumb, row, col)

        layout.addWidget(grid_container)

        return group

    def _create_video_thumbnail(self, video: dict) -> QWidget:
        """
        Create a video thumbnail widget with play icon overlay.

        Args:
            video: Video dictionary with path, duration, etc.
        """
        thumb_widget = QLabel()
        thumb_widget.setFixedSize(200, 200)
        thumb_widget.setAlignment(Qt.AlignCenter)
        thumb_widget.setStyleSheet("""
            QLabel {
                background: #f8f9fa;
                border: 1px solid #e8eaed;
                border-radius: 4px;
            }
            QLabel:hover {
                border: 2px solid #1a73e8;
            }
        """)

        # Set mouse cursor programmatically (Qt doesn't support cursor in stylesheets)
        from PySide6.QtCore import Qt as QtCore
        thumb_widget.setCursor(QtCore.PointingHandCursor)

        # Load video thumbnail
        video_path = video.get('path', '')

        try:
            # Try to load video thumbnail from video thumbnail service
            from services.video_thumbnail_service import get_video_thumbnail_service
            thumb_service = get_video_thumbnail_service()
            thumb_path = thumb_service.get_thumbnail_path(video_path)

            if thumb_path and os.path.exists(thumb_path):
                pixmap = QPixmap(str(thumb_path))
                if not pixmap.isNull():
                    scaled = pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    thumb_widget.setPixmap(scaled)
                else:
                    thumb_widget.setText("🎬\nVideo")
            else:
                thumb_widget.setText("🎬\nVideo")
        except Exception as e:
            print(f"[GoogleLayout] Error loading video thumbnail for {video_path}: {e}")
            thumb_widget.setText("🎬\nVideo")

        # FIXED: Open lightbox instead of video player directly
        # This allows browsing through mixed photos and videos
        thumb_widget.mousePressEvent = lambda event: self._open_photo_lightbox(video_path)

        return thumb_widget

    def _open_video_player(self, video_path: str):
        """
        Open video player for the given video path with navigation support.

        Args:
            video_path: Path to video file
        """
        print(f"[GoogleLayout] 🎬 Opening video player for: {video_path}")

        try:
            # Get all videos for navigation
            from services.video_service import VideoService
            video_service = VideoService()

            all_videos = video_service.get_videos_by_project(self.project_id) if self.project_id else []
            video_paths = [v['path'] for v in all_videos]

            # Find current video index
            start_index = 0
            try:
                start_index = video_paths.index(video_path)
            except ValueError:
                print(f"[GoogleLayout] ⚠️ Video not found in list, using index 0")

            print(f"[GoogleLayout] Found {len(video_paths)} videos, current index: {start_index}")

            # Check if main_window is accessible
            if not hasattr(self, 'main_window') or self.main_window is None:
                print("[GoogleLayout] ⚠️ ERROR: main_window not accessible")
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(None, "Video Player Error",
                    "Cannot open video player: Main window not accessible.\n\n"
                    "Try switching to Current Layout to play videos.")
                return

            # Check if _open_video_player method exists
            if not hasattr(self.main_window, '_open_video_player'):
                print("[GoogleLayout] ⚠️ ERROR: main_window doesn't have _open_video_player method")
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(None, "Video Player Error",
                    "Video player not available in this layout.\n\n"
                    "Try switching to Current Layout to play videos.")
                return

            # Open video player with navigation support
            self.main_window._open_video_player(video_path, video_paths, start_index)
            print(f"[GoogleLayout] ✓ Video player opened successfully")

        except Exception as e:
            print(f"[GoogleLayout] ⚠️ ERROR opening video player: {e}")
            import traceback
            traceback.print_exc()

            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(None, "Video Player Error",
                f"Failed to open video player:\n\n{str(e)}\n\n"
                "Check console for details.")

    def _create_date_group(self, date_str: str, photos: List[Tuple], thumb_size: int = 200) -> QWidget:
        """
        Create a date group widget (header + photo grid).

        QUICK WIN #4: Now supports collapse/expand functionality.

        Args:
            date_str: Date string "YYYY-MM-DD"
            photos: List of (path, date_taken, width, height)
        """
        group = QFrame()
        group.setStyleSheet("""
            QFrame {
                background: white;
                border: 1px solid #e8eaed;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(group)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(12)

        # QUICK WIN #4: Initialize collapse state (default: expanded)
        if date_str not in self.date_group_collapsed:
            self.date_group_collapsed[date_str] = False  # False = expanded

        # Header (with collapse/expand button)
        header = self._create_date_header(date_str, len(photos))
        layout.addWidget(header)

        # Photo grid (pass thumb_size)
        grid = self._create_photo_grid(photos, thumb_size)
        layout.addWidget(grid)

        # QUICK WIN #4: Store grid reference for collapse/expand
        self.date_group_grids[date_str] = grid

        # Apply initial collapse state
        if self.date_group_collapsed.get(date_str, False):
            grid.hide()

        return group

    def _create_date_header(self, date_str: str, count: int) -> QWidget:
        """
        Create date group header with date and photo count.

        QUICK WIN #4: Now includes collapse/expand button.
        """
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        # QUICK WIN #4: Collapse/Expand button (▼ = expanded, ► = collapsed)
        collapse_btn = QPushButton()
        is_collapsed = self.date_group_collapsed.get(date_str, False)
        collapse_btn.setText("►" if is_collapsed else "▼")
        collapse_btn.setFixedSize(24, 24)
        collapse_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                font-size: 12pt;
                color: #5f6368;
                padding: 0;
            }
            QPushButton:hover {
                color: #202124;
                background: #f1f3f4;
                border-radius: 4px;
            }
        """)
        collapse_btn.setCursor(Qt.PointingHandCursor)
        collapse_btn.clicked.connect(lambda: self._toggle_date_group(date_str, collapse_btn))
        header_layout.addWidget(collapse_btn)

        # Format date nicely
        try:
            date_obj = datetime.fromisoformat(date_str)
            formatted_date = date_obj.strftime("%B %d, %Y (%A)")
        except:
            formatted_date = date_str

        # Date label (clickable for collapse/expand)
        date_label = QLabel(f"📅 {formatted_date}")
        date_label.setStyleSheet("""
            font-size: 14pt;
            font-weight: bold;
            color: #202124;
            padding: 4px;
        """)
        date_label.setCursor(Qt.PointingHandCursor)
        date_label.mousePressEvent = lambda e: self._toggle_date_group(date_str, collapse_btn)
        header_layout.addWidget(date_label)

        # Photo count
        count_label = QLabel(f"({count} photo{'s' if count != 1 else ''})")
        count_label.setStyleSheet("font-size: 10pt; color: #5f6368; margin-left: 8px;")
        header_layout.addWidget(count_label)

        header_layout.addStretch()

        return header

    def _toggle_date_group(self, date_str: str, collapse_btn: QPushButton):
        """
        QUICK WIN #4: Toggle collapse/expand state for a date group.

        Args:
            date_str: Date string "YYYY-MM-DD"
            collapse_btn: The collapse/expand button widget
        """
        try:
            # Get current state
            is_collapsed = self.date_group_collapsed.get(date_str, False)
            new_state = not is_collapsed

            # Update state
            self.date_group_collapsed[date_str] = new_state

            # Get grid widget
            grid = self.date_group_grids.get(date_str)
            if not grid:
                print(f"[GooglePhotosLayout] ⚠️ Grid not found for {date_str}")
                return

            # Toggle visibility
            if new_state:  # Collapsing
                grid.hide()
                collapse_btn.setText("►")
                print(f"[GooglePhotosLayout] ▲ Collapsed date group: {date_str}")
            else:  # Expanding
                grid.show()
                collapse_btn.setText("▼")
                print(f"[GooglePhotosLayout] ▼ Expanded date group: {date_str}")

        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error toggling date group {date_str}: {e}")

    def _create_date_group_placeholder(self, metadata: dict) -> QWidget:
        """
        QUICK WIN #3: Create placeholder widget for virtual scrolling.

        Placeholder maintains scroll position by matching estimated group height.
        Will be replaced with actual rendered group when it enters viewport.

        Args:
            metadata: Dict with date_str, photos, thumb_size, index

        Returns:
            QWidget: Placeholder with estimated height
        """
        placeholder = QWidget()

        # Estimate height based on photo count
        estimated_height = self._estimate_date_group_height(
            len(metadata['photos']),
            metadata['thumb_size']
        )

        placeholder.setFixedHeight(estimated_height)
        placeholder.setStyleSheet("background: #f8f9fa;")  # Light gray placeholder

        # Store metadata on widget for lazy rendering
        placeholder.setProperty('date_group_metadata', metadata)
        placeholder.setProperty('is_placeholder', True)

        return placeholder

    def _estimate_date_group_height(self, photo_count: int, thumb_size: int) -> int:
        """
        QUICK WIN #3: Estimate date group height for placeholder sizing.

        Height = header + grid + margins
        - Header: ~60px (date label + spacing)
        - Grid: rows * (thumb_size + spacing)
        - Margins: 28px (16 top, 12 bottom from layout.setContentsMargins)

        Args:
            photo_count: Number of photos in group
            thumb_size: Thumbnail size in pixels

        Returns:
            int: Estimated height in pixels
        """
        # Calculate responsive columns (same as grid rendering)
        columns = self._calculate_responsive_columns(thumb_size)

        # Calculate number of rows needed
        rows = (photo_count + columns - 1) // columns  # Ceiling division

        # Component heights
        header_height = 60  # Date label + spacing
        spacing = 2  # GOOGLE PHOTOS STYLE
        grid_height = rows * (thumb_size + spacing)
        margins = 28  # 16 + 12 from setContentsMargins
        border = 2  # 1px border top + bottom

        total_height = header_height + grid_height + margins + border

        return total_height

    def _render_visible_date_groups(self, viewport, viewport_rect):
        """
        QUICK WIN #3: Render date groups that are visible in viewport.

        Checks which date groups intersect with the viewport and replaces
        placeholders with actual rendered groups.

        Args:
            viewport: Timeline viewport widget
            viewport_rect: Viewport rectangle
        """
        try:
            groups_to_render = []

            # Check each date group to see if it's visible
            for metadata in self.date_groups_metadata:
                index = metadata['index']

                # Skip if already rendered
                if index in self.rendered_date_groups:
                    continue

                # Get the widget (placeholder)
                widget = self.date_group_widgets.get(index)
                if not widget:
                    continue

                # Check if widget is visible in viewport
                try:
                    # Map widget position to viewport coordinates
                    widget_pos = widget.mapTo(viewport, widget.rect().topLeft())
                    widget_rect = widget.rect()
                    widget_rect.moveTo(widget_pos)

                    # If widget intersects viewport, it's visible
                    if viewport_rect.intersects(widget_rect):
                        groups_to_render.append((index, metadata))

                except Exception as e:
                    continue

            # Render visible groups
            if groups_to_render:
                print(f"[GooglePhotosLayout] 🎨 Rendering {len(groups_to_render)} date groups that entered viewport...")

                for index, metadata in groups_to_render:
                    try:
                        # Create actual rendered group
                        rendered_group = self._create_date_group(
                            metadata['date_str'],
                            metadata['photos'],
                            metadata['thumb_size']
                        )

                        # Replace placeholder with rendered group in layout
                        old_widget = self.date_group_widgets[index]
                        layout_index = self.timeline_layout.indexOf(old_widget)

                        if layout_index != -1:
                            # Remove placeholder
                            self.timeline_layout.removeWidget(old_widget)
                            old_widget.deleteLater()

                            # Insert rendered group at same position
                            self.timeline_layout.insertWidget(layout_index, rendered_group)
                            self.date_group_widgets[index] = rendered_group
                            self.rendered_date_groups.add(index)

                    except Exception as e:
                        print(f"[GooglePhotosLayout] ⚠️ Error rendering date group {index}: {e}")
                        continue

                print(f"[GooglePhotosLayout] ✓ Now {len(self.rendered_date_groups)}/{len(self.date_groups_metadata)} groups rendered")

        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error in virtual scrolling: {e}")

    def _create_photo_grid(self, photos: List[Tuple], thumb_size: int = 200) -> QWidget:
        """
        Create photo grid with thumbnails.

        QUICK WIN #2: Responsive grid that adapts to viewport width.
        Google Photos Style: Minimal spacing for dense, clean grid.
        """
        grid_container = QWidget()
        grid = QGridLayout(grid_container)
        grid.setSpacing(2)  # GOOGLE PHOTOS STYLE: Minimal padding
        grid.setContentsMargins(0, 0, 0, 0)

        # QUICK WIN #2: Calculate responsive columns based on viewport width
        # This makes the grid perfect on 1080p, 4K, mobile, etc.
        columns = self._calculate_responsive_columns(thumb_size)

        # Store grid reference for resize handling (QUICK WIN #2)
        if not hasattr(self, '_photo_grids'):
            self._photo_grids = []
        self._photo_grids.append({
            'container': grid_container,
            'grid': grid,
            'photos': photos,
            'thumb_size': thumb_size,
            'columns': columns
        })

        # Add photo thumbnails
        for i, photo in enumerate(photos):
            path, date_taken, width, height = photo

            row = i // columns
            col = i % columns

            thumb = self._create_thumbnail(path, thumb_size)
            grid.addWidget(thumb, row, col)

        return grid_container

    def _calculate_responsive_columns(self, thumb_size: int) -> int:
        """
        QUICK WIN #2: Calculate optimal column count based on viewport width.

        Algorithm (matches Google Photos):
        - Get available width from timeline viewport
        - Calculate how many thumbnails fit
        - Enforce min/max constraints (2-8 columns)
        - Account for spacing and margins

        Args:
            thumb_size: Thumbnail width in pixels

        Returns:
            int: Optimal number of columns (2-8)
        """
        # Get viewport width (timeline scroll area)
        if hasattr(self, 'timeline_scroll'):
            viewport_width = self.timeline_scroll.viewport().width()
        else:
            # Fallback during initialization
            viewport_width = 1200  # Reasonable default

        # Account for margins (20px left + 20px right from timeline_layout)
        available_width = viewport_width - 40

        # Account for grid spacing (2px between each thumbnail)
        spacing = 2

        # Calculate how many thumbnails fit
        # Formula: (width - margins) / (thumb_size + spacing)
        cols = int(available_width / (thumb_size + spacing))

        # Enforce constraints
        # Min: 2 columns (prevents single-column on small screens)
        # Max: 8 columns (prevents tiny thumbnails on huge screens)
        cols = max(2, min(8, cols))

        print(f"[GooglePhotosLayout] 📐 Responsive grid: {cols} columns (viewport: {viewport_width}px, thumb: {thumb_size}px)")

        return cols

    def _on_thumbnail_loaded(self, path: str, pixmap: QPixmap, size: int):
        """Callback when async thumbnail loading completes."""
        # Find the button for this path
        button = self.thumbnail_buttons.get(path)
        if not button:
            return  # Button was destroyed (e.g., during reload)

        try:
            # Update button with loaded thumbnail
            if pixmap and not pixmap.isNull():
                scaled = pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                button.setIcon(QIcon(scaled))
                button.setIconSize(QSize(size - 4, size - 4))
                button.setText("")  # Clear placeholder text
            else:
                button.setText("📷")  # No thumbnail - show placeholder
        except Exception as e:
            print(f"[GooglePhotosLayout] Error updating thumbnail for {path}: {e}")
            button.setText("❌")

    def _on_timeline_scrolled(self):
        """
        QUICK WIN #5: Debounced scroll handler for smooth 60 FPS performance.

        Instead of processing every scroll event (which can be hundreds per second),
        we restart a timer on each scroll. Only when scrolling stops (or slows down)
        for 150ms do we actually process the heavy operations.

        This prevents lag and dropped frames during fast scrolling.
        """
        # Restart debounce timer - will trigger _on_scroll_debounced() after 150ms of no scrolling
        self.scroll_debounce_timer.stop()
        self.scroll_debounce_timer.start(self.scroll_debounce_delay)

    def _on_scroll_debounced(self):
        """
        QUICK WIN #1, #3, #5: Process scroll events after debouncing.

        This is called 150ms after scrolling stops/slows down.

        Two functions:
        1. Load thumbnails that are now visible (Quick Win #1)
        2. Render date groups that entered viewport (Quick Win #3)
        """
        # Get viewport rectangle
        viewport = self.timeline_scroll.viewport()
        viewport_rect = viewport.rect()

        # QUICK WIN #3: Virtual scrolling - render date groups that entered viewport
        if self.virtual_scroll_enabled and self.date_groups_metadata:
            self._render_visible_date_groups(viewport, viewport_rect)

        # QUICK WIN #1: Lazy thumbnail loading
        if not self.unloaded_thumbnails:
            return  # All thumbnails already loaded

        # QUICK WIN #5: Limit checks to prevent lag with huge libraries
        # Only check first 200 unloaded items per scroll event
        # This balances responsiveness vs performance
        max_checks = 200
        items_to_check = list(self.unloaded_thumbnails.items())[:max_checks]

        # Find and load visible thumbnails
        paths_to_load = []
        for path, (button, size) in items_to_check:
            # Check if button is visible in viewport
            try:
                # Map button position to viewport coordinates
                button_pos = button.mapTo(viewport, button.rect().topLeft())
                button_rect = button.rect()
                button_rect.moveTo(button_pos)

                # If button intersects viewport, it's visible
                if viewport_rect.intersects(button_rect):
                    paths_to_load.append(path)

            except Exception as e:
                # Button might have been deleted
                continue

        # Load visible thumbnails
        if paths_to_load:
            print(f"[GooglePhotosLayout] 📜 Scroll detected, loading {len(paths_to_load)} visible thumbnails...")
            for path in paths_to_load:
                button, size = self.unloaded_thumbnails.pop(path)
                # Queue async loading
                loader = ThumbnailLoader(path, size, self.thumbnail_signals)
                self.thumbnail_thread_pool.start(loader)

            print(f"[GooglePhotosLayout] ✓ Loaded {len(paths_to_load)} thumbnails, {len(self.unloaded_thumbnails)} remaining")

    def _create_thumbnail(self, path: str, size: int) -> QWidget:
        """
        Create thumbnail widget for a photo with selection checkbox.

        Phase 2: Enhanced with checkbox overlay for batch selection.
        Phase 3: ASYNC thumbnail loading to prevent UI freeze with large photo sets.
        """
        from PySide6.QtWidgets import QCheckBox, QVBoxLayout

        # Container widget
        container = QWidget()
        container.setFixedSize(size, size)
        container.setStyleSheet("background: transparent;")

        # Thumbnail button with placeholder
        thumb = QPushButton(container)
        thumb.setGeometry(0, 0, size, size)
        # QUICK WIN #8: Modern hover effects with smooth transitions
        # QUICK WIN #9: Skeleton loading state with gradient
        thumb.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #e8eaed, stop:0.5 #f1f3f4, stop:1 #e8eaed);
                border: 2px solid #dadce0;
                border-radius: 4px;
                color: #5f6368;
                font-size: 9pt;
            }
            QPushButton:hover {
                background: #ffffff;
                border-color: #1a73e8;
                border-width: 2px;
            }
        """)
        thumb.setCursor(Qt.PointingHandCursor)

        # QUICK WIN #9: Skeleton loading indicator (subtle, professional)
        thumb.setText("⏳")

        # Store button for async update
        self.thumbnail_buttons[path] = thumb

        # QUICK WIN #1: Load first 50 immediately, rest on scroll
        # This removes the 30-photo limit while maintaining initial performance
        if self.thumbnail_load_count < self.initial_load_limit:
            self.thumbnail_load_count += 1
            # Queue async thumbnail loading with SHARED signal object
            loader = ThumbnailLoader(path, size, self.thumbnail_signals)
            self.thumbnail_thread_pool.start(loader)
        else:
            # Store for lazy loading on scroll
            self.unloaded_thumbnails[path] = (thumb, size)
            print(f"[GooglePhotosLayout] Deferred thumbnail #{self.thumbnail_load_count + 1}: {os.path.basename(path)}")

        # Phase 2: Selection checkbox (overlay top-left corner)
        # QUICK WIN #8: Enhanced with modern hover effects
        checkbox = QCheckBox(container)
        checkbox.setGeometry(8, 8, 24, 24)
        checkbox.setStyleSheet("""
            QCheckBox {
                background: rgba(255, 255, 255, 0.9);
                border: 2px solid #dadce0;
                border-radius: 4px;
                padding: 2px;
            }
            QCheckBox:hover {
                background: rgba(255, 255, 255, 1.0);
                border-color: #1a73e8;
            }
            QCheckBox:checked {
                background: #1a73e8;
                border-color: #1a73e8;
            }
            QCheckBox:checked:hover {
                background: #1557b0;
                border-color: #1557b0;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
        """)
        checkbox.setCursor(Qt.PointingHandCursor)
        checkbox.setVisible(self.selection_mode)  # Only visible in selection mode

        # Store references
        container.setProperty("photo_path", path)
        container.setProperty("thumbnail_button", thumb)
        container.setProperty("checkbox", checkbox)

        # Connect signals
        thumb.clicked.connect(lambda: self._on_photo_clicked(path))
        checkbox.stateChanged.connect(lambda state: self._on_selection_changed(path, state))

        return container

    def _on_photo_clicked(self, path: str):
        """
        Handle photo thumbnail click with Shift+Ctrl multi-selection support.

        - Normal click: Open lightbox
        - Ctrl+Click: Add/remove from selection (toggle)
        - Shift+Click: Range select from last selected to current
        - Selection mode: Toggle selection
        """
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt

        print(f"[GooglePhotosLayout] Photo clicked: {path}")

        # Get keyboard modifiers
        modifiers = QApplication.keyboardModifiers()
        ctrl_pressed = bool(modifiers & Qt.ControlModifier)
        shift_pressed = bool(modifiers & Qt.ShiftModifier)

        # SHIFT+CLICK: Range selection (from last selected to current)
        if shift_pressed and self.last_selected_path and self.all_displayed_paths:
            print(f"[GooglePhotosLayout] Shift+Click range selection from {self.last_selected_path} to {path}")
            try:
                # Find indices of last selected and current photo
                last_idx = self.all_displayed_paths.index(self.last_selected_path)
                current_idx = self.all_displayed_paths.index(path)

                # Select all photos in range
                start_idx = min(last_idx, current_idx)
                end_idx = max(last_idx, current_idx)

                for idx in range(start_idx, end_idx + 1):
                    range_path = self.all_displayed_paths[idx]
                    if range_path not in self.selected_photos:
                        self.selected_photos.add(range_path)
                        self._update_checkbox_state(range_path, True)

                self._update_selection_ui()
                print(f"[GooglePhotosLayout] ✓ Range selected: {end_idx - start_idx + 1} photos")
                return

            except (ValueError, IndexError) as e:
                print(f"[GooglePhotosLayout] ⚠️ Range selection error: {e}")
                # Fall through to normal selection

        # CTRL+CLICK: Toggle selection (add/remove)
        if ctrl_pressed:
            print(f"[GooglePhotosLayout] Ctrl+Click toggle selection: {path}")
            self._toggle_photo_selection(path)
            self.last_selected_path = path  # Update last selected for future Shift+Click
            return

        # NORMAL CLICK in selection mode: Toggle selection
        if self.selection_mode:
            self._toggle_photo_selection(path)
            self.last_selected_path = path
        else:
            # NORMAL CLICK: Open lightbox/preview
            self._open_photo_lightbox(path)

    def _open_photo_lightbox(self, path: str):
        """
        Open media lightbox/preview dialog (supports both photos AND videos).

        Args:
            path: Path to photo or video to display
        """
        print(f"[GooglePhotosLayout] 👁️ Opening lightbox for: {path}")

        # Collect all media paths (photos + videos) in timeline order
        all_media = self._get_all_media_paths()

        if not all_media:
            print("[GooglePhotosLayout] ⚠️ No media to display in lightbox")
            return

        # Create and show lightbox dialog
        try:
            lightbox = MediaLightbox(path, all_media, parent=self.main_window)
            lightbox.exec()
            print("[GooglePhotosLayout] ✓ MediaLightbox closed")

        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error opening lightbox: {e}")
            import traceback
            traceback.print_exc()

    def _get_all_media_paths(self) -> List[str]:
        """
        Get all media paths (photos + videos) in timeline order (newest to oldest).

        Returns:
            List of media paths
        """
        all_paths = []

        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()

            # Query all photos for current project, ordered by date
            photo_query = """
                SELECT DISTINCT pm.path
                FROM photo_metadata pm
                JOIN project_images pi ON pm.path = pi.image_path
                WHERE pi.project_id = ?
                AND pm.date_taken IS NOT NULL
                ORDER BY pm.date_taken DESC
            """

            # Query all videos for current project, ordered by date
            video_query = """
                SELECT DISTINCT path
                FROM video_metadata
                WHERE project_id = ?
                AND created_date IS NOT NULL
                ORDER BY created_date DESC
            """

            with db._connect() as conn:
                conn.execute("PRAGMA busy_timeout = 5000")
                cur = conn.cursor()

                # Get photos
                cur.execute(photo_query, (self.project_id,))
                photo_rows = cur.fetchall()
                photo_paths = [row[0] for row in photo_rows]

                # Get videos
                cur.execute(video_query, (self.project_id,))
                video_rows = cur.fetchall()
                video_paths = [row[0] for row in video_rows]

                # Combine and sort by date (already sorted individually, merge them)
                # For now, just append videos after photos (both are sorted by date desc)
                # TODO: Could merge-sort by actual date if needed
                all_paths = photo_paths + video_paths

                print(f"[GooglePhotosLayout] Found {len(photo_paths)} photos + {len(video_paths)} videos = {len(all_paths)} total media")

        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error fetching media paths: {e}")

        return all_paths

    def _on_selection_changed(self, path: str, state: int):
        """
        Handle checkbox selection change.

        Args:
            path: Photo path
            state: Qt.CheckState (0=unchecked, 2=checked)
        """
        from PySide6.QtCore import Qt

        if state == Qt.Checked:
            self.selected_photos.add(path)
            print(f"[GooglePhotosLayout] ✓ Selected: {path}")
        else:
            self.selected_photos.discard(path)
            print(f"[GooglePhotosLayout] ✗ Deselected: {path}")

        # Update selection counter and action buttons
        self._update_selection_ui()

    def _toggle_photo_selection(self, path: str):
        """
        Toggle photo selection and update checkbox.
        """
        # Find checkbox for this photo
        container = self._find_thumbnail_container(path)
        if container:
            checkbox = container.property("checkbox")
            if checkbox:
                # Toggle checkbox (will trigger _on_selection_changed)
                checkbox.setChecked(not checkbox.isChecked())

    def _find_thumbnail_container(self, path: str) -> QWidget:
        """
        Find thumbnail container widget by photo path.
        """
        # Iterate through all date groups to find the thumbnail
        for i in range(self.timeline_layout.count()):
            date_group = self.timeline_layout.itemAt(i).widget()
            if not date_group:
                continue

            # Find grid inside date group
            group_layout = date_group.layout()
            if not group_layout:
                continue

            for j in range(group_layout.count()):
                item = group_layout.itemAt(j)
                if not item or not item.widget():
                    continue

                widget = item.widget()
                if hasattr(widget, 'layout') and widget.layout():
                    # This is a grid container
                    grid = widget.layout()
                    for k in range(grid.count()):
                        container = grid.itemAt(k).widget()
                        if container and container.property("photo_path") == path:
                            return container

        return None

    def _update_checkbox_state(self, path: str, checked: bool):
        """
        Update checkbox state for a specific photo (for multi-selection support).

        Args:
            path: Photo path
            checked: True to check, False to uncheck
        """
        container = self._find_thumbnail_container(path)
        if container:
            checkbox = container.property("checkbox")
            if checkbox:
                # Update checkbox state without triggering signal
                checkbox.blockSignals(True)
                checkbox.setChecked(checked)
                checkbox.blockSignals(False)

    def _update_selection_ui(self):
        """
        Update selection counter and show/hide action buttons.

        QUICK WIN #6: Now also controls floating toolbar.
        """
        count = len(self.selected_photos)

        # Update toolbar selection counter (add if doesn't exist)
        if not hasattr(self, 'selection_label'):
            from PySide6.QtWidgets import QLabel
            self.selection_label = QLabel()
            self.selection_label.setStyleSheet("font-weight: bold; padding: 0 12px;")
            # Insert selection label in toolbar (after existing actions)
            toolbar = self._toolbar
            # Simply add to toolbar without complex index logic
            toolbar.addWidget(self.selection_label)

        # Update counter text
        if count > 0:
            self.selection_label.setText(f"✓ {count} selected")
            self.selection_label.setVisible(True)

            # Show action buttons
            self.btn_delete.setVisible(True)
            self.btn_favorite.setVisible(True)

            # QUICK WIN #6: Show and update floating toolbar
            if hasattr(self, 'floating_toolbar') and hasattr(self, 'selection_count_label'):
                self.selection_count_label.setText(f"{count} selected")
                self._position_floating_toolbar()
                self.floating_toolbar.show()
                self.floating_toolbar.raise_()  # Bring to front
        else:
            self.selection_label.setVisible(False)

            # Hide action buttons when nothing selected
            self.btn_delete.setVisible(False)
            self.btn_favorite.setVisible(False)

            # QUICK WIN #6: Hide floating toolbar when no selection
            if hasattr(self, 'floating_toolbar'):
                self.floating_toolbar.hide()

        print(f"[GooglePhotosLayout] Selection updated: {count} photos selected")

    def _position_floating_toolbar(self):
        """
        QUICK WIN #6: Position floating toolbar at bottom center of viewport.
        """
        if not hasattr(self, 'floating_toolbar'):
            return

        # Get parent widget size
        parent = self.floating_toolbar.parent()
        if not parent:
            return

        parent_width = parent.width()
        parent_height = parent.height()

        toolbar_width = self.floating_toolbar.width()
        toolbar_height = self.floating_toolbar.height()

        # Position at bottom center
        x = (parent_width - toolbar_width) // 2
        y = parent_height - toolbar_height - 20  # 20px from bottom

        self.floating_toolbar.move(x, y)

    def _on_select_all(self):
        """
        QUICK WIN #6: Select all visible photos.
        """
        # Select all displayed photos
        for path in self.all_displayed_paths:
            if path not in self.selected_photos:
                self.selected_photos.add(path)
                self._update_checkbox_state(path, True)

        self._update_selection_ui()
        print(f"[GooglePhotosLayout] ✓ Selected all {len(self.selected_photos)} photos")

    def _on_clear_selection(self):
        """
        QUICK WIN #6: Clear all selected photos.
        """
        # Deselect all photos
        for path in list(self.selected_photos):
            self._update_checkbox_state(path, False)

        self.selected_photos.clear()
        self._update_selection_ui()
        print("[GooglePhotosLayout] ✗ Cleared all selections")

    def keyPressEvent(self, event: QKeyEvent):
        """
        QUICK WIN #7: Keyboard navigation in photo grid.

        Shortcuts:
        - Ctrl+A: Select all photos
        - Escape: Clear selection
        - Delete: Delete selected photos
        - Ctrl+F: Focus search box
        - Enter: Open first selected photo in lightbox

        Args:
            event: QKeyEvent
        """
        key = event.key()
        modifiers = event.modifiers()

        # Ctrl+A: Select All
        if key == Qt.Key_A and modifiers == Qt.ControlModifier:
            print("[GooglePhotosLayout] ⌨️ Ctrl+A - Select all")
            self._on_select_all()
            event.accept()

        # Escape: Clear selection
        elif key == Qt.Key_Escape:
            if len(self.selected_photos) > 0:
                print("[GooglePhotosLayout] ⌨️ ESC - Clear selection")
                self._on_clear_selection()
                event.accept()
            else:
                super().keyPressEvent(event)

        # Delete: Delete selected photos
        elif key == Qt.Key_Delete:
            if len(self.selected_photos) > 0:
                print(f"[GooglePhotosLayout] ⌨️ DELETE - Delete {len(self.selected_photos)} photos")
                self._on_delete_selected()
                event.accept()
            else:
                super().keyPressEvent(event)

        # Ctrl+F: Focus search box
        elif key == Qt.Key_F and modifiers == Qt.ControlModifier:
            print("[GooglePhotosLayout] ⌨️ Ctrl+F - Focus search")
            if hasattr(self, 'search_box'):
                self.search_box.setFocus()
                self.search_box.selectAll()
            event.accept()

        # Enter: Open first selected photo
        elif key == Qt.Key_Return or key == Qt.Key_Enter:
            if len(self.selected_photos) > 0:
                first_photo = list(self.selected_photos)[0]
                print(f"[GooglePhotosLayout] ⌨️ ENTER - Open {first_photo}")
                self._on_photo_clicked(first_photo)
                event.accept()
            else:
                super().keyPressEvent(event)

        # S: Toggle selection mode
        elif key == Qt.Key_S and not modifiers:
            print("[GooglePhotosLayout] ⌨️ S - Toggle selection mode")
            if hasattr(self, 'btn_select'):
                self.btn_select.setChecked(not self.btn_select.isChecked())
                self._toggle_selection_mode(self.btn_select.isChecked())
            event.accept()

        else:
            # Pass to parent for other keys
            super().keyPressEvent(event)

    def _toggle_selection_mode(self, checked: bool):
        """
        Toggle selection mode on/off.

        Args:
            checked: Whether Select button is checked
        """
        self.selection_mode = checked
        print(f"[GooglePhotosLayout] Selection mode: {'ON' if checked else 'OFF'}")

        # Show/hide all checkboxes
        self._update_checkboxes_visibility()

        # Update button text
        if checked:
            self.btn_select.setText("☑️ Cancel")
            self.btn_select.setStyleSheet("QPushButton { background: #1a73e8; color: white; }")
        else:
            self.btn_select.setText("☑️ Select")
            self.btn_select.setStyleSheet("")

            # Clear selection when exiting selection mode
            self._clear_selection()

    def _update_checkboxes_visibility(self):
        """
        Show or hide all checkboxes based on selection mode.
        """
        # Iterate through all thumbnails
        for i in range(self.timeline_layout.count()):
            date_group = self.timeline_layout.itemAt(i).widget()
            if not date_group:
                continue

            group_layout = date_group.layout()
            if not group_layout:
                continue

            for j in range(group_layout.count()):
                item = group_layout.itemAt(j)
                if not item or not item.widget():
                    continue

                widget = item.widget()
                if hasattr(widget, 'layout') and widget.layout():
                    grid = widget.layout()
                    for k in range(grid.count()):
                        container = grid.itemAt(k).widget()
                        if container:
                            checkbox = container.property("checkbox")
                            if checkbox:
                                checkbox.setVisible(self.selection_mode)

    def _clear_selection(self):
        """
        Clear all selected photos and uncheck checkboxes.
        """
        # Uncheck all checkboxes
        for path in list(self.selected_photos):
            container = self._find_thumbnail_container(path)
            if container:
                checkbox = container.property("checkbox")
                if checkbox:
                    checkbox.setChecked(False)

        self.selected_photos.clear()
        self._update_selection_ui()

    def _on_delete_selected(self):
        """
        Delete all selected photos.
        """
        from PySide6.QtWidgets import QMessageBox

        if not self.selected_photos:
            return

        count = len(self.selected_photos)

        # Confirm deletion
        reply = QMessageBox.question(
            self.main_window,
            "Delete Photos",
            f"Are you sure you want to delete {count} photo{'s' if count > 1 else ''}?\n\n"
            "This will remove them from the database but NOT delete the actual files.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        print(f"[GooglePhotosLayout] Deleting {count} photos...")

        # TODO Phase 2: Implement actual deletion from database
        # For now, just clear selection and show message
        QMessageBox.information(
            self.main_window,
            "Delete Photos",
            f"{count} photo{'s' if count > 1 else ''} deleted successfully!\n\n"
            "(Note: Actual deletion not yet implemented - Phase 2 placeholder)"
        )

        self._clear_selection()
        self._load_photos()  # Refresh timeline

    def _on_favorite_selected(self):
        """
        Mark all selected photos as favorites.
        """
        from PySide6.QtWidgets import QMessageBox

        if not self.selected_photos:
            return

        count = len(self.selected_photos)

        print(f"[GooglePhotosLayout] Marking {count} photos as favorites...")

        # TODO Phase 2: Implement actual favorite tagging in database
        # For now, just show message
        QMessageBox.information(
            self.main_window,
            "Mark as Favorite",
            f"{count} photo{'s' if count > 1 else ''} marked as favorite!\n\n"
            "(Note: Favorite tagging not yet implemented - Phase 2 placeholder)"
        )

        self._clear_selection()

    # ============ Phase 2: Search Functionality ============

    def _on_search_text_changed(self, text: str):
        """
        Handle search text change (real-time filtering).
        """
        # Debounce: only search after user stops typing for 300ms
        if hasattr(self, '_search_timer'):
            self._search_timer.stop()

        from PySide6.QtCore import QTimer
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(lambda: self._perform_search(text))
        self._search_timer.start(300)  # 300ms debounce

    def _perform_search(self, text: str = None):
        """
        Perform search and filter photos.

        Args:
            text: Search query (if None, use search_box text)
        """
        if text is None:
            text = self.search_box.text()

        text = text.strip().lower()

        print(f"[GooglePhotosLayout] 🔍 Searching for: '{text}'")

        if not text:
            # Empty search - reload all photos
            self._load_photos()
            return

        # Search in photo paths (filename search)
        # Future: could extend to EXIF data, tags, etc.
        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()

            # Search query with LIKE pattern
            query = """
                SELECT DISTINCT pm.path, pm.date_taken, pm.width, pm.height
                FROM photo_metadata pm
                JOIN project_images pi ON pm.path = pi.image_path
                WHERE pi.project_id = ?
                AND pm.date_taken IS NOT NULL
                AND LOWER(pm.path) LIKE ?
                ORDER BY pm.date_taken DESC
            """

            search_pattern = f"%{text}%"

            with db._connect() as conn:
                conn.execute("PRAGMA busy_timeout = 5000")
                cur = conn.cursor()
                cur.execute(query, (self.project_id, search_pattern))
                rows = cur.fetchall()

            # Clear and rebuild timeline with search results
            self._rebuild_timeline_with_results(rows, text)

        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Search error: {e}")

    def _rebuild_timeline_with_results(self, rows, search_text: str):
        """
        Rebuild timeline with search results.
        """
        # Clear existing timeline and trees for search results
        while self.timeline_layout.count():
            child = self.timeline_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self.timeline_tree.clear()
        self.folders_tree.clear()  # Clear folders too for consistency
        self.people_tree.clear()  # Clear people too for consistency
        self.videos_tree.clear()  # Clear videos too for consistency

        if not rows:
            # No results
            empty_label = QLabel(f"🔍 No results for '{search_text}'\n\nTry different search terms")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet("font-size: 12pt; color: #888; padding: 60px;")
            self.timeline_layout.addWidget(empty_label)
            print(f"[GooglePhotosLayout] No search results for: '{search_text}'")
            return

        # Group and display results
        photos_by_date = self._group_photos_by_date(rows)
        self._build_timeline_tree(photos_by_date)

        # Add search results header
        header = QLabel(f"🔍 Found {len(rows)} results for '{search_text}'")
        header.setStyleSheet("font-size: 11pt; font-weight: bold; padding: 10px 20px; color: #1a73e8;")
        self.timeline_layout.insertWidget(0, header)

        # Create date groups (use current thumb size)
        thumb_size = getattr(self, 'current_thumb_size', 200)
        for date_str, photos in photos_by_date.items():
            date_group = self._create_date_group(date_str, photos, thumb_size)
            self.timeline_layout.addWidget(date_group)

        self.timeline_layout.addStretch()

        print(f"[GooglePhotosLayout] Search results: {len(rows)} photos in {len(photos_by_date)} dates")

    # ============ Phase 2: Zoom Functionality ============

    def _on_zoom_changed(self, value: int):
        """
        Handle zoom slider change - adjust thumbnail size.

        Args:
            value: New thumbnail size in pixels (100-400)
        """
        print(f"[GooglePhotosLayout] 🔎 Zoom changed to: {value}px")

        # Update label
        self.zoom_value_label.setText(f"{value}px")

        # Reload photos with new thumbnail size
        # Store current scroll position
        scroll_pos = self.timeline.verticalScrollBar().value()

        # Reload with new size
        self._load_photos(thumb_size=value)

        # Restore scroll position (approximate)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, lambda: self.timeline.verticalScrollBar().setValue(scroll_pos))

    def _clear_filter(self):
        """
        Clear all date/folder/person filters and show all photos.
        """
        print("[GooglePhotosLayout] Clearing all filters")

        # Reload without filters
        self._load_photos(
            thumb_size=self.current_thumb_size,
            filter_year=None,
            filter_month=None,
            filter_folder=None,
            filter_person=None
        )

        # Clear search box as well if it has text
        if self.search_box.text():
            self.search_box.clear()

    def get_sidebar(self):
        """Get sidebar component."""
        return getattr(self, 'sidebar', None)

    def get_grid(self):
        """Grid is integrated into timeline view."""
        return None

    def on_layout_activated(self):
        """Called when this layout becomes active."""
        print("[GooglePhotosLayout] 📍 Layout activated")

        # CRITICAL FIX: Disconnect before connecting to prevent duplicate signal connections
        # Create Project button is already connected in toolbar creation
        try:
            self.btn_scan.clicked.disconnect()
        except:
            pass
        try:
            self.btn_faces.clicked.disconnect()
        except:
            pass

        # Connect Scan and Faces buttons to MainWindow actions
        if hasattr(self.main_window, '_on_scan_repository'):
            self.btn_scan.clicked.connect(self.main_window._on_scan_repository)
            print("[GooglePhotosLayout] ✓ Connected Scan button")

        if hasattr(self.main_window, '_on_detect_and_group_faces'):
            self.btn_faces.clicked.connect(self.main_window._on_detect_and_group_faces)
            print("[GooglePhotosLayout] ✓ Connected Faces button")

    def _on_create_project_clicked(self):
        """Handle Create Project button click."""
        print("[GooglePhotosLayout] 🆕🆕🆕 CREATE PROJECT BUTTON CLICKED! 🆕🆕🆕")

        # Debug: Check if main_window exists and has breadcrumb_nav
        if not hasattr(self, 'main_window'):
            print("[GooglePhotosLayout] ❌ ERROR: self.main_window does not exist!")
            return

        # CRITICAL FIX: _create_new_project is in BreadcrumbNavigation, not MainWindow!
        # MainWindow has self.breadcrumb_nav which contains the method
        if not hasattr(self.main_window, 'breadcrumb_nav'):
            print(f"[GooglePhotosLayout] ❌ ERROR: main_window does not have breadcrumb_nav!")
            return

        if not hasattr(self.main_window.breadcrumb_nav, '_create_new_project'):
            print(f"[GooglePhotosLayout] ❌ ERROR: breadcrumb_nav does not have _create_new_project method!")
            return

        print("[GooglePhotosLayout] ✓ Calling breadcrumb_nav._create_new_project()...")

        # Call BreadcrumbNavigation's project creation dialog
        self.main_window.breadcrumb_nav._create_new_project()

        print("[GooglePhotosLayout] ✓ Project creation dialog completed")

        # CRITICAL: Update project_id after creation
        from app_services import get_default_project_id
        self.project_id = get_default_project_id()
        print(f"[GooglePhotosLayout] Updated project_id: {self.project_id}")

        # Refresh project selector and layout
        self._populate_project_selector()
        self._load_photos()
        print("[GooglePhotosLayout] ✓ Layout refreshed after project creation")

    def _populate_project_selector(self):
        """
        Populate the project selector combobox with available projects.
        """
        try:
            from app_services import list_projects
            projects = list_projects()

            # Block signals while updating to prevent triggering change handler
            self.project_combo.blockSignals(True)
            self.project_combo.clear()

            if not projects:
                self.project_combo.addItem("(No projects)", None)
                self.project_combo.setEnabled(False)
            else:
                for proj in projects:
                    self.project_combo.addItem(proj["name"], proj["id"])
                self.project_combo.setEnabled(True)

                # Select current project
                if self.project_id:
                    for i in range(self.project_combo.count()):
                        if self.project_combo.itemData(i) == self.project_id:
                            self.project_combo.setCurrentIndex(i)
                            break

            # Unblock signals and connect change handler
            self.project_combo.blockSignals(False)
            try:
                self.project_combo.currentIndexChanged.disconnect()
            except:
                pass  # No previous connection
            self.project_combo.currentIndexChanged.connect(self._on_project_changed)

            print(f"[GooglePhotosLayout] Project selector populated with {len(projects)} projects")

        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error populating project selector: {e}")

    def _on_project_changed(self, index: int):
        """
        Handle project selection change in combobox.
        """
        new_project_id = self.project_combo.itemData(index)
        if new_project_id is None or new_project_id == self.project_id:
            return

        print(f"[GooglePhotosLayout] 📂 Project changed: {self.project_id} → {new_project_id}")
        self.project_id = new_project_id

        # Reload photos for the new project
        self._load_photos()
