# Face Cluster Worker Context Manager Fix

**Critical Bug**: `AttributeError: '_GeneratorContextManager' object has no attribute 'cursor'`

## Root Cause

The `ReferenceDB._connect()` method is decorated with `@contextmanager` (line 406 of reference_db.py):

```python
@contextmanager
def _connect(self):
    """
    Usage:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(...)
    """
```

However, `face_cluster_worker.py` was calling it incorrectly:

```python
# WRONG (line 101):
conn = db._connect()  # Returns _GeneratorContextManager, not connection!
cur = conn.cursor()   # ERROR: _GeneratorContextManager has no cursor() method
```

## Fix Required

**File**: `workers/face_cluster_worker.py`

### 1. FaceClusterWorker.run() method (line 94-284)

**Change line 101-102:**
```python
# Before:
conn = db._connect()
cur = conn.cursor()

# After:
with db._connect() as conn:
    cur = conn.cursor()
```

**Then indent lines 104-268** by 4 spaces (to be inside the `with` block)

**Remove** `conn.close()` calls at lines:
- Line 116 (early return for no embeddings)
- Line 135 (early return for not enough faces)
- Line 168 (cancellation return)
- Line 268 (final close)

### 2. cluster_faces_1st() function (line 287-378)

**Change line 293-294:**
```python
# Before:
conn = db._connect()
cur = conn.cursor()

# After:
with db._connect() as conn:
    cur = conn.cursor()
```

**Then indent lines 296-376** by 4 spaces

**Remove** `conn.close()` at line 377

### 3. cluster_faces() function (line 380-534)

**Change line 386-387:**
```python
# Before:
conn = db._connect()
cur = conn.cursor()

# After:
with db._connect() as conn:
    cur = conn.cursor()
```

**Then indent lines 389-529** by 4 spaces

**Remove** `conn.close()` at line 533

## Manual Fix Implementation

Due to the large scope of indentation changes required, the fix should be applied using a Python script that:

1. Detects the three functions
2. Wraps database operations in `with` blocks
3. Properly indents all code inside the blocks
4. Removes manual `conn.close()` calls

## Testing

After applying the fix:

1. **Syntax check**: `python3 -m py_compile workers/face_cluster_worker.py`
2. **Run clustering**: Test with project that has face embeddings
3. **Verify**: No `AttributeError: '_GeneratorContextManager'` errors

## Impact

- **Fixes**: Fatal face clustering crash
- **Improves**: Proper resource cleanup via context manager
- **Risk**: Low - context manager is the correct pattern per ReferenceDB design

## References

- Error log: Debug-Log line 2025-11-21 14:09:38,861
- ReferenceDB._connect(): reference_db.py:406-424
- Python contextmanager: https://docs.python.org/3/library/contextlib.html#contextlib.contextmanager
