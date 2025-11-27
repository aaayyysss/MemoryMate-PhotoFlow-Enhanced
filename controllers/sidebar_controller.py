"""
SidebarController - Sidebar Navigation Event Handling

Extracted from main_window_qt.py (Phase 1, Step 1.3)

Responsibilities:
- Folder selection event handling
- Date branch navigation
- Videos tab selection
- Thumbnail refresh coordination
- Tag filter integration

Version: 09.20.00.00
"""


class SidebarController:
    """Encapsulates folder/branch event handling & thumbnail refresh."""
    def __init__(self, main):
        self.main = main

    def on_folder_selected(self, folder_id: int):
        self.main.grid.set_folder(folder_id)

        if getattr(self.main, "active_tag_filter", "all") != "all":
            self.main._apply_tag_filter(self.main.active_tag_filter)

        if self.main.thumbnails and hasattr(self.main.grid, "get_visible_paths"):
            self.main.thumbnails.clear()
            self.main.thumbnails.load_thumbnails(self.main.grid.get_visible_paths())

    def on_branch_selected(self, branch_key: str):
        self.main.grid.set_branch(branch_key)

        if getattr(self.main, "active_tag_filter", "all") != "all":
            self.main._apply_tag_filter(self.main.active_tag_filter)

        # REMOVED: Forced zoom slider update causes white thumbnails and incorrect layout
        # The grid already applies correct zoom geometry in reload()
        # if hasattr(self.main.grid, "_on_slider_changed"):
        #     self.main.grid._on_slider_changed(self.main.grid.zoom_slider.value())

        if hasattr(self.main.grid, "list_view"):
            self.main.grid.list_view.scrollToTop()

        if self.main.thumbnails and hasattr(self.main.grid, "get_visible_paths"):
            self.main.thumbnails.clear()
            self.main.thumbnails.load_thumbnails(self.main.grid.get_visible_paths())

    def on_videos_selected(self):
        """Handle videos tab selection - show all videos for current project"""
        # 🎬 Phase 4: Videos support
        if hasattr(self.main.grid, "set_videos"):
            self.main.grid.set_videos()

        if getattr(self.main, "active_tag_filter", "all") != "all":
            self.main._apply_tag_filter(self.main.active_tag_filter)

        if hasattr(self.main.grid, "list_view"):
            self.main.grid.list_view.scrollToTop()

        if self.main.thumbnails and hasattr(self.main.grid, "get_visible_paths"):
            self.main.thumbnails.clear()
            self.main.thumbnails.load_thumbnails(self.main.grid.get_visible_paths())
