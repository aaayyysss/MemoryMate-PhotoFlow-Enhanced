# layouts/apple_layout.py
# Apple Photos-style layout (PLACEHOLDER - Coming Soon)
# Balanced design with sidebar, zoom levels, and clean grid

from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide6.QtCore import Qt
from .base_layout import BaseLayout


class ApplePhotosLayout(BaseLayout):
    """
    Apple Photos-style layout (COMING SOON).

    Planned Structure:
    ┌─────────────────────────────────────────────┐
    │  ☰  Library | Memories | Albums | Search   │
    ├──────────┬──────────────────────────────────┤
    │ Albums   │  📅 All Photos - 1,234 items     │
    │ ─────    │  ┌────────────────────────────┐ │
    │ Recents  │  │ Years → Months → Days      │ │
    │ Favorites│  ├────────────────────────────┤ │
    │ People   │  │ [Zoom: ━━●━━]  [Grid: ●■■]│ │
    │ Places   │  ├────────────────────────────┤ │
    │ Media    │  │  ┌──┬──┬──┬──┐            │ │
    │  │─Video │  │  │  │  │  │  │ Nov 25    │ │
    │  └─Live  │  │  └──┴──┴──┴──┘            │ │
    └──────────┴──┴──────────────────────────────┘

    Features (Planned):
    - Sidebar with Albums/People/Places
    - Zoom slider (Years/Months/Days/All)
    - Clean grid with date sections
    - Smart albums and categories
    - Balanced professional/casual design
    """

    def get_name(self) -> str:
        return "Apple Photos Style"

    def get_id(self) -> str:
        return "apple"

    def create_layout(self) -> QWidget:
        """
        Create placeholder widget for Apple Photos layout.
        """
        placeholder = QWidget()
        layout = QVBoxLayout(placeholder)
        layout.setAlignment(Qt.AlignCenter)

        # "Coming Soon" message
        title = QLabel("🍎 Apple Photos Layout")
        title.setStyleSheet("font-size: 24pt; font-weight: bold; color: #000;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Coming Soon")
        subtitle.setStyleSheet("font-size: 14pt; color: #666;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        description = QLabel(
            "Balanced design with sidebar and zoom levels\n"
            "Albums • People • Places • Smart Categories\n"
            "Years/Months/Days zoom\n\n"
            "Stay tuned for the update!"
        )
        description.setStyleSheet("font-size: 11pt; color: #888; margin-top: 20px;")
        description.setAlignment(Qt.AlignCenter)
        layout.addWidget(description)

        return placeholder

    def get_sidebar(self):
        """Apple Photos layout will have a sidebar (when implemented)."""
        return None

    def get_grid(self):
        """Grid with zoom levels (when implemented)."""
        return None
