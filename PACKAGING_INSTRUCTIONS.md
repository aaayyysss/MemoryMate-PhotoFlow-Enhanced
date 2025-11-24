# MemoryMate-PhotoFlow Packaging Instructions

**Updated**: 2025-11-24 (Phase 2 - Device Monitor fixes)

Complete guide to package MemoryMate-PhotoFlow as a standalone Windows executable that runs on PCs without Python installed.

---

## 📋 Prerequisites

### 1. Python Environment
- Python 3.8+ (64-bit recommended)
- Virtual environment (recommended)

### 2. Install Dependencies
```bash
# Create virtual environment (recommended)
python -m venv venv
venv\Scripts\activate

# Install all dependencies
pip install -r requirements.txt

# Install PyInstaller
pip install pyinstaller>=6.0.0
```

### 3. Download Face Detection Models
**CRITICAL**: Run face detection at least once before packaging to download the buffalo_l models:
```bash
python download_face_models.py
```

Or run the app once and trigger face detection:
```bash
python main_qt.py
```

The models will be downloaded to:
```
C:\Users\YourUsername\.insightface\models\buffalo_l\
```

**Verify models exist** before packaging! The spec file will bundle these.

---

## 🏗️ Building the Executable

### Step 1: Clean Previous Builds
```bash
# Remove previous build artifacts
rmdir /s /q build
rmdir /s /q dist
del *.spec.bak
```

### Step 2: Run PyInstaller
```bash
pyinstaller memorymate_pyinstaller.spec
```

**Expected output**:
```
Found 9 model files in C:\Users\YourUsername\.insightface\models\buffalo_l
...
Building EXE from EXE-00.toc completed successfully.
```

### Step 3: Verify Build
Check the `dist/MemoryMate-PhotoFlow/` directory contains:
- `MemoryMate-PhotoFlow-v2.0.1.exe` - Main executable
- `_internal/` - All dependencies and libraries
- `lang/` - Language files
- `locales/` - Locale data
- `config/` - Configuration files
- `migrations/` - Database migrations
- `insightface/models/buffalo_l/` - Face detection models

---

## 🧪 Testing the Package

### On the Build PC (with Python):
```bash
cd dist\MemoryMate-PhotoFlow
MemoryMate-PhotoFlow-v2.0.1.exe
```

### On Target PC (without Python):
1. Copy entire `dist/MemoryMate-PhotoFlow/` folder to target PC
2. Run `MemoryMate-PhotoFlow-v2.0.1.exe`
3. Test key features:
   - ✅ Application launches without console window
   - ✅ Face detection works (models loaded correctly)
   - ✅ Mobile device detection (auto/manual modes)
   - ✅ Photo scanning and metadata extraction
   - ✅ Video playback
   - ✅ Database operations (create/read/update)
   - ✅ Language switching
   - ✅ Settings persistence

---

## 🚨 Common Issues & Solutions

### Issue 1: "InsightFace models not found"
**Symptom**: Face detection fails with "models not found" error

**Solution**:
1. Verify models exist: `dir %USERPROFILE%\.insightface\models\buffalo_l`
2. Re-run: `python download_face_models.py`
3. Rebuild: `pyinstaller memorymate_pyinstaller.spec`

### Issue 2: "Module not found: device_monitor"
**Symptom**: Import error on device auto-detection

**Solution**: Spec file updated to include `services.device_monitor` (fixed in this version)

### Issue 3: Console window appears
**Symptom**: Black console window shows behind app

**Solution**: Spec file set to `console=False` (fixed in this version)

### Issue 4: Missing dependencies
**Symptom**: Import errors for opencv, insightface, sklearn, etc.

**Solution**:
```bash
pip install -r requirements.txt
pyinstaller memorymate_pyinstaller.spec
```

### Issue 5: "Permission denied" errors on Windows
**Symptom**: Can't write to Program Files directory

**Solution**: Install to user directory (e.g., `C:\Users\YourUsername\AppData\Local\MemoryMate-PhotoFlow\`)

---

## 📦 Distribution Package Structure

```
MemoryMate-PhotoFlow/
├── MemoryMate-PhotoFlow-v2.0.1.exe    # Main executable
├── _internal/                          # PyInstaller internals
│   ├── base_library.zip               # Python standard library
│   ├── python311.dll                  # Python runtime
│   ├── PySide6/                       # Qt framework
│   ├── insightface/                   # Face detection
│   ├── cv2/                           # OpenCV
│   ├── sklearn/                       # Scikit-learn
│   ├── onnxruntime/                   # ONNX runtime
│   └── ...other dependencies...
├── lang/                               # Language files (en, fr, nl, es, pt)
├── locales/                            # Locale data
├── config/                             # Configuration files
├── migrations/                         # Database migration scripts
├── insightface/models/buffalo_l/       # Face detection models
│   ├── 1k3d68.onnx
│   ├── 2d106det.onnx
│   ├── det_10g.onnx
│   ├── genderage.onnx
│   ├── w600k_r50.onnx
│   └── ...other model files...
└── README.txt                          # User instructions (optional)
```

**Total size**: ~1.5-2.0 GB (includes ML models and Qt framework)

---

## 🔧 Customization Options

### Debug Mode (Show Console)
Edit `memorymate_pyinstaller.spec` line 209:
```python
console=True,  # Shows console window for debugging
```

### Optimize Binary Size
Add to spec file:
```python
upx=True,           # Compress binaries (already enabled)
upx_exclude=[       # Exclude large files that don't compress well
    'vcruntime140.dll',
    'python311.dll',
],
```

### Single-File Executable (Not Recommended)
Replace `COLLECT` with `onefile=True` in `EXE`:
```python
exe = EXE(
    ...
    onefile=True,  # Creates single .exe (slower startup, larger size)
    ...
)
```

**Note**: Single-file is NOT recommended for this app due to:
- Large ML models (buffalo_l ~150MB)
- Slow extraction on every startup
- Potential antivirus false positives

---

## ✅ Audit Checklist

Before releasing, verify:

- [x] All dependencies in requirements.txt
- [x] InsightFace models bundled correctly
- [x] services.device_monitor included (Phase 2 fix)
- [x] Root-level UI modules included (sidebar_qt, etc.)
- [x] ctypes.wintypes for Windows device detection
- [x] console=False for production
- [x] app_icon.ico applied
- [x] Runtime hook for InsightFace paths
- [x] Language files (lang/, locales/)
- [x] Database migrations
- [x] Test utilities excluded

---

## 📝 Version History

**v2.0.1** (2025-11-24 - Phase 2)
- ✅ Fixed mobile device detection (auto + manual modes)
- ✅ Fixed scan freeze at 9% (ThreadPoolExecutor deadlock)
- ✅ Added device_monitor to packaging
- ✅ Added scan result caching
- ✅ Enhanced progress feedback

**v2.0.0** (2025-11-XX)
- Initial packaging with face detection
- InsightFace buffalo_l integration
- Windows MTP device support

---

## 🆘 Support

If packaging fails:
1. Check console output for missing modules
2. Verify all dependencies installed: `pip list`
3. Ensure models downloaded: `dir %USERPROFILE%\.insightface`
4. Clean build: `rmdir /s /q build dist`
5. Rebuild: `pyinstaller memorymate_pyinstaller.spec`

For runtime errors on target PC:
1. Check Windows Event Viewer (Application logs)
2. Run with debug mode: Edit spec `console=True` and rebuild
3. Check crash_log.txt in app directory

---

**Last Updated**: 2025-11-24 (Phase 2 - Transaction Fixes & Device Optimization)
