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
DokuWiki Importer for Agora Bridge.

Enumerates pages from a DokuWiki instance via its `?do=index` namespace tree,
fetches clean page bodies via `?do=export_xhtmlbody`, converts HTML to Agora
Markdown (preserving internal [[wikilinks]], tags, and absolute media/file URLs),
and saves .md subnode files organized by namespace.
"""

import argparse
import calendar
import datetime
import html as html_lib
import json
import logging
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from typing import Dict, List, Optional, Set, Tuple

import feedparser
import html2text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
L = logging.getLogger("import_dokuwiki")

DEFAULT_USER_AGENT = "AgoraBridge/1.0 (+https://anagora.org/agora-bridge)"
STATE_FILENAME = ".dokuwiki_sync_state.json"

# Stock DokuWiki system/boilerplate pages skipped by default.
DEFAULT_SKIP_PAGES: Set[str] = {
    "sidebar",
    "playground:playground",
    "wiki:dokuwiki",
    "wiki:syntax",
    "wiki:welcome",
}


def sanitize_filename(name: str) -> str:
    """Sanitizes a page title for use as a filesystem filename."""
    name = html_lib.unescape(name)
    name = re.sub(r'[/\\:*?"<>|]', "-", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name or "index"


def normalize_doku_url(url: str) -> str:
    """Normalizes a DokuWiki base URL (e.g. https://example.org/wiki/doku.php)."""
    url = url.strip()
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.rstrip("/")
    if not path.endswith("doku.php"):
        path = f"{path}/doku.php" if path else "/doku.php"
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def fetch_text(url: str, ctx: ssl.SSLContext, timeout: int = 20, retries: int = 2) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < retries:
                retry_after = e.headers.get("Retry-After")
                wait_s = 5.0
                if retry_after and retry_after.isdigit():
                    wait_s = min(float(retry_after), 60.0)
                else:
                    wait_s = 5.0 * (attempt + 1)
                L.warning(f"HTTP {e.code} from {url}; backing off {wait_s}s...")
                time.sleep(wait_s)
                continue
            raise


def discover_pages(
    base_url: str,
    ctx: ssl.SSLContext,
    delay: float = 0.1,
    include_defaults: bool = False,
) -> Tuple[Dict[str, str], str]:
    """
    Recursively traverses DokuWiki's `?do=index` namespace tree.

    Returns:
        (pages, url_style) where:
        - pages maps DokuWiki page_id (e.g. 'elektronik:ctrl_m') -> display title
        - url_style is 'path' (doku.php/<id>) or 'query' (doku.php?id=<id>)
    """
    L.info(f"Discovering DokuWiki pages from {base_url}?do=index")
    visited_ns: Set[str] = set()
    queue: deque[str] = deque([""])
    pages: Dict[str, str] = {}
    url_style = "query"
    detected_style = False

    while queue:
        ns = queue.popleft()
        if ns in visited_ns:
            continue
        visited_ns.add(ns)

        index_url = (
            f"{base_url}?do=index"
            if not ns
            else f"{base_url}?do=index&idx={urllib.parse.quote(ns)}"
        )
        try:
            page_html = fetch_text(index_url, ctx)
        except Exception as e:
            L.warning(f"Failed to fetch index for namespace '{ns}': {e}")
            continue

        # Scope parsing to #index__tree so sidebar links are ignored
        start_idx = page_html.find('id="index__tree"')
        if start_idx != -1:
            end_idx = page_html.find("<!-- wikipage stop -->", start_idx)
            tree_html = page_html[start_idx:end_idx] if end_idx != -1 else page_html[start_idx:]
        else:
            tree_html = page_html

        # Discover sub-namespaces
        for m_ns in re.finditer(r"<a\b[^>]*class=[\"'][^\"']*\bidx_dir\b[^\"']*[\"'][^>]*>", tree_html, re.IGNORECASE):
            tag = m_ns.group(0)
            m_href = re.search(r'href=["\']([^"\']+)["\']', tag, re.IGNORECASE)
            if not m_href:
                continue
            href = html_lib.unescape(m_href.group(1))
            parsed_href = urllib.parse.urlparse(href)
            qs = urllib.parse.parse_qs(parsed_href.query)
            if "idx" in qs and qs["idx"]:
                sub_ns = qs["idx"][0]
                if sub_ns not in visited_ns:
                    queue.append(sub_ns)

        # Discover pages
        for m_a in re.finditer(
            r"<a\b([^>]*class=[\"'][^\"']*\bwikilink1\b[^\"']*[\"'][^>]*)>(.*?)</a>",
            tree_html,
            re.DOTALL | re.IGNORECASE,
        ):
            attrs, inner = m_a.group(1), m_a.group(2)
            m_id = re.search(r'data-wiki-id=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            if not m_id:
                m_id = re.search(r'title=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            if not m_id:
                continue

            page_id = html_lib.unescape(m_id.group(1)).strip()
            if not page_id:
                continue

            if not detected_style:
                m_href = re.search(r'href=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
                if m_href and "doku.php/" in m_href.group(1):
                    url_style = "path"
                detected_style = True

            if not include_defaults and page_id.lower() in DEFAULT_SKIP_PAGES:
                continue

            title = html_lib.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
            pages[page_id] = title or page_id.split(":")[-1]

        if delay > 0:
            time.sleep(delay)

    L.info(f"Discovered {len(pages)} pages across {len(visited_ns)} namespaces (url_style={url_style})")
    return pages, url_style


def canonical_page_url(base_url: str, page_id: str, url_style: str) -> str:
    if url_style == "path":
        return f"{base_url}/{urllib.parse.quote(page_id, safe=':')}"
    return f"{base_url}?id={urllib.parse.quote(page_id, safe=':')}"


def build_target_map(pages: Dict[str, str]) -> Dict[str, str]:
    """
    Maps each DokuWiki page_id -> Agora wikilink target (sanitized title).
    Also handles collisions within the same namespace directory.
    """
    target_map: Dict[str, str] = {}
    used_paths: Dict[Tuple[str, str], str] = {}

    for page_id in sorted(pages.keys()):
        title = pages[page_id]
        parts = page_id.split(":")
        ns_dir = os.path.join(*parts[:-1]) if len(parts) > 1 else ""
        slug = parts[-1]
        clean_title = sanitize_filename(title)

        key = (ns_dir.lower(), clean_title.lower())
        if key in used_paths:
            clean_title = sanitize_filename(f"{title} ({slug})")
            key = (ns_dir.lower(), clean_title.lower())

        used_paths[key] = page_id
        target_map[page_id] = clean_title

    return target_map


def preprocess_dokuwiki_html(
    body_html: str,
    base_url: str,
    page_url: str,
    target_map: Dict[str, str],
) -> Tuple[str, List[str], Optional[str]]:
    """
    Cleans DokuWiki export_xhtmlbody HTML before markdown conversion.

    Returns:
        (cleaned_html, tags, extracted_h1_title)
    """
    # Strip HTML comments (including DokuWiki <!-- EDIT{...} --> markers)
    cleaned = re.sub(r"<!--.*?-->", "", body_html, flags=re.DOTALL)
    # Strip scripts, styles, and TOC blocks
    cleaned = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'<div[^>]*id=["\']dw__toc["\'][^>]*>.*?</div>\s*</div>', "", cleaned, flags=re.DOTALL | re.IGNORECASE)

    # Extract first H1 title if present
    h1_title: Optional[str] = None
    m_h1 = re.search(r"<h1[^>]*>(.*?)</h1>", cleaned, re.DOTALL | re.IGNORECASE)
    if m_h1:
        h1_title = html_lib.unescape(re.sub(r"<[^>]+>", "", m_h1.group(1))).strip() or None

    # Extract DokuWiki tag plugin blocks (<div class="tags">...</div>)
    tags: List[str] = []

    def extract_tags(m):
        block = m.group(0)
        for m_tag in re.finditer(r"<a\b[^>]*rel=[\"']tag[\"'][^>]*>(.*?)</a>", block, re.DOTALL | re.IGNORECASE):
            t = html_lib.unescape(re.sub(r"<[^>]+>", "", m_tag.group(1))).strip()
            if t and t not in tags:
                tags.append(t)
        return ""

    cleaned = re.sub(
        r'<div[^>]*class=["\'][^"\']*\btags\b[^"\']*["\'][^>]*>.*?</div>',
        extract_tags,
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Unwrap DokuWiki detail.php image links: <a href="...detail.php..." class="media"><img ...></a> -> <img ...>
    cleaned = re.sub(
        r'<a\b[^>]*href=["\'][^"\']*detail\.php[^"\']*["\'][^>]*>\s*(<img\b[^>]*>)\s*</a>',
        r"\1",
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Convert internal DokuWiki links to a sentinel dokuwiki:// scheme before html2text
    parsed_base = urllib.parse.urlparse(base_url)
    base_path = parsed_base.path  # e.g. /wiki/doku.php

    def rewrite_anchor(m):
        attrs = m.group(1)
        inner = m.group(2)

        # Check if this is an internal wikilink (wikilink1 / wikilink2) or links to doku.php
        m_cls = re.search(r'class=["\']([^"\']*)["\']', attrs, re.IGNORECASE)
        cls = m_cls.group(1) if m_cls else ""
        m_href = re.search(r'href=["\']([^"\']*)["\']', attrs, re.IGNORECASE)
        href = html_lib.unescape(m_href.group(1)) if m_href else ""

        # Skip tag links that might appear outside .tags div
        if 'rel="tag"' in attrs or "rel='tag'" in attrs or "do=showtag" in href:
            tag_text = html_lib.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
            if tag_text:
                return f'<a href="dokuwiki://{urllib.parse.quote(tag_text)}">{inner}</a>'

        wiki_id = None
        if "wikilink1" in cls or "wikilink2" in cls:
            m_id = re.search(r'data-wiki-id=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            if not m_id:
                m_id = re.search(r'title=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            if m_id:
                wiki_id = html_lib.unescape(m_id.group(1)).strip()

        if not wiki_id and href:
            full_href = urllib.parse.urljoin(page_url, href)
            p = urllib.parse.urlparse(full_href)
            if p.netloc == parsed_base.netloc and p.path.startswith(base_path):
                qs = urllib.parse.parse_qs(p.query)
                if "do" not in qs:
                    if p.path.startswith(base_path + "/"):
                        wiki_id = urllib.parse.unquote(p.path[len(base_path) + 1 :]).strip("/")
                    elif "id" in qs and qs["id"]:
                        wiki_id = qs["id"][0]

        if wiki_id and not re.search(r"<img\b", inner, re.IGNORECASE):
            # Strip anchor fragment if present
            wiki_id_clean = wiki_id.split("#")[0]
            target = target_map.get(wiki_id_clean)
            if not target:
                # Fallback: humanize last segment of wiki_id
                target = wiki_id_clean.split(":")[-1].replace("_", " ")
            encoded = urllib.parse.quote(target, safe="")
            return f'<a href="dokuwiki://{encoded}">{inner}</a>'

        # Otherwise, ensure relative hrefs (e.g. fetch.php PDFs) are absolute
        if href and not href.startswith(("http://", "https://", "mailto:", "#", "dokuwiki://")):
            abs_href = urllib.parse.urljoin(page_url, href)
            new_attrs = re.sub(
                r'href=["\'][^"\']*["\']',
                f'href="{abs_href}"',
                attrs,
                count=1,
                flags=re.IGNORECASE,
            )
            return f"<a{new_attrs}>{inner}</a>"

        return m.group(0)

    cleaned = re.sub(r"<a\b([^>]*)>(.*?)</a>", rewrite_anchor, cleaned, flags=re.DOTALL | re.IGNORECASE)

    # Make all img src attributes absolute
    def replace_img_src(m):
        src = html_lib.unescape(m.group(1).strip())
        if src.startswith("data:"):
            return m.group(0)
        full = urllib.parse.urljoin(page_url, src)
        return f'src="{full}"'

    cleaned = re.sub(r'src=["\']([^"\']+)["\']', replace_img_src, cleaned, flags=re.IGNORECASE)

    return cleaned, tags, h1_title


def dokuwiki_html_to_markdown(
    body_html: str,
    base_url: str,
    page_url: str,
    title: str,
    target_map: Dict[str, str],
) -> str:
    """Converts DokuWiki export_xhtmlbody HTML to clean Agora Markdown."""
    cleaned_html, tags, h1_title = preprocess_dokuwiki_html(body_html, base_url, page_url, target_map)
    effective_title = h1_title or title

    h = html2text.HTML2Text()
    h.ignore_links = False
    h.body_width = 0
    h.ignore_images = False
    h.protect_links = True
    h.unicode_snob = True

    md = h.handle(cleaned_html).strip()

    # Convert sentinel dokuwiki:// links into Agora [[wikilinks]]
    def replace_doku_link(m):
        label = m.group(1).strip()
        target = urllib.parse.unquote(m.group(2)).strip()
        if not target:
            return label
        if not label or label.lower() == target.lower():
            return f"[[{target}]]"
        return f"[[{target}|{label}]]"

    md = re.sub(
        r"(?<!\!)\[([^\]]*)\]\((?:<)?dokuwiki://([^\s\)>]+)(?:>)?\)",
        replace_doku_link,
        md,
    )

    # Collapse excessive blank lines
    md = re.sub(r"\n{3,}", "\n\n", md).strip()

    # Ensure top-level heading is present
    first_line = md.splitlines()[0] if md else ""
    if not first_line.startswith("# ") and effective_title:
        md = f"# {effective_title}\n\n{md}" if md else f"# {effective_title}"

    # Append tags as Agora wikilinks
    if tags:
        tag_links = ", ".join(f"[[{t}]]" for t in tags)
        md = f"{md}\n\nTags: {tag_links}"

    # Append canonical source link
    md = f"{md}\n\n---\n- Source: <{page_url}>\n"
    return md


def _load_sync_state(output_dir: str) -> dict:
    state_path = os.path.join(output_dir, STATE_FILENAME)
    if not os.path.exists(state_path):
        return {}
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        L.warning(f"Could not read sync state {state_path}: {e}")
        return {}


def _save_sync_state(output_dir: str, state: dict):
    state_path = os.path.join(output_dir, STATE_FILENAME)
    try:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        L.warning(f"Could not write sync state {state_path}: {e}")


def _doku_feed_url(base_url: str) -> str:
    """Derives DokuWiki's feed.php URL from normalized doku.php base_url."""
    if base_url.endswith("/doku.php"):
        return base_url[:-len("/doku.php")] + "/feed.php?type=rss2&num=50"
    return base_url.rsplit("/", 1)[0] + "/feed.php?type=rss2&num=50"


def _extract_page_id_from_link(link: str, base_url: str) -> Optional[str]:
    """Extracts a DokuWiki page_id from a feed entry link."""
    parsed = urllib.parse.urlparse(link)
    qs = urllib.parse.parse_qs(parsed.query)
    if "id" in qs and qs["id"]:
        return qs["id"][0].strip(":").lower()
    base_path = urllib.parse.urlparse(base_url).path.rstrip("/")
    if parsed.path.startswith(base_path + "/"):
        raw_id = urllib.parse.unquote(parsed.path[len(base_path) + 1:]).strip("/")
        if raw_id:
            return raw_id.replace("/", ":").strip(":").lower()
    return None


def _check_feed_changes(
    base_url: str,
    since_epoch: float,
    ctx: ssl.SSLContext,
    include_defaults: bool = False,
) -> Optional[List[str]]:
    """
    Fetches DokuWiki's feed.php and returns a list of page_ids modified since `since_epoch`.
    Returns None if feed.php is unavailable or unparseable (signaling fallback to full sync).
    """
    feed_url = _doku_feed_url(base_url)
    try:
        xml_text = fetch_text(feed_url, ctx)
    except Exception as e:
        L.warning(f"Could not fetch DokuWiki feed {feed_url}: {e}")
        return None

    parsed_feed = feedparser.parse(xml_text)
    if getattr(parsed_feed, "bozo", False) and not parsed_feed.entries:
        L.warning(f"Failed to parse DokuWiki feed {feed_url}")
        return None

    changed_ids: List[str] = []
    seen: Set[str] = set()
    # 60s overlap buffer to protect against minor clock skew
    cutoff = since_epoch - 60.0

    for entry in parsed_feed.entries:
        ts_struct = entry.get("updated_parsed") or entry.get("published_parsed")
        if ts_struct:
            entry_epoch = float(calendar.timegm(ts_struct))
            if entry_epoch < cutoff:
                continue
        link = entry.get("link", "")
        pid = _extract_page_id_from_link(link, base_url)
        if not pid:
            continue
        if not include_defaults and pid in DEFAULT_SKIP_PAGES:
            continue
        if pid not in seen:
            seen.add(pid)
            changed_ids.append(pid)

    return changed_ids


def _export_single_page(
    page_id: str,
    title: str,
    base_url: str,
    url_style: str,
    target_map: Dict[str, str],
    output_dir: str,
    ctx: ssl.SSLContext,
) -> Tuple[bool, bool]:
    """Exports one DokuWiki page. Returns (ok, written)."""
    page_url = canonical_page_url(base_url, page_id, url_style)
    export_url = f"{base_url}?id={urllib.parse.quote(page_id, safe=':')}&do=export_xhtmlbody"

    try:
        body_html = fetch_text(export_url, ctx)
        if not body_html or len(body_html.strip()) < 20:
            L.warning(f"Skipping {page_id}: empty export_xhtmlbody response")
            return False, False

        markdown = dokuwiki_html_to_markdown(body_html, base_url, page_url, title, target_map)

        parts = page_id.split(":")
        ns_dir = os.path.join(output_dir, *parts[:-1]) if len(parts) > 1 else output_dir
        os.makedirs(ns_dir, exist_ok=True)

        target_name = target_map.get(page_id) or sanitize_filename(title or parts[-1])
        filename = f"{target_name}.md"
        filepath = os.path.join(ns_dir, filename)

        existing = None
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                existing = f.read()

        if existing != markdown:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(markdown)
            L.debug(f"Wrote {os.path.relpath(filepath, output_dir)} ({len(markdown)} bytes)")
            return True, True
        else:
            L.debug(f"Unchanged {os.path.relpath(filepath, output_dir)}")
            return True, False
    except Exception as e:
        L.warning(f"Error importing {page_id} ({export_url}): {e}")
        return False, False


def import_dokuwiki(
    url: str,
    output_dir: str,
    limit: int = 1000,
    delay: float = 0.5,
    include_defaults: bool = False,
    full: bool = False,
) -> int:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    base_url = normalize_doku_url(url)
    os.makedirs(output_dir, exist_ok=True)
    sync_started_epoch = time.time()
    state = _load_sync_state(output_dir)

    # Incremental sync via feed.php after initial import
    if not full and state.get("last_sync_epoch") and state.get("target_map"):
        changed_ids = _check_feed_changes(
            base_url,
            float(state["last_sync_epoch"]),
            ctx,
            include_defaults=include_defaults,
        )
        if changed_ids is not None:
            if not changed_ids:
                L.info(f"No DokuWiki changes in feed.php since last sync for {base_url} (1 request).")
                state["last_sync_epoch"] = sync_started_epoch
                _save_sync_state(output_dir, state)
                return len(state["target_map"])

            L.info(f"Found {len(changed_ids)} changed DokuWiki pages via feed.php; updating incrementally.")
            target_map = dict(state["target_map"])
            pages_titles = dict(state.get("pages", {}))
            url_style = state.get("url_style", "path")
            written_count = 0
            for pid in changed_ids[:limit]:
                title = pages_titles.get(pid, pid.split(":")[-1])
                if pid not in target_map:
                    target_map[pid] = sanitize_filename(title)
                ok, written = _export_single_page(pid, title, base_url, url_style, target_map, output_dir, ctx)
                if written:
                    written_count += 1
                if delay > 0:
                    time.sleep(delay)

            state["last_sync_epoch"] = sync_started_epoch
            state["target_map"] = target_map
            _save_sync_state(output_dir, state)
            L.info(f"Incremental DokuWiki sync complete: {len(changed_ids)} checked, {written_count} updated.")
            return len(target_map)

    pages, url_style = discover_pages(base_url, ctx, delay=delay, include_defaults=include_defaults)
    if not pages:
        L.error(f"No pages discovered at {base_url}")
        return 0

    target_map = build_target_map(pages)
    page_ids = sorted(pages.keys())[:limit]

    L.info(f"Importing {len(page_ids)} DokuWiki pages into {output_dir} (delay={delay}s)...")
    success_count = 0
    written_count = 0

    for page_id in page_ids:
        title = pages[page_id]
        ok, written = _export_single_page(page_id, title, base_url, url_style, target_map, output_dir, ctx)
        if ok:
            success_count += 1
        if written:
            written_count += 1

        if delay > 0:
            time.sleep(delay)

    if success_count > 0:
        _save_sync_state(output_dir, {
            "last_sync_epoch": sync_started_epoch,
            "base_url": base_url,
            "url_style": url_style,
            "target_map": target_map,
            "pages": pages,
        })

    L.info(
        f"Finished: {success_count}/{len(page_ids)} pages processed "
        f"({written_count} written/updated) into {output_dir}"
    )
    return success_count


def main():
    parser = argparse.ArgumentParser(description="DokuWiki Importer for Agora Bridge")
    parser.add_argument(
        "--url",
        required=True,
        help="DokuWiki URL (e.g. https://brain4free.org/wiki/doku.php/)",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory to save converted markdown subnodes",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Maximum number of pages to import (default: 1000)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Polite delay in seconds between HTTP requests (default: 0.5)",
    )
    parser.add_argument(
        "--include-defaults",
        action="store_true",
        help="Include default DokuWiki pages (sidebar, playground, wiki:syntax, etc.)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Force a full re-import instead of incremental feed.php sync",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()
    if args.verbose:
        L.setLevel(logging.DEBUG)

    count = import_dokuwiki(
        url=args.url,
        output_dir=args.output_dir,
        limit=args.limit,
        delay=args.delay,
        include_defaults=args.include_defaults,
        full=args.full,
    )
    if count == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
