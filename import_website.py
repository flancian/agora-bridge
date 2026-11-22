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
import calendar
from datetime import datetime, timezone
import logging
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
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


def _parse_iso_timestamp(value: Optional[str]) -> Optional[float]:
    """Parses an ISO 8601 date/datetime string into a UTC Unix timestamp."""
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
            dt = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def _matches_prefix(url: str, prefix: Optional[str]) -> bool:
    """Checks whether url falls under prefix, excluding the exact prefix index itself."""
    if not prefix:
        return True
    clean_prefix = prefix.rstrip("/")
    clean_url = url.split("?")[0].rstrip("/")
    return clean_url.startswith(clean_prefix) and clean_url != clean_prefix


def discover_alternate_feeds(html: str, base_url: str) -> List[str]:
    """Finds RSS/Atom <link rel="alternate"> URLs declared in an HTML document."""
    feeds: List[str] = []
    for tag in re.findall(r'<link\b[^>]*>', html, flags=re.IGNORECASE):
        rel_m = re.search(r'\brel=["\']?([^"\'\s>]+)', tag, flags=re.IGNORECASE)
        type_m = re.search(r'\btype=["\']?([^"\'\s>]+)', tag, flags=re.IGNORECASE)
        href_m = re.search(r'\bhref=["\']([^"\']+)["\']', tag, flags=re.IGNORECASE)
        if not (rel_m and type_m and href_m):
            continue
        if "alternate" not in rel_m.group(1).lower():
            continue
        mime = type_m.group(1).lower()
        if mime in ("application/rss+xml", "application/atom+xml", "application/feed+json"):
            full_url = urllib.parse.urljoin(base_url, href_m.group(1).strip())
            if full_url not in feeds:
                feeds.append(full_url)
    return feeds


def discover_sitemap_urls(
    sitemap_url: str,
    prefix: Optional[str],
    limit: int,
    ctx: ssl.SSLContext,
    max_depth: int = 2,
    _seen_sitemaps: Optional[Set[str]] = None,
) -> List[Tuple[str, Optional[float]]]:
    """Parses a sitemap.xml or sitemapindex and returns (url, lastmod_epoch) pairs."""
    if max_depth < 0:
        return []
    seen = _seen_sitemaps if _seen_sitemaps is not None else set()
    if sitemap_url in seen:
        return []
    seen.add(sitemap_url)

    L.info(f"Fetching sitemap: {sitemap_url}")
    try:
        req = urllib.request.Request(sitemap_url, headers={"User-Agent": DEFAULT_USER_AGENT})
        with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
            raw = resp.read()
        return parse_sitemap_xml(raw, prefix=prefix, limit=limit, ctx=ctx, max_depth=max_depth, seen_sitemaps=seen)
    except Exception as e:
        L.error(f"Failed to fetch sitemap {sitemap_url}: {e}")
        return []


def parse_sitemap_xml(
    raw_xml: bytes,
    prefix: Optional[str],
    limit: int,
    ctx: Optional[ssl.SSLContext] = None,
    max_depth: int = 2,
    seen_sitemaps: Optional[Set[str]] = None,
) -> List[Tuple[str, Optional[float]]]:
    """Parses sitemap XML bytes into (url, lastmod_epoch) pairs, recursing into sitemapindex."""
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as e:
        L.error(f"Invalid sitemap XML: {e}")
        return []

    root_name = root.tag.rsplit("}", 1)[-1].lower()
    results: List[Tuple[str, Optional[float]]] = []
    seen_urls: Set[str] = set()

    if root_name == "sitemapindex" and max_depth > 0 and ctx is not None:
        for child in root:
            if child.tag.rsplit("}", 1)[-1].lower() != "sitemap":
                continue
            loc = None
            for sub in child:
                if sub.tag.rsplit("}", 1)[-1].lower() == "loc" and sub.text:
                    loc = sub.text.strip()
                    break
            if loc and len(results) < limit:
                nested = discover_sitemap_urls(
                    loc, prefix=prefix, limit=limit - len(results), ctx=ctx,
                    max_depth=max_depth - 1, _seen_sitemaps=seen_sitemaps,
                )
                for u, mtime in nested:
                    if u not in seen_urls:
                        seen_urls.add(u)
                        results.append((u, mtime))
        return results[:limit]

    for child in root:
        if child.tag.rsplit("}", 1)[-1].lower() != "url":
            continue
        loc = None
        lastmod = None
        for sub in child:
            tag = sub.tag.rsplit("}", 1)[-1].lower()
            if tag == "loc" and sub.text:
                loc = sub.text.strip()
            elif tag == "lastmod" and sub.text:
                lastmod = _parse_iso_timestamp(sub.text)
        if not loc:
            continue
        clean_url = loc.split("?")[0].rstrip("/")
        if any(clean_url.lower().endswith(ext) for ext in SKIP_EXTENSIONS):
            continue
        if not _matches_prefix(loc, prefix):
            continue
        if loc not in seen_urls:
            seen_urls.add(loc)
            results.append((loc, lastmod))
            if len(results) >= limit:
                break

    L.info(f"Discovered {len(results)} URLs from sitemap")
    return results


def parse_feed_bytes(raw: bytes, limit: int) -> List[Tuple[str, str, str, Optional[float]]]:
    """Parses RSS/Atom bytes into (url, title, raw_content, updated_epoch) tuples."""
    parsed = feedparser.parse(raw)
    entries: List[Tuple[str, str, str, Optional[float]]] = []
    for e in parsed.entries[:limit]:
        link = e.get("link", "")
        title = e.get("title", "")
        content = ""
        if "content" in e and len(e.content) > 0:
            content = e.content[0].get("value", "")
        elif "summary" in e:
            content = e.get("summary", "")
        ts = None
        if "published_parsed" in e:
            ts = e.get("published_parsed")
        if "updated_parsed" in e and e.get("updated_parsed"):
            ts = e.get("updated_parsed")
        updated_epoch = float(calendar.timegm(ts)) if ts else None
        if link:
            entries.append((link, title, content, updated_epoch))
    return entries


def discover_feed_entries(feed_url: str, limit: int, ctx: ssl.SSLContext) -> List[Tuple[str, str, str, Optional[float]]]:
    """Fetches an RSS/Atom feed and returns a list of (url, title, raw_content, updated_epoch)."""
    L.info(f"Fetching feed: {feed_url}")
    try:
        req = urllib.request.Request(feed_url, headers={"User-Agent": DEFAULT_USER_AGENT})
        with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
            raw = resp.read()
        entries = parse_feed_bytes(raw, limit)
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
    force: bool = False,
    remote_mtime: Optional[float] = None,
    feed_only: bool = False,
) -> bool:
    """Fetches a page (or uses substantial feed_content directly), converts to Markdown, and writes .md file."""
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
        if remote_mtime is None or remote_mtime <= os.path.getmtime(filepath) + 1:
            L.debug(f"Skipping already existing subnode: {filename}")
            return True

    try:
        body_html = ""
        title = fallback_title or ""

        # When running feed-only and the feed already provides substantial content, avoid extra HTTP fetches
        feed_plain_len = len(re.sub(r"<[^>]+>", "", feed_content or "").strip()) if feed_content else 0
        if feed_only and feed_content and feed_plain_len >= 150:
            body_html = make_absolute_media(feed_content, url)
            if not title:
                title = urllib.parse.unquote(slug).replace("-", " ").replace("_", " ").title()
        else:
            req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
            with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
                html = resp.read().decode("utf-8", errors="ignore")

            title, body_html = extract_content_and_title(html, url)
            if fallback_title and (not title or len(title) < 3):
                title = fallback_title

            # If body_html is thin but we have feed_content, use feed_content
            if len(body_html) < 150 and feed_content and len(feed_content) > len(body_html):
                body_html = make_absolute_media(feed_content, url)

        if not body_html or len(body_html) < 50:
            L.warning(f"Skipping {url}: content too short ({len(body_html)} bytes)")
            return False

        markdown = html_to_markdown(body_html, url, domain, title)

        # Append source metadata
        markdown = f"{markdown}\n\n---\n- Source: <{url}>\n"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(markdown)
        if remote_mtime is not None:
            os.utime(filepath, (remote_mtime, remote_mtime))

        L.debug(f"Saved: {filename} ({len(markdown)} bytes)")
        return True

    except Exception as e:
        L.warning(f"Error processing {url}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Live Website, Feed & Sitemap Importer for Agora Bridge")
    parser.add_argument("--url", required=True, help="Website, feed, or sitemap URL to import")
    parser.add_argument("--output-dir", required=True, help="Directory to save recovered markdown subnodes")
    parser.add_argument("--prefix", help="URL prefix filter for child/sitemap/feed links")
    parser.add_argument("--web-pattern", help="Web pattern from sources.yaml (e.g. https://.../{slug})")
    parser.add_argument("--feed", help="Optional RSS/Atom feed URL to import")
    parser.add_argument("--sitemap", help="Optional XML sitemap URL to discover pages from")
    parser.add_argument("--feed-only", action="store_true", help="Import only from --feed without HTML crawling")
    parser.add_argument("--sitemap-only", action="store_true", help="Import only from --sitemap without HTML crawling")
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

    # Explicit --prefix filters sitemap/feed/crawl; fallback web_pattern/url prefix applies only to HTML crawling
    crawl_prefix = args.prefix
    if not crawl_prefix and args.web_pattern:
        clean_web = re.sub(r'^https?://web\.archive\.org/web/\*/', '', args.web_pattern)
        if "{slug}" in clean_web:
            crawl_prefix = clean_web.split("{slug}")[0]
    if not crawl_prefix:
        crawl_prefix = args.url

    urls_to_process: List[Tuple[str, Optional[str], Optional[str], Optional[float]]] = []
    existing_links: Set[str] = set()

    # 1. RSS/Atom feed discovery (when --feed is given)
    if args.feed:
        feed_entries = discover_feed_entries(args.feed, args.limit, ctx)
        for link, title, content, updated_epoch in feed_entries:
            if args.prefix and not _matches_prefix(link, args.prefix):
                continue
            if link not in existing_links:
                urls_to_process.append((link, title, content, updated_epoch))
                existing_links.add(link)

    # 2. XML Sitemap discovery (when --sitemap is given)
    if args.sitemap:
        sitemap_entries = discover_sitemap_urls(args.sitemap, args.prefix, args.limit, ctx)
        for link, lastmod_epoch in sitemap_entries:
            if link not in existing_links:
                urls_to_process.append((link, None, None, lastmod_epoch))
                existing_links.add(link)

    # 3. HTML child URL discovery (unless --feed-only or --sitemap-only)
    if not args.feed_only and not args.sitemap_only:
        child_urls = discover_child_urls(args.url, crawl_prefix, args.limit, ctx)
        for u in child_urls:
            if u not in existing_links:
                urls_to_process.append((u, None, None, None))
                existing_links.add(u)

        # If no explicit feed/sitemap was given, try auto-discovering alternate RSS/Atom feeds on start_url
        if not args.feed and not args.sitemap and len(urls_to_process) < args.limit:
            try:
                req = urllib.request.Request(args.url, headers={"User-Agent": DEFAULT_USER_AGENT})
                with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
                    start_html = resp.read().decode("utf-8", errors="ignore")
                for alt_feed in discover_alternate_feeds(start_html, args.url)[:2]:
                    for link, title, content, updated_epoch in discover_feed_entries(alt_feed, args.limit, ctx):
                        if not _matches_prefix(link, crawl_prefix):
                            continue
                        if link not in existing_links and len(urls_to_process) < args.limit:
                            urls_to_process.append((link, title, content, updated_epoch))
                            existing_links.add(link)
            except Exception as e:
                L.debug(f"Alternate feed auto-discovery skipped for {args.url}: {e}")

    # 4. If no URLs found and not in feed/sitemap-only mode, attempt to import the single start URL
    if not urls_to_process and not args.feed_only and not args.sitemap_only:
        urls_to_process.append((args.url, None, None, None))

    L.info(f"Importing {len(urls_to_process)} pages into {args.output_dir}...")
    success_count = 0

    for url, title, feed_content, remote_mtime in urls_to_process:
        ok = fetch_and_save_page(
            url,
            args.output_dir,
            ctx,
            domain,
            fallback_title=title,
            feed_content=feed_content,
            remote_mtime=remote_mtime,
            feed_only=args.feed_only,
        )
        if ok:
            success_count += 1
        if not args.feed_only:
            time.sleep(0.15)

    L.info(f"Finished: successfully imported {success_count} pages into {args.output_dir}")

    if success_count == 0:
        L.error(f"Failed to import any pages for {args.url}")
        sys.exit(1)


if __name__ == "__main__":
    main()
