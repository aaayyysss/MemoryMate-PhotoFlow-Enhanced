# layouts/base_layout.py
# Abstract base class for UI layouts
# Defines the interface that all layouts must implement

from abc import ABC, abstractmethod
from PySide6.QtWidgets import QWidget, QSplitter
from typing import Optional, Dict, Any


class BaseLayout(ABC):
    """
    Abstract base class for MemoryMate-PhotoFlow UI layouts.

    All layout implementations must inherit from this class and implement
    the required abstract methods.

    Responsibilities:
    - Create and manage the main UI layout
    - Handle component placement (sidebar, grid, inspector, etc.)
    - Manage layout-specific settings
    - Provide consistent interface for MainWindow
    """

    def __init__(self, main_window):
        """
        Initialize the layout.

        Args:
            main_window: Reference to MainWindow instance (provides access to settings, db, etc.)
        """
        self.main_window = main_window
        self.settings = main_window.settings if hasattr(main_window, 'settings') else None
        self.db = main_window.db if hasattr(main_window, 'db') else None

        # Components (to be created by subclasses)
        self.sidebar = None
        self.grid = None
        self.inspector = None
        self.main_splitter = None

    @abstractmethod
    def get_name(self) -> str:
        """
        Get the display name of this layout.

        Returns:
            str: Human-readable layout name (e.g., "Current Layout", "Google Photos")
        """
        pass

    @abstractmethod
    def get_id(self) -> str:
        """
        Get the unique identifier for this layout.

        Returns:
            str: Unique layout ID (e.g., "current", "google", "apple")
        """
        pass

    @abstractmethod
    def create_layout(self) -> QWidget:
        """
        Create and return the main layout widget.

        This method should:
        1. Create all UI components (sidebar, grid, etc.)
        2. Arrange them in the desired layout
        3. Connect signals/slots
        4. Return the root widget

        Returns:
            QWidget: The root widget containing the entire layout
        """
        pass

    @abstractmethod
    def get_sidebar(self):
        """
        Get the sidebar component.

        Returns:
            Sidebar widget instance (or None if layout doesn't have a sidebar)
        """
        pass

    @abstractmethod
    def get_grid(self):
        """
        Get the thumbnail grid component.

        Returns:
            ThumbnailGrid widget instance
        """
        pass

    def get_inspector(self):
        """
        Get the inspector/preview panel component.

        Returns:
            Inspector widget instance (or None if layout doesn't have one)
        """
        return self.inspector

    def save_state(self) -> Dict[str, Any]:
        """
        Save layout-specific state (splitter positions, panel visibility, etc.).

        Returns:
            dict: Layout state that can be saved to settings
        """
        state = {}

        # Save splitter positions if main_splitter exists
        if self.main_splitter and isinstance(self.main_splitter, QSplitter):
            state['splitter_sizes'] = self.main_splitter.sizes()

        return state

    def restore_state(self, state: Dict[str, Any]):
        """
        Restore layout-specific state from saved settings.

        Args:
            state: Layout state dictionary from settings
        """
        if not state:
            return

        # Restore splitter positions if available
        if 'splitter_sizes' in state and self.main_splitter:
            try:
                self.main_splitter.setSizes(state['splitter_sizes'])
            except Exception as e:
                print(f"[Layout] Failed to restore splitter sizes: {e}")

    def cleanup(self):
        """
        Clean up resources when switching away from this layout.

        Override this method if your layout needs to do cleanup
        (e.g., stop timers, disconnect signals, etc.)
        """
        pass

    def on_layout_activated(self):
        """
        Called when this layout becomes active.

        Override this method if your layout needs to do initialization
        when it's activated (e.g., start timers, refresh data, etc.)
        """
        pass
