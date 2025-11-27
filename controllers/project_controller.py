"""
ProjectController - Project Switching Logic

Extracted from main_window_qt.py (Phase 1, Step 1.3)

Responsibilities:
- Project combo box change handling
- Project switching coordination
- Thumbnail cache clearing
- Sidebar/grid project updates

Version: 09.20.00.00
"""


class ProjectController:
    """Owns project switching & persistence logic."""
    def __init__(self, main):
        self.main = main

    def on_project_changed(self, idx: int):
        pid = self.main.project_combo.itemData(idx)
        if pid is None:
            return
        if self.main.thumbnails:
            self.main.thumbnails.clear()
        self.main.sidebar.set_project(pid)
        self.main.grid.set_project(pid)
