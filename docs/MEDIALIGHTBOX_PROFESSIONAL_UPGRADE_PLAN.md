# MediaLightbox Professional Upgrade Plan

**Target File:** `layouts/google_layout.py` - `MediaLightbox` class
**Current Size:** 3,732 LOC (entire file)
**Date:** 2025-11-27

## Overview

Transform the Google-Layout MediaLightbox into a professional-grade photo viewer matching Google Photos, Adobe Lightroom, and Apple Photos quality with three major feature sets:

1. **Professional Auto-Hide System** - Clean, distraction-free viewing
2. **Lightroom-Style Stepped Zoom** - Predictable, professional zoom controls
3. **Smart Window Management** - Professional sizing and fullscreen

---

## Current Implementation Analysis

### MediaLightbox Class (lines 46-1419)

**Current Features:**
- ✅ Photo and video support
- ✅ Basic zoom (continuous 1.2x multiplier)
- ✅ Top/bottom toolbars (always visible)
- ✅ Keyboard shortcuts
- ✅ Slideshow mode
- ✅ Info panel toggle
- ✅ Overlay navigation buttons

**Current Zoom System:**
```python
# Current (Continuous zoom)
zoom_level = 1.0
zoom_in:  zoom_level *= 1.2  # Unpredictable increments
zoom_out: zoom_level /= 1.2
zoom_modes: "fit", "fill", "manual"
```

**Current Toolbar System:**
```python
# Always visible (lines 183-310)
top_toolbar = _create_top_toolbar()     # Height: 60px
bottom_toolbar = _create_bottom_toolbar()  # Height: 60px
# Buttons: 36x36px
```

**Current Window Sizing:**
```python
# Line 100
setWindowState(Qt.WindowMaximized)  # Always maximized
```

---

## Feature 1: Professional Auto-Hide Toolbar System

### Objectives
- ✅ Hidden by default for clean, distraction-free viewing
- ✅ Smooth 200ms fade-in on mouse movement
- ✅ Auto-hide after 2 seconds of inactivity
- ✅ Larger, more clickable buttons (56x56px)
- ✅ Dark semi-transparent styling (Google Photos style)

### Implementation Plan

#### 1.1 Add Opacity Control (QGraphicsOpacityEffect)

**Location:** `_setup_ui()` method (line 96)

**Changes:**
```python
# Add after toolbar creation (lines 109, 162)
from PySide6.QtWidgets import QGraphicsOpacityEffect
from PySide6.QtCore import QPropertyAnimation, QTimer

# Create opacity effects
self.top_toolbar_opacity = QGraphicsOpacityEffect()
self.top_toolbar.setGraphicsEffect(self.top_toolbar_opacity)
self.top_toolbar_opacity.setOpacity(0.0)  # Hidden by default

self.bottom_toolbar_opacity = QGraphicsOpacityEffect()
self.bottom_toolbar.setGraphicsEffect(self.bottom_toolbar_opacity)
self.bottom_toolbar_opacity.setOpacity(0.0)  # Hidden by default

# Create fade animations
self.toolbar_fade_in = QPropertyAnimation(self.top_toolbar_opacity, b"opacity")
self.toolbar_fade_in.setDuration(200)  # 200ms smooth fade
self.toolbar_fade_in.setStartValue(0.0)
self.toolbar_fade_in.setEndValue(1.0)

self.toolbar_fade_out = QPropertyAnimation(self.top_toolbar_opacity, b"opacity")
self.toolbar_fade_out.setDuration(200)
self.toolbar_fade_out.setStartValue(1.0)
self.toolbar_fade_out.setEndValue(0.0)

# Auto-hide timer
self.toolbar_hide_timer = QTimer()
self.toolbar_hide_timer.setSingleShot(True)
self.toolbar_hide_timer.setInterval(2000)  # 2 seconds
self.toolbar_hide_timer.timeout.connect(self._hide_toolbars)

# Toolbar visibility state
self.toolbars_visible = False
```

#### 1.2 Add Mouse Movement Tracking

**Location:** New method `mouseMoveEvent()`

**Changes:**
```python
def mouseMoveEvent(self, event):
    """Show toolbars on mouse movement."""
    super().mouseMoveEvent(event)
    self._show_toolbars()

def _show_toolbars(self):
    """Show toolbars with fade-in animation."""
    if not self.toolbars_visible:
        self.toolbars_visible = True

        # Animate both toolbars
        self.top_toolbar_opacity.setOpacity(1.0)
        self.bottom_toolbar_opacity.setOpacity(1.0)

    # Restart hide timer
    self.toolbar_hide_timer.stop()
    self.toolbar_hide_timer.start()

def _hide_toolbars(self):
    """Hide toolbars with fade-out animation."""
    if self.toolbars_visible:
        self.toolbars_visible = False

        # Animate both toolbars
        self.top_toolbar_opacity.setOpacity(0.0)
        self.bottom_toolbar_opacity.setOpacity(0.0)
```

#### 1.3 Increase Button Sizes

**Location:** `_create_top_toolbar()` and `_create_bottom_toolbar()`

**Changes:**
```python
# OLD (lines 220, 229, etc.)
button.setFixedSize(36, 36)

# NEW
button.setFixedSize(56, 56)  # Professional size, easier to click
button.setStyleSheet("""
    QPushButton {
        background: rgba(255, 255, 255, 0.15);  # More visible
        color: white;
        border: none;
        border-radius: 28px;  # Half of 56px
        font-size: 18pt;  # Larger icons
    }
    QPushButton:hover {
        background: rgba(255, 255, 255, 0.25);
    }
    QPushButton:pressed {
        background: rgba(255, 255, 255, 0.35);
    }
""")
```

#### 1.4 Update Toolbar Styling

**Location:** `_create_top_toolbar()` (line 187-193)

**Changes:**
```python
# More visible gradient for better contrast
toolbar.setStyleSheet("""
    QWidget {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 rgba(0, 0, 0, 0.9),  # Darker
            stop:1 rgba(0, 0, 0, 0));
    }
""")
```

**Files Modified:**
- `layouts/google_layout.py` - MediaLightbox class

**Estimated LOC:** ~60 lines added

---

## Feature 2: Professional Zoom System (Lightroom-Style)

### Objectives
- ✅ Stepped zoom (not continuous) for predictability
- ✅ Clear zoom modes: Fit, Fill, 100%, Custom
- ✅ Standard zoom steps: 25% → 33% → 50% → 67% → 100% → 150% → 200% → 300% → 400% → 600% → 800%
- ✅ Keyboard shortcuts: 0 (fit), 1 (100%), +/- (zoom)
- ✅ Smart scaling (maintain aspect ratio, no stretching)
- ✅ Clear status display ("🔍 Fit to Window", "🔍 150%")
- ✅ Auto-adjust on window resize

### Implementation Plan

#### 2.1 Define Zoom Levels

**Location:** `__init__()` method (line 78-83)

**Changes:**
```python
# OLD
self.zoom_level = 1.0
self.min_zoom = 0.1
self.max_zoom = 5.0
self.zoom_mode = "fit"  # "fit", "fill", or "100%"

# NEW
# Professional stepped zoom levels (Lightroom-style)
self.ZOOM_STEPS = [0.25, 0.33, 0.50, 0.67, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0]
self.zoom_level = 1.0
self.zoom_step_index = 4  # Start at 100% (index of 1.0)
self.zoom_mode = "fit"  # "fit", "fill", "actual", "custom"
self.original_pixmap = None
```

#### 2.2 Rewrite Zoom Methods

**Location:** Replace `_zoom_in()` and `_zoom_out()` (lines 1245-1263)

**Changes:**
```python
def _zoom_in(self):
    """Zoom to next stepped level."""
    if self._is_video(self.media_path):
        return

    if self.zoom_mode in ["fit", "fill"]:
        # First zoom in switches to 100%
        self.zoom_mode = "actual"
        self.zoom_level = 1.0
        self.zoom_step_index = 4  # 100%
    elif self.zoom_step_index < len(self.ZOOM_STEPS) - 1:
        # Step to next zoom level
        self.zoom_step_index += 1
        self.zoom_level = self.ZOOM_STEPS[self.zoom_step_index]
        self.zoom_mode = "custom"

    self._apply_zoom()
    self._update_zoom_status()

def _zoom_out(self):
    """Zoom to previous stepped level."""
    if self._is_video(self.media_path):
        return

    if self.zoom_mode in ["fit", "fill"]:
        return  # Already at minimum

    if self.zoom_step_index > 0:
        # Step to previous zoom level
        self.zoom_step_index -= 1
        self.zoom_level = self.ZOOM_STEPS[self.zoom_step_index]

        # If stepping below 100%, switch to fit mode
        if self.zoom_level < 1.0:
            self.zoom_mode = "fit"
            self._fit_to_window()
        else:
            self.zoom_mode = "custom"

    self._apply_zoom()
    self._update_zoom_status()

def _zoom_to_fit(self):
    """Zoom to fit window (Keyboard: 0)."""
    if self._is_video(self.media_path):
        return

    self.zoom_mode = "fit"
    self._fit_to_window()
    self._update_zoom_status()

def _zoom_to_actual(self):
    """Zoom to 100% actual size (Keyboard: 1)."""
    if self._is_video(self.media_path):
        return

    self.zoom_mode = "actual"
    self.zoom_level = 1.0
    self.zoom_step_index = 4  # Index of 1.0
    self._apply_zoom()
    self._update_zoom_status()

def _zoom_to_fill(self):
    """Zoom to fill window (may crop edges)."""
    if self._is_video(self.media_path):
        return

    self.zoom_mode = "fill"
    self._fill_window()
    self._update_zoom_status()
```

#### 2.3 Add Smart Zoom Modes

**Location:** New methods after `_apply_zoom()`

**Changes:**
```python
def _fit_to_window(self):
    """Fit entire image to window (letterboxing if needed)."""
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

def _fill_window(self):
    """Fill window completely (may crop edges to avoid letterboxing)."""
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
```

#### 2.4 Update Status Display

**Location:** Replace `_update_status_label()` (line 1293)

**Changes:**
```python
def _update_zoom_status(self):
    """Update status label with professional zoom indicators."""
    if self._is_video(self.media_path):
        zoom_text = ""
    elif self.zoom_mode == "fit":
        zoom_text = "🔍 Fit to Window"
    elif self.zoom_mode == "fill":
        zoom_text = "🔍 Fill Window"
    elif self.zoom_mode == "actual":
        zoom_text = "🔍 100% (Actual Size)"
    else:
        zoom_pct = int(self.zoom_level * 100)
        zoom_text = f"🔍 {zoom_pct}%"

    # Update status label
    status_parts = []
    if zoom_text:
        status_parts.append(zoom_text)
    if self.slideshow_active:
        status_parts.append("⏵ Slideshow")

    self.status_label.setText(" | ".join(status_parts) if status_parts else "")
```

#### 2.5 Add Keyboard Shortcuts

**Location:** `keyPressEvent()` method

**Changes:**
```python
# Add to keyPressEvent (find existing method)
elif event.key() == Qt.Key_0:
    self._zoom_to_fit()
elif event.key() == Qt.Key_1:
    self._zoom_to_actual()
elif event.key() == Qt.Key_Plus or event.key() == Qt.Key_Equal:
    self._zoom_in()
elif event.key() == Qt.Key_Minus:
    self._zoom_out()
```

#### 2.6 Auto-Adjust on Resize

**Location:** Add `resizeEvent()` method

**Changes:**
```python
def resizeEvent(self, event):
    """Handle window resize - auto-adjust zoom if in fit/fill mode."""
    super().resizeEvent(event)

    # Reapply zoom in fit/fill modes
    if self.zoom_mode == "fit":
        self._fit_to_window()
    elif self.zoom_mode == "fill":
        self._fill_window()

    self._update_zoom_status()
```

**Files Modified:**
- `layouts/google_layout.py` - MediaLightbox class

**Estimated LOC:** ~120 lines added/modified

---

## Feature 3: Smart Window Sizing & Fullscreen

### Objectives
- ✅ Smart initial size: 90% of screen (not 100%)
- ✅ Centered on screen for professional appearance
- ✅ Starts maximized (not fullscreen) - user choice
- ✅ F11 fullscreen toggle with distraction-free mode
- ✅ Toolbars auto-hide in fullscreen
- ✅ Dynamic zoom adjustment on resize

### Implementation Plan

#### 3.1 Smart Window Sizing

**Location:** `_setup_ui()` method (line 98-101)

**Changes:**
```python
# OLD
self.setWindowTitle("Media Viewer")
self.setWindowState(Qt.WindowMaximized)
self.setStyleSheet("background: #000000;")

# NEW
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRect

self.setWindowTitle("Media Viewer")

# Smart sizing: 90% of screen, centered
screen = QApplication.primaryScreen().geometry()
width = int(screen.width() * 0.9)
height = int(screen.height() * 0.9)
x = (screen.width() - width) // 2
y = (screen.height() - height) // 2

self.setGeometry(QRect(x, y, width, height))
self.setStyleSheet("background: #000000;")

# Start maximized (not fullscreen - user can restore)
self.showMaximized()
```

#### 3.2 Enhance Fullscreen Toggle

**Location:** Replace `_toggle_fullscreen()` (line 1411)

**Changes:**
```python
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
```

#### 3.3 Update Toolbar Behavior in Fullscreen

**Location:** Modify `_show_toolbars()` and `_hide_toolbars()`

**Changes:**
```python
def _show_toolbars(self):
    """Show toolbars with fade-in animation."""
    if not self.toolbars_visible:
        self.toolbars_visible = True
        self.top_toolbar_opacity.setOpacity(1.0)
        self.bottom_toolbar_opacity.setOpacity(1.0)

    # Only auto-hide in fullscreen mode
    if self.isFullScreen():
        self.toolbar_hide_timer.stop()
        self.toolbar_hide_timer.start()

def _hide_toolbars(self):
    """Hide toolbars with fade-out animation (fullscreen only)."""
    # Only hide if in fullscreen
    if self.isFullScreen() and self.toolbars_visible:
        self.toolbars_visible = False
        self.top_toolbar_opacity.setOpacity(0.0)
        self.bottom_toolbar_opacity.setOpacity(0.0)
```

**Files Modified:**
- `layouts/google_layout.py` - MediaLightbox class

**Estimated LOC:** ~40 lines modified

---

## Implementation Summary

### Changes Required

| Component | Lines Changed | Complexity |
|-----------|--------------|------------|
| Auto-hide system | ~60 added | Medium |
| Zoom system | ~120 modified | High |
| Window sizing | ~40 modified | Low |
| **Total** | **~220 LOC** | **Medium-High** |

### Modified Methods

**Existing Methods (Modified):**
- `_setup_ui()` - Add opacity effects, animations, timers
- `_zoom_in()` - Replace with stepped zoom
- `_zoom_out()` - Replace with stepped zoom
- `_apply_zoom()` - Update for new zoom modes
- `_update_status_label()` - Rename to `_update_zoom_status()`, enhance display
- `_toggle_fullscreen()` - Add toolbar auto-hide
- `keyPressEvent()` - Add 0, 1, +/- shortcuts
- `_create_top_toolbar()` - Increase button sizes (36→56px)
- `_create_bottom_toolbar()` - Increase button sizes (36→56px)

**New Methods (Added):**
- `mouseMoveEvent()` - Track mouse for toolbar reveal
- `_show_toolbars()` - Fade-in animation
- `_hide_toolbars()` - Fade-out animation
- `_zoom_to_fit()` - Fit to window mode (keyboard: 0)
- `_zoom_to_actual()` - 100% actual size (keyboard: 1)
- `_zoom_to_fill()` - Fill window mode
- `_fit_to_window()` - Calculate fit scaling
- `_fill_window()` - Calculate fill scaling
- `resizeEvent()` - Auto-adjust zoom on resize

### Dependencies

**No new dependencies required** - all features use existing PySide6 APIs:
- `QGraphicsOpacityEffect` - For fade animations
- `QPropertyAnimation` - For smooth opacity transitions
- `QTimer` - For auto-hide timing
- `QRect` - For window geometry
- `QApplication.primaryScreen()` - For screen dimensions

---

## Testing Plan

### 1. Auto-Hide System Tests
- [ ] Toolbars hidden on startup
- [ ] Toolbars fade in (200ms) on mouse movement
- [ ] Toolbars auto-hide after 2 seconds
- [ ] Button size increased to 56x56px
- [ ] Buttons clickable and visible

### 2. Zoom System Tests
- [ ] Press 0 → Fit to Window
- [ ] Press 1 → 100% Actual Size
- [ ] Press + → Step through zoom levels (25%, 33%, 50%... 800%)
- [ ] Press - → Step back through zoom levels
- [ ] Window resize → Auto-adjust in fit/fill modes
- [ ] Status displays correct zoom level
- [ ] No stretching/distortion at any zoom level

### 3. Window Sizing Tests
- [ ] Opens at 90% screen size
- [ ] Centered on screen
- [ ] Starts maximized (not fullscreen)
- [ ] F11 → Enter fullscreen
- [ ] F11 → Exit fullscreen
- [ ] Toolbars auto-hide in fullscreen
- [ ] Toolbars stay visible when not fullscreen

### 4. Integration Tests
- [ ] Zoom + auto-hide work together
- [ ] Fullscreen + auto-hide work together
- [ ] Window resize + zoom adjustment
- [ ] Keyboard shortcuts work in all modes
- [ ] Video playback unaffected

---

## Rollout Plan

### Phase 1: Auto-Hide System (60 LOC)
**Priority:** High
**Estimated Time:** 1-2 hours

1. Add opacity effects and animations
2. Implement mouse tracking
3. Add auto-hide timer
4. Increase button sizes
5. Test fade animations

### Phase 2: Zoom System (120 LOC)
**Priority:** High
**Estimated Time:** 2-3 hours

1. Define zoom steps
2. Rewrite zoom methods
3. Add fit/fill/actual modes
4. Update status display
5. Add keyboard shortcuts
6. Test all zoom levels

### Phase 3: Window Sizing (40 LOC)
**Priority:** Medium
**Estimated Time:** 1 hour

1. Update initial window geometry
2. Enhance fullscreen toggle
3. Update toolbar behavior
4. Test resize handling

### Total Estimated Time: 4-6 hours

---

## Success Criteria

✅ **Auto-Hide System**
- Toolbars hidden by default
- Smooth 200ms fade on reveal
- 2-second auto-hide timeout
- Larger 56x56px buttons
- Professional Google Photos-style appearance

✅ **Zoom System**
- 11 predictable zoom steps
- Clear mode indicators
- Keyboard shortcuts (0, 1, +/-)
- No stretching/distortion
- Auto-adjust on resize

✅ **Window Management**
- Opens at 90% screen size, centered
- Starts maximized (user choice)
- F11 fullscreen toggle
- Toolbars auto-hide in fullscreen
- Professional appearance

---

## Backward Compatibility

**All changes are backward compatible:**
- Existing keyboard shortcuts preserved
- Video playback unchanged
- Info panel behavior unchanged
- Navigation buttons unchanged
- Slideshow mode unchanged

**Only improvements:**
- Better UX with auto-hide
- More predictable zoom
- Smarter window sizing

---

## Future Enhancements (Out of Scope)

1. **Zoom to Selection** - Click+drag to zoom to specific area
2. **Zoom History** - Return to previous zoom level
3. **Custom Zoom Input** - Type exact percentage (e.g., "125%")
4. **Zoom Presets** - Save favorite zoom levels
5. **Touch Gestures** - Pinch-to-zoom support
6. **Thumbnail Strip** - Bottom filmstrip for quick navigation

---

## Conclusion

This plan transforms MediaLightbox from a basic viewer into a **professional-grade photo viewer** matching industry leaders:

- **Google Photos** - Auto-hide UI, clean viewing
- **Adobe Lightroom** - Stepped zoom, professional controls
- **Apple Photos** - Smart sizing, polished appearance

**Expected Result:** A distraction-free, professional photo viewing experience that delights users and matches modern photo app expectations.
