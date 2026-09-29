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
Wayback Machine / Archive.org Wiki Importer for Agora Bridge.

Crawls archived wiki snapshots from Archive.org, extracts page content,
converts HTML markup into Markdown (preserving [[wikilinks]]), and saves .md subnode files.
"""

import argparse
import json
import logging
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
L = logging.getLogger("import_wayback")

def sanitize_filename(name: str) -> str:
    name = re.sub(r'[/\\:*?"<>|]', '-', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name or "index"

def html_to_markdown(html_content: str, domain: str) -> str:
    """Converts wiki page HTML into Markdown, mapping internal links to [[wikilinks]]."""
    if not html_content:
        return ""

    # Remove script, style, and navigation headers/footers
    text = re.sub(r'<script.*?>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<nav.*?>.*?</nav>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<header.*?>.*?</header>', '', text, flags=re.DOTALL | re.IGNORECASE)

    # Convert headings
    for i in range(6, 0, -1):
        hashes = "#" * i
        text = re.sub(rf'<h{i}[^>]*>(.*?)</h{i}>', rf'\n\n{hashes} \1\n\n', text, flags=re.DOTALL | re.IGNORECASE)

    # Convert code blocks
    text = re.sub(r'<pre[^>]*>(.*?)</pre>', r'\n```\n\1\n```\n', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', text, flags=re.DOTALL | re.IGNORECASE)

    # Convert bold & italic
    text = re.sub(r'<(strong|b)[^>]*>(.*?)</\1>', r'**\2**', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<(em|i)[^>]*>(.*?)</\1>', r'*\2*', text, flags=re.DOTALL | re.IGNORECASE)

    # Convert internal wiki links <a href="...">label</a>
    def replace_link(match):
        href = match.group(1).strip()
        label = re.sub(r'<[^>]+>', '', match.group(2)).strip()
        
        # Check if internal wiki link
        if href.startswith("/") or domain in href or "doku.php" in href or "index.php" in href:
            # extract slug
            slug = href.split("?")[-1].replace("id=", "").split("/")[-1]
            slug = urllib.parse.unquote(slug).strip()
            if not slug or slug.endswith((".png", ".jpg", ".css", ".js")):
                return label
            if label.lower() == slug.lower():
                return f"[[{slug}]]"
            return f"[[{slug}|{label}]]" if label else f"[[{slug}]]"
        elif href.startswith("http"):
            return f"[{label}]({href})" if label else href
        return label

    text = re.sub(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', replace_link, text, flags=re.DOTALL | re.IGNORECASE)

    # Paragraphs and line breaks
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<p[^>]*>(.*?)</p>', r'\n\1\n', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<li[^>]*>(.*?)</li>', r'\n* \1', text, flags=re.DOTALL | re.IGNORECASE)

    # Strip remaining HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Clean multiple spaces and blank lines
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    return text.strip()

def discover_pages_via_cdx(target: str, limit: int, ctx: ssl.SSLContext) -> list:
    """Queries Wayback Machine CDX API for snapshots under domain/url with HTTPS and HTTP fallback."""
    L.info(f"Querying Wayback CDX API for: {target}")
    query = target.replace("https://", "").replace("http://", "").rstrip("/*")
    domain = query.split("/")[0]

    cdx_urls = [
        f"https://web.archive.org/cdx/search/cdx?url={query}/*&output=json&filter=statuscode:200&filter=mimetype:text/html&fl=original,timestamp&limit={limit*3}",
        f"http://web.archive.org/cdx/search/cdx?url={query}/*&output=json&filter=statuscode:200&filter=mimetype:text/html&fl=original,timestamp&limit={limit*3}"
    ]

    urls_map = {}
    success = False
    for cdx_url in cdx_urls:
        req = urllib.request.Request(cdx_url, headers={"User-Agent": "AgoraBridge/1.0"})
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for row in data[1:]:
                    orig, ts = row[0], row[1]
                    if not any(ext in orig for ext in [".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".pdf", ".json", ".txt", "do="]):
                        urls_map[orig] = ts
                success = True
                break
        except Exception as e:
            L.warning(f"CDX query failed for {cdx_url}: {e}")

    if not success:
        L.error(f"All CDX queries failed for {target}")

    # Also crawl internal links from main page snapshot if available
    main_url = f"https://{domain}/"
    if main_url in urls_map:
        main_ts = urls_map[main_url]
        for scheme in ["https", "http"]:
            wayback_main = f"{scheme}://web.archive.org/web/{main_ts}id_/{main_url}"
            try:
                m_req = urllib.request.Request(wayback_main, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(m_req, context=ctx, timeout=8) as resp:
                    main_html = resp.read().decode("utf-8", errors="ignore")
                    sub_links = re.findall(r'href=["\'](/[^"\']+)["\']', main_html)
                    for link in sub_links:
                        link_clean = link.split("?")[0].rstrip("/")
                        if link_clean and not any(ext in link_clean for ext in [".css", ".js", ".png", ".jpg", ".gif", ".ico", ".svg", "lib/"]):
                            full_orig = f"https://{domain}{link_clean}"
                            if full_orig not in urls_map:
                                urls_map[full_orig] = ""
                    break
            except Exception as e:
                L.warning(f"Failed to extract subpages from {wayback_main}: {e}")

    L.info(f"Found {len(urls_map)} unique page snapshots for {target}")
    return list(urls_map.items())[:limit]

def fetch_and_convert_page(orig_url: str, timestamp: str, domain: str, output_dir: str, ctx: ssl.SSLContext) -> bool:
    """Fetches snapshot HTML from Wayback Machine and converts to Markdown."""
    # Fast check: if file already exists from a previous run, skip network download
    slug = orig_url.split("?")[-1].replace("id=", "").rstrip("/").split("/")[-1]
    slug = urllib.parse.unquote(slug)
    if slug and slug != domain and "doku.php" not in slug and "index.php" not in slug:
        fast_filename = sanitize_filename(slug) + ".md"
        if os.path.exists(os.path.join(output_dir, fast_filename)):
            return True

    schemes = ["https", "http"]
    html = ""
    for scheme in schemes:
        if timestamp:
            wayback_url = f"{scheme}://web.archive.org/web/{timestamp}id_/{orig_url}"
        else:
            wayback_url = f"{scheme}://web.archive.org/web/2/{orig_url}"
        req = urllib.request.Request(wayback_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            if html:
                break
        except Exception as e:
            L.warning(f"Failed to fetch {wayback_url}: {e}")

    if not html:
        return False

    try:
        # Extract page title / slug
        slug = orig_url.split("?")[-1].replace("id=", "").rstrip("/").split("/")[-1]
        slug = urllib.parse.unquote(slug)
        if not slug or slug == domain or "doku.php" in slug or "index.php" in slug:
            # fallback to title tag
            m_title = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
            if m_title:
                slug = m_title.group(1).replace("[]", "").strip()
            else:
                slug = "index"

        # Extract main body container if present
        m_body = re.search(r'(<div[^>]*class="[^"]*page[^"]*"[^>]*>.*?</div>\s*<!--\s*/\s*content\s*-->|<div[^>]*id="dokuwiki__content"[^>]*>.*?</div>|<div[^>]*id="bodyContent"[^>]*>.*?</div>|<main[^>]*>.*?</main>)', html, re.DOTALL | re.IGNORECASE)
        body_html = m_body.group(1) if m_body else html

        markdown = html_to_markdown(body_html, domain)
        if not markdown or len(markdown) < 20:
            return False

        filename = sanitize_filename(slug) + ".md"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# {slug}\n\n{markdown}\n")
        L.debug(f"Saved subnode: {filename}")
        return True

    except Exception as e:
        L.error(f"Failed to convert {orig_url}: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Wayback Machine Wiki Importer for Agora Bridge")
    parser.add_argument("--domain", required=False, help="Domain to recover (e.g. wiki.idiot.io, telavivmakers.org)")
    parser.add_argument("--url", required=False, help="URL to recover (e.g. https://wiki.idiot.io)")
    parser.add_argument("--output-dir", required=True, help="Directory to save recovered markdown subnodes")
    parser.add_argument("--limit", type=int, default=300, help="Maximum number of pages to recover")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    if args.verbose:
        L.setLevel(logging.DEBUG)

    target = args.url or args.domain
    if not target:
        L.error("Either --domain or --url must be specified")
        sys.exit(1)

    domain = target.replace("https://", "").replace("http://", "").split("/")[0]

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    os.makedirs(args.output_dir, exist_ok=True)
    snapshots = discover_pages_via_cdx(target, args.limit, ctx)

    count = 0
    for orig_url, ts in snapshots:
        ok = fetch_and_convert_page(orig_url, ts, domain, args.output_dir, ctx)
        if ok is not False:
            count += 1

    L.info(f"Successfully processed {count} snapshots into {args.output_dir}")
    if count == 0:
        L.error(f"Failed to recover any snapshots for {target}")
        sys.exit(1)

if __name__ == "__main__":
    main()
