"""
ComicScraper - Scraper Engine
Uses Playwright (async) to navigate comic websites, find images, and download them.
Optimized for comic reader sites (Komiku, AsuraScans, etc.) with lazy-loading and
specific container structures.
"""

import os
import re
import asyncio
from typing import List, Optional
from urllib.parse import urlparse, urljoin

from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Configurable constants
# ---------------------------------------------------------------------------

# Container selectors — target the main reading area where comic images live
# These are prioritized; the scraper finds the container first, then extracts images inside it.
READING_CONTAINERS = [
    "#Chimages",           # Komiku-style
    "#Baca_Komik",         # Komiku alternative
    ".reading-content",    # Common
    ".chapter-content",    # Common
    ".chapter-container",  # Common
    ".comic-content",      # Common
    ".manga-content",      # Common
    "#reader-area",        # Reader area
    ".reader-area",        # Reader area
    "#all",                # Some sites
    ".entry-content",      # WordPress-style
    ".post-content",       # Post content
    "main article",        # Generic
    "#chapter_img",        # Image container ID
    ".chapter_img",        # Image container class
]

# Image URL attribute priority — check these in order to get the real image URL
# Many sites use placeholder src and store real URL in data-* attributes
IMAGE_URL_ATTRS = ["data-src", "data-lazy-src", "data-original", "src"]

# Minimum dimensions for a valid comic page image
MIN_IMAGE_WIDTH = 400
MIN_IMAGE_HEIGHT = 400

# File extensions to accept
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

# Patterns to filter OUT (logos, icons, ads, UI elements)
BLOCKED_PATTERNS = re.compile(
    r"(avatar|icon|logo|banner|button|spacer|pixel|tracking|analytics|"
    r"social|share|like|comment|advertisement|ads?\/|banner|"
    r"emoji|smiley|sprite|thumb|thumbnail|nav|menu|header|footer|"
    r"sidebar|widget|ad-|ads-)",
    re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Helper: Extract chapter slug from URL
# ---------------------------------------------------------------------------

def extract_chapter_slug(url: str) -> str:
    """
    Extract a chapter identifier from a comic URL.

    Handles various URL patterns:
    - https://site.com/comic-name-chapter-01/     -> chapter-01
    - https://site.com/manga/title/chapter-100/    -> chapter-100
    - https://site.com/comic/title/ch050/           -> ch050
    - https://site.com/read/title/123/              -> 123
    - Falls back to the last URL path segment

    Args:
        url: The comic chapter URL.

    Returns:
        A sanitized chapter slug string.
    """
    parsed = urlparse(url)
    path = parsed.path.rstrip('/')

    # Split path into segments
    segments = [s for s in path.split('/') if s]

    # Pattern 1: Look for "chapter-XX" or "ch-XX" or "chXX" pattern in any segment
    chapter_pattern = re.compile(
        r'^(chapter[-_]?\d+|ch[-_]?\d+|ep[-_]?\d+|episode[-_]?\d+)$',
        re.IGNORECASE
    )
    for seg in reversed(segments):
        if chapter_pattern.match(seg):
            return seg.lower().replace('_', '-')

    # Pattern 2: Look for segments that are purely numeric (chapter number)
    numeric_pattern = re.compile(r'^\d{1,4}$')
    for seg in reversed(segments):
        if numeric_pattern.match(seg):
            return f"chapter-{seg.zfill(3)}"

    # Pattern 3: Fallback — use the last meaningful segment
    # Skip common parent path segments
    skip_segments = {'home', 'read', 'manga', 'comic', 'comics', 'series',
                     'title', 'series', 'chapter', 'ch', 'ep', 'episode',
                     'page', 'pages', 'online', 'free', 'read', 'view'}
    for seg in reversed(segments):
        slug = seg.lower().strip()
        if slug and slug not in skip_segments and len(slug) > 1:
            # Clean up the slug
            slug = re.sub(r'[^a-z0-9\-_]', '-', slug)
            slug = re.sub(r'-+', '-', slug).strip('-')
            if slug:
                return slug

    # Ultimate fallback: use "chapter-001"
    return "chapter-001"


# User-Agent rotation pool
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


# ---------------------------------------------------------------------------
# Helper: create a dummy placeholder image when scraping fails
# ---------------------------------------------------------------------------

def _create_dummy_image(save_path: str, page_number: int, width: int = 800, height: int = 1200):
    """Create a dummy comic page image for testing / fallback."""
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((width // 2 - 50, height // 2 - 50), f"Page {page_number}", fill=(0, 0, 0))
    draw.text((width // 2 - 100, height // 2 + 20),
              f"This is dummy comic page #{page_number}", fill=(100, 100, 100))
    draw.rectangle([50, 50, width - 50, height // 3], outline=(200, 200, 200), width=2)
    draw.rectangle([50, height // 3 + 25, width - 50, 2 * height // 3], outline=(200, 200, 200), width=2)
    draw.rectangle([50, 2 * height // 3 + 25, width - 50, height - 50], outline=(200, 200, 200), width=2)
    img.save(save_path)
    return save_path


# ---------------------------------------------------------------------------
# Image validation — dimension and pattern filtering
# ---------------------------------------------------------------------------

def _is_valid_comic_image(img_info: dict, page_url: str) -> bool:
    """
    Validate if an image is likely a comic page based on:
    1. Dimensions (width > 400px OR height > width, typical for vertical scroll comics)
    2. URL patterns (no logos, icons, ads, etc.)
    3. File extension
    """
    src = (img_info.get("src") or img_info.get("data-src") or 
           img_info.get("data-lazy-src") or "").lower()
    
    if not src:
        return False
    
    # Check file extension
    ext = os.path.splitext(urlparse(src).path)[1].lower()
    if ext and ext not in ALLOWED_EXTENSIONS:
        return False
    
    # Block known non-content patterns
    if BLOCKED_PATTERNS.search(src):
        return False
    
    # Block SVGs and data URIs
    if src.startswith("data:") or src.endswith(".svg"):
        return False
    
    # Check dimensions
    try:
        width = int(img_info.get("width", 0) or 0)
        height = int(img_info.get("height", 0) or 0)
    except (ValueError, TypeError):
        width = 0
        height = 0
    
    # Primary filter: width > MIN_IMAGE_WIDTH OR height > width (vertical comic strip)
    if width >= MIN_IMAGE_WIDTH or (height > 0 and height > width):
        return True
    
    # Secondary: both dimensions meet minimum
    if width >= MIN_IMAGE_WIDTH and height >= MIN_IMAGE_HEIGHT:
        return True
    
    # Tertiary: if natural dimensions are available (from loaded image)
    natural_width = img_info.get("naturalWidth", 0)
    natural_height = img_info.get("naturalHeight", 0)
    try:
        if int(natural_width) >= MIN_IMAGE_WIDTH or (int(natural_height) > int(natural_width)):
            return True
    except (ValueError, TypeError):
        pass
    
    return False


def _get_image_url(img_info: dict) -> str:
    """Extract the real image URL, prioritizing data-* attributes over src."""
    for attr in IMAGE_URL_ATTRS:
        url = img_info.get(attr)
        if url and url.strip() and not url.startswith("data:"):
            return url.strip()
    return ""


# ---------------------------------------------------------------------------
# Main scrape function
# ---------------------------------------------------------------------------

async def scrape_comic(
    url: str,
    output_dir: str = "temp",
    custom_containers: Optional[List[str]] = None,
    scroll_pause_ms: int = 300,
    max_scrolls: int = 20,
    headless: bool = True,
    fallback_to_dummy: bool = True,
) -> List[str]:
    """
    Navigate to a comic URL using Playwright, find comic page images,
    and download them sequentially.

    Args:
        url: The comic chapter URL to scrape.
        output_dir: Directory to save downloaded images.
        custom_containers: Override the default container selectors.
        scroll_pause_ms: Milliseconds to pause between scroll steps (for lazy loading).
        max_scrolls: Maximum scroll attempts before stopping.
        headless: Run browser in headless mode.
        fallback_to_dummy: If True, generate dummy images when scraping fails.

    Returns:
        List of file paths to downloaded images.
    """
    from playwright.async_api import async_playwright

    os.makedirs(output_dir, exist_ok=True)
    image_paths: List[str] = []
    containers = custom_containers or READING_CONTAINERS

    print(f"[SCRAPER] Navigating to: {url}")

    try:
        async with async_playwright() as p:
            import random
            user_agent = random.choice(USER_AGENTS)

            # Launch browser with anti-detection args
            browser = await p.chromium.launch(
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-web-security",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
            )

            context = await browser.new_context(
                user_agent=user_agent,
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                ignore_https_errors=True,
            )

            # Remove webdriver detection
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                window.chrome = { runtime: {} };
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """)

            page = await context.new_page()
            page.set_default_timeout(60000)

            # Navigate to the target URL
            response = await page.goto(url, wait_until="domcontentloaded", timeout=90000)
            status_code = response.status if response else "N/A"
            print(f"[SCRAPER] Page loaded with status: {status_code}")

            # Wait for initial content to render
            await page.wait_for_timeout(3000)

            # Handle potential popups / cookie banners
            try:
                close_selectors = (
                    "button:has-text('Close'), button:has-text('×'), "
                    "button:has-text('OK'), button:has-text('Accept'), "
                    ".popup-close, .modal-close, [aria-label='Close'], "
                    ".close-btn, .dismiss-btn"
                )
                close_buttons = await page.query_selector_all(close_selectors)
                for btn in close_buttons:
                    if await btn.is_visible():
                        await btn.click()
                        await page.wait_for_timeout(500)
            except Exception:
                pass

            # ==========================================================
            # STEP 1: Smooth sequential scroll to trigger lazy loading
            # ==========================================================
            print("[SCRAPER] Starting lazy-load scroll sequence...")
            
            # Get total scrollable height
            total_height = await page.evaluate("() => document.documentElement.scrollHeight")
            viewport_height = await page.evaluate("() => window.innerHeight")
            
            # Scroll in small increments with delays
            scroll_step = viewport_height * 0.6  # 60% of viewport per scroll
            current_scroll = 0
            
            for i in range(max_scrolls):
                # Scroll down
                await page.evaluate(f"window.scrollTo(0, {current_scroll})")
                await page.wait_for_timeout(scroll_pause_ms)
                
                current_scroll += scroll_step
                
                # Check if we've reached the bottom
                current_max = await page.evaluate("() => document.documentElement.scrollHeight")
                if current_scroll >= current_max - viewport_height:
                    print(f"[SCRAPER] Reached bottom after {i + 1} scrolls")
                    break
                
                # Log progress every 5 scrolls
                if (i + 1) % 5 == 0:
                    progress = min(100, int((current_scroll / max(current_max, 1)) * 100))
                    print(f"[SCRAPER] Scroll progress: {progress}%")

            # Scroll back to top
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(1000)

            # ==========================================================
            # STEP 2: Find the main reading container
            # ==========================================================
            print("[SCRAPER] Searching for reading container...")
            container = None
            
            for container_selector in containers:
                try:
                    elements = await page.query_selector_all(container_selector)
                    if elements:
                        # Check if this container has images
                        for el in elements:
                            inner_imgs = await el.query_selector_all("img")
                            if inner_imgs:
                                container = el
                                print(f"[SCRAPER] Found reading container: '{container_selector}' "
                                      f"with {len(inner_imgs)} images")
                                break
                        if container:
                            break
                except Exception as e:
                    continue

            # ==========================================================
            # STEP 3: Extract images from container (or all images if no container)
            # ==========================================================
            found_images = []
            
            if container:
                # Extract images from the specific container
                img_elements = await container.query_selector_all("img")
                print(f"[SCRAPER] Extracting images from container...")
            else:
                # Fallback: get all images on the page
                img_elements = await page.query_selector_all("img")
                print("[SCRAPER] No specific container found. Using all page images.")

            for img_el in img_elements:
                try:
                    img_info = await img_el.evaluate("""
                        el => ({
                            src: el.getAttribute('src') || '',
                            'data-src': el.getAttribute('data-src') || '',
                            'data-lazy-src': el.getAttribute('data-lazy-src') || '',
                            'data-original': el.getAttribute('data-original') || '',
                            alt: el.getAttribute('alt') || '',
                            width: el.naturalWidth || el.width || 0,
                            height: el.naturalHeight || el.height || 0,
                            naturalWidth: el.naturalWidth || 0,
                            naturalHeight: el.naturalHeight || 0,
                            class: el.className || '',
                        })
                    """)
                    
                    # Get the real image URL
                    real_url = _get_image_url(img_info)
                    if real_url:
                        img_info["src"] = real_url
                        
                        # Validate the image
                        if _is_valid_comic_image(img_info, url):
                            found_images.append(img_info)
                            
                except Exception as e:
                    continue

            print(f"[SCRAPER] Found {len(found_images)} valid comic page images")

            # ==========================================================
            # STEP 4: Deduplicate and filter
            # ==========================================================
            seen_urls = set()
            filtered_images = []
            
            for img in found_images:
                src = img.get("src", "")
                
                # Normalize relative URLs
                if src and (src.startswith("/") or src.startswith(".")):
                    src = urljoin(url, src)
                    img["src"] = src
                
                # Skip if already seen
                if src in seen_urls or not src:
                    continue
                seen_urls.add(src)
                
                # Final extension check
                ext = os.path.splitext(urlparse(src).path)[1].lower()
                if ext and ext not in ALLOWED_EXTENSIONS:
                    continue
                
                filtered_images.append(img)

            print(f"[SCRAPER] After deduplication: {len(filtered_images)} images")

            # ==========================================================
            # STEP 5: Download images with resume/skip logic
            # ==========================================================
            # Check which files already exist in the output directory
            existing_files = set()
            if os.path.isdir(output_dir):
                for fname in os.listdir(output_dir):
                    if fname.startswith("comic_page_") and any(fname.endswith(ext) for ext in ALLOWED_EXTENSIONS):
                        existing_files.add(fname)

            skipped_count = 0
            downloaded_count = 0

            for idx, img_info in enumerate(filtered_images):
                src = img_info["src"]
                
                # Determine file extension
                parsed = urlparse(src)
                ext = os.path.splitext(parsed.path)[1].lower()
                if not ext or ext not in ALLOWED_EXTENSIONS:
                    ext = ".png"
                
                filename = f"comic_page_{idx + 1:03d}{ext}"
                save_path = os.path.join(output_dir, filename)

                # --- Resume/skip check: if file already exists, skip download ---
                if filename in existing_files and os.path.exists(save_path):
                    file_size = os.path.getsize(save_path)
                    if file_size > 0:
                        print(f"[SCRAPER] RESUME SKIP: {filename} already exists ({file_size:,} bytes)")
                        image_paths.append(save_path)
                        skipped_count += 1
                        continue
                    else:
                        # File is empty/corrupt, re-download it
                        print(f"[SCRAPER] RE-DOWNLOAD: {filename} exists but is empty (0 bytes)")
                        existing_files.discard(filename)

                try:
                    print(f"[SCRAPER] Downloading page {idx + 1}/{len(filtered_images)}: {src[:80]}...")
                    
                    # Navigate to image URL and download
                    await page.goto(src, wait_until="domcontentloaded", timeout=30000)
                    
                    # Try to fetch the image data
                    img_data = await page.evaluate(f"""
                        async () => {{
                            try {{
                                const resp = await fetch('{src}', {{
                                    headers: {{
                                        'Referer': '{url}',
                                        'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8'
                                    }}
                                }});
                                if (!resp.ok) return null;
                                const blob = await resp.blob();
                                const reader = new FileReader();
                                return new Promise((resolve) => {{
                                    reader.onload = () => resolve(reader.result);
                                    reader.readAsDataURL(blob);
                                }});
                            }} catch (e) {{
                                return null;
                            }}
                        }}
                    """)

                    if img_data and img_data.startswith("data:"):
                        import base64
                        base64_data = img_data.split(",")[1]
                        img_bytes = base64.b64decode(base64_data)
                        with open(save_path, "wb") as f:
                            f.write(img_bytes)
                        image_paths.append(save_path)
                        downloaded_count += 1
                        print(f"[SCRAPER] Saved: {filename} ({len(img_bytes):,} bytes)")
                    else:
                        # Fallback: take screenshot
                        print(f"[SCRAPER] Fetch failed, taking screenshot...")
                        await page.screenshot(path=save_path, full_page=False)
                        image_paths.append(save_path)
                        downloaded_count += 1
                        print(f"[SCRAPER] Saved (screenshot): {filename}")

                except Exception as e:
                    print(f"[SCRAPER] Failed to download page {idx + 1}: {e}")
                    continue

            if skipped_count > 0:
                print(f"[SCRAPER] Resume: {skipped_count} images skipped, {downloaded_count} newly downloaded")
            else:
                print(f"[SCRAPER] Downloaded: {downloaded_count} images")

            await browser.close()

    except Exception as e:
        print(f"[SCRAPER] CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

    # ==========================================================
    # Fallback: generate dummy images if nothing downloaded
    # ==========================================================
    if not image_paths and fallback_to_dummy:
        print("[SCRAPER] No real images downloaded. Generating dummy images for testing.")
        for i in range(1, 4):
            file_path = os.path.join(output_dir, f"comic_page_{i}.png")
            _create_dummy_image(file_path, i)
            image_paths.append(file_path)
            print(f"[SCRAPER] Generated dummy page {i}: {file_path}")

    print(f"[SCRAPER] Done. Total images: {len(image_paths)}")
    return image_paths