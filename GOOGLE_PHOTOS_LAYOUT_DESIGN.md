# Google Photos Layout - Design Specification

## 📐 Layout Structure Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ ⚠️ MENU BAR (STAYS FIXED - NOT PART OF LAYOUT)                │
├─────────────────────────────────────────────────────────────────┤
│ 📂 Scan │ 👤 Faces │ 🔍 Search │ ↻ │ ⬆️ │ 🗑️ │ ⭐          │ ← GOOGLE TOOLBAR
├───────────┬─────────────────────────────────────────────────────┤
│           │  📅 December 2024                      [Zoom: ⊖ ⊕] │
│  SIDEBAR  │  ┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐ │
│           │  │     │     │     │     │     │     │     │     │ │
│  📅 2024  │  │ IMG │ IMG │ IMG │ IMG │ IMG │ IMG │ IMG │ IMG │ │
│  • Dec 15 │  │     │     │     │     │     │     │     │     │ │
│  • Dec 10 │  └─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┘ │
│  • Nov 28 │                                                     │
│           │  📅 November 2024                      [Zoom: ⊖ ⊕] │
│  📅 2023  │  ┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐ │
│  • Dec 25 │  │     │     │     │     │     │     │     │     │ │
│  • Nov 10 │  │ IMG │ IMG │ IMG │ IMG │ IMG │ IMG │ IMG │ IMG │ │
│           │  │     │     │     │     │     │     │     │     │ │
│  📁 Albums│  └─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┘ │
│  • Family │                                                     │
│  • Vacatn │  📅 October 2024                       [Zoom: ⊖ ⊕] │
│  • Work   │  ┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐ │
│           │  │ IMG │ IMG │ IMG │ IMG │ IMG │ IMG │ IMG │ IMG │ │
└───────────┴─────────────────────────────────────────────────────┘
```

## 🎨 Design Philosophy

**Goal:** Emulate Google Photos' clean, timeline-based approach:
- **Timeline First:** Photos grouped by date (year/month/day)
- **Minimal Chrome:** Clean interface, photos are the focus
- **Large Thumbnails:** Generous spacing, zoomable
- **Quick Access:** Sidebar for fast date/album navigation
- **Batch Operations:** Select multiple photos easily

## 📦 Component Breakdown

### 1. **Minimal Sidebar** (200px width, collapsible)

#### **Search Section:**
```
┌─────────────────────┐
│ 🔍 Search photos... │
└─────────────────────┘
```
- Full-text search
- Filter by date/location/people

#### **Timeline Navigation:**
```
📅 Years & Months
  📅 2024
    • December (15 photos)
    • November (32 photos)
    • October (28 photos)
  📅 2023
    • December (45 photos)
    • November (20 photos)
```
- Click year to expand/collapse months
- Click month to jump to that section in timeline

#### **Albums Section:**
```
📁 Albums
  • 📷 Family (120 photos)
  • 🏖️ Vacation (85 photos)
  • 💼 Work (45 photos)
  + Create new album
```
- User-created albums
- Click to filter timeline to album photos

#### **Settings/Actions:**
```
⚙️ Layout Settings
  • Thumbnail size
  • Date grouping
  • View density
```

---

### 2. **Timeline View** (Main Content Area)

#### **Structure:**

Each date group is a self-contained section:

```
┌─────────────────────────────────────────────────────────────────┐
│ 📅 December 15, 2024 (Monday)               [🔽 Collapse] [Zoom]│
├─────────────────────────────────────────────────────────────────┤
│ [✓] Select All (8 photos)                                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│  │         │ │         │ │         │ │         │ │         │  │
│  │  IMG    │ │  IMG    │ │  IMG    │ │  IMG    │ │  IMG    │  │
│  │ 3264x   │ │ 3264x   │ │ 3264x   │ │ 3264x   │ │ 3264x   │  │
│  │ 2448    │ │ 2448    │ │ 2448    │ │ 2448    │ │ 2448    │  │
│  └─────────┘ └─────────┘ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│                          │         │ │         │ │         │  │
│  ┌─────────┐ ┌─────────┐ │  IMG    │ │  IMG    │ │  IMG    │  │
│  │         │ │         │ │         │ │         │ │         │  │
│  │  IMG    │ │  IMG    │ └─────────┘ └─────────┘ └─────────┘  │
│  │         │ │         │                                       │
│  └─────────┘ └─────────┘                                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ 📅 December 10, 2024 (Wednesday)            [🔽 Collapse] [Zoom]│
├─────────────────────────────────────────────────────────────────┤
│ [✓] Select All (12 photos)                                      │
├─────────────────────────────────────────────────────────────────┤
│  (photos...)                                                     │
└─────────────────────────────────────────────────────────────────┘
```

#### **Date Group Features:**

1. **Header Bar:**
   - Date (formatted: "December 15, 2024 (Monday)")
   - Photo count
   - Collapse/expand button
   - Zoom slider specific to this group

2. **Selection Bar:**
   - "Select All" checkbox for this date group
   - Shows selection count when photos selected

3. **Photo Grid:**
   - Responsive grid (adjusts to window width)
   - Default: 5-8 photos per row
   - Large thumbnails (200px default, zoomable 150-350px)
   - Hover: Show selection checkbox overlay
   - Click: Open photo details/lightbox

---

### 3. **Google Photos Layout Toolbar** (Built into layout)

```
┌────────────────────────────────────────────────────────────────────────┐
│ 📂 Scan Repository │ 👤 Detect Faces │ 🔍 [Search...] │ ↻ Refresh │   │
│ ⬆️ Upload │ 🗑️ Delete │ ⭐ Favorite │ 📤 Share                        │
└────────────────────────────────────────────────────────────────────────┘
```

**Primary Actions (Always Visible):**
- 📂 **Scan Repository** - Scan folder to add new photos to database
- 👤 **Detect Faces** - Run face detection and clustering on photos
- 🔍 **Search** - Filter photos by keyword, date, or tags
- ↻ **Refresh** - Reload timeline from database

**Selection Actions (Show when photos selected):**
- ⬆️ **Upload** - Add new photos manually
- 🗑️ **Delete** - Delete selected photos
- ⭐ **Favorite** - Mark selected as favorites
- 📤 **Share** - Export/share selected photos

**Note:** This toolbar is PART OF the Google layout (not the main app toolbar)

**Important:** Scan Repository and Face Detection are **critical workflows** that must be easily accessible in this layout, so they're prominently placed at the start of the toolbar.

---

### 4. **Batch Selection UI** - Clarification

#### **What is Batch Selection?**

"Batch selection" means the ability to select multiple photos at once for bulk operations.

#### **How It Works in Google Photos Style:**

**Visual Indicators:**
```
Normal State:
┌─────────┐
│         │
│  IMG    │
│         │
└─────────┘

Hover State:
┌─────────┐
│ [ ]     │  ← Checkbox appears
│  IMG    │
│         │
└─────────┘

Selected State:
┌─────────┐
│ [✓]     │  ← Checked, photo highlighted
│  IMG    │
│         │
└─────────┘
```

**Selection Methods:**

1. **Click Checkbox:** Toggle individual photo
2. **Shift+Click:** Select range (from last selected to clicked)
3. **Ctrl+Click:** Add/remove from selection
4. **"Select All" (per date):** Select all photos in that date group
5. **Drag Select:** (Future enhancement) Drag to select multiple

**Selection Actions Bar:**

When photos are selected, show floating action bar:
```
┌─────────────────────────────────────────────────────────────────┐
│ ✓ 15 photos selected │ ⭐ Favorite │ 🗑️ Delete │ 📤 Share │ ✕ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔧 Technical Implementation Plan

### **Component Structure:**

```
google_layout.py
├── GooglePhotosLayout (BaseLayout)
│   ├── create_layout() → QWidget
│   │   ├── Main Splitter (Horizontal)
│   │   │   ├── GooglePhotosSidebar (200px)
│   │   │   │   ├── Search Bar
│   │   │   │   ├── Timeline Tree (years/months)
│   │   │   │   └── Albums List
│   │   │   └── GooglePhotosTimeline (Main Area)
│   │   │       ├── Timeline Toolbar
│   │   │       ├── Scroll Area
│   │   │       │   └── Date Groups Container
│   │   │       │       ├── DateGroup Widget (Dec 15)
│   │   │       │       │   ├── Header (date, collapse, zoom)
│   │   │       │       │   ├── Selection Bar
│   │   │       │       │   └── Photo Grid (FlowLayout)
│   │   │       │       ├── DateGroup Widget (Dec 10)
│   │   │       │       └── DateGroup Widget (Nov 28)
│   │   │       └── Selection Action Bar (floating)
```

### **Key Classes:**

1. **GooglePhotosLayout** - Main layout class
2. **GooglePhotosSidebar** - Left sidebar widget
3. **GooglePhotosTimeline** - Timeline scroll area
4. **DateGroupWidget** - Individual date section
5. **PhotoThumbnailWidget** - Single photo with selection
6. **SelectionActionBar** - Floating action bar for selected photos

### **Data Flow:**

```
Database (photo_metadata)
    ↓ Group by date_taken
Timeline Groups (by year/month/day)
    ↓ Render
DateGroupWidget (per day)
    ↓ Load thumbnails
PhotoThumbnailWidget (per photo)
    ↓ User interaction
Selection State
    ↓ Show/hide
SelectionActionBar
```

---

## 🎯 Features Breakdown

### **Phase 1: Core Layout (Must Have)**
✅ Minimal sidebar (search + timeline navigation + albums)
✅ Timeline view with date grouping (by day)
✅ Large zoomable thumbnails (200px default)
✅ Photo details on click (lightbox/details panel)
✅ Basic batch selection (checkboxes + selection state)

### **Phase 2: Enhanced Selection (Nice to Have)**
⚠️ Selection action bar (delete, favorite, share)
⚠️ Shift+Click range selection
⚠️ Ctrl+Click multi-selection
⚠️ "Select All" per date group

### **Phase 3: Advanced Features (Future)**
🔮 Drag-to-select
🔮 Search functionality
🔮 Album management
🔮 Photo editing

---

## 🎨 Visual Design Details

### **Colors & Spacing:**

```python
# Google Photos Color Palette
BACKGROUND = "#ffffff"          # Clean white
HEADER_BG = "#f8f9fa"           # Light gray headers
ACCENT_BLUE = "#1a73e8"         # Google blue
SELECTED_OVERLAY = "#e8f0fe"    # Light blue selection
HOVER_OVERLAY = "#f1f3f4"       # Gray hover
TEXT_PRIMARY = "#202124"        # Dark text
TEXT_SECONDARY = "#5f6368"      # Gray text

# Spacing
SIDEBAR_WIDTH = 200
THUMBNAIL_DEFAULT = 200
THUMBNAIL_MIN = 150
THUMBNAIL_MAX = 350
GROUP_SPACING = 20
PHOTO_SPACING = 8
```

### **Typography:**

```python
# Font Sizes
DATE_HEADER = "18pt bold"      # "December 15, 2024"
PHOTO_COUNT = "10pt"           # "(15 photos)"
SIDEBAR_ITEM = "11pt"          # Sidebar entries
```

---

## ❓ Clarification: Batch Selection UI

**Question:** "Batch selection UI? more clarification."

**Answer:**

**Batch Selection UI** refers to the visual interface elements that enable selecting multiple photos at once:

1. **Checkboxes:** Small checkbox overlay on each photo thumbnail
2. **Visual Feedback:** Selected photos show blue border/overlay
3. **Selection Counter:** "15 photos selected"
4. **Action Bar:** Floating bar with actions (Delete, Favorite, Share, etc.)
5. **Keyboard Shortcuts:** Shift/Ctrl for multi-select

**Visual Example:**

```
Before Selection:
┌───────┐ ┌───────┐ ┌───────┐
│       │ │       │ │       │
│ Photo │ │ Photo │ │ Photo │
└───────┘ └───────┘ └───────┘

After Selecting 2 Photos:
┌───────────────────────────────────────┐
│ ✓ 2 selected │ ⭐ │ 🗑️ │ 📤 │ ✕     │ ← Floating Action Bar
└───────────────────────────────────────┘
┌───────┐ ┌───────┐ ┌───────┐
│ [✓]   │ │ [✓]   │ │       │
│ Photo │ │ Photo │ │ Photo │
│ BLUE  │ │ BLUE  │ │       │
└───────┘ └───────┘ └───────┘
  ↑          ↑
Selected   Selected
```

**Do you want this feature in Phase 1?** Or should we start simpler and add it later?

---

## 🚀 Implementation Approach

### **Step 1: Basic Structure**
- Create GooglePhotosLayout class
- Implement minimal sidebar (just structure, no functionality)
- Implement timeline scroll area (empty for now)

### **Step 2: Timeline Rendering**
- Query photos grouped by date
- Create DateGroupWidget
- Render photo thumbnails in grid

### **Step 3: Interactivity**
- Click photo → open lightbox
- Zoom slider → adjust thumbnail size
- Collapse/expand date groups

### **Step 4: Selection (if Phase 1)**
- Add checkboxes to thumbnails
- Track selection state
- Show selection action bar

---

## 📊 Performance Considerations

1. **Lazy Loading:** Only render visible date groups
2. **Thumbnail Caching:** Reuse existing thumbnail cache
3. **Virtual Scrolling:** For very large photo collections
4. **Batch Rendering:** Render 50-100 photos at a time

---

## ✅ Review Checklist

Before implementation, please confirm:

- [ ] Layout structure looks good?
- [ ] Sidebar features are what you want?
- [ ] Timeline date grouping is correct?
- [ ] Thumbnail size/zoom approach works?
- [ ] Batch selection UI is clear now?
- [ ] Should we include batch selection in Phase 1, or add it later?
- [ ] Any changes or additions needed?

---

## 🎯 Next Steps

Once you approve this design:

1. Implement `GooglePhotosLayout` class structure
2. Create sidebar components
3. Implement timeline view with date grouping
4. Add photo grid rendering
5. Connect to existing database/thumbnail system
6. Test and refine

**Estimated Implementation:** 3-4 hours of focused work

---

## 📝 Notes

- **Toolbar:** Google layout will have its own toolbar (built into the layout)
- **Generic Toolbar:** Will be hidden or kept for other layouts (we'll decide)
- **Data Source:** Will use existing `photo_metadata` table
- **Thumbnails:** Will use existing thumbnail cache system
- **Lightbox:** Will reuse existing lightbox for photo details

**Ready to proceed?** Please review and let me know what changes (if any) are needed! 🚀
