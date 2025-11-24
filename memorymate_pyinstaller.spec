# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for MemoryMate-PhotoFlow
Includes proper packaging of InsightFace models and dependencies
"""

import os
import sys
from pathlib import Path

block_cipher = None

# Get the InsightFace models directory
insightface_models_dir = os.path.expanduser('~/.insightface/models/buffalo_l')

# Collect all model files
model_datas = []
if os.path.exists(insightface_models_dir):
    for root, dirs, files in os.walk(insightface_models_dir):
        for file in files:
            src = os.path.join(root, file)
            # Map to insightface/models/buffalo_l in the bundle
            rel_path = os.path.relpath(src, os.path.dirname(insightface_models_dir))
            dst = os.path.join('insightface', 'models', os.path.dirname(rel_path))
            model_datas.append((src, dst))
    print(f"Found {len(model_datas)} model files in {insightface_models_dir}")
else:
    print(f"WARNING: InsightFace models not found at {insightface_models_dir}")
    print("Please run face detection once to download models before packaging")

# Additional data files
datas = [
    # Language files (both directories)
    ('lang', 'lang'),
    ('locales', 'locales'),
    
    # Configuration files
    ('config', 'config'),
    
    # SQL migration files
    ('migrations', 'migrations'),
    
    # Python package directories (required for imports)
    ('repository', 'repository'),
    ('services', 'services'),
    ('workers', 'workers'),
    ('ui', 'ui'),
    ('utils', 'utils'),
    
    # Note: Databases are excluded as requested (reference_data.db, thumb_cache_db, etc.)
    # Users will create fresh databases on first run
]

# Add model files
datas.extend(model_datas)

# Hidden imports for ML libraries and project modules
hiddenimports = [
    # ML/AI libraries
    'insightface',
    'insightface.app',
    'insightface.model_zoo',
    'onnxruntime',
    'onnxruntime.capi',
    'onnxruntime.capi.onnxruntime_pybind11_state',
    'numpy',
    'cv2',
    'PIL',
    'PIL.Image',
    'PIL.ImageOps',
    'PIL.ImageQt',
    'sklearn',
    'sklearn.cluster',
    'sklearn.preprocessing',
    
    # Qt framework
    'PySide6',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',
    
    # Windows COM support (pywin32)
    'win32com',
    'win32com.client',
    'win32com.shell',
    'win32api',
    'win32con',
    'pythoncom',
    'pywintypes',
    
    # HEIF/HEIC image support
    'pillow_heif',
    
    # Project modules
    'repository',
    'repository.base_repository',
    'repository.folder_repository',
    'repository.photo_repository',
    'repository.project_repository',
    'repository.tag_repository',
    'repository.video_repository',
    'repository.migrations',
    'repository.schema',
    
    'services',
    'services.device_id_extractor',
    'services.device_import_service',
    'services.device_sources',
    'services.exif_parser',
    'services.face_detection_service',
    'services.metadata_service',
    'services.mtp_import_adapter',
    'services.photo_deletion_service',
    'services.photo_scan_service',
    'services.search_service',
    'services.tag_service',
    'services.thumbnail_service',
    'services.video_metadata_service',
    'services.video_service',
    'services.video_thumbnail_service',
    
    'workers',
    'workers.face_cluster_worker',
    'workers.face_detection_worker',
    'workers.meta_backfill_pool',
    'workers.meta_backfill_single',
    'workers.mtp_copy_worker',
    'workers.progress_writer',
    'workers.video_metadata_worker',
    'workers.video_thumbnail_worker',
    
    'ui',
    'ui.device_import_dialog',
    'ui.face_settings_dialog',
    'ui.mtp_deep_scan_dialog',
    'ui.mtp_import_dialog',
    'ui.people_list_view',
    'ui.people_manager_dialog',
    
    'utils',
    'utils.translation_manager',
    
    # Core app modules
    'config.face_detection_config',
    'logging_config',
    'db_config',
    'db_writer',
    'settings_manager_qt',
    'app_services',
]

a = Analysis(
    ['main_qt.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyi_rth_insightface.py'],  # Hook to set InsightFace model paths
    excludes=[
        'matplotlib',  # Exclude if not needed
        'tkinter',     # Exclude if not needed
        'pytest',      # Test framework not needed in production
        'tests',       # Test files not needed
        'utils.test_insightface_models',  # Test utility, not needed in production
        'utils.diagnose_insightface',     # Diagnostic utility, not needed in production
        'utils.insightface_check',        # Check utility, not needed in production
        'utils.ffmpeg_check',             # Check utility, not needed in production
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MemoryMate-PhotoFlow-v2.0.1',  # Updated version for device fix
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Set to True for debugging, False for production windowed app
    disable_windowing_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add path to .ico file if you have one
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MemoryMate-PhotoFlow'
)
