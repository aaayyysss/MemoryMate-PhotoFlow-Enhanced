# layouts/google_layout.py
# Google Photos-style layout - Timeline-based, date-grouped, minimalist design

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSplitter, QToolBar, QLineEdit, QTreeWidget,
    QTreeWidgetItem, QFrame, QGridLayout, QSizePolicy, QDialog
)
from PySide6.QtCore import Qt, Signal, QSize, QEvent
from PySide6.QtGui import QPixmap, QIcon, QKeyEvent, QImage
from .base_layout import BaseLayout
from typing import Dict, List, Tuple
from collections import defaultdict
from datetime import datetime
import os


class PhotoLightbox(QDialog):
    """
    Full-screen photo lightbox/preview dialog.

    Features:
    - Full-screen image display
    - Metadata panel (EXIF, date, dimensions)
    - Navigation arrows (prev/next)
    - Close button and ESC key
    """

    def __init__(self, photo_path: str, all_photos: List[str], parent=None):
        """
        Initialize photo lightbox.

        Args:
            photo_path: Path to photo to display
            all_photos: List of all photo paths in timeline order
            parent: Parent widget
        """
        super().__init__(parent)

        self.photo_path = photo_path
        self.all_photos = all_photos
        self.current_index = all_photos.index(photo_path) if photo_path in all_photos else 0

        self._setup_ui()
        self._load_photo()

    def _setup_ui(self):
        """Setup lightbox UI."""
        # Window settings
        self.setWindowTitle("Photo Preview")
        self.setWindowState(Qt.WindowMaximized)
        self.setStyleSheet("background: #1a1a1a;")

        # Main layout
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Left: Image display area
        image_container = QWidget()
        image_container.setStyleSheet("background: #1a1a1a;")
        image_layout = QVBoxLayout(image_container)
        image_layout.setContentsMargins(20, 20, 20, 20)

        # Top bar with close button
        top_bar = QHBoxLayout()
        top_bar.addStretch()

        close_btn = QPushButton("✕ Close")
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 11pt;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
            }
        """)
        close_btn.clicked.connect(self.close)
        top_bar.addWidget(close_btn)
        image_layout.addLayout(top_bar)

        # Image display
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background: transparent;")
        self.image_label.setScaledContents(False)
        image_layout.addWidget(self.image_label, 1)

        # Navigation buttons (bottom)
        nav_layout = QHBoxLayout()

        self.prev_btn = QPushButton("← Previous")
        self.prev_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 4px;
                padding: 10px 20px;
                font-size: 11pt;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
            }
            QPushButton:disabled {
                background: rgba(255, 255, 255, 0.05);
                color: rgba(255, 255, 255, 0.3);
            }
        """)
        self.prev_btn.clicked.connect(self._previous_photo)
        nav_layout.addWidget(self.prev_btn)

        nav_layout.addStretch()

        # Photo counter
        self.counter_label = QLabel()
        self.counter_label.setStyleSheet("color: white; font-size: 10pt;")
        nav_layout.addWidget(self.counter_label)

        nav_layout.addStretch()

        self.next_btn = QPushButton("Next →")
        self.next_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 4px;
                padding: 10px 20px;
                font-size: 11pt;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
            }
            QPushButton:disabled {
                background: rgba(255, 255, 255, 0.05);
                color: rgba(255, 255, 255, 0.3);
            }
        """)
        self.next_btn.clicked.connect(self._next_photo)
        nav_layout.addWidget(self.next_btn)

        image_layout.addLayout(nav_layout)

        main_layout.addWidget(image_container, 3)

        # Right: Metadata panel
        metadata_panel = QWidget()
        metadata_panel.setFixedWidth(350)
        metadata_panel.setStyleSheet("""
            QWidget {
                background: #2a2a2a;
                border-left: 1px solid #404040;
            }
        """)

        metadata_layout = QVBoxLayout(metadata_panel)
        metadata_layout.setContentsMargins(20, 20, 20, 20)
        metadata_layout.setSpacing(16)

        # Metadata header
        header = QLabel("📊 Photo Information")
        header.setStyleSheet("color: white; font-size: 13pt; font-weight: bold;")
        metadata_layout.addWidget(header)

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
        metadata_layout.addWidget(metadata_scroll)

        main_layout.addWidget(metadata_panel)

    def _load_photo(self):
        """Load and display the current photo."""
        try:
            # Load image
            pixmap = QPixmap(self.photo_path)

            if pixmap.isNull():
                self.image_label.setText("❌ Failed to load image")
                self.image_label.setStyleSheet("color: white; font-size: 14pt;")
                return

            # Scale to fit while maintaining aspect ratio
            # Get available space (accounting for padding and nav buttons)
            max_width = self.width() - 400  # Leave space for metadata panel
            max_height = self.height() - 200  # Leave space for top/bottom bars

            scaled_pixmap = pixmap.scaled(
                max_width, max_height,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

            self.image_label.setPixmap(scaled_pixmap)

            # Update counter
            self.counter_label.setText(
                f"{self.current_index + 1} of {len(self.all_photos)}"
            )

            # Update navigation buttons
            self.prev_btn.setEnabled(self.current_index > 0)
            self.next_btn.setEnabled(self.current_index < len(self.all_photos) - 1)

            # Load metadata
            self._load_metadata()

        except Exception as e:
            print(f"[PhotoLightbox] Error loading photo: {e}")
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
            file_size = os.path.getsize(self.photo_path)
            file_size_mb = file_size / (1024 * 1024)
            filename = os.path.basename(self.photo_path)

            # Add filename
            self._add_metadata_field("📄 Filename", filename)

            # Add file size
            self._add_metadata_field("💾 File Size", f"{file_size_mb:.2f} MB")

            # Get image dimensions
            pixmap = QPixmap(self.photo_path)
            if not pixmap.isNull():
                self._add_metadata_field(
                    "📐 Dimensions",
                    f"{pixmap.width()} × {pixmap.height()} px"
                )

            # Get EXIF metadata
            try:
                from services.exif_parser import EXIFParser
                exif_parser = EXIFParser()
                metadata = exif_parser.parse_image_full(self.photo_path)

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
                print(f"[PhotoLightbox] Error loading EXIF: {e}")
                self._add_metadata_field("⚠️ EXIF Data", "Not available")

            # Add file path (at bottom)
            self._add_metadata_field("📁 Path", self.photo_path, word_wrap=True)

        except Exception as e:
            print(f"[PhotoLightbox] Error loading metadata: {e}")
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

    def _previous_photo(self):
        """Navigate to previous photo."""
        if self.current_index > 0:
            self.current_index -= 1
            self.photo_path = self.all_photos[self.current_index]
            self._load_photo()

    def _next_photo(self):
        """Navigate to next photo."""
        if self.current_index < len(self.all_photos) - 1:
            self.current_index += 1
            self.photo_path = self.all_photos[self.current_index]
            self._load_photo()

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard shortcuts."""
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() == Qt.Key_Left:
            self._previous_photo()
        elif event.key() == Qt.Key_Right:
            self._next_photo()
        else:
            super().keyPressEvent(event)


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

        # Spacer at bottom
        layout.addStretch()

        return sidebar

    def _create_timeline(self) -> QWidget:
        """
        Create timeline scroll area with date groups.
        """
        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("""
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

        scroll.setWidget(self.timeline_container)

        return scroll

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

        # Clear existing timeline
        try:
            while self.timeline_layout.count():
                child = self.timeline_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

            # CRITICAL FIX: Only clear trees when NOT filtering
            # When filtering, we want to keep the tree structure visible
            # so users can see all available years/months/folders/people and switch between them
            has_filters = filter_year is not None or filter_month is not None or filter_folder is not None or filter_person is not None
            if not has_filters:
                # Clear trees only when showing all photos (no filters)
                self.timeline_tree.clear()
                self.folders_tree.clear()
                self.people_tree.clear()
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
            # CRITICAL FIX: When filtering by person, we need to show ALL photos of that person
            # even if they don't have date_taken metadata. The date_taken filter should only
            # apply to timeline view, not person-filtered view.
            if filter_person is not None:
                # Person filter: Don't require date_taken (show all photos of this person)
                query_parts = ["""
                    SELECT DISTINCT pm.path, pm.date_taken, pm.width, pm.height
                    FROM photo_metadata pm
                    JOIN project_images pi ON pm.path = pi.image_path
                    WHERE pi.project_id = ?
                """]
            else:
                # Timeline view: Require date_taken for chronological display
                query_parts = ["""
                    SELECT DISTINCT pm.path, pm.date_taken, pm.width, pm.height
                    FROM photo_metadata pm
                    JOIN project_images pi ON pm.path = pi.image_path
                    WHERE pi.project_id = ?
                    AND pm.date_taken IS NOT NULL
                """]

            params = [self.project_id]

            # Add year filter
            if filter_year is not None:
                query_parts.append("AND strftime('%Y', pm.date_taken) = ?")
                params.append(str(filter_year))

            # Add month filter (requires year)
            if filter_month is not None and filter_year is not None:
                query_parts.append("AND strftime('%m', pm.date_taken) = ?")
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

            # Build timeline, folders, and people trees (only if not filtering)
            # This shows ALL years/months/folders/people, not just filtered ones
            if filter_year is None and filter_month is None and filter_folder is None and filter_person is None:
                self._build_timeline_tree(photos_by_date)
                self._build_folders_tree(rows)
                self._build_people_tree()

            # Create date group widgets
            for date_str, photos in photos_by_date.items():
                date_group = self._create_date_group(date_str, photos, thumb_size)
                self.timeline_layout.addWidget(date_group)

            # Add spacer at bottom
            self.timeline_layout.addStretch()

            print(f"[GooglePhotosLayout] Loaded {len(rows)} photos in {len(photos_by_date)} date groups")

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

        Returns:
            dict: {date_str: [(path, date_taken, width, height), ...]}
        """
        groups = defaultdict(list)

        for row in rows:
            path, date_taken, width, height = row

            # Parse date
            try:
                if isinstance(date_taken, str):
                    # Format: "2024-11-25 14:30:00" or "2024-11-25"
                    date_obj = datetime.fromisoformat(date_taken.replace(' ', 'T'))
                else:
                    # Already datetime object
                    date_obj = date_taken

                # Group by date only (YYYY-MM-DD)
                date_str = date_obj.strftime("%Y-%m-%d")
                groups[date_str].append((path, date_taken, width, height))

            except Exception as e:
                print(f"[GooglePhotosLayout] Error parsing date '{date_taken}': {e}")
                continue

        return dict(groups)

    def _build_timeline_tree(self, photos_by_date: Dict[str, List[Tuple]]):
        """
        Build timeline tree in sidebar (Years > Months with counts).
        """
        # Group by year and month
        years_months = defaultdict(lambda: defaultdict(int))

        for date_str in photos_by_date.keys():
            try:
                date_obj = datetime.fromisoformat(date_str)
                year = date_obj.year
                month = date_obj.month
                count = len(photos_by_date[date_str])
                years_months[year][month] += count
            except:
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

    def _create_date_group(self, date_str: str, photos: List[Tuple], thumb_size: int = 200) -> QWidget:
        """
        Create a date group widget (header + photo grid).

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

        # Header
        header = self._create_date_header(date_str, len(photos))
        layout.addWidget(header)

        # Photo grid (pass thumb_size)
        grid = self._create_photo_grid(photos, thumb_size)
        layout.addWidget(grid)

        return group

    def _create_date_header(self, date_str: str, count: int) -> QWidget:
        """
        Create date group header with date and photo count.
        """
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        # Format date nicely
        try:
            date_obj = datetime.fromisoformat(date_str)
            formatted_date = date_obj.strftime("%B %d, %Y (%A)")
        except:
            formatted_date = date_str

        # Date label
        date_label = QLabel(f"📅 {formatted_date}")
        date_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #202124;")
        header_layout.addWidget(date_label)

        # Photo count
        count_label = QLabel(f"({count} photo{'s' if count != 1 else ''})")
        count_label.setStyleSheet("font-size: 10pt; color: #5f6368; margin-left: 8px;")
        header_layout.addWidget(count_label)

        header_layout.addStretch()

        return header

    def _create_photo_grid(self, photos: List[Tuple], thumb_size: int = 200) -> QWidget:
        """
        Create photo grid with thumbnails.
        """
        grid_container = QWidget()
        grid = QGridLayout(grid_container)
        grid.setSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)

        # Calculate grid layout - responsive columns based on thumbnail size
        if thumb_size <= 150:
            columns = 7  # Small thumbs → more columns
        elif thumb_size <= 200:
            columns = 5  # Default
        elif thumb_size <= 300:
            columns = 4  # Large thumbs
        else:
            columns = 3  # Extra large thumbs

        # Add photo thumbnails
        for i, photo in enumerate(photos):
            path, date_taken, width, height = photo

            row = i // columns
            col = i % columns

            thumb = self._create_thumbnail(path, thumb_size)
            grid.addWidget(thumb, row, col)

        return grid_container

    def _create_thumbnail(self, path: str, size: int) -> QWidget:
        """
        Create thumbnail widget for a photo with selection checkbox.

        Phase 2: Enhanced with checkbox overlay for batch selection.
        """
        from PySide6.QtWidgets import QCheckBox, QVBoxLayout

        # Container widget
        container = QWidget()
        container.setFixedSize(size, size)
        container.setStyleSheet("background: transparent;")

        # Thumbnail button
        thumb = QPushButton(container)
        thumb.setGeometry(0, 0, size, size)
        thumb.setStyleSheet("""
            QPushButton {
                background: #f1f3f4;
                border: 1px solid #dadce0;
                border-radius: 4px;
            }
            QPushButton:hover {
                border-color: #1a73e8;
                border-width: 2px;
            }
        """)

        # Load thumbnail using app_services (correct method)
        try:
            from app_services import get_thumbnail

            # Get thumbnail pixmap (handles both images and videos)
            pixmap = get_thumbnail(path, size)

            if pixmap and not pixmap.isNull():
                # Scale pixmap to fit button while maintaining aspect ratio
                scaled = pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                thumb.setIcon(QIcon(scaled))
                thumb.setIconSize(QSize(size - 4, size - 4))
            else:
                # No thumbnail - show placeholder
                thumb.setText("📷")

        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error loading thumbnail for {path}: {e}")
            thumb.setText("❌")

        # Phase 2: Selection checkbox (overlay top-left corner)
        checkbox = QCheckBox(container)
        checkbox.setGeometry(8, 8, 24, 24)
        checkbox.setStyleSheet("""
            QCheckBox {
                background: rgba(255, 255, 255, 0.9);
                border: 2px solid #dadce0;
                border-radius: 4px;
                padding: 2px;
            }
            QCheckBox:checked {
                background: #1a73e8;
                border-color: #1a73e8;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
        """)
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
        Handle photo thumbnail click.
        """
        print(f"[GooglePhotosLayout] Photo clicked: {path}")

        # Phase 2: If selection mode is active, toggle selection
        if self.selection_mode:
            self._toggle_photo_selection(path)
        else:
            # Phase 2: Open lightbox/preview
            self._open_photo_lightbox(path)

    def _open_photo_lightbox(self, path: str):
        """
        Open photo lightbox/preview dialog.

        Args:
            path: Path to photo to display
        """
        print(f"[GooglePhotosLayout] 👁️ Opening lightbox for: {path}")

        # Collect all photo paths in timeline order
        all_photos = self._get_all_photo_paths()

        if not all_photos:
            print("[GooglePhotosLayout] ⚠️ No photos to display in lightbox")
            return

        # Create and show lightbox dialog
        try:
            lightbox = PhotoLightbox(path, all_photos, parent=self.main_window)
            lightbox.exec()
            print("[GooglePhotosLayout] ✓ Lightbox closed")

        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error opening lightbox: {e}")
            import traceback
            traceback.print_exc()

    def _get_all_photo_paths(self) -> List[str]:
        """
        Get all photo paths in timeline order (newest to oldest).

        Returns:
            List of photo paths
        """
        all_paths = []

        try:
            from reference_db import ReferenceDB
            db = ReferenceDB()

            # Query all photos for current project, ordered by date
            query = """
                SELECT DISTINCT pm.path
                FROM photo_metadata pm
                JOIN project_images pi ON pm.path = pi.image_path
                WHERE pi.project_id = ?
                AND pm.date_taken IS NOT NULL
                ORDER BY pm.date_taken DESC
            """

            with db._connect() as conn:
                conn.execute("PRAGMA busy_timeout = 5000")
                cur = conn.cursor()
                cur.execute(query, (self.project_id,))
                rows = cur.fetchall()

                all_paths = [row[0] for row in rows]

        except Exception as e:
            print(f"[GooglePhotosLayout] ⚠️ Error fetching photo paths: {e}")

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

    def _update_selection_ui(self):
        """
        Update selection counter and show/hide action buttons.
        """
        count = len(self.selected_photos)

        # Update toolbar selection counter (add if doesn't exist)
        if not hasattr(self, 'selection_label'):
            from PySide6.QtWidgets import QLabel
            self.selection_label = QLabel()
            self.selection_label.setStyleSheet("font-weight: bold; padding: 0 12px;")
            # Insert before spacer in toolbar
            toolbar = self._toolbar
            spacer_index = toolbar.actions().index(toolbar.widgetForAction(toolbar.actions()[-3]).parent()) if len(toolbar.actions()) > 3 else 0
            toolbar.insertWidget(toolbar.actions()[spacer_index] if spacer_index < len(toolbar.actions()) else None, self.selection_label)

        # Update counter text
        if count > 0:
            self.selection_label.setText(f"✓ {count} selected")
            self.selection_label.setVisible(True)

            # Show action buttons
            self.btn_delete.setVisible(True)
            self.btn_favorite.setVisible(True)
        else:
            self.selection_label.setVisible(False)

            # Hide action buttons when nothing selected
            self.btn_delete.setVisible(False)
            self.btn_favorite.setVisible(False)

        print(f"[GooglePhotosLayout] Selection updated: {count} photos selected")

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
