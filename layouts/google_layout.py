# layouts/google_layout.py
# Google Photos-style layout - Timeline-based, date-grouped, minimalist design

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSplitter, QToolBar, QLineEdit, QTreeWidget,
    QTreeWidgetItem, QFrame, QGridLayout, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QIcon
from .base_layout import BaseLayout
from typing import Dict, List, Tuple
from collections import defaultdict
from datetime import datetime


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
        toolbar.addWidget(self.btn_create_project)

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
        toolbar.addWidget(self.search_box)

        toolbar.addSeparator()

        # Refresh button
        self.btn_refresh = QPushButton("↻ Refresh")
        self.btn_refresh.setToolTip("Reload timeline from database")
        self.btn_refresh.clicked.connect(self._load_photos)
        toolbar.addWidget(self.btn_refresh)

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        # Selection actions (will show/hide based on selection)
        self.btn_delete = QPushButton("🗑️ Delete")
        self.btn_delete.setToolTip("Delete selected photos")
        self.btn_delete.setVisible(False)
        toolbar.addWidget(self.btn_delete)

        self.btn_favorite = QPushButton("⭐ Favorite")
        self.btn_favorite.setToolTip("Mark selected as favorites")
        self.btn_favorite.setVisible(False)
        toolbar.addWidget(self.btn_favorite)

        # Store toolbar reference
        self._toolbar = toolbar

        return toolbar

    def _create_sidebar(self) -> QWidget:
        """
        Create minimal sidebar with search + timeline navigation.
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

        # Timeline navigation header
        header = QLabel("📅 Timeline")
        header.setStyleSheet("font-size: 12pt; font-weight: bold; color: #202124;")
        layout.addWidget(header)

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
        layout.addWidget(self.timeline_tree)

        # Albums section (placeholder for Phase 2)
        albums_header = QLabel("📁 Albums")
        albums_header.setStyleSheet("font-size: 12pt; font-weight: bold; color: #202124; margin-top: 12px;")
        layout.addWidget(albums_header)

        albums_label = QLabel("Coming in Phase 2...")
        albums_label.setStyleSheet("font-size: 9pt; color: #888; margin-left: 8px;")
        layout.addWidget(albums_label)

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

    def _load_photos(self):
        """
        Load photos from database and populate timeline.
        """
        print("[GooglePhotosLayout] Loading photos from database...")

        # Clear existing timeline
        while self.timeline_layout.count():
            child = self.timeline_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Clear timeline tree
        self.timeline_tree.clear()

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
            query = """
                SELECT DISTINCT pm.path, pm.date_taken, pm.width, pm.height
                FROM photo_metadata pm
                JOIN project_images pi ON pm.path = pi.image_path
                WHERE pi.project_id = ?
                AND pm.date_taken IS NOT NULL
                ORDER BY pm.date_taken DESC
            """

            # Use ReferenceDB's connection pattern
            with db._connect() as conn:
                cur = conn.cursor()
                cur.execute(query, (self.project_id,))
                rows = cur.fetchall()

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

            # Build timeline tree
            self._build_timeline_tree(photos_by_date)

            # Create date group widgets
            for date_str, photos in photos_by_date.items():
                date_group = self._create_date_group(date_str, photos)
                self.timeline_layout.addWidget(date_group)

            # Add spacer at bottom
            self.timeline_layout.addStretch()

            print(f"[GooglePhotosLayout] Loaded {len(rows)} photos in {len(photos_by_date)} date groups")

        except Exception as e:
            print(f"[GooglePhotosLayout] Error loading photos: {e}")
            import traceback
            traceback.print_exc()

            # Show error message
            error_label = QLabel(f"❌ Error loading photos:\n{str(e)}")
            error_label.setAlignment(Qt.AlignCenter)
            error_label.setStyleSheet("font-size: 11pt; color: #d93025; padding: 40px;")
            self.timeline_layout.addWidget(error_label)

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
            year_item.setExpanded(True)
            self.timeline_tree.addTopLevelItem(year_item)

            for month in sorted(years_months[year].keys(), reverse=True):
                count = years_months[year][month]
                month_name = datetime(year, month, 1).strftime("%B")
                month_item = QTreeWidgetItem([f"  • {month_name} ({count})"])
                year_item.addChild(month_item)

    def _create_date_group(self, date_str: str, photos: List[Tuple]) -> QWidget:
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

        # Photo grid
        grid = self._create_photo_grid(photos)
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

    def _create_photo_grid(self, photos: List[Tuple]) -> QWidget:
        """
        Create photo grid with thumbnails.
        """
        grid_container = QWidget()
        grid = QGridLayout(grid_container)
        grid.setSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)

        # Default thumbnail size (will make zoomable in Phase 2)
        thumb_size = 200

        # Calculate columns based on container width
        # For now, use fixed 5 columns
        columns = 5

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
        Create thumbnail widget for a photo.
        """
        thumb = QPushButton()
        thumb.setFixedSize(size, size)
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

        # Store path for click handling
        thumb.setProperty("photo_path", path)
        thumb.clicked.connect(lambda: self._on_photo_clicked(path))

        return thumb

    def _on_photo_clicked(self, path: str):
        """
        Handle photo thumbnail click.
        """
        print(f"[GooglePhotosLayout] Photo clicked: {path}")
        # TODO Phase 2: Open lightbox or details panel
        # For now, just print

    def get_sidebar(self):
        """Get sidebar component."""
        return getattr(self, 'sidebar', None)

    def get_grid(self):
        """Grid is integrated into timeline view."""
        return None

    def on_layout_activated(self):
        """Called when this layout becomes active."""
        print("[GooglePhotosLayout] Layout activated")

        # Connect toolbar buttons to MainWindow actions if available
        if hasattr(self.main_window, '_create_new_project'):
            self.btn_create_project.clicked.connect(self._on_create_project_clicked)
            print("[GooglePhotosLayout] Connected Create Project button")

        if hasattr(self.main_window, '_on_scan_repository'):
            self.btn_scan.clicked.connect(self.main_window._on_scan_repository)
            print("[GooglePhotosLayout] Connected Scan button to MainWindow")

        if hasattr(self.main_window, '_on_detect_and_group_faces'):
            self.btn_faces.clicked.connect(self.main_window._on_detect_and_group_faces)
            print("[GooglePhotosLayout] Connected Faces button to MainWindow")

    def _on_create_project_clicked(self):
        """Handle Create Project button click."""
        print("[GooglePhotosLayout] Create Project clicked")
        # Call MainWindow's project creation dialog
        self.main_window._create_new_project()
        # Refresh the layout after project creation
        self._load_photos()
