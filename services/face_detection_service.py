# face_detection_service.py
# Phase 5: Face Detection Service using InsightFace
# Detects faces in photos and generates 512-dimensional embeddings
# Uses InsightFace with buffalo_l model and OnnxRuntime backend
# ------------------------------------------------------

import os
import numpy as np
from typing import List, Tuple, Optional
from PIL import Image
import logging
import cv2
import threading

from config.face_detection_config import get_face_config

logger = logging.getLogger(__name__)

# Lazy import InsightFace (only load when needed)
_insightface_app = None
_providers_used = None
_insightface_lock = threading.Lock()  # Thread-safe initialization lock (P0 Fix #4)


def _detect_available_providers():
    """
    Detect available ONNX Runtime providers (GPU/CPU).

    Returns automatic GPU detection based on proof of concept from OldPy/photo_sorter.py

    Returns:
        tuple: (providers_list, hardware_type)
            - providers_list: List of provider names for ONNXRuntime
            - hardware_type: 'GPU' or 'CPU'
    """
    try:
        import onnxruntime as ort
        available_providers = ort.get_available_providers()

        # Prefer GPU (CUDA), fallback to CPU
        if 'CUDAExecutionProvider' in available_providers:
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
            hardware_type = 'GPU'
            logger.info("🚀 CUDA (GPU) available - Using GPU acceleration for face detection")
        else:
            providers = ['CPUExecutionProvider']
            hardware_type = 'CPU'
            logger.info("💻 Using CPU for face detection (CUDA not available)")

        return providers, hardware_type

    except ImportError:
        logger.warning("ONNXRuntime not found, defaulting to CPU")
        return ['CPUExecutionProvider'], 'CPU'


def _find_buffalo_directory():
    """
    Find buffalo_l directory, accepting both standard and non-standard structures.

    Accepts:
    - det_10g.onnx (standard detector)
    - scrfd_10g_bnkps.onnx (alternative detector)

    Returns:
        Path to buffalo_l directory (not parent), or None if not found
    """
    import sys

    # Detector variants (accept either one)
    detector_variants = ['det_10g.onnx', 'scrfd_10g_bnkps.onnx']

    def has_detector(path):
        """Check if path contains at least one detector variant."""
        for detector in detector_variants:
            if os.path.exists(os.path.join(path, detector)):
                return True
        return False

    # Priority 1: Custom path from settings (offline use)
    try:
        from settings_manager_qt import SettingsManager
        settings = SettingsManager()
        custom_path = settings.get_setting('insightface_model_path', '')
        if custom_path and os.path.exists(custom_path):
            # Check if this IS the buffalo_l directory
            if has_detector(custom_path):
                logger.info(f"🎯 Using custom model path (buffalo_l directory): {custom_path}")
                return custom_path

            # Check for models/buffalo_l/ subdirectory
            buffalo_sub = os.path.join(custom_path, 'models', 'buffalo_l')
            if os.path.exists(buffalo_sub) and has_detector(buffalo_sub):
                logger.info(f"🎯 Using custom model path: {buffalo_sub}")
                return buffalo_sub

            # Check for buffalo_l/ subdirectory (non-standard)
            buffalo_sub = os.path.join(custom_path, 'buffalo_l')
            if os.path.exists(buffalo_sub) and has_detector(buffalo_sub):
                logger.info(f"🎯 Using custom model path (nested): {buffalo_sub}")
                return buffalo_sub

            # Check for nested buffalo_l/buffalo_l/ (user's structure from log)
            buffalo_nested = os.path.join(custom_path, 'buffalo_l', 'buffalo_l')
            if os.path.exists(buffalo_nested) and has_detector(buffalo_nested):
                logger.info(f"🎯 Using custom model path (double-nested): {buffalo_nested}")
                return buffalo_nested

            logger.warning(f"⚠️ Custom path configured but no valid buffalo_l found: {custom_path}")
    except Exception as e:
        logger.debug(f"Error checking custom path: {e}")

    # Priority 2: PyInstaller bundle
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        bundle_dir = sys._MEIPASS
        buffalo_path = os.path.join(bundle_dir, 'insightface', 'models', 'buffalo_l')
        if os.path.exists(buffalo_path) and has_detector(buffalo_path):
            logger.info(f"🎁 Using bundled models: {buffalo_path}")
            return buffalo_path

    # Priority 3: App directory
    try:
        app_root = os.path.dirname(os.path.dirname(__file__))
        buffalo_path = os.path.join(app_root, 'models', 'buffalo_l')
        if os.path.exists(buffalo_path) and has_detector(buffalo_path):
            logger.info(f"📁 Using local bundled models: {buffalo_path}")
            return buffalo_path
    except Exception as e:
        logger.debug(f"Error checking app directory: {e}")

    # Priority 4: User home
    user_home = os.path.expanduser('~/.insightface')
    buffalo_path = os.path.join(user_home, 'models', 'buffalo_l')
    if os.path.exists(buffalo_path) and has_detector(buffalo_path):
        logger.info(f"🏠 Using user home models: {buffalo_path}")
        return buffalo_path

    # Not found - return None
    logger.warning("⚠️ No buffalo_l models found in any location")
    return None


def _get_insightface_app():
    """
    Lazy load InsightFace application with automatic GPU/CPU detection.

    Uses the proven pattern from OldPy/photo_sorter.py proof of concept:
    - Passes buffalo_l directory DIRECTLY as root (not parent)
    - Does NOT pass providers to FaceAnalysis.__init__() for compatibility
    - Only uses providers for ctx_id selection in prepare()
    - Accepts both det_10g.onnx and scrfd_10g_bnkps.onnx detectors
    - Model caching to avoid reloading

    P0 Fix #4: Uses double-checked locking to prevent race condition
    where multiple threads could initialize models simultaneously.
    """
    global _insightface_app, _providers_used

    # First check without lock (fast path for already initialized)
    if _insightface_app is None:
        # Acquire lock for initialization
        with _insightface_lock:
            # Double-check inside lock (another thread may have initialized)
            if _insightface_app is None:
                try:
                    from insightface.app import FaceAnalysis

                    # Detect best available providers
                    providers, hardware_type = _detect_available_providers()
                    _providers_used = providers

                    # Find buffalo_l directory
                    buffalo_dir = _find_buffalo_directory()

                    if not buffalo_dir:
                        raise RuntimeError(
                            "InsightFace models (buffalo_l) not found.\n\n"
                            "Please configure the model path in Preferences → Face Detection\n"
                            "or download models using: python download_face_models.py"
                        )

                    # P1-8 FIX: Validate ONNX model files exist and have reasonable size
                    import os
                    required_models = ['det_10g.onnx', 'genderage.onnx', 'w600k_r50.onnx']
                    for model_file in required_models:
                        model_path = os.path.join(buffalo_dir, model_file)
                        if not os.path.exists(model_path):
                            logger.warning(f"P1-8: Missing model file: {model_file}")
                        else:
                            file_size = os.path.getsize(model_path)
                            if file_size < 1000:  # Less than 1KB = likely corrupted
                                raise RuntimeError(
                                    f"Model file appears corrupted: {model_file} ({file_size} bytes)\n"
                                    f"Please re-download models using: python download_face_models.py"
                                )
                            logger.debug(f"P1-8: Validated {model_file} ({file_size / 1024 / 1024:.1f} MB)")

                    # Save successful path to settings for future use
                    try:
                        from settings_manager_qt import SettingsManager
                        settings = SettingsManager()
                        current_saved = settings.get_setting('insightface_model_path', '')
                        # Only save if not already set (preserves user's manual configuration)
                        if not current_saved:
                            settings.set_setting('insightface_model_path', buffalo_dir)
                            logger.info(f"💾 Saved InsightFace model path to settings: {buffalo_dir}")
                    except Exception as e:
                        logger.debug(f"Could not save model path to settings: {e}")

                    # CRITICAL: Pass buffalo_l directory DIRECTLY as root
                    # This matches the proof of concept approach from OldPy/photo_sorter.py
                    # Do NOT pass parent directory, pass the buffalo_l directory itself!
                    logger.info(f"✓ Initializing InsightFace with buffalo_l directory: {buffalo_dir}")

                    # COMPATIBILITY: Detect InsightFace version and log details
                    try:
                        import insightface
                        insightface_version = getattr(insightface, '__version__', 'unknown')
                        logger.info(f"📦 InsightFace version: {insightface_version}")
                    except Exception as e:
                        logger.debug(f"Could not detect InsightFace version: {e}")
                        insightface_version = 'unknown'

                    # Version detection: Check if FaceAnalysis supports providers parameter
                    # This ensures compatibility with BOTH old and new InsightFace versions
                    import inspect
                    sig = inspect.signature(FaceAnalysis.__init__)
                    supports_providers = 'providers' in sig.parameters

                    # Initialize FaceAnalysis with version-appropriate parameters
                    # RESTORED FROM WORKING VERSION: Pass BOTH name and root parameters
                    # buffalo_dir IS the buffalo_l directory (not parent), pass it as root
                    # This matches the proven working pattern from previous version
                    init_params = {'name': 'buffalo_l', 'root': buffalo_dir}

                    if supports_providers:
                        # NEWER VERSION: Pass providers for optimal performance
                        init_params['providers'] = providers
                        logger.info(f"✓ Using providers parameter (newer InsightFace v{insightface_version})")
                        logger.info(f"✓ Providers: {providers}")
                        _insightface_app = FaceAnalysis(**init_params)

                        # For newer versions, ctx_id is derived from providers automatically
                        # But we still need to call prepare()
                        # IMPORTANT: det_size MUST be (640, 640) for buffalo_l model
                        # The model was trained specifically for this input size
                        # Using different sizes causes shape mismatch errors

                        # COMPATIBILITY: Use hardware-appropriate ctx_id
                        use_cuda = isinstance(providers, (list, tuple)) and 'CUDAExecutionProvider' in providers
                        ctx_id = 0 if use_cuda else -1

                        try:
                            _insightface_app.prepare(ctx_id=ctx_id, det_size=(640, 640))
                            logger.info(f"✅ InsightFace (buffalo_l v{insightface_version}) loaded successfully")
                            logger.info(f"   Hardware: {hardware_type}, ctx_id={ctx_id}, det_size=640x640")
                        except TypeError as te:
                            # FALLBACK: det_size might not be supported in some versions
                            logger.warning(f"det_size parameter not supported, falling back to default: {te}")
                            _insightface_app.prepare(ctx_id=ctx_id)
                            logger.info(f"✅ InsightFace (buffalo_l v{insightface_version}) loaded with default det_size")
                        except Exception as prepare_error:
                            logger.error(f"Model preparation failed: {prepare_error}")
                            logger.error("This usually means:")
                            logger.error("  1. Model files are corrupted or incomplete")
                            logger.error("  2. InsightFace version incompatible with models")
                            logger.error("  3. Wrong directory structure")
                            raise RuntimeError(f"Failed to prepare InsightFace models: {prepare_error}") from prepare_error
                    else:
                        # OLDER VERSION: Use ctx_id approach (proof of concept compatibility)
                        logger.info(f"✓ Using ctx_id approach (older InsightFace, proof of concept compatible)")
                        _insightface_app = FaceAnalysis(**init_params)

                        # Use providers ONLY for ctx_id selection (proof of concept approach)
                        use_cuda = isinstance(providers, (list, tuple)) and 'CUDAExecutionProvider' in providers
                        ctx_id = 0 if use_cuda else -1
                        logger.info(f"✓ Using {hardware_type} acceleration (ctx_id={ctx_id})")

                        # Prepare model with simple parameters (matches proof of concept)
                        # IMPORTANT: det_size MUST be (640, 640) for buffalo_l model
                        # The model was trained specifically for this input size
                        # Using different sizes causes shape mismatch errors
                        try:
                            _insightface_app.prepare(ctx_id=ctx_id, det_size=(640, 640))
                            logger.info(f"✅ InsightFace (buffalo_l) loaded successfully with {hardware_type} acceleration (det_size=640x640)")
                        except Exception as prepare_error:
                            logger.error(f"Model preparation failed: {prepare_error}")
                            logger.error("This usually means:")
                            logger.error("  1. Model files are corrupted or incomplete")
                            logger.error("  2. InsightFace version incompatible with models")
                            logger.error("  3. Wrong directory structure")
                            raise RuntimeError(f"Failed to prepare InsightFace models: {prepare_error}") from prepare_error

                except ImportError as e:
                    logger.error(f"❌ InsightFace library not installed: {e}")
                    logger.error("Install with: pip install insightface onnxruntime")
                    raise ImportError(
                        "InsightFace library required for face detection. "
                        "Install with: pip install insightface onnxruntime"
                    ) from e
                except Exception as e:
                    logger.error(f"❌ Failed to initialize InsightFace: {e}")
                    logger.error(f"Error details: {type(e).__name__}: {str(e)}")
                    raise
    return _insightface_app


def cleanup_insightface():
    """
    Clean up InsightFace models and release GPU/CPU resources.

    P0 Fix #1: Implement explicit resource cleanup to prevent memory leaks.
    Call this when shutting down the application or when face detection
    is no longer needed.

    The global `_insightface_app` persists indefinitely without cleanup,
    accumulating GPU/CPU memory on systems with 8GB RAM when processing 1000+ photos.
    """
    global _insightface_app, _providers_used

    with _insightface_lock:
        if _insightface_app is not None:
            try:
                # Try to explicitly delete the model to release resources
                del _insightface_app
                _insightface_app = None
                _providers_used = None
                logger.info("✓ InsightFace models cleaned up and resources released")
            except Exception as e:
                logger.warning(f"Error during InsightFace cleanup: {e}")
                # Still set to None even if deletion failed
                _insightface_app = None
                _providers_used = None


def get_hardware_info():
    """
    Get information about the hardware being used for face detection.

    Returns:
        dict: Hardware information
            - 'type': 'GPU' or 'CPU'
            - 'providers': List of ONNXRuntime providers
            - 'cuda_available': bool
    """
    providers, hardware_type = _detect_available_providers()

    try:
        import onnxruntime as ort
        available = ort.get_available_providers()
        cuda_available = 'CUDAExecutionProvider' in available
    except (ImportError, AttributeError) as e:
        # BUG-H5 FIX: Log CUDA detection failures
        print(f"[FaceDetection] Failed to detect CUDA: {e}")
        cuda_available = False

    return {
        'type': hardware_type,
        'providers': providers,
        'cuda_available': cuda_available
    }


class FaceDetectionService:
    """
    Service for detecting faces and generating embeddings using InsightFace.

    Uses InsightFace library which provides:
    - Face detection via RetinaFace (accurate, fast)
    - 512-dimensional face embeddings via ArcFace ResNet
    - High accuracy face recognition
    - OnnxRuntime backend for CPU/GPU inference

    Model: buffalo_l (large model, high accuracy)
    - Detection: RetinaFace
    - Recognition: ArcFace (ResNet100)
    - Embedding dimension: 512 (vs 128 for dlib)
    - Backend: OnnxRuntime

    Usage:
        service = FaceDetectionService()
        faces = service.detect_faces("photo.jpg")
        for face in faces:
            print(f"Found face at {face['bbox']} with confidence {face['confidence']}")
            print(f"Embedding shape: {face['embedding'].shape}")  # (512,)
    """

    @staticmethod
    def check_backend_availability() -> dict:
        """
        Check availability of face detection backends WITHOUT initializing them.

        This method checks if the required libraries can be imported
        without triggering expensive model downloads or initializations.

        Returns:
            Dictionary mapping backend name to availability status:
            {
                "insightface": bool,  # True if insightface and onnxruntime are available
                "face_recognition": False  # No longer supported
            }
        """
        availability = {
            "insightface": False,
            "face_recognition": False  # Deprecated, not supported
        }

        # Check InsightFace availability
        try:
            import insightface  # Just check if module exists
            import onnxruntime  # Check OnnxRuntime too
            availability["insightface"] = True
        except ImportError:
            pass

        return availability

    def __init__(self, model: str = "buffalo_l"):
        """
        Initialize face detection service.

        Args:
            model: Detection model to use (buffalo_l, buffalo_s, antelopev2)
                   - "buffalo_l" (recommended, high accuracy)
                   - "buffalo_s" (smaller, faster, lower accuracy)
                   - "antelopev2" (latest model)
        """
        self.model = model
        self.app = _get_insightface_app()
        logger.info(f"[FaceDetection] Initialized InsightFace with model={model}")

    def is_available(self) -> bool:
        """
        Check if the service is available and ready to use.

        Returns:
            True if InsightFace is initialized and ready, False otherwise
        """
        try:
            return self.app is not None
        except Exception:
            return False

    @staticmethod
    def calculate_face_quality(face_dict: dict, img: np.ndarray) -> float:
        """
        Calculate face quality score (0-1, higher is better).

        Quality factors:
        1. Blur detection (Laplacian variance)
        2. Face size (larger = better quality)
        3. Detection confidence

        Args:
            face_dict: Face dictionary with bbox info
            img: Original image (BGR format)

        Returns:
            float: Quality score (0-1)
        """
        try:
            quality_score = 1.0

            x1, y1 = face_dict['bbox_x'], face_dict['bbox_y']
            x2 = x1 + face_dict['bbox_w']
            y2 = y1 + face_dict['bbox_h']

            # Ensure coordinates are within image bounds
            h, w = img.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            # 1. Blur detection (Laplacian variance)
            face_region = img[y1:y2, x1:x2]
            if face_region.size > 0:
                gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)
                blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()

                # Normalize blur score (typical range: 0-500+)
                if blur_score < 50:  # Very blurry
                    quality_score *= 0.3
                elif blur_score < 100:  # Somewhat blurry
                    quality_score *= 0.6
                elif blur_score < 200:  # Acceptable
                    quality_score *= 0.9
                # else: sharp, keep 1.0

            # 2. Face size scoring (larger faces = better quality)
            face_area = face_dict['bbox_w'] * face_dict['bbox_h']
            if face_area < 40*40:  # Very small
                quality_score *= 0.4
            elif face_area < 80*80:  # Small
                quality_score *= 0.7
            elif face_area < 120*120:  # Medium
                quality_score *= 0.9
            # else: large, keep 1.0

            # 3. Detection confidence
            quality_score *= face_dict['confidence']

            return min(1.0, max(0.0, quality_score))

        except Exception as e:
            logger.debug(f"Error calculating face quality: {e}")
            return face_dict['confidence']  # Fallback to confidence only

    def detect_faces(self, image_path: str, project_id: Optional[int] = None) -> List[dict]:
        """
        Detect all faces in an image and generate embeddings.

        Args:
            image_path: Path to image file

        Returns:
            List of face dictionaries with:
            {
                'bbox': [x1, y1, x2, y2],  # Face bounding box
                'bbox_x': int,  # X coordinate (top-left)
                'bbox_y': int,  # Y coordinate (top-left)
                'bbox_w': int,  # Width
                'bbox_h': int,  # Height
                'embedding': np.array (512,),  # Face embedding vector (ArcFace)
                'confidence': float  # Detection confidence (0-1)
            }

        Example:
            faces = service.detect_faces("photo.jpg")
            print(f"Found {len(faces)} faces")
        """
        try:
            # Check if file exists
            if not os.path.exists(image_path):
                logger.warning(f"Image not found: {image_path}")
                return []

            # Load image using OpenCV (InsightFace expects BGR format)
            # Use cv2.imdecode to handle Unicode filenames (e.g., Arabic, Chinese, etc.)
            try:
                # Read file as binary and decode with cv2
                # This handles Unicode filenames that cv2.imread() can't process
                with open(image_path, 'rb') as f:
                    file_bytes = np.frombuffer(f.read(), dtype=np.uint8)
                    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

                if img is None:
                    logger.warning(f"Failed to load image {image_path}")
                    return []
            except Exception as e:
                logger.warning(f"Failed to load image {image_path}: {e}")
                return []

            # Detect faces and extract embeddings
            cfg = get_face_config()
            params = cfg.get_detection_params(project_id)
            conf_th = float(params.get('confidence_threshold', 0.65))
            min_face_size = int(params.get('min_face_size', 20))
            show_low_conf = bool(cfg.get('show_low_confidence', False))
            # Returns list of Face objects with bbox, embedding, det_score, etc.
            # Optional downscale for very large images to improve speed/memory
            try:
                max_dim = max(img.shape[0], img.shape[1])
                if max_dim > 3000:
                    scale = 2000.0 / max_dim
                    resized_img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                    # CRITICAL: Check if resize succeeded before replacing img
                    # cv2.resize can return None for corrupted images or Unicode path issues
                    if resized_img is not None:
                        img = resized_img
                        logger.debug(f"Downscaled image for detection: scale={scale:.3f}")
                    else:
                        logger.warning(f"Image resize failed for {image_path}, using original size")
            except Exception as resize_error:
                logger.warning(f"Failed to resize {image_path}: {resize_error}")
                # Continue with original img (don't modify it)
            detected_faces = self.app.get(img)

            if not detected_faces:
                logger.debug(f"No faces found in {image_path}")
                return []

            # Convert InsightFace results to our format
            faces = []
            for face in detected_faces:
                # Get bounding box: [x1, y1, x2, y2]
                bbox = face.bbox.astype(int)
                x1, y1, x2, y2 = bbox

                # Calculate dimensions
                bbox_x = int(x1)
                bbox_y = int(y1)
                bbox_w = int(x2 - x1)
                bbox_h = int(y2 - y1)

                # Get confidence score from detection
                confidence = float(face.det_score)

                # Get embedding (512-dimensional ArcFace embedding)
                embedding = face.normed_embedding  # Already normalized to unit length

                faces.append({
                    'bbox': bbox.tolist(),
                    'bbox_x': bbox_x,
                    'bbox_y': bbox_y,
                    'bbox_w': bbox_w,
                    'bbox_h': bbox_h,
                    'embedding': embedding,
                    'confidence': confidence
                })

            # OPTIMIZATION: Calculate quality scores for all faces
            for face in faces:
                face['quality'] = self.calculate_face_quality(face, img)

            # Filter by size and confidence
            if show_low_conf:
                faces = [f for f in faces if min(f['bbox_w'], f['bbox_h']) >= min_face_size]
            else:
                faces = [f for f in faces if f['confidence'] >= conf_th and min(f['bbox_w'], f['bbox_h']) >= min_face_size]

            # OPTIMIZATION: Sort by quality (best quality first)
            # This helps clustering: best quality faces become cluster representatives
            faces = sorted(faces, key=lambda f: f['quality'], reverse=True)

            logger.info(f"[FaceDetection] Found {len(faces)} faces in {os.path.basename(image_path)}")
            return faces

        except Exception as e:
            logger.error(f"Error detecting faces in {image_path}: {e}")
            return []

    def save_face_crop(self, image_path: str, face: dict, output_path: str) -> bool:
        """
        Save a cropped face image to disk.

        Args:
            image_path: Original image path
            face: Face dictionary with 'bbox' key
            output_path: Path to save cropped face

        Returns:
            True if successful, False otherwise
        """
        try:
            # BUG-C2 FIX: Use context manager to prevent resource leak
            with Image.open(image_path) as img:
                # Extract bounding box
                bbox_x = face['bbox_x']
                bbox_y = face['bbox_y']
                bbox_w = face['bbox_w']
                bbox_h = face['bbox_h']

                # Add padding (10% on each side)
                padding = int(min(bbox_w, bbox_h) * 0.1)
                x1 = max(0, bbox_x - padding)
                y1 = max(0, bbox_y - padding)
                x2 = min(img.width, bbox_x + bbox_w + padding)
                y2 = min(img.height, bbox_y + bbox_h + padding)

                # Crop face
                face_img = img.crop((x1, y1, x2, y2))

                # Convert RGBA to RGB if necessary (required for JPEG)
                # This handles PNG files with transparency
                if face_img.mode == 'RGBA':
                    # Create white background
                    rgb_img = Image.new('RGB', face_img.size, (255, 255, 255))
                    # Paste using alpha channel as mask
                    rgb_img.paste(face_img, mask=face_img.split()[3])
                    face_img = rgb_img
                    logger.debug(f"Converted RGBA to RGB for JPEG compatibility")
                elif face_img.mode not in ('RGB', 'L'):
                    # Convert any other modes to RGB
                    face_img = face_img.convert('RGB')
                    logger.debug(f"Converted {img.mode} to RGB")

                # Resize to standard size for consistency
                # Get crop size from config (default 160x160 for better quality)
                try:
                    cfg = get_face_config()
                    crop_size = int(cfg.get('crop_size', 160))
                except Exception:
                    crop_size = 160
                face_img = face_img.resize((crop_size, crop_size), Image.Resampling.LANCZOS)

                # Ensure directory exists
                os.makedirs(os.path.dirname(output_path), exist_ok=True)

                # Save with explicit format based on extension
                # Get quality setting from config
                try:
                    cfg = get_face_config()
                    crop_quality = int(cfg.get('crop_quality', 95))
                except Exception:
                    crop_quality = 95

                file_ext = os.path.splitext(output_path)[1].lower()
                if file_ext in ['.jpg', '.jpeg']:
                    face_img.save(output_path, format='JPEG', quality=crop_quality)
                elif file_ext == '.png':
                    face_img.save(output_path, format='PNG')
                else:
                    # Default to JPEG
                    face_img.save(output_path, format='JPEG', quality=crop_quality)

                logger.debug(f"Saved face crop to {output_path}")
                return True
            # BUG-C2 FIX: img automatically closed by context manager

        except Exception as e:
            logger.error(f"Failed to save face crop: {e}")
            return False

    def batch_detect_faces(self, image_paths: List[str],
                          max_workers: int = 4) -> dict:
        """
        Detect faces in multiple images (parallel processing).

        Args:
            image_paths: List of image paths
            max_workers: Number of parallel workers

        Returns:
            Dictionary mapping image_path -> list of faces

        Example:
            results = service.batch_detect_faces(["img1.jpg", "img2.jpg"])
            for path, faces in results.items():
                print(f"{path}: {len(faces)} faces")
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results = {}
        total = len(image_paths)
        # P1-4 FIX: Track failures to inform user
        failed_count = 0

        logger.info(f"[FaceDetection] Processing {total} images with {max_workers} workers")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all detection tasks
            futures = {executor.submit(self.detect_faces, path): path
                      for path in image_paths}

            # Collect results as they complete
            processed = 0
            for future in as_completed(futures):
                path = futures[future]
                try:
                    faces = future.result(timeout=30)  # P1-4 FIX: Add timeout
                    results[path] = faces
                    processed += 1

                    if processed % 10 == 0:
                        logger.info(f"[FaceDetection] Progress: {processed}/{total} images")

                except Exception as e:
                    # P1-4 FIX: Use warning-level logging and track failures
                    logger.warning(f"Face detection failed for {path}: {e}")
                    failed_count += 1
                    results[path] = []
                    processed += 1

        # P1-4 FIX: Log failure summary for user awareness
        if failed_count > 0:
            logger.warning(f"[FaceDetection] Batch complete with {failed_count}/{total} failures")
        else:
            logger.info(f"[FaceDetection] Batch complete: {processed}/{total} images processed successfully")

        return results


# Singleton instance
_face_detection_service = None

def get_face_detection_service(model: str = "buffalo_l") -> FaceDetectionService:
    """Get or create singleton FaceDetectionService instance."""
    global _face_detection_service
    if _face_detection_service is None:
        _face_detection_service = FaceDetectionService(model=model)
    return _face_detection_service


def create_face_detection_service(config: dict) -> Optional[FaceDetectionService]:
    """
    Create a new FaceDetectionService instance from configuration.

    This function creates a fresh instance (not singleton) for testing purposes.

    Args:
        config: Configuration dictionary with keys:
            - backend: "insightface" (only supported backend)
            - insightface_model: Model name ("buffalo_l", "buffalo_s", "antelopev2")

    Returns:
        FaceDetectionService instance or None if backend not supported/available

    Example:
        config = {"backend": "insightface", "insightface_model": "buffalo_l"}
        service = create_face_detection_service(config)
    """
    backend = config.get("backend", "insightface")

    if backend != "insightface":
        logger.warning(f"Unsupported backend: {backend}. Only 'insightface' is supported.")
        return None

    # Check if InsightFace is available
    availability = FaceDetectionService.check_backend_availability()
    if not availability.get("insightface", False):
        logger.error("InsightFace backend not available. Install with: pip install insightface onnxruntime")
        return None

    # Get model name from config
    model = config.get("insightface_model", "buffalo_l")

    try:
        return FaceDetectionService(model=model)
    except Exception as e:
        logger.error(f"Failed to create FaceDetectionService: {e}")
        return None
