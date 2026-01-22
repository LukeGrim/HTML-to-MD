#!/usr/bin/env python3
"""
HTML to Markdown Converter

Converts one or more HTML files or webpages to clean markdown text, preserving structure
through headings and whitespace. Links are removed from the output.

Output files are automatically saved to the 'output' folder with .md extension.

Usage:
    python clean.py <input1> [input2] [input3] ...

Arguments:
    input - One or more paths to HTML files or URLs to fetch HTML from

Options:
    --wait-time MS   Time to wait for JS rendering in milliseconds (default: 5000)
    --render-js      Always use headless browser for URLs (requires playwright)
    --no-render-js   Never use headless browser, even for JS-rendered pages

Examples:
    python clean.py https://example.com/page
    python clean.py page.html
    python clean.py page1.html page2.html page3.html
    python clean.py page.html https://example.com/page
    python clean.py --render-js https://spa-website.com/page
    python clean.py --render-js --wait-time 10000 https://slow-spa.com/page

Dependencies:
    beautifulsoup4 (pip install beautifulsoup4)

Optional Dependencies (for JavaScript-rendered pages):
    playwright (pip install playwright && playwright install chromium)
"""

import argparse
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path
from urllib.parse import urlparse
try:
    from bs4 import BeautifulSoup, Comment
except ImportError:
    print("Error: BeautifulSoup is not installed. Install with 'pip install beautifulsoup4'")
    sys.exit(1)

# Optional dependency for JavaScript rendering
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# SPA framework indicators that suggest JavaScript-rendered content
SPA_INDICATORS = [
    '__sveltekit_',      # SvelteKit
    '__NEXT_DATA__',     # Next.js
    '__NUXT__',          # Nuxt.js (Vue)
    'window.__remixContext',  # Remix
    '_app/immutable/',   # SvelteKit assets
    'react-root',        # React
    'data-reactroot',    # React
]

def detect_js_rendered_content(soup: BeautifulSoup, html_content: str) -> bool:
    """
    Detect if the page content is rendered by JavaScript (SPA).
    """
    # Check for SPA framework indicators in raw HTML
    has_spa_indicator = any(indicator in html_content for indicator in SPA_INDICATORS)
    
    if not has_spa_indicator:
        return False
    
    # Check if main content containers are empty or near-empty
    # Look for common content containers
    content_containers = (
        soup.find('main') or 
        soup.find('article') or 
        soup.find(class_=lambda c: c and 'main-content' in ' '.join(c).lower() if isinstance(c, list) else 'main-content' in c.lower() if c else False) or
        soup.find(id=lambda i: i and 'content' in i.lower() if i else False)
    )
    
    if content_containers:
        # Get text content, ignoring scripts and styles
        for tag in content_containers.find_all(['script', 'style']):
            tag.decompose()
        text_content = content_containers.get_text(strip=True)
        # If main content area has very little text, it's likely JS-rendered
        if len(text_content) < 100:
            return True
    
    # Check for empty placeholder divs that are common in SPAs
    # e.g., <div id="app"></div>, <div id="root"></div>, <div id="__next"></div>
    spa_root_ids = ['app', 'root', '__next', 'scalar-api-reference', 'application']
    for root_id in spa_root_ids:
        element = soup.find(id=root_id)
        if element and not element.get_text(strip=True):
            return True
    
    return False

def is_url(path: str) -> bool:
    """Check if the given path is a URL."""
    try:
        result = urlparse(path)
        return result.scheme in ('http', 'https')
    except ValueError:
        return False

def get_output_path(input_path: str, output_dir: str = "output") -> str:
    """Generate output path in the output folder based on input filename."""
    if is_url(input_path):
        # Extract filename from URL path
        parsed = urlparse(input_path)
        url_path = parsed.path.rstrip('/')
        if url_path:
            basename = os.path.basename(url_path)
            # Remove query strings or fragments from basename
            basename = basename.split('?')[0].split('#')[0]
        else:
            basename = parsed.netloc.replace('.', '_')
        
        if not basename:
            basename = "page"
    else:
        basename = os.path.basename(input_path)
    
    # Change extension to .md
    name_without_ext = os.path.splitext(basename)[0]
    output_filename = f"{name_without_ext}.md"
    
    return os.path.join(output_dir, output_filename)

def fetch_url(url: str) -> str:
    """Fetch HTML content from a URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows 11; Win64; x64)'
    }
    request = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            # Try to detect encoding from response headers
            charset = response.headers.get_content_charset()
            if charset:
                return response.read().decode(charset)
            else:
                # Fall back to UTF-8
                return response.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        print(f"Error: HTTP {e.code} - {e.reason} when fetching '{url}'")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error: Could not connect to '{url}': {e.reason}")
        sys.exit(1)
    except UnicodeDecodeError:
        print(f"Error: Unable to decode content from '{url}' as UTF-8.")
        sys.exit(1)

def fetch_url_with_js(url: str, timeout: int = 30000, wait_time: int = 5000) -> str:
    """Fetch URL using headless browser to render JavaScript.
    
    Args:
        url: The URL to fetch
        timeout: Navigation timeout in milliseconds (default 30 seconds)
        wait_time: Additional time to wait after networkidle for JS rendering (default 5 seconds)
    
    Returns:
        The fully rendered HTML content
    
    Raises:
        Exception: If browser fails to launch or page fails to load
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, timeout=timeout)
            page.wait_for_load_state('networkidle')
            # Additional wait for JS frameworks to finish rendering
            if wait_time > 0:
                page.wait_for_timeout(wait_time)
            html = page.content()
            return html
        finally:
            browser.close()

def remove_non_content_elements(soup: BeautifulSoup) -> None:
    """Remove elements that don't contribute to main content."""
    # Remove script, style, and other non-content tags
    for tag_name in ['script', 'style', 'nav', 'footer', 'header', 'aside', 'table', 'noscript', 'iframe', 'button']:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    
    # Remove HTML comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

# Tags that should never be removed by UI pattern matching (main content containers)
PROTECTED_CONTENT_TAGS = ['body', 'main', 'article', 'section']

def remove_ui_elements(soup: BeautifulSoup) -> None:
    """Remove common UI elements like sidebars, TOCs, and navigation by class/ID patterns."""
    # Patterns that indicate UI chrome rather than content
    # Note: Use specific patterns to avoid false positives on content IDs like 'web-search'
    ui_class_patterns = ['sidebar', 'toc', 'table-of-contents', 'breadcrumb', 'navigation', 
                         'nav-', 'menu', 'search-box', 'search-form', 'search-input', 
                         'searchbar', 'search-widget', 'skip-to', 'toolbar']
    ui_id_patterns = ['sidebar', 'toc', 'table-of-contents', 'navigation', 'breadcrumb',
                      'menu', 'search-box', 'search-form', 'search-input', 'searchbar']
    
    # Collect elements to remove (to avoid modifying while iterating)
    elements_to_remove = []
    
    # Find elements by class
    for element in soup.find_all(class_=True):
        if element.attrs is None:
            continue
        classes = element.get('class', [])
        if classes:
            class_str = ' '.join(classes).lower()
            if any(pattern in class_str for pattern in ui_class_patterns):
                elements_to_remove.append(element)
    
    # Find elements by ID
    for element in soup.find_all(id=True):
        if element.attrs is None:
            continue
        elem_id = element.get('id', '')
        if elem_id:
            elem_id_lower = elem_id.lower()
            if any(pattern in elem_id_lower for pattern in ui_id_patterns):
                elements_to_remove.append(element)
    
    # Remove collected elements
    for element in elements_to_remove:
        if element.parent is not None:  # Element still in tree
            if element.name in PROTECTED_CONTENT_TAGS:
                continue  # Don't remove main content containers
            element.decompose()

def remove_links(soup: BeautifulSoup) -> None:
    """Remove links but keep the anchor text in place."""
    for anchor in soup.find_all('a'):
        anchor.unwrap()
def extract_title(soup: BeautifulSoup) -> str:
    """Extract the page title from <title> tag."""
    title_tag = soup.find('title')
    if title_tag:
        title_text = title_tag.get_text(strip=True)
        title_tag.decompose()
        return title_text
    return ""

def convert_code_blocks(soup: BeautifulSoup) -> None:
    """Convert <pre> and <code> blocks to markdown fenced code blocks."""
    for pre in soup.find_all('pre'):
        # Get raw text content, preserving internal whitespace
        code_text = pre.get_text()
        # Wrap in fenced code block
        fenced = f"\n\n```\n{code_text}\n```\n\n"
        pre.replace_with(fenced)
def convert_headings(soup: BeautifulSoup) -> None:
    """Convert h1-h6 tags to markdown heading markers."""
    for level in range(1, 7):
        for heading in soup.find_all(f'h{level}'):
            text = heading.get_text(strip=True)
            if text:
                markdown_heading = f"\n\n{'#' * level} {text}\n\n"
                heading.replace_with(markdown_heading)
            else:
                heading.decompose()

def convert_list_item(li, indent_level: int = 0, ordered: bool = False, index: int = 1) -> str:
    """Recursively convert a list item and its nested lists to markdown."""
    indent = "    " * indent_level
    result_lines = []
    
    # Get direct text content (not from nested lists)
    # Clone the li to work with
    direct_text_parts = []
    for child in li.children:
        if hasattr(child, 'name') and child.name in ['ul', 'ol']:
            continue  # Skip nested lists for now
        if hasattr(child, 'get_text'):
            direct_text_parts.append(child.get_text(strip=True))
        elif isinstance(child, str):
            text = child.strip()
            if text:
                direct_text_parts.append(text)
    
    direct_text = ' '.join(direct_text_parts).strip()
    
    # Create the list item marker
    if ordered:
        marker = f"{index}."
    else:
        marker = "-"
    
    if direct_text:
        result_lines.append(f"{indent}{marker} {direct_text}")
    
    # Process nested lists
    for nested_ul in li.find_all('ul', recursive=False):
        for nested_li in nested_ul.find_all('li', recursive=False):
            nested_result = convert_list_item(nested_li, indent_level + 1, ordered=False)
            if nested_result:
                result_lines.append(nested_result)
    
    for nested_ol in li.find_all('ol', recursive=False):
        for idx, nested_li in enumerate(nested_ol.find_all('li', recursive=False), start=1):
            nested_result = convert_list_item(nested_li, indent_level + 1, ordered=True, index=idx)
            if nested_result:
                result_lines.append(nested_result)
    
    return '\n'.join(result_lines)

def convert_lists(soup: BeautifulSoup) -> None:
    """Convert list items to markdown format with proper nesting."""
    # Process only top-level lists (not nested ones)
    for ul in soup.find_all('ul'):
        # Skip if this ul is nested inside another list
        if ul.find_parent(['ul', 'ol']):
            continue
        
        list_lines = []
        for li in ul.find_all('li', recursive=False):
            item_text = convert_list_item(li, indent_level=0, ordered=False)
            if item_text:
                list_lines.append(item_text)
        
        if list_lines:
            ul.replace_with('\n' + '\n'.join(list_lines) + '\n')
        else:
            ul.decompose()
    
    for ol in soup.find_all('ol'):
        # Skip if this ol is nested inside another list
        if ol.find_parent(['ul', 'ol']):
            continue
        
        list_lines = []
        for idx, li in enumerate(ol.find_all('li', recursive=False), start=1):
            item_text = convert_list_item(li, indent_level=0, ordered=True, index=idx)
            if item_text:
                list_lines.append(item_text)
        
        if list_lines:
            ol.replace_with('\n' + '\n'.join(list_lines) + '\n')
        else:
            ol.decompose()

def add_inline_spacing(soup: BeautifulSoup) -> None:
    """Add spaces around inline elements to prevent word concatenation."""
    inline_tags = ['code', 'strong', 'em', 'b', 'i', 'span']
    
    for tag_name in inline_tags:
        for tag in soup.find_all(tag_name):
            # Check if we need to add space before
            prev_sibling = tag.previous_sibling
            if prev_sibling and isinstance(prev_sibling, str) and prev_sibling and not prev_sibling.endswith((' ', '\n', '\t')):
                tag.insert_before(' ')
            
            # Check if we need to add space after
            next_sibling = tag.next_sibling
            if next_sibling and isinstance(next_sibling, str) and next_sibling and not next_sibling.startswith((' ', '\n', '\t')):
                tag.insert_after(' ')
            
            # Unwrap the tag (keep content, remove markup)
            tag.unwrap()

def add_block_spacing(soup: BeautifulSoup) -> None:
    """Add spacing markers for block-level elements."""
    # Note: 'pre' is handled separately by convert_code_blocks
    block_tags = ['p', 'div', 'section', 'article', 'blockquote']
    
    for tag_name in block_tags:
        for tag in soup.find_all(tag_name):
            # Add newlines before and after content
            text = tag.get_text()
            tag.replace_with(f"\n\n{text}\n\n")
    
    # Handle line breaks
    for br in soup.find_all('br'):
        br.replace_with('\n')

def normalize_whitespace(text: str) -> str:
    """Collapse excessive whitespace while preserving paragraph structure."""
    # Normalize different types of whitespace to spaces (except newlines)
    text = re.sub(r'[^\S\n]+', ' ', text)
    
    # Collapse multiple newlines to maximum of two (paragraph break)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Remove spaces at the beginning and end of lines
    text = re.sub(r' *\n *', '\n', text)
    
    # Remove leading/trailing whitespace from the whole text
    text = text.strip()
    
    return text

def remove_feedback_patterns(text: str) -> str:
    """Remove common UI feedback widget patterns."""
    # Remove "Was this page helpful?" and similar patterns
    patterns = [
        r'Was this page helpful\??\s*',
        r'\bYes\s*No\b',
        r'YesNo\b',
        r'Rate this page.*',
        r'Give feedback.*',
        r'Edit this page.*',
        r'⌘[A-Z]',  # Keyboard shortcut indicators like ⌘K
    ]
    
    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    return text

def remove_empty_sections(text: str) -> str:
    """Remove headings that have no content before the next heading."""
    lines = text.split('\n')
    result = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Check if this is a heading line
        if line.strip().startswith('#'):
            # Look ahead to see if next non-empty line is also a heading
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            
            # If we reached end of file or next content is a heading, skip this heading
            if j >= len(lines) or lines[j].strip().startswith('#'):
                i += 1
                continue
        
        result.append(line)
        i += 1
    
    return '\n'.join(result)

def html_to_markdown(html_content: str, used_js_rendering: bool = False) -> tuple[str, bool]:
    """Convert HTML content to clean markdown text.
    
    Args:
        html_content: The HTML string to convert
        used_js_rendering: Whether headless browser was used to render this content
    
    Returns:
        tuple: (markdown_content, is_js_rendered) where is_js_rendered indicates
               if the content appears to be JavaScript-rendered (SPA).
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Detect JS-rendered content before modifying the soup
    is_js_rendered = detect_js_rendered_content(soup, html_content)
    
    # Re-parse since detection may have modified the soup
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Step 1: Extract title before removing elements
    title = extract_title(soup)
    
    # Step 2: Remove non-content elements (scripts, styles, nav, etc.)
    remove_non_content_elements(soup)
    
    # Step 3: Remove UI chrome (sidebars, TOCs, breadcrumbs by class/ID)
    remove_ui_elements(soup)
    
    # Step 4: Remove link markup (keep anchor text)
    remove_links(soup)
    
    # Step 5: Add spacing around inline elements before unwrapping
    add_inline_spacing(soup)
    
    # Step 6: Convert code blocks to fenced markdown
    convert_code_blocks(soup)
    
    # Step 7: Convert headings to markdown
    convert_headings(soup)
    
    # Step 8: Convert lists to markdown (with nesting support)
    convert_lists(soup)
    
    # Step 9: Add spacing for block elements
    add_block_spacing(soup)
    
    # Step 10: Extract text and normalize whitespace
    text = soup.get_text()
    text = normalize_whitespace(text)
    
    # Step 11: Remove common feedback UI patterns
    text = remove_feedback_patterns(text)
    
    # Step 12: Remove empty sections (headings with no content)
    text = remove_empty_sections(text)
    
    # Step 13: Add title as H1 if extracted
    if title:
        text = f"# {title}\n\n{text}"
    
    # Step 14: Add conversion notice at top
    if used_js_rendering:
        notice = "> [This file is converted from HTML using headless browser rendering. Non-primary content has been removed while trying to preserve structure.]\n\n"
    elif is_js_rendered:
        notice = "> [This file is converted from HTML. Non-primary content has been removed while trying to preserve structure.]\n>\n> **Warning: This page appears to use JavaScript rendering. The main content may be missing because a headless browser was not used before conversion.**\n\n"
    else:
        notice = "> [This file is converted from HTML. Non-primary content has been removed while trying to preserve structure.]\n\n"
    text = notice + text
    
    return text, is_js_rendered

def process_input(input_path: str, output_dir: str, render_js_mode: str = 'auto', wait_time: int = 5000) -> bool:
    """Process a single input file or URL. Returns True on success.
    
    Args:
        input_path: Path to HTML file or URL
        output_dir: Directory to write output markdown files
        render_js_mode: 'auto' (default), 'always', or 'never'
            - 'auto': Use Playwright only when JS rendering is detected
            - 'always': Always use Playwright for URLs (requires playwright)
            - 'never': Never use Playwright, just warn about JS content
        wait_time: Time to wait for JS rendering in milliseconds (default 5000)
    """
    output_path = get_output_path(input_path, output_dir)
    used_js_rendering = False
    
    # Read HTML from file or URL
    if is_url(input_path):
        # For 'always' mode, use Playwright directly
        if render_js_mode == 'always':
            if not PLAYWRIGHT_AVAILABLE:
                print(f"Error: --render-js requires playwright. Install with:")
                print(f"       pip install playwright && playwright install chromium")
                return False
            try:
                print(f"Rendering '{input_path}' with headless browser...")
                html_content = fetch_url_with_js(input_path, wait_time=wait_time)
                used_js_rendering = True
            except Exception as e:
                print(f"Error: Failed to render '{input_path}' with headless browser: {e}")
                return False
        else:
            # Start with simple fetch
            html_content = fetch_url(input_path)
            
            # Check if JS rendering is needed (only for 'auto' mode)
            if render_js_mode == 'auto':
                soup = BeautifulSoup(html_content, 'html.parser')
                is_js_page = detect_js_rendered_content(soup, html_content)
                
                if is_js_page:
                    if PLAYWRIGHT_AVAILABLE:
                        # Try to render with Playwright
                        try:
                            print(f"  JS rendering detected, re-fetching '{input_path}' with headless browser...")
                            html_content = fetch_url_with_js(input_path, wait_time=wait_time)
                            used_js_rendering = True
                        except Exception as e:
                            print(f"  Warning: Failed to render JavaScript for '{input_path}': {e}")
                            print(f"           Falling back to static HTML. Content may be incomplete.")
                    else:
                        # Playwright not available, will show warning later
                        pass
    else:
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
        except FileNotFoundError:
            print(f"Error: Input file '{input_path}' not found.")
            return False
        except PermissionError:
            print(f"Error: Permission denied reading '{input_path}'.")
            return False
        except UnicodeDecodeError:
            print(f"Error: Unable to decode '{input_path}' as UTF-8.")
            return False
    
    # Convert to markdown
    markdown_content, is_js_rendered = html_to_markdown(html_content, used_js_rendering)
    
    # Write markdown file
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
    except PermissionError:
        print(f"Error: Permission denied writing to '{output_path}'.")
        return False
    except OSError as e:
        print(f"Error: Could not write to '{output_path}': {e}")
        return False
    
    print(f"Converted '{input_path}' -> '{output_path}'")
    
    # Show appropriate message based on what happened
    if used_js_rendering:
        print(f"  Note: Content was rendered using a headless browser.")
    elif is_js_rendered:
        # JS was detected but we didn't render it
        print(f"  Warning: '{input_path}' appears to be JavaScript-rendered and . Content may be incomplete.")
        if not PLAYWRIGHT_AVAILABLE:
            print(f"  Tip: Install playwright for automatic JS rendering:")
            print(f"       pip install playwright && playwright install chromium")
    
    return True

def main():
    parser = argparse.ArgumentParser(
        description='Convert HTML to markdown. Remove links and preserve structure. Outputs saved to output folder.'
    )
    parser.add_argument(
        'inputs',
        nargs='+',
        help='One or more paths to HTML files or URLs (http/https)'
    )
    parser.add_argument(
        '-o', '--output-dir',
        default='output',
        help='Output directory for markdown files (default: output)'
    )
    
    # JS rendering options (mutually exclusive)
    js_group = parser.add_mutually_exclusive_group()
    js_group.add_argument(
        '--render-js',
        action='store_true',
        help='Always use headless browser for URLs (requires playwright)'
    )
    js_group.add_argument(
        '--no-render-js',
        action='store_true',
        help='Never use headless browser, even for JS-rendered pages'
    )
    parser.add_argument(
        '--wait-time',
        type=int,
        default=5000,
        metavar='MS',
        help='Time to wait for JS rendering in milliseconds (default: 5000)'
    )
    
    args = parser.parse_args()
    
    # Determine render mode
    if args.render_js:
        render_js_mode = 'always'
    elif args.no_render_js:
        render_js_mode = 'never'
    else:
        render_js_mode = 'auto'
    
    # Ensure output directory exists
    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)
    
    # Process each input
    success_count = 0
    fail_count = 0
    
    for input_path in args.inputs:
        if process_input(input_path, output_dir, render_js_mode, args.wait_time):
            success_count += 1
        else:
            fail_count += 1
    
    # Summary for multiple files
    if len(args.inputs) > 1:
        print(f"\nSummary: {success_count} succeeded, {fail_count} failed")

if __name__ == '__main__':
    main()