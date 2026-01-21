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

Examples:
    python clean.py https://example.com/page
    python clean.py page.html
    python clean.py page1.html page2.html page3.html
    python clean.py page.html https://example.com/page

Dependencies:
    beautifulsoup4 (pip install beautifulsoup4)
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

def remove_non_content_elements(soup: BeautifulSoup) -> None:
    """Remove elements that don't contribute to main content."""
    # Remove script, style, and other non-content tags
    for tag_name in ['script', 'style', 'nav', 'footer', 'header', 'aside', 'table', 'noscript', 'iframe', 'button']:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    
    # Remove HTML comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

def remove_ui_elements(soup: BeautifulSoup) -> None:
    """Remove common UI elements like sidebars, TOCs, and navigation by class/ID patterns."""
    # Patterns that indicate UI chrome rather than content
    ui_class_patterns = ['sidebar', 'toc', 'table-of-contents', 'breadcrumb', 'navigation', 
                         'nav-', 'menu', 'search', 'skip-to', 'toolbar']
    ui_id_patterns = ['sidebar', 'toc', 'table-of-contents', 'navigation', 'breadcrumb',
                      'menu', 'search']
    
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

def html_to_markdown(html_content: str) -> str:
    """Convert HTML content to clean markdown text."""
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
    notice = "> [This file is converted from HTML. Non-primary content has been removed while trying to preserve structure.]\n\n"
    text = notice + text
    
    return text

def process_input(input_path: str, output_dir: str) -> bool:
    """Process a single input file or URL. Returns True on success."""
    output_path = get_output_path(input_path, output_dir)
    
    # Read HTML from file or URL
    if is_url(input_path):
        html_content = fetch_url(input_path)
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
            print(f"Error: Unable to decode '{input_path}' as UTF-8. Try a different encoding.")
            return False
    
    # Convert to markdown
    markdown_content = html_to_markdown(html_content)
    
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
    
    args = parser.parse_args()
    
    # Ensure output directory exists
    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)
    
    # Process each input
    success_count = 0
    fail_count = 0
    
    for input_path in args.inputs:
        if process_input(input_path, output_dir):
            success_count += 1
        else:
            fail_count += 1
    
    # Summary for multiple files
    if len(args.inputs) > 1:
        print(f"\nSummary: {success_count} succeeded, {fail_count} failed")

if __name__ == '__main__':
    main()