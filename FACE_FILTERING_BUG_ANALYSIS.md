# Face Filtering Bug - Deep Analysis

## Summary
Clicking on people/faces in Google Photos layout shows "No photos found" even though face_crops table has entries for those faces.

---

## What We Know (From Debug Logs)

### ✅ **Confirmed Facts:**

1. **Face Detection Works**
   - 21 photos processed
   - 33 faces detected
   - 12 person groups (face_000 through face_011)

2. **face_crops Table Has Data**
   - face_000: 8 face crops across 8 unique images
   - face_006: 7 face crops
   - face_011: 3 face crops
   - Total: 33 entries, 12 unique branch_keys

3. **Paths Look Identical**
   ```
   face_crops:      c:/users/asus/onedrive/documents/python/test-photos/photos/refs/1/ewkj3802.jpg
   photo_metadata:  c:/users/asus/onedrive/documents/python/test-photos/photos/refs/1/ewkj3802.jpg
   ```

4. **SQL Query Structure**
   ```sql
   SELECT DISTINCT pm.path, pm.date_taken, pm.width, pm.height
   FROM photo_metadata pm
   JOIN project_images pi ON pm.path = pi.image_path
   WHERE pi.project_id = 1
   AND pm.date_taken IS NOT NULL
   AND pm.path IN (
       SELECT DISTINCT image_path
       FROM face_crops
       WHERE project_id = 1 AND branch_key = 'face_000'
   )
   ```

5. **Parameters**: `[1, 1, 'face_000']` → (project_id, project_id, branch_key)

6. **Result**: "No photos found in project 1"

---

## The Mystery

**If paths are identical, why does the query return 0 results?**

### Possible Causes (in order of likelihood):

#### **1. Photos Not in project_images Table** ⭐⭐⭐⭐⭐ (Most Likely)

**Hypothesis**: The photos in face_crops exist in photo_metadata, but are NOT linked in project_images for project_id=1.

**The JOIN Requires**:
```sql
JOIN project_images pi ON pm.path = pi.image_path
WHERE pi.project_id = 1
```

**This means**: A photo MUST be in project_images table linked to project 1, otherwise JOIN returns no rows!

**Why This Happens**:
- Face detection ran on all photos in photo_metadata
- But only some photos were added to project_images for project 1
- Result: face_crops has faces from photos that aren't in the current project

**How to Verify**:
```sql
-- Check if face_000 paths are in project_images
SELECT COUNT(*)
FROM face_crops fc
JOIN project_images pi ON fc.image_path = pi.image_path
WHERE fc.branch_key = 'face_000' AND fc.project_id = 1 AND pi.project_id = 1;
-- If this returns 0, that's the problem!
```

---

#### **2. Face Detection Used Wrong project_id** ⭐⭐⭐⭐

**Hypothesis**: Face detection stored faces with project_id=1, but the photos actually belong to a different project.

**How to Verify**:
```sql
-- Check what project the photos are actually in
SELECT DISTINCT pi.project_id
FROM face_crops fc
JOIN project_images pi ON fc.image_path = pi.image_path
WHERE fc.branch_key = 'face_000';
-- If this returns project_id=2 or 3, that's the mismatch!
```

---

#### **3. Subtle Path Differences** ⭐⭐

**Hypothesis**: Paths look identical but have subtle differences (whitespace, encoding, etc.)

**How to Verify**:
```sql
-- Check exact byte-level comparison
SELECT fc.image_path AS fc_path, pm.path AS pm_path,
       LENGTH(fc.image_path) AS fc_len, LENGTH(pm.path) AS pm_len
FROM face_crops fc
CROSS JOIN photo_metadata pm
WHERE fc.branch_key = 'face_000' AND fc.image_path LIKE '%ewkj3802%'
  AND pm.path LIKE '%ewkj3802%';
-- If lengths differ, there's whitespace/encoding issue
```

---

#### **4. date_taken IS NULL** ⭐

**Hypothesis**: Photos in face_crops don't have date_taken metadata.

**The query filters**: `AND pm.date_taken IS NOT NULL`

**How to Verify**:
```sql
SELECT COUNT(*)
FROM photo_metadata pm
WHERE pm.path IN (
    SELECT image_path FROM face_crops WHERE branch_key = 'face_000'
)
AND pm.date_taken IS NULL;
-- If this is > 0, some photos are being filtered out
```

---

## Recommended Fix Strategy (Tomorrow)

### **Step 1: Quick Diagnosis**

Run these queries directly in SQLite:

```sql
-- Query 1: Are face_000 photos in project_images at all?
SELECT fc.image_path, pi.project_id
FROM face_crops fc
LEFT JOIN project_images pi ON fc.image_path = pi.image_path
WHERE fc.branch_key = 'face_000' AND fc.project_id = 1
LIMIT 5;

-- Query 2: How many match?
SELECT
    COUNT(*) as total_face_crops,
    COUNT(pi.image_path) as in_project_images
FROM face_crops fc
LEFT JOIN project_images pi ON fc.image_path = pi.image_path AND pi.project_id = 1
WHERE fc.branch_key = 'face_000' AND fc.project_id = 1;
```

---

### **Step 2: Apply Fix Based on Results**

#### **If photos NOT in project_images** (Expected):

**Option A: Fix the query** (Quick fix, might not be semantically correct)
```sql
-- Remove project_images requirement
SELECT DISTINCT pm.path, pm.date_taken, pm.width, pm.height
FROM photo_metadata pm
WHERE pm.date_taken IS NOT NULL
AND pm.path IN (
    SELECT DISTINCT image_path
    FROM face_crops
    WHERE project_id = 1 AND branch_key = 'face_000'
)
```

**Option B: Fix face_crops project_id** (Proper fix if detection ran on wrong project)
```sql
-- Update face_crops to match actual project
UPDATE face_crops
SET project_id = (
    SELECT pi.project_id
    FROM project_images pi
    WHERE pi.image_path = face_crops.image_path
    LIMIT 1
)
WHERE project_id = 1;
```

**Option C: Add photos to project_images** (If photos should be in project)
```sql
-- Add missing photos to project_images
INSERT INTO project_images (project_id, image_path)
SELECT DISTINCT 1, image_path
FROM face_crops
WHERE project_id = 1
AND image_path NOT IN (
    SELECT image_path FROM project_images WHERE project_id = 1
);
```

---

#### **If photos in WRONG project**:

**Fix**: Update face_crops to use correct project_id
```sql
UPDATE face_crops
SET project_id = (
    SELECT pi.project_id
    FROM project_images pi
    WHERE pi.image_path = face_crops.image_path
    LIMIT 1
);
```

---

### **Step 3: Test Fix**

After applying fix:
1. Restart app
2. Go to Google Photos layout
3. Click on face_000
4. Should see 8 photos!

---

## Code Changes Needed (If Query Fix)

If we need to remove project_images JOIN requirement:

**File**: `layouts/google_layout.py`
**Line**: ~874-880

**Change FROM**:
```python
query_parts = ["""
    SELECT DISTINCT pm.path, pm.date_taken, pm.width, pm.height
    FROM photo_metadata pm
    JOIN project_images pi ON pm.path = pi.image_path
    WHERE pi.project_id = ?
    AND pm.date_taken IS NOT NULL
"""]
```

**Change TO**:
```python
query_parts = ["""
    SELECT DISTINCT pm.path, pm.date_taken, pm.width, pm.height
    FROM photo_metadata pm
    WHERE pm.project_id = ?
    AND pm.date_taken IS NOT NULL
"""]
```

**But this requires**: photo_metadata table to have project_id column!

---

## Next Session TODO

1. ✅ Pull latest code to get project_images debug
2. ✅ Test and share log with project_images check output
3. ✅ Run diagnostic SQL queries above
4. ✅ Apply appropriate fix based on findings
5. ✅ Test face filtering works
6. ✅ Commit and push fix

---

## Files to Check Tomorrow

- `layouts/google_layout.py` - Query construction
- `workers/face_detection_worker.py` - How project_id is set
- `workers/face_cluster_worker.py` - How clustering assigns branch_keys
- `reference_db.py` - Schema definitions

---

## Most Likely Solution (My Prediction)

**The issue**: Photos in face_crops aren't in project_images for project 1.

**The fix**: Either:
1. Remove the project_images JOIN from the query (if photo_metadata has project_id)
2. OR add the photos to project_images
3. OR fix face_crops to use correct project_id

We'll know for sure once we see the project_images debug output tomorrow!

---

**Status**: Ready for debugging tomorrow morning! 🌅
