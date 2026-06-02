"""
ComicScraper WebUI
A Gradio-based interface for scraping comics, with PaddleOCR, translation, PDF, image stitching,
auto-compression, and a standalone manual image compressor.
Supports batch URL processing and organized subfolder output.
"""

import os
import re
import asyncio
from typing import List, Tuple

import gradio as gr

from engine.scraper import scrape_comic, extract_chapter_slug
from engine.processor import (
    stitch_images,
    create_pdf,
    compress_manual_images,
    run_ocr_on_page,
)


# Default base directory for all outputs
DEFAULT_BASE_DIR = "./outputs"


def _ensure_dir(path: str) -> str:
    """Ensure directory exists and return the absolute path."""
    abs_path = os.path.abspath(path)
    os.makedirs(abs_path, exist_ok=True)
    return abs_path


def _sanitize_title(title: str) -> str:
    """Remove filesystem-unsafe characters from a title string."""
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', title.strip())
    if not sanitized:
        sanitized = "Unknown_Comic"
    return sanitized


def _build_folder_paths(base_save_dir: str, comic_title: str, chapter_slug: str) -> dict:
    """
    Build the organized folder structure:
      raw_pages/{chapter_slug}/  -> raw downloaded images
      pdf/                       -> PDF output
      stitched/                  -> stitched long image output
      ocr_texts/{chapter_slug}/  -> OCR text files

    Returns a dict with keys: 'comic_dir', 'raw_dir', 'pdf_dir', 'stitched_dir', 'ocr_dir'
    """
    safe_title = _sanitize_title(comic_title)
    base_dir = _ensure_dir(base_save_dir)
    comic_dir = os.path.join(base_dir, safe_title)

    raw_dir = os.path.join(comic_dir, "raw_pages", chapter_slug)
    pdf_dir = os.path.join(comic_dir, "pdf")
    stitched_dir = os.path.join(comic_dir, "stitched")
    ocr_dir = os.path.join(comic_dir, "ocr_texts", chapter_slug)

    _ensure_dir(raw_dir)
    _ensure_dir(pdf_dir)
    _ensure_dir(stitched_dir)
    _ensure_dir(ocr_dir)

    return {
        "comic_dir": comic_dir,
        "raw_dir": raw_dir,
        "pdf_dir": pdf_dir,
        "stitched_dir": stitched_dir,
        "ocr_dir": ocr_dir,
    }


async def process_chapter(
    base_save_dir: str,
    comic_title: str,
    url: str,
    enable_ocr: bool,
    enable_translate: bool,
    use_gpu_ocr: bool,
    save_pdf: bool,
    save_long_image: bool,
    target_lang: str,
    auto_compress: bool,
    compress_quality: int,
    log_lines: list,
    progress: gr.Progress,
    base_progress: float,
    progress_range: float,
) -> str:
    """
    Process a single comic URL: scrape, PaddleOCR/translate, generate output.

    Returns:
        The file path to the generated output (PDF or image), or empty string.
    """
    download_path = ""

    # --- Extract chapter slug from URL ---
    chapter_slug = extract_chapter_slug(url)
    log_lines.append(f"\n{'='*50}")
    log_lines.append(f"[INFO] Processing: {url}")
    log_lines.append(f"[INFO] Chapter slug: {chapter_slug}")

    # --- Build organized folder structure ---
    folders = _build_folder_paths(base_save_dir, comic_title, chapter_slug)
    log_lines.append(f"[INFO] Raw pages dir: {folders['raw_dir']}")
    log_lines.append(f"[INFO] PDF dir: {folders['pdf_dir']}")
    log_lines.append(f"[INFO] Stitched dir: {folders['stitched_dir']}")
    log_lines.append(f"[INFO] OCR texts dir: {folders['ocr_dir']}")

    # --- Step 1: Scrape raw images into raw_pages/{chapter_slug}/ ---
    log_lines.append("[STATUS] Starting comic scraping...")
    progress(
        base_progress + progress_range * 0.1,
        desc=f"[{chapter_slug}] Scraping..."
    )

    image_paths = await scrape_comic(url, output_dir=folders["raw_dir"])
    log_lines.append(f"[STATUS] Scraped {len(image_paths)} page(s).")
    if image_paths:
        log_lines.append(f"[INFO] Pages: {[os.path.basename(p) for p in image_paths]}")

    if not image_paths:
        log_lines.append("[ERROR] No images were scraped. Skipping this URL.")
        return ""

    # --- Step 2: PaddleOCR (if enabled) ---
    if enable_ocr:
        progress(
            base_progress + progress_range * 0.3,
            desc=f"[{chapter_slug}] Running PaddleOCR..."
        )
        log_lines.append(f"\n[STATUS] Running PaddleOCR on {len(image_paths)} pages...")
        log_lines.append(f"[INFO] OCR GPU mode: {'ENABLED' if use_gpu_ocr else 'DISABLED (CPU)'}")

        for idx, img_path in enumerate(image_paths):
            log_lines.append(f"\n--- Page {idx + 1} ---")

            # Run PaddleOCR on this page
            page_text = run_ocr_on_page(
                image_path=img_path,
                ocr_dir=folders["ocr_dir"],
                page_index=idx,
                use_gpu=use_gpu_ocr,
            )

            log_lines.append(f"[OCR] Detected text ({len(page_text.split(chr(10)))} blocks)")

            # If translation is also enabled, translate the OCR text
            if enable_translate and page_text and page_text != "[No text detected]":
                try:
                    from deep_translator import GoogleTranslator
                    lang_map = {
                        "english": "en", "indonesian": "id", "japanese": "ja",
                        "korean": "ko", "chinese": "zh-CN", "french": "fr",
                        "spanish": "es", "german": "de",
                    }
                    target_code = lang_map.get(target_lang.lower(), "en")
                    translated = GoogleTranslator(source="auto", target=target_code).translate(page_text)
                    log_lines.append(f"[TRANSLATE] ({target_lang}):\n{translated}")
                except Exception as e:
                    log_lines.append(f"[TRANSLATE] Error: {e}")

    else:
        log_lines.append("\n[STATUS] OCR disabled. Skipping text detection.")

    # --- Step 3: Generate output files in their dedicated subfolders ---
    quality = compress_quality if auto_compress else None

    if save_pdf:
        progress(
            base_progress + progress_range * 0.7,
            desc=f"[{chapter_slug}] Creating PDF..."
        )
        log_lines.append(f"\n[STATUS] Generating PDF...")
        pdf_path = create_pdf(
            image_paths,
            output_path=os.path.join(folders["pdf_dir"], f"{chapter_slug}.pdf"),
            quality=quality,
        )
        log_lines.append(f"[STATUS] PDF created: {pdf_path}")
        download_path = pdf_path

    if save_long_image:
        progress(
            base_progress + progress_range * 0.85,
            desc=f"[{chapter_slug}] Stitching image..."
        )
        log_lines.append(f"\n[STATUS] Stitching images into long image...")
        # stitch_images returns the ACTUAL path (may differ if PNG fallback triggered)
        actual_stitched_path = stitch_images(
            image_paths,
            output_path=os.path.join(folders["stitched_dir"], f"{chapter_slug}_long.png"),
            quality=quality,
        )
        log_lines.append(f"[STATUS] Long image created: {actual_stitched_path}")
        if not save_pdf:
            download_path = actual_stitched_path

    if not save_pdf and not save_long_image:
        log_lines.append("\n[STATUS] No output format selected. Nothing to save.")
        download_path = ""

    log_lines.append(f"[STATUS] Chapter {chapter_slug} complete!")
    log_lines.append(f"{'='*50}\n")

    return download_path


async def process_comic(
    base_save_dir: str,
    comic_title: str,
    urls_text: str,
    enable_ocr: bool,
    enable_translate: bool,
    use_gpu_ocr: bool,
    save_pdf: bool,
    save_long_image: bool,
    target_lang: str,
    auto_compress: bool,
    compress_quality: int,
    progress: gr.Progress = gr.Progress()
) -> Tuple[str, list]:
    """
    Main processing function connected to Gradio UI.
    Handles batch URL processing.

    Args:
        base_save_dir: Base directory for all outputs (e.g., "./outputs").
        comic_title: Human-readable comic title (used as folder name).
        urls_text: Multi-line text with one URL per line.
        enable_ocr: Whether to run PaddleOCR on the pages.
        enable_translate: Whether to translate OCR'd text.
        use_gpu_ocr: Whether to use GPU for OCR inference.
        save_pdf: Whether to generate a PDF.
        save_long_image: Whether to stitch images into one long image.
        target_lang: Target language for translation.
        auto_compress: Whether to enable image compression.
        compress_quality: JPEG quality level (1-100) when compression is enabled.
        progress: Gradio progress tracker.

    Returns:
        Tuple of (status_log, list of downloadable_file_paths).
    """
    log_lines = []
    all_output_paths = []

    try:
        # Parse URLs from multi-line text
        urls = [u.strip() for u in urls_text.strip().split('\n') if u.strip()]

        if not urls:
            log_lines.append("[ERROR] No URLs provided. Please enter at least one URL.")
            return "\n".join(log_lines), []

        log_lines.append(f"[INFO] Processing {len(urls)} URL(s)...")
        log_lines.append(f"[INFO] Comic title: {comic_title}")
        log_lines.append(f"[INFO] Base save directory: {base_save_dir}")
        if auto_compress:
            log_lines.append(f"[INFO] Auto-compression enabled (quality={compress_quality})")
        else:
            log_lines.append("[INFO] Auto-compression disabled (full quality)")
        log_lines.append(f"[INFO] PaddleOCR: {'ENABLED' if enable_ocr else 'DISABLED'}")
        if enable_ocr:
            log_lines.append(f"[INFO] GPU mode: {'ENABLED' if use_gpu_ocr else 'DISABLED (CPU)'}")

        # Process each URL sequentially
        for idx, url in enumerate(urls):
            chapter_progress = idx / max(len(urls), 1)
            chapter_range = 1.0 / max(len(urls), 1)

            progress(
                chapter_progress,
                desc=f"Processing chapter {idx + 1}/{len(urls)}..."
            )

            output_path = await process_chapter(
                base_save_dir=base_save_dir,
                comic_title=comic_title,
                url=url,
                enable_ocr=enable_ocr,
                enable_translate=enable_translate,
                use_gpu_ocr=use_gpu_ocr,
                save_pdf=save_pdf,
                save_long_image=save_long_image,
                target_lang=target_lang,
                auto_compress=auto_compress,
                compress_quality=compress_quality,
                log_lines=log_lines,
                progress=progress,
                base_progress=chapter_progress,
                progress_range=chapter_range,
            )

            if output_path:
                all_output_paths.append(output_path)

        # --- Summary ---
        progress(1.0, desc="Done!")
        log_lines.append(f"\n{'='*50}")
        log_lines.append(f"[SUMMARY] Processed {len(urls)} URL(s)")
        log_lines.append(f"[SUMMARY] Generated {len(all_output_paths)} output file(s)")
        if all_output_paths:
            log_lines.append("[SUMMARY] Outputs:")
            for p in all_output_paths:
                log_lines.append(f"  - {p}")
        log_lines.append(f"{'='*50}")

        # Save batch log to comic directory
        try:
            safe_title = _sanitize_title(comic_title)
            comic_dir = os.path.join(_ensure_dir(base_save_dir), safe_title)
            batch_log_path = os.path.join(comic_dir, "batch_log.txt")
            with open(batch_log_path, "w", encoding="utf-8") as f:
                f.write("\n".join(log_lines))
        except Exception:
            pass

    except Exception as e:
        log_lines.append(f"\n[FATAL ERROR] {str(e)}")
        import traceback
        log_lines.append(traceback.format_exc())

    return "\n".join(log_lines), all_output_paths


# -----------------------------------------------------------------------
# BUILD GRADIO UI
# -----------------------------------------------------------------------
with gr.Blocks(
    title="ComicScraper WebUI",
) as demo:

    gr.Markdown(
        """
        # 🦸 ComicScraper WebUI
        Enter one or more comic URLs (one per line), configure your options, and click **Start Processing**.
        """
    )

    # =============================================================
    # SECTION 1: AUTO SCRAPER & PROCESSOR
    # =============================================================

    # --- Configuration Section: Save Directory & Comic Title ---
    with gr.Row():
        with gr.Column(scale=1):
            base_dir_input = gr.Textbox(
                label="📁 Base Save Directory",
                value="./outputs",
                placeholder="./outputs",
                info="All comics will be saved under this folder."
            )
        with gr.Column(scale=2):
            comic_title_input = gr.Textbox(
                label="📖 Comic Title",
                placeholder="e.g., Solo Leveling",
                info="Used to create the output folder (special chars will be sanitized)."
            )

    # --- Batch URL Input (TextArea) ---
    url_input = gr.TextArea(
        label="🔗 Comic URLs (One URL per line)",
        placeholder="https://komiku.org/manga-title-chapter-01/\nhttps://komiku.org/manga-title-chapter-02/\nhttps://komiku.org/manga-title-chapter-03/",
        lines=5,
        max_lines=20,
    )

    # --- Language ---
    with gr.Row():
        with gr.Column(scale=1):
            lang_dropdown = gr.Dropdown(
                label="🌐 Translation Language",
                choices=["English", "Indonesian", "Japanese", "Korean", "Chinese", "French", "Spanish", "German"],
                value="Indonesian",
                interactive=True
            )

    # --- Feature Toggles ---
    with gr.Row():
        with gr.Column():
            ocr_checkbox = gr.Checkbox(
                label="📝 Enable PaddleOCR (Extract Text)",
                value=False,
                info="Extract text from comic pages using PaddleOCR."
            )
            use_gpu_ocr_cb = gr.Checkbox(
                label="⚡ Use GPU for OCR",
                value=False,
                info="Enable GPU acceleration for OCR processing (requires compatible GPU + CUDA/PaddlePaddle-GPU)."
            )
            translate_checkbox = gr.Checkbox(
                label="🔄 Enable Auto-Translate",
                value=False,
                info="Translate extracted text (requires OCR enabled)."
            )

        with gr.Column():
            pdf_checkbox = gr.Checkbox(
                label="📄 Save as PDF",
                value=True,
                info="Convert pages into a single PDF file per chapter."
            )
            image_checkbox = gr.Checkbox(
                label="🖼️ Save as Long Image",
                value=True,
                info="Stitch all pages into one long vertical image per chapter."
            )

    # --- Auto Compression Toggle & Slider ---
    with gr.Row():
        with gr.Column(scale=1):
            auto_compress_cb = gr.Checkbox(
                label="🗜️ Enable Auto Compression",
                value=False,
                info="Compress images when creating PDF and stitched outputs to save disk space."
            )
        with gr.Column(scale=2):
            auto_slider = gr.Slider(
                minimum=10,
                maximum=100,
                value=85,
                step=5,
                label="Auto Compress Quality (For Scraper)",
                info="Higher = better quality but larger file size."
            )

    # --- Action Button & Output for Scraper ---
    with gr.Row():
        process_btn = gr.Button("🚀 Start Processing", variant="primary", size="lg")

    with gr.Row():
        with gr.Column(scale=1):
            status_output = gr.Textbox(
                label="Status Log",
                lines=20,
                interactive=False,
                elem_classes=["status-log"]
            )

        with gr.Column(scale=1):
            file_output = gr.File(
                label="📥 Download Outputs",
                file_count="multiple",
                interactive=False
            )

    # =============================================================
    # SECTION 2: MANUAL IMAGE COMPRESSOR
    # =============================================================

    gr.Markdown("---")
    gr.Markdown(
        """
        ## 🗜️ Manual Image Compressor
        Upload images (JPG/PNG) to compress them individually. Compressed files are saved as JPEG with optimization.
        """
    )

    with gr.Row():
        with gr.Column(scale=2):
            manual_files = gr.File(
                label="Upload Images to Compress (JPG/PNG)",
                file_count="multiple",
                file_types=["image"],
            )
        with gr.Column(scale=1):
            manual_slider = gr.Slider(
                minimum=10,
                maximum=100,
                value=85,
                step=5,
                label="Manual Compress Quality",
                info="Lower = smaller file size but lower quality."
            )

    with gr.Row():
        manual_btn = gr.Button("🎯 Generate Compressed Images", variant="primary", size="lg")

    with gr.Row():
        manual_output = gr.File(
            label="📥 Download Compressed Images",
            file_count="multiple",
            interactive=False
        )

    # =============================================================
    # EVENT HANDLERS
    # =============================================================

    # --- Wire up scraper button ---
    process_btn.click(
        fn=process_comic,
        inputs=[
            base_dir_input,
            comic_title_input,
            url_input,
            ocr_checkbox,
            translate_checkbox,
            use_gpu_ocr_cb,
            pdf_checkbox,
            image_checkbox,
            lang_dropdown,
            auto_compress_cb,
            auto_slider,
        ],
        outputs=[status_output, file_output],
        api_name="process_comic"
    )

    # --- Wire up manual compressor button ---
    manual_btn.click(
        fn=compress_manual_images,
        inputs=[manual_files, manual_slider],
        outputs=manual_output,
        api_name="compress_images"
    )

    # --- Dynamic interactivity: disable translate if OCR off ---
    def toggle_translate(ocr_enabled):
        return gr.update(interactive=ocr_enabled)

    ocr_checkbox.change(
        fn=toggle_translate,
        inputs=ocr_checkbox,
        outputs=translate_checkbox
    )

if __name__ == "__main__":
    print("=" * 60)
    print("  ComicScraper WebUI")
    print("  Running at: http://localhost:7860")
    print("=" * 60)
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        theme=gr.themes.Soft(),
        css="""
            footer { display: none !important; }
            .status-log { height: 400px; overflow-y: auto; }
        """
    )