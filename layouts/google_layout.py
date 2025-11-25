# layouts/google_layout.py
# Google Photos-style layout (PLACEHOLDER - Coming Soon)
# Timeline-based, date-grouped, minimalist design

from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide6.QtCore import Qt
from .base_layout import BaseLayout


class GooglePhotosLayout(BaseLayout):
    """
    Google Photos-style layout (COMING SOON).

    Planned Structure:
    ┌─────────────────────────────────────────────┐
    │  ☰  [🔍 Search...]      👤 Profile  ⚙️     │
    ├─────────────────────────────────────────────┤
    │  Photos | Albums | Sharing | Utilities     │
    ├─────────────────────────────────────────────┤
    │  📅 November 2025                           │
    │  ┌───────────────────────────────────────┐ │
    │  │ Nov 25 (15 photos)                    │ │
    │  │  ┌──┬──┬──┬──┬──┐                    │ │
    │  │  │  │  │  │  │  │                    │ │
    │  │  └──┴──┴──┴──┴──┘                    │ │
    │  └───────────────────────────────────────┘ │
    │  💡 Memories  |  🎭 Faces  |  📍 Places    │
    └─────────────────────────────────────────────┘

    Features (Planned):
    - Timeline-based view (grouped by date)
    - Prominent search bar
    - Smart categories (Memories, Faces, Places)
    - Clean, minimalist design
    - Auto-scrolling infinite feed
    """

    def get_name(self) -> str:
        return "Google Photos Style"

    def get_id(self) -> str:
        return "google"

    def create_layout(self) -> QWidget:
        """
        Create placeholder widget for Google Photos layout.
        """
        placeholder = QWidget()
        layout = QVBoxLayout(placeholder)
        layout.setAlignment(Qt.AlignCenter)

        # "Coming Soon" message
        title = QLabel("🎨 Google Photos Layout")
        title.setStyleSheet("font-size: 24pt; font-weight: bold; color: #1a73e8;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Coming Soon")
        subtitle.setStyleSheet("font-size: 14pt; color: #666;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        description = QLabel(
            "Timeline-based view with smart grouping\n"
            "Prominent search • Memories • Faces • Places\n\n"
            "Stay tuned for the update!"
        )
        description.setStyleSheet("font-size: 11pt; color: #888; margin-top: 20px;")
        description.setAlignment(Qt.AlignCenter)
        layout.addWidget(description)

        return placeholder

    def get_sidebar(self):
        """Google Photos layout doesn't have a traditional sidebar."""
        return None

    def get_grid(self):
        """Grid is integrated into the timeline view."""
        return None
