"""
ComicScraper - Processor Engine
Handles image stitching, PDF creation, OCR scanning, translation, and image compression.
"""

import os
import io
from typing import List, Tuple, Optional

from PIL import Image
import img2pdf

# Disable Pillow's DecompressionBombWarning to allow processing massive webtoons
Image.MAX_IMAGE_PIXELS = None

# Maximum supported dimension for JPEG format (65,535 pixels)
JPEG_MAX_DIM = 65000


# ---------------------------------------------------------------------------
# Image Compression Helpers
# ---------------------------------------------------------------------------

def _compress_image(
    image: Image.Image,
    quality: int = 85,
    format: str = "JPEG",
    optimize: bool = True,
) -> Image.Image:
    """
    Compress a PIL Image in-memory and return the compressed version.
    Converts to RGB if necessary (for JPEG saving).
    """
    if image.mode != "RGB":
        image = image.convert("RGB")

    buf = io.BytesIO()
    image.save(buf, format=format, quality=quality, optimize=optimize)
    buf.seek(0)
    compressed = Image.open(buf)
    compressed.load()  # Force load to keep the buffer alive
    return compressed


def _compress_and_save(
    image_path: str,
    output_path: str,
    quality: int = 85,
    format: str = "JPEG",
    optimize: bool = True,
) -> str:
    """
    Open an image, compress it, and save to output_path.
    Automatically falls back to PNG if image dimensions exceed JPEG's 65,535 pixel limit.

    Returns the output path.
    """
    img = Image.open(image_path)
    if img.mode != "RGB":
        img = img.convert("RGB")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Check if dimensions exceed JPEG's limit (65535px)
    width, height = img.size
    if width > JPEG_MAX_DIM or height > JPEG_MAX_DIM:
        # Fallback to PNG for extreme dimensions
        safe_path = output_path.rsplit('.', 1)[0] + '.png'
        img.save(safe_path, format='PNG', optimize=True)
        img.close()
        print(f"[PROCESSOR] DIMENSION FALLBACK: {image_path} ({width}x{height}) "
              f"exceeds JPEG limit, saved as PNG: {safe_path}")
        return safe_path

    # Normal JPEG compression
    img.save(output_path, format=format, quality=quality, optimize=optimize)
    img.close()
    return output_path


# ---------------------------------------------------------------------------
# Image Stitching (bulletproof with try/except + PNG fallback)
# ---------------------------------------------------------------------------

def stitch_images(
    image_paths: List[str],
    output_path: str = "temp/stitched_output.png",
    quality: Optional[int] = None,
) -> str:
    """
    Vertically stitch a list of images into one long image.
    Includes try/except fallback to PNG if JPEG saving fails.

    Args:
        image_paths: List of file paths to images to stitch.
        output_path: Where to save the stitched result.
        quality: If set (1-100), apply JPEG compression before saving.
                 If None, save at original quality.

    Returns:
        The ACTUAL file path where the image was saved (.jpg or .png).
    """
    if not image_paths:
        raise ValueError("No image paths provided for stitching.")

    images = [Image.open(path) for path in image_paths]

    # Calculate total height and max width
    total_height = sum(img.height for img in images)
    max_width = max(img.width for img in images)

    # Create a new blank image
    stitched = Image.new("RGB", (max_width, total_height), color=(255, 255, 255))

    # Paste images vertically
    y_offset = 0
    for img in images:
        stitched.paste(img, (0, y_offset))
        y_offset += img.height

    # Save — wrapped in try/except for bulletproof PNG fallback
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    try:
        width, height = stitched.size
        quality_val = quality if (quality is not None and 1 <= quality <= 100) else 100

        # Force PNG if dimensions exceed JPEG's 65,535 pixel limit
        if width > JPEG_MAX_DIM or height > JPEG_MAX_DIM:
            final_path = output_path.rsplit('.', 1)[0] + '.png'
            print(f"[PROCESSOR] Dimensions ({width}x{height}) exceed JPEG limits. Saving as PNG...")
            stitched.save(final_path, format='PNG', optimize=True)
            print(f"[PROCESSOR] Stitched image saved (PNG fallback): {final_path}")
            return final_path

        # Try saving as JPEG with quality setting
        compressed = _compress_image(stitched, quality=quality_val)
        compressed.save(output_path)
        compressed.close()
        print(f"[PROCESSOR] Stitched + compressed image saved to: {output_path} (quality={quality_val})")
        return output_path

    except Exception as e:
        # If saving fails for ANY reason, force PNG fallback
        print(f"[PROCESSOR] Warning during image save: {e}. Forcing PNG fallback...")
        final_path = output_path.rsplit('.', 1)[0] + '.png'
        try:
            stitched.save(final_path, format='PNG', optimize=True)
        except Exception as e2:
            print(f"[PROCESSOR] PNG fallback also failed: {e2}")
            raise
        print(f"[PROCESSOR] Stitched image saved (PNG error fallback): {final_path}")
        return final_path

    finally:
        # Close all opened images
        for img in images:
            img.close()
        stitched.close()


# ---------------------------------------------------------------------------
# PDF Creation
# ---------------------------------------------------------------------------

def create_pdf(
    image_paths: List[str],
    output_path: str = "temp/output.pdf",
    quality: Optional[int] = None,
) -> str:
    """
    Convert a list of images into a single PDF file.

    Args:
        image_paths: List of file paths to images to include in the PDF.
        output_path: Where to save the resulting PDF.
        quality: If set (1-100), compress images before embedding in PDF.
                 If None, use original images as-is.

    Returns:
        The file path to the generated PDF.
    """
    if not image_paths:
        raise ValueError("No image paths provided for PDF creation.")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    if quality is not None and 1 <= quality <= 100:
        # Compress each image before PDF conversion
        compressed_images = []
        temp_dir = os.path.join(os.path.dirname(output_path), ".compressed_temp")
        os.makedirs(temp_dir, exist_ok=True)

        for idx, img_path in enumerate(image_paths):
            temp_path = os.path.join(temp_dir, f"compressed_{idx:03d}.jpg")
            _compress_and_save(img_path, temp_path, quality=quality)
            compressed_images.append(temp_path)

        # Generate PDF from compressed images
        with open(output_path, "wb") as f:
            f.write(img2pdf.convert(compressed_images))

        # Cleanup temp files
        for p in compressed_images:
            try:
                os.remove(p)
            except Exception:
                pass
        try:
            os.rmdir(temp_dir)
        except Exception:
            pass

        print(f"[PROCESSOR] PDF saved (compressed, quality={quality}): {output_path}")
    else:
        # Use original images directly
        with open(output_path, "wb") as f:
            f.write(img2pdf.convert(image_paths))
        print(f"[PROCESSOR] PDF saved: {output_path}")

    return output_path


# ---------------------------------------------------------------------------
# Manual Image Compressor (standalone)
# ---------------------------------------------------------------------------

def compress_manual_images(
    file_paths: List[str],
    quality: int = 85,
    output_dir: str = "outputs/manual_compressed",
) -> List[str]:
    """
    Compress one or more uploaded images and save as JPEG with specified quality.

    Args:
        file_paths: List of file paths or Gradio file objects.
        quality: JPEG quality level (1-100).
        output_dir: Directory to save compressed outputs.

    Returns:
        List of paths to the compressed images.
    """
    os.makedirs(output_dir, exist_ok=True)
    compressed_paths = []

    for idx, fp in enumerate(file_paths):
        try:
            # Gradio may pass dicts ({"path": "...", ...}) or plain strings
            if isinstance(fp, dict):
                source_path = fp.get("path") or fp.get("name", "")
            else:
                source_path = str(fp)

            if not source_path or not os.path.isfile(source_path):
                print(f"[COMPRESSOR] Skipping invalid path: {source_path}")
                continue

            # Determine output filename (initially .jpg, may switch to .png)
            base = os.path.splitext(os.path.basename(source_path))[0]
            output_filename = f"{base}_compressed_{quality}.jpg"
            output_path = os.path.join(output_dir, output_filename)

            # Compress and save
            img = Image.open(source_path)
            if img.mode != "RGB":
                img = img.convert("RGB")

            # Check if dimensions exceed JPEG's limit (65535px)
            width, height = img.size
            if width > JPEG_MAX_DIM or height > JPEG_MAX_DIM:
                # Fallback to PNG for extreme dimensions
                safe_filename = f"{base}_compressed_{quality}.png"
                output_path = os.path.join(output_dir, safe_filename)
                img.save(output_path, format='PNG', optimize=True)
                print(f"[COMPRESSOR] DIMENSION FALLBACK: ({width}x{height}) "
                      f"exceeds JPEG limit, saved as PNG")
            else:
                # Normal JPEG compression
                img.save(output_path, format="JPEG", quality=quality, optimize=True)
            img.close()

            original_size = os.path.getsize(source_path)
            compressed_size = os.path.getsize(output_path)
            savings = 100 - (compressed_size / max(original_size, 1) * 100.0)

            compressed_paths.append(output_path)
            print(
                f"[COMPRESSOR] {base}: "
                f"{original_size:,} bytes -> {compressed_size:,} bytes "
                f"({savings:.1f}% saved)"
            )

        except Exception as e:
            print(f"[COMPRESSOR] Error compressing file {idx}: {e}")
            continue

    print(f"[COMPRESSOR] Done. Compressed {len(compressed_paths)} file(s) to '{output_dir}'")
    return compressed_paths


# ---------------------------------------------------------------------------
# PaddleOCR & Translation
# ---------------------------------------------------------------------------

# Module-level variable to hold the single OCR engine instance
_ocr_engine_instance = None


def _extract_text_from_result(data) -> list:
    """
    Recursively search for strings in nested PaddleOCR/PaddleX result objects.
    Traverses lists, tuples, and dicts to find all text strings.
    """
    extracted = []
    if isinstance(data, str):
        extracted.append(data)
    elif isinstance(data, (list, tuple)):
        for item in data:
            extracted.extend(_extract_text_from_result(item))
    elif isinstance(data, dict):
        for key, value in data.items():
            extracted.extend(_extract_text_from_result(key))
            extracted.extend(_extract_text_from_result(value))
    return extracted


def run_ocr_on_page(
    image_path: str,
    ocr_dir: str,
    page_index: int,
    use_gpu: bool = False,
) -> str:
    """
    Run PaddleOCR on a single image page and save the detected text
    to a .txt file inside ocr_dir.

    Args:
        image_path: Path to the image file to scan.
        ocr_dir: Directory where OCR text files will be saved.
        page_index: 0-based page number (for filename like page_01.txt).
        use_gpu: Reserved for future GPU support (not currently passed to engine).

    Returns:
        The extracted text (one line per detected text block).
    """
    global _ocr_engine_instance

    os.makedirs(ocr_dir, exist_ok=True)
    page_num = page_index + 1
    txt_path = os.path.join(ocr_dir, f"page_{page_num:02d}.txt")

    try:
        # MASTER INITIALIZATION - ONLY RUN ONCE
        if _ocr_engine_instance is None:
            from paddleocr import PaddleOCR
            import logging
            logging.getLogger('ppocr').setLevel(logging.WARNING)

            print("[OCR] Initializing PaddleOCR engine (once)...")
            # Disable angle classification to avoid tuple indexing bugs in PaddleOCR v5
            # Use minimal parameters for maximum compatibility
            _ocr_engine_instance = PaddleOCR(lang='ch', use_angle_cls=False, enable_mkldnn=False)
            print("[OCR] PaddleOCR engine ready.")

        ocr_engine = _ocr_engine_instance
        print(f"[OCR] Running inference on page {page_num}...")

        # PaddleOCR v5 expects file paths, not numpy arrays
        # Pass the raw image path directly to the OCR engine
        result = ocr_engine.ocr(image_path)

        # Diagnostic: show result structure (first 500 chars)
        print(f"[OCR] Result type: {type(result).__name__}, length: {len(result) if result else 0}")
        if result and page_num == 1:  # Only print structure for first page
            print(f"[OCR] Result structure: {str(result)[:500]}")
        
        # PaddleOCR v5 returns a list of dicts with 'rec_texts' key
        extracted_text = ""
        if result and isinstance(result, list):
            for page_res in result:
                if isinstance(page_res, dict):
                    # Access the 'rec_texts' key which contains the list of detected strings
                    rec_texts = page_res.get('rec_texts', [])
                    if isinstance(rec_texts, list):
                        for text_line in rec_texts:
                            if isinstance(text_line, str) and len(text_line.strip()) > 0:
                                extracted_text += text_line + "\n"
                elif isinstance(page_res, str):
                    # Fallback for unexpected types
                    extracted_text += page_res + "\n"

        if not extracted_text.strip():
            extracted_text = "[No text detected]"

        # Save
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(extracted_text.strip())

        text_block_count = len([l for l in extracted_text.split('\n') if l.strip()])
        print(f"[OCR] Saved text for page {page_num} ({text_block_count} lines): {txt_path}")
        return extracted_text.strip()

    except ImportError as e:
        error_msg = f"[OCR ERROR] PaddleOCR not installed: {e}"
        print(error_msg)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"[OCR ERROR] {e}"
        print(error_msg)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(error_msg)
        return error_msg