## How to Use

Run **python clean.py** with one or more HTML file or link arguments:

```bash
# Link to page
python clean.py https://example.com/page
# HTML file
python clean.py page.html
# Multiple files
python clean.py page1.html page2.html page3.html
# Mix of files and links
python clean.py page.html https://example.com/page
```

Converted markdown will be sent to the /output subdirectory.

## JavaScript-Rendered Pages (SPAs)

Pages built with JavaScript frameworks like **React**, **Vue**, **Svelte**, **Next.js**, or **Nuxt** render their content dynamically after page load.
By default, this tool will:

- Detect if a page appears to be JS-rendered
- Automatically re-fetch it using a headless browser (if Playwright is installed)
- Wait 5 seconds for rendering to finish before converting

### Installing Playwright

To enable automatic JS rendering support:

```bash
pip install playwright
playwright install chromium
```

### Options

| Option | Description |
|--------|-------------|
| **-o, --output-dir** | Output directory (default: output) |
| **--wait-time MS** | Time to wait for JS rendering in milliseconds (default: 5000) |
| **--render-js** | Always use headless browser for URLs (requires playwright) |
| **--no-render-js** | Never use headless browser, even for JS-rendered pages |

### Examples

```bash
# Auto mode (default): detects JS pages and renders them automatically
python clean.py https://spa-site.com/page
# Increase wait time for slow-loading SPAs
python clean.py --wait-time 10000 https://slow-spa.com/page
# Force JS rendering behavior for all URLs
python clean.py --render-js https://any-site.com/page
# Disable JS rendering behavior
python clean.py --no-render-js https://spa-site.com/page
```

### Without Playwright

If Playwright is not installed, or diabled, the converter will display a warning when it detects JS-rendered content. Output may be incomplete.