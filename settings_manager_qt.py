# settings_manager_qt.py
# Version 09.16.01.01 dated 20251020
#

import json, os
import warnings
import logging



SETTINGS_FILE = "photo_app_settings.json"

DEFAULT_SETTINGS = {
    "skip_unchanged_photos": True,  # ✅ incremental scanning
    "use_exif_for_date": True,
    "dark_mode": False,
    "language": "en",  # Language code (en, ar, es, etc.)
    "thumbnail_cache_enabled": True,
    "cache_size_mb": 500,
    "show_decoder_warnings": False,  # if True, Qt + Pillow warnings are visible
    "db_debug_logging": False,
    "show_sql_queries": False,
    "use_cache_warmup": True,   # 👈 new toggle, on by default
    "cache_auto_cleanup": True,  # 👈 added new default
    "ffprobe_path": "",  # Custom path to ffprobe executable (empty = use system PATH)

    # Scan exclusions (folders to skip during photo scanning)
    # Empty list = use platform-specific defaults from PhotoScanService
    # Non-empty list = override defaults with custom exclusions
    "scan_exclude_folders": [],  # Example: ["node_modules", ".git", "my_private_folder"]

    # --- Badge overlay settings ---
    "badge_overlays_enabled": True,
    "badge_size_px": 22,
    "badge_shape": "circle",  # circle | rounded | square
    "badge_max_count": 4,
    "badge_shadow": True,
    
    # --- GPS & Location settings ---
    "gps_clustering_radius_km": 5.0,  # Cluster photos within this radius (1-50 km)
    "gps_reverse_geocoding_enabled": True,  # Auto-fetch location names from coordinates
    "gps_geocoding_timeout_sec": 2.0,  # Timeout for reverse geocoding API calls
    "gps_cache_location_names": True,  # Cache location names to reduce API calls
}


# ============================================================
# 🧠 Decoder warning toggle integration (Qt + Pillow)
# ============================================================

def apply_decoder_warning_policy():
    """
    Apply global decoder warning visibility according to settings.
    Called early in app startup (before any Qt GUI creation).
    """
    sm = SettingsManager()
    show_warnings = sm.get("show_decoder_warnings", False)

    if not show_warnings:
        # Silence Qt image I/O warnings globally
        os.environ["QT_LOGGING_RULES"] = "qt.gui.imageio.warning=false"

        # Silence Pillow decompression & ICC noise
        warnings.filterwarnings("ignore", message=".*DecompressionBombWarning.*")
        warnings.filterwarnings("ignore", message=".*invalid rendering intent.*")
        warnings.filterwarnings("ignore", message=".*iCCP.*")
        logging.getLogger("PIL").setLevel(logging.ERROR)

        print("🔇 Decoder warnings suppressed (Qt, Pillow, ICC).")
    else:
        os.environ.pop("QT_LOGGING_RULES", None)
        logging.getLogger("PIL").setLevel(logging.INFO)
        print("⚠️ Decoder warnings ENABLED for debugging.")


class SettingsManager:
    def __init__(self):
        self._data = DEFAULT_SETTINGS.copy()
        self._load()

    def _load(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._data.update(data)
            except Exception:
                pass

    def save(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            print(f"[Settings] Save failed: {e}")

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
        self.save()

    def get_setting(self, key, default=None):
        """Alias for get() for compatibility."""
        return self.get(key, default)

    def set_setting(self, key, value):
        """Alias for set() for compatibility."""
        self.set(key, value)
