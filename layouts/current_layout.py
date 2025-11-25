# layouts/current_layout.py
# Current/Classic layout - the existing MemoryMate-PhotoFlow layout
# 2-panel design: Sidebar (left) | Grid+ChipBar (right)

from PySide6.QtWidgets import QWidget, QSplitter, QVBoxLayout, QHBoxLayout, QPushButton
from PySide6.QtCore import Qt
from .base_layout import BaseLayout


class CurrentLayout(BaseLayout):
    """
    Current/Classic MemoryMate-PhotoFlow layout.

    Structure:
    ┌────────────────────────────────────────────┐
    │  [Toolbar]                                 │
    ├──────────┬─────────────────────────────────┤
    │          │  [Chip Bar: ⭐👤🎬📅]          │
    │ Sidebar  │  ┌───────────────────────────┐ │
    │  ├─Tree  │  │                           │ │
    │  ├─Tags  │  │    Thumbnail Grid         │ │
    │  ├─Date  │  │                           │ │
    │  └─Videos│  └───────────────────────────┘ │
    └──────────┴─────────────────────────────────┘

    Features:
    - Collapsible sidebar (tree/tabs)
    - Chip filter bar (favorites, people, videos, etc.)
    - Thumbnail grid with variable sizes
    - No inspector panel (double-click for preview)
    """

    def get_name(self) -> str:
        return "Current Layout"

    def get_id(self) -> str:
        return "current"

    def create_layout(self) -> QWidget:
        """
        Create the current/classic layout.

        NOTE: For now, this returns None and the MainWindow uses its existing
        layout code. In a future refactoring, we'll move the actual layout
        creation code here.
        """
        # TODO: Refactor MainWindow's layout code into this method
        # For now, signal that MainWindow should use its existing layout
        return None

    def get_sidebar(self):
        """Get sidebar component from MainWindow."""
        return self.main_window.sidebar if hasattr(self.main_window, 'sidebar') else None

    def get_grid(self):
        """Get grid component from MainWindow."""
        return self.main_window.grid if hasattr(self.main_window, 'grid') else None

    def on_layout_activated(self):
        """
        Called when Current layout becomes active.

        CRITICAL FIX: Refresh sidebar and grid to ensure all branches and sections
        show updated data after scanning in other layouts (e.g., Google layout).
        """
        print("[CurrentLayout] Layout activated - refreshing sidebar and grid")

        # Refresh sidebar to show updated folder/date/tag counts
        sidebar = self.get_sidebar()
        if sidebar and hasattr(sidebar, 'reload'):
            try:
                print("[CurrentLayout] Reloading sidebar...")
                sidebar.reload()
                print("[CurrentLayout] ✓ Sidebar reload completed")
            except Exception as e:
                print(f"[CurrentLayout] ⚠️ Error reloading sidebar: {e}")

        # Refresh grid to show updated thumbnails
        grid = self.get_grid()
        if grid and hasattr(grid, 'reload'):
            try:
                print("[CurrentLayout] Reloading grid...")
                grid.reload()
                print("[CurrentLayout] ✓ Grid reload completed")
            except Exception as e:
                print(f"[CurrentLayout] ⚠️ Error reloading grid: {e}")
