# layouts/layout_manager.py
# Layout Manager - handles switching between different UI layouts

from typing import Dict, Optional
from PySide6.QtWidgets import QWidget
from .base_layout import BaseLayout
from .current_layout import CurrentLayout
from .google_layout import GooglePhotosLayout
from .apple_layout import ApplePhotosLayout
from .lightroom_layout import LightroomLayout


class LayoutManager:
    """
    Manages UI layout switching for MemoryMate-PhotoFlow.

    Responsibilities:
    - Register available layouts
    - Switch between layouts
    - Save/restore layout preferences
    - Manage layout lifecycle (cleanup, activation)
    """

    def __init__(self, main_window):
        """
        Initialize the layout manager.

        Args:
            main_window: Reference to MainWindow instance
        """
        self.main_window = main_window
        self.settings = main_window.settings if hasattr(main_window, 'settings') else None

        # Registry of available layouts
        self._layouts: Dict[str, type] = {}
        self._current_layout: Optional[BaseLayout] = None
        self._current_layout_id: str = "current"

        # Register built-in layouts
        self._register_builtin_layouts()

    def _register_builtin_layouts(self):
        """Register all built-in layout classes."""
        self.register_layout(CurrentLayout)
        self.register_layout(GooglePhotosLayout)
        self.register_layout(ApplePhotosLayout)
        self.register_layout(LightroomLayout)

    def register_layout(self, layout_class: type):
        """
        Register a layout class.

        Args:
            layout_class: A class that inherits from BaseLayout
        """
        if not issubclass(layout_class, BaseLayout):
            raise TypeError(f"{layout_class} must inherit from BaseLayout")

        # Create temporary instance to get ID
        temp_instance = layout_class(self.main_window)
        layout_id = temp_instance.get_id()

        self._layouts[layout_id] = layout_class
        print(f"[LayoutManager] Registered layout: {temp_instance.get_name()} (id={layout_id})")

    def get_available_layouts(self) -> Dict[str, str]:
        """
        Get list of available layouts.

        Returns:
            dict: {layout_id: layout_name} mapping
        """
        layouts = {}
        for layout_id, layout_class in self._layouts.items():
            temp_instance = layout_class(self.main_window)
            layouts[layout_id] = temp_instance.get_name()
        return layouts

    def switch_layout(self, layout_id: str) -> bool:
        """
        Switch to a different layout.

        Args:
            layout_id: ID of the layout to switch to

        Returns:
            bool: True if switch was successful, False otherwise
        """
        if layout_id not in self._layouts:
            print(f"[LayoutManager] ❌ Unknown layout: {layout_id}")
            return False

        if layout_id == self._current_layout_id:
            print(f"[LayoutManager] Already using layout: {layout_id}")
            return True

        print(f"[LayoutManager] Switching layout: {self._current_layout_id} → {layout_id}")

        # Save current layout state
        if self._current_layout:
            state = self._current_layout.save_state()
            if self.settings:
                self.settings.set(f"layout_{self._current_layout_id}_state", state)

            # Cleanup current layout
            self._current_layout.cleanup()

        # Create new layout instance
        layout_class = self._layouts[layout_id]
        new_layout = layout_class(self.main_window)

        # Create layout widget
        layout_widget = new_layout.create_layout()

        # Handle layout switching in MainWindow
        if layout_widget is not None:
            # New layout provides its own widget
            self.main_window.setCentralWidget(layout_widget)
        else:
            # Layout uses MainWindow's existing components (like CurrentLayout)
            # No change needed - MainWindow already has the layout
            pass

        # Update current layout
        self._current_layout = new_layout
        self._current_layout_id = layout_id

        # Restore layout state
        if self.settings:
            saved_state = self.settings.get(f"layout_{layout_id}_state", {})
            new_layout.restore_state(saved_state)

        # Activate new layout
        new_layout.on_layout_activated()

        # Save preference
        if self.settings:
            self.settings.set("current_layout", layout_id)

        print(f"[LayoutManager] ✓ Switched to: {new_layout.get_name()}")
        return True

    def get_current_layout(self) -> Optional[BaseLayout]:
        """Get the currently active layout instance."""
        return self._current_layout

    def get_current_layout_id(self) -> str:
        """Get the ID of the currently active layout."""
        return self._current_layout_id

    def initialize_default_layout(self):
        """
        Initialize the default layout (on app startup).

        Reads the saved layout preference and activates it.
        Falls back to "current" layout if no preference is saved.
        """
        # Get saved preference
        preferred_layout = "current"
        if self.settings:
            preferred_layout = self.settings.get("current_layout", "current")

        # Validate preference
        if preferred_layout not in self._layouts:
            print(f"[LayoutManager] Invalid saved layout '{preferred_layout}', using 'current'")
            preferred_layout = "current"

        # Initialize layout
        print(f"[LayoutManager] Initializing default layout: {preferred_layout}")
        self.switch_layout(preferred_layout)
