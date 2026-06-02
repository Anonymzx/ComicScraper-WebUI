# ComicScraper WebUI

**Local, Offline, Automated Comic Processing** A powerful Gradio-based WebUI to scrape, stitch, and extract text from web-based comics. Generate clean, high-resolution stitched comics or PDF exports with AI-powered OCR text extraction — **100% offline**.

<p align="center">
  <img src="https://img.shields.io/badge/Language-Multi-brightgreen" alt="Languages">
  <img src="https://img.shields.io/badge/🇮🇩_Indonesian-Supported-red" alt="Indonesian">
  <img src="https://img.shields.io/badge/OCR-PaddleOCR-yellow" alt="PaddleOCR">
  <img src="https://img.shields.io/badge/Offline-Yes-blue" alt="Offline">
  <img src="https://img.shields.io/badge/License-MIT-orange" alt="License">
</p>

---

## 🖼️ UI Overview
<p align="center">
<img width="1168" height="834" alt="image" src="https://github.com/user-attachments/assets/cad9ffc4-6e3e-4869-9b1e-f6bb93aae91f" />
<img width="1189" height="430" alt="image" src="https://github.com/user-attachments/assets/1fc19ad5-c057-4fcb-a60d-665bd61ae8b7" />

</p>
**Core Functionalities:**
- **Automated Scraper**: Scrapes comic chapters with intelligent lazy-load handling.
- **Smart Stitching**: Automatically merges pages into long strips. Handles ultra-high resolution via intelligent PNG fallback.
- **AI Text Extraction**: Built-in OCR pipeline to extract text from comic panels into clean `.txt` files.
- **PDF Export**: Generate ready-to-read PDF documents automatically.

---

## ✨ Key Features

| Feature | Benefit |
|---------|---------|
| 🌐 **Multi-Site Support** | Scrape comics from various popular platforms. |
| 🖼️ **Intelligent Stitching** | Merges pages perfectly; auto-detects limit and switches to PNG when necessary. |
| 🔍 **AI-Powered OCR** | Extract text from panels using the latest PaddleOCR (PP-OCRv5). |
| ⚡ **Offline First** | Works 100% locally. No API keys, no subscription, no data leaks. |
| 📄 **Automated PDF** | Direct conversion from images to organized PDF files. |
| ⚙️ **Optimized Engine** | Efficient CPU/GPU utilization for fast scraping and processing. |

---

## 🚀 Installation

### ▶️ Windows (One-Click Setup)
```bash
git clone [https://github.com/Anonymzx/ComicScraper-WebUI.git](https://github.com/Anonymzx/ComicScraper-WebUI.git)
cd ComicScraper-WebUI

```

1. Double-click `install.bat` → auto-creates venv + installs all dependencies.
2. Double-click `run.bat` → launches the WebUI.
3. Open [http://localhost:7860](https://www.google.com/search?q=http://localhost:7860) in your browser.

### 🐧 Linux / macOS / Advanced Users

```bash
git clone [https://github.com/Anonymzx/ComicScraper-WebUI.git](https://github.com/Anonymzx/ComicScraper-WebUI.git)
cd ComicScraper-WebUI
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Launch
python app.py

```

---

## 💻 System Requirements

| Component | Minimum | Recommended |
| --- | --- | --- |
| **CPU** | Dual-core | Quad-core or better |
| **RAM** | 4 GB | 8 GB+ |
| **Storage** | 500 MB | 2 GB+ (for chapters/cache) |
| **OS** | Windows 10 / Linux / macOS | Latest stable release |

---

## 🛠️ Troubleshooting

| Issue | Likely Cause | Solution |
| --- | --- | --- |
| ❌ Scraper fails | Target site changed structure | Check if the URL is still accessible in browser |
| 🐌 Slow OCR | CPU mode | Ensure your environment has proper drivers for acceleration |
| 🪟 App closes instantly | Missing dependency | Launch via terminal to see error log |
| 📄 Output empty | OCR model cache | Delete `C:\Users\<User>\.paddlex` if model fails to load |

---

## 🤝 Contributing & Support

Found a bug? Have a feature idea?

1. 🐛 [Open an Issue](https://www.google.com/search?q=https://github.com/Anonymzx/ComicScraper-WebUI/issues) — Describe the issue clearly.
2. 🔀 Submit a Pull Request — Include a description of your changes.
3. 💬 Join discussions in the repo's *Discussions* tab.
4. Star the repo if you find it useful!

**Ways to Contribute:**

* 🌐 Add scraper support for more comic sites.
* 🎨 Improve WebUI/UX with Gradio components.
* 🧪 Test on different hardware configurations.
* 📝 Write usage guides.

---

## ☕ Support the Project

If you find this tool useful, consider supporting the development!

<p align="center">
  <a href="https://ko-fi.com/anonymzx" target="_blank">
    <img src="https://storage.ko-fi.com/cdn/kofi3.png?v=3" alt="Buy Me a Coffee" height="40">
  </a>
</p>

---

<p align="center">
  <sub>Built with ❤️ by <a href="https://github.com/Anonymzx">@Anonymzx</a> • For creators, developers, and privacy-first users</sub>
</p>

<p align="center">
  <a href="https://github.com/Anonymzx/Supertonic-WebUI/stargazers">
    <img src="https://img.shields.io/github/stars/Anonymzx/Supertonic-WebUI?style=social" alt="GitHub Stars">
  </a>
  <a href="https://github.com/Anonymzx/Supertonic-WebUI/network/members">
    <img src="https://img.shields.io/github/forks/Anonymzx/Supertonic-WebUI?style=social" alt="GitHub Forks">
  </a>
</p>
