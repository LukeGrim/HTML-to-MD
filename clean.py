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
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
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
    for tag_name in ['script', 'style', 'nav', 'footer', 'header', 'aside', 'table', 'noscript', 'iframe']:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    
    # Remove HTML comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

def remove_links(soup: BeautifulSoup) -> None:
    """Remove all anchor tags and their contents from the document."""
    for anchor in soup.find_all('a'):
        anchor.decompose()

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

def convert_lists(soup: BeautifulSoup) -> None:
    """Convert list items to markdown format."""
    # Handle unordered lists
    for ul in soup.find_all('ul'):
        for li in ul.find_all('li', recursive=False):
            text = li.get_text(strip=True)
            if text:
                li.replace_with(f"\n- {text}")
    
    # Handle ordered lists
    for ol in soup.find_all('ol'):
        for idx, li in enumerate(ol.find_all('li', recursive=False), start=1):
            text = li.get_text(strip=True)
            if text:
                li.replace_with(f"\n{idx}. {text}")

def add_block_spacing(soup: BeautifulSoup) -> None:
    """Add spacing markers for block-level elements."""
    block_tags = ['p', 'div', 'section', 'article', 'blockquote', 'pre']
    
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

def html_to_markdown(html_content: str) -> str:
    """Convert HTML content to clean markdown text."""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Step 1: Remove non-content elements
    remove_non_content_elements(soup)
    
    # Step 2: Remove all links
    remove_links(soup)
    
    # Step 3: Convert headings to markdown
    convert_headings(soup)
    
    # Step 4: Convert lists to markdown
    convert_lists(soup)
    
    # Step 5: Add spacing for block elements
    add_block_spacing(soup)
    
    # Step 6: Extract text and normalize whitespace
    text = soup.get_text()
    text = normalize_whitespace(text)
    
    # Step 7: Add conversion notice at top
    notice = "> [This file is converted from HTML. Links have been removed.]\n\n"
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