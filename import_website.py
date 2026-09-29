#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Live Website & Feed Importer for Agora Bridge.

Crawls live websites, sections, and feeds, extracts main article content,
converts HTML markup into Markdown (preserving [[wikilinks]] and resolving absolute images),
and saves clean .md subnode files for the Agora.
"""

import argparse
import logging
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from typing import List, Optional, Set, Tuple

import feedparser
import html2text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
L = logging.getLogger("import_website")

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 AgoraBridge/1.0"

SKIP_EXTENSIONS = (
    ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".pdf", ".zip", ".tar.gz", ".tgz", ".rar", ".mp3", ".mp4",
    ".wav", ".ogg", ".xml", ".json", ".txt"
)


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[/\\:*?"<>|]', '-', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name or "index"


def make_absolute_media(html_text: str, base_url: str) -> str:
    """Converts relative img src paths (quoted or unquoted) to absolute URLs."""
    def replace_src(m):
        src = m.group(1).strip()
        full = urllib.parse.urljoin(base_url, src)
        return f'src="{full}"'

    html_text = re.sub(r'src=["\']?([^\s"\'#>]+)[\"\']?', replace_src, html_text, flags=re.IGNORECASE)
    return html_text


def convert_internal_links_to_wikilinks(md_text: str, domain: str) -> str:
    """Converts internal links to Agora [[wikilinks]]."""
    def replace_link(m):
        label = m.group(1).strip()
        url = m.group(2).strip()
        parsed = urllib.parse.urlparse(url)

        if parsed.netloc == domain or (not parsed.netloc and url.startswith("/")):
            slug = parsed.path.rstrip("/").split("/")[-1]
            slug = urllib.parse.unquote(slug)
            if not slug or any(slug.lower().endswith(ext) for ext in SKIP_EXTENSIONS):
                return f"[{label}]({url})"
            if not label or label.lower() == slug.lower():
                return f"[[{slug}]]"
            return f"[[{slug}|{label}]]"
        return f"[{label}]({url})"

    # Handles optional <> brackets from html2text, with negative lookbehind to avoid altering images
    return re.sub(r'(?<!\!)\[([^\]]*)\]\((?:<)?(https?://[^\s\)>]+|/[^\s\)>]+)(?:>)?\)', replace_link, md_text)


def extract_content_and_title(html: str, page_url: str) -> Tuple[str, str]:
    """Extracts (title, clean_body_html) from an HTML page."""
    body_html = ""
    title = ""

    # 1. WordPress / CMS specific containers (dossier, post, page)
    # Skipping donation or campaign widget articles
    wp_articles = re.findall(
        r'<article[^>]*class=["\']([^"\']*(?:type-post|type-dossier|type-page|hentry)[^"\']*)["\'][^>]*>(.*?)</article>',
        html,
        re.DOTALL | re.IGNORECASE
    )
    for cls, content in wp_articles:
        if "campaign" not in cls and "donation" not in cls:
            body_html = content
            m_h1 = re.search(r'<h1[^>]*>(.*?)</h1>', content, re.DOTALL | re.IGNORECASE)
            if m_h1:
                title = re.sub(r'<[^>]+>', '', m_h1.group(1)).strip()
            break

    # 2. Stahlnow blog container (Foundation .columns with .blog_title)
    if not body_html and "blog_title" in html:
        m_bt = re.search(r'<div[^>]*class=["\'][^"\']*blog_title[^"\']*["\'][^>]*>(.*?)</div>', html, re.DOTALL | re.IGNORECASE)
        if m_bt:
            title = re.sub(r'<[^>]+>', '', m_bt.group(1)).strip()
        m_st = re.search(
            r'(<div[^>]*class=["\'][^"\']*(?:small-12 medium-7 large-7|blog_title)[^"\']*["\'][^>]*>.*?(?:</div>\s*</div>\s*</div>))',
            html,
            re.DOTALL | re.IGNORECASE
        )
        if m_st:
            body_html = m_st.group(1)

    # 3. CCCZH / HTML5 <article> inside maindiv or standalone <article>
    if not body_html:
        articles = re.findall(r'<article[^>]*>(.*?)</article>', html, re.DOTALL | re.IGNORECASE)
        for art in articles:
            if "campaign" not in art[:100] and "donation" not in art[:100] and len(art) > 150:
                body_html = art
                m_h1 = re.search(r'<h1[^>]*>(.*?)</h1>', art, re.DOTALL | re.IGNORECASE)
                if m_h1:
                    title = re.sub(r'<[^>]+>', '', m_h1.group(1)).strip()
                break

    # 4. Content div (El RIDO, DokuWiki, MediaWiki)
    if not body_html:
        m_cnt = re.search(r'<div[^>]*id=["\']content["\'][^>]*>(.*?)</div>\s*<div[^>]*id=["\']foot', html, re.DOTALL | re.IGNORECASE)
        if m_cnt:
            body_html = m_cnt.group(1)

    # 5. Generic <main> container
    if not body_html:
        m_main = re.search(r'<main[^>]*>(.*?)</main>', html, re.DOTALL | re.IGNORECASE)
        if m_main:
            body_html = m_main.group(1)

    # 6. Fallback to <body>
    if not body_html:
        m_b = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
        body_html = m_b.group(1) if m_b else html

    # If title not found yet, check h1 inside body_html or page <title>
    if not title:
        m_h1 = re.search(r'<h1[^>]*>(.*?)</h1>', body_html or html, re.DOTALL | re.IGNORECASE)
        if m_h1:
            title = re.sub(r'<[^>]+>', '', m_h1.group(1)).strip()

    if not title:
        m_t = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
        if m_t:
            t = m_t.group(1).strip()
            for sep in [' | ', ' - ', ' – ', ' — ']:
                if sep in t:
                    parts = t.split(sep)
                    t = parts[0] if len(parts[0]) > 3 else parts[-1]
            title = t

    if not title:
        slug = page_url.rstrip("/").split("/")[-1]
        title = urllib.parse.unquote(slug).replace("-", " ").replace("_", " ").title()

    # Clean scripts, styles, forms, navigation headers/footers
    body_html = re.sub(r'<(script|style|nav|form|aside)[^>]*>.*?</\1>', '', body_html, flags=re.DOTALL | re.IGNORECASE)
    # Remove navigation header tags
    body_html = re.sub(r'<header[^>]*class=["\'][^"\']*(?:navbar|nav|sticky)[^"\']*["\'][^>]*>.*?</header>', '', body_html, flags=re.DOTALL | re.IGNORECASE)

    # Ensure relative media assets are absolute
    body_html = make_absolute_media(body_html, page_url)

    return title, body_html


def html_to_markdown(html_content: str, page_url: str, domain: str, title: str) -> str:
    """Converts HTML snippet to formatted Markdown with Agora wikilinks."""
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.body_width = 0
    h.ignore_images = False
    h.protect_links = True

    md = h.handle(html_content).strip()
    md = convert_internal_links_to_wikilinks(md, domain)

    # Clean redundant blank lines
    md = re.sub(r'\n{3,}', '\n\n', md)

    # Prepend top-level heading if absent
    first_line = md.splitlines()[0] if md else ""
    if not first_line.startswith("# ") and not first_line.strip() == title:
        md = f"# {title}\n\n{md}"

    return md


def discover_child_urls(start_url: str, prefix: str, limit: int, ctx: ssl.SSLContext) -> List[str]:
    """Crawls start_url and finds all matching child page URLs, following pagination if present."""
    L.info(f"Discovering child URLs from {start_url} (prefix: {prefix})")
    discovered: Set[str] = set()
    pages_to_crawl = [start_url]
    crawled_pages: Set[str] = set()

    clean_start = start_url.rstrip("/")

    while pages_to_crawl and len(discovered) < limit:
        current_page = pages_to_crawl.pop(0)
        if current_page in crawled_pages:
            continue
        crawled_pages.add(current_page)

        try:
            req = urllib.request.Request(current_page, headers={"User-Agent": DEFAULT_USER_AGENT})
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            L.warning(f"Failed to fetch crawl page {current_page}: {e}")
            continue

        links = re.findall(r'href=["\']?([^\s"\'#>]+)', html)
        for link in links:
            full_url = urllib.parse.urljoin(current_page, link)
            clean_url = full_url.split("?")[0].rstrip("/")

            # Check if asset or feed
            if any(clean_url.lower().endswith(ext) for ext in SKIP_EXTENSIONS):
                continue
            if clean_url.endswith("/feed"):
                continue

            # Check if pagination link (e.g. /news/page/2/) to queue for more crawling
            if re.search(r'/page/\d+/?$', clean_url) and clean_url.startswith(prefix.rstrip("/")):
                if clean_url not in crawled_pages and clean_url not in pages_to_crawl and len(crawled_pages) < 5:
                    pages_to_crawl.append(clean_url)
                continue

            # Check if matching child article
            if clean_url.startswith(prefix.rstrip("/")) and clean_url != clean_start:
                discovered.add(clean_url)
                if len(discovered) >= limit:
                    break

        time.sleep(0.15)

    L.info(f"Discovered {len(discovered)} matching child URLs under {prefix}")
    return sorted(list(discovered))[:limit]


def discover_feed_entries(feed_url: str, limit: int, ctx: ssl.SSLContext) -> List[Tuple[str, str, str]]:
    """Fetches an RSS/Atom feed and returns a list of (url, title, raw_content)."""
    L.info(f"Fetching feed: {feed_url}")
    try:
        req = urllib.request.Request(feed_url, headers={"User-Agent": DEFAULT_USER_AGENT})
        with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
            raw = resp.read()
        parsed = feedparser.parse(raw)
        entries = []
        for e in parsed.entries[:limit]:
            link = e.get("link", "")
            title = e.get("title", "")
            content = ""
            if "content" in e and len(e.content) > 0:
                content = e.content[0].get("value", "")
            elif "summary" in e:
                content = e.get("summary", "")
            if link:
                entries.append((link, title, content))
        L.info(f"Discovered {len(entries)} entries from feed {feed_url}")
        return entries
    except Exception as e:
        L.error(f"Failed to parse feed {feed_url}: {e}")
        return []


def fetch_and_save_page(
    url: str,
    output_dir: str,
    ctx: ssl.SSLContext,
    domain: str,
    fallback_title: Optional[str] = None,
    feed_content: Optional[str] = None,
    force: bool = False
) -> bool:
    """Fetches a page, converts to Markdown, and writes .md file."""
    # Determine filename from URL slug early to avoid redundant network requests
    slug = url.rstrip("/").split("/")[-1]
    slug = urllib.parse.unquote(slug)
    if not slug or slug == domain:
        slug = sanitize_filename(fallback_title or "index")
    else:
        slug = sanitize_filename(slug)

    filename = f"{slug}.md"
    filepath = os.path.join(output_dir, filename)

    if os.path.exists(filepath) and not force:
        L.debug(f"Skipping already existing subnode: {filename}")
        return True

    try:
        html = ""
        # Fetch page HTML
        req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
        with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        title, body_html = extract_content_and_title(html, url)
        if fallback_title and (not title or len(title) < 3):
            title = fallback_title

        # If body_html is thin but we have feed_content, use feed_content
        if len(body_html) < 150 and feed_content and len(feed_content) > len(body_html):
            body_html = feed_content

        if not body_html or len(body_html) < 50:
            L.warning(f"Skipping {url}: content too short ({len(body_html)} bytes)")
            return False

        markdown = html_to_markdown(body_html, url, domain, title)

        # Append source metadata
        markdown = f"{markdown}\n\n---\n- Source: <{url}>\n"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(markdown)

        L.debug(f"Saved: {filename} ({len(markdown)} bytes)")
        return True

    except Exception as e:
        L.warning(f"Error processing {url}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Live Website & Feed Importer for Agora Bridge")
    parser.add_argument("--url", required=True, help="Website URL to crawl (section URL or main page)")
    parser.add_argument("--output-dir", required=True, help="Directory to save recovered markdown subnodes")
    parser.add_argument("--prefix", help="URL prefix filter for child links (defaults to --url or derived from web pattern)")
    parser.add_argument("--web-pattern", help="Web pattern from sources.yaml (e.g. https://.../{slug})")
    parser.add_argument("--feed", help="Optional RSS/Atom feed URL to import")
    parser.add_argument("--limit", type=int, default=200, help="Maximum number of pages to import")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    if args.verbose:
        L.setLevel(logging.DEBUG)

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    parsed_url = urllib.parse.urlparse(args.url)
    domain = parsed_url.netloc

    os.makedirs(args.output_dir, exist_ok=True)

    # Determine prefix
    prefix = args.prefix
    if not prefix and args.web_pattern:
        # Strip Wayback prefix if user had it configured
        clean_web = re.sub(r'^https?://web\.archive\.org/web/\*/', '', args.web_pattern)
        if "{slug}" in clean_web:
            prefix = clean_web.split("{slug}")[0]

    if not prefix:
        prefix = args.url

    urls_to_process: List[Tuple[str, Optional[str], Optional[str]]] = []

    # If feed is specified, use feed entries
    if args.feed:
        feed_entries = discover_feed_entries(args.feed, args.limit, ctx)
        for link, title, content in feed_entries:
            urls_to_process.append((link, title, content))

    # Also discover child URLs from the page
    child_urls = discover_child_urls(args.url, prefix, args.limit, ctx)
    existing_links = {u for u, _, _ in urls_to_process}
    for u in child_urls:
        if u not in existing_links:
            urls_to_process.append((u, None, None))
            existing_links.add(u)

    # If no child URLs found and no feed, attempt to import the single start URL
    if not urls_to_process:
        urls_to_process.append((args.url, None, None))

    L.info(f"Importing {len(urls_to_process)} pages into {args.output_dir}...")
    success_count = 0

    for url, title, feed_content in urls_to_process:
        ok = fetch_and_save_page(url, args.output_dir, ctx, domain, fallback_title=title, feed_content=feed_content)
        if ok:
            success_count += 1
        time.sleep(0.15)

    L.info(f"Finished: successfully imported {success_count} pages into {args.output_dir}")

    if success_count == 0:
        L.error(f"Failed to import any pages for {args.url}")
        sys.exit(1)


if __name__ == "__main__":
    main()
