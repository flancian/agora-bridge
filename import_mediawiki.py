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
MediaWiki importer for the Agora Bridge.

Fetches content from a MediaWiki instance via its API or parses an XML dump file,
converts wikitext to Markdown (preserving [[wikilinks]]), and saves .md subnode files.
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
import xml.etree.ElementTree as ET

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
L = logging.getLogger("import_mediawiki")

def wikitext_to_markdown(text: str) -> str:
    """
    Converts MediaWiki wikitext markup into Markdown.
    Preserves [[wikilinks]] intact.
    """
    if not text:
        return ""

    lines = text.splitlines()
    md_lines = []

    for line in lines:
        # Headings: ===== Title ===== -> ##### Title, etc.
        m_head = re.match(r'^(={1,6})\s*(.*?)\s*\1$', line)
        if m_head:
            level = len(m_head.group(1))
            title = m_head.group(2)
            # MediaWiki == is h2, = is h1
            hashes = "#" * min(level, 6)
            md_lines.append(f"{hashes} {title}")
            continue

        # External links: [http://example.com Display Text] -> [Display Text](http://example.com)
        line = re.sub(r'\[(https?://[^\s]+)\s+([^\]]+)\]', r'[\2](\1)', line)
        # Bare external link in brackets: [http://example.com] -> <http://example.com>
        line = re.sub(r'\[(https?://[^\s]+)\]', r'<\1>', line)

        # Bold & Italic
        # '''bold''' -> **bold**
        line = re.sub(r"'''(.*?)'''", r"**\1**", line)
        # ''italic'' -> *italic*
        line = re.sub(r"''(.*?)''", r"*\1*", line)

        # Ordered lists: # item -> 1. item
        if line.startswith("# "):
            line = "1. " + line[2:]

        md_lines.append(line)

    return "\n".join(md_lines)

def sanitize_filename(title: str) -> str:
    """Sanitizes a page title for use as a filesystem filename."""
    filename = title.replace("/", "-").replace("\\", "-").replace(":", "-")
    filename = re.sub(r'\s+', ' ', filename).strip()
    return filename

def fetch_api_pages(api_url: str, output_dir: str):
    """Fetches all pages from a MediaWiki API and saves them to output_dir."""
    L.info(f"Fetching pages via MediaWiki API: {api_url}")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    os.makedirs(output_dir, exist_ok=True)

    apcontinue = None
    page_count = 0

    while True:
        params = {
            "action": "query",
            "list": "allpages",
            "aplimit": "50",
            "format": "json"
        }
        if apcontinue:
            params["apcontinue"] = apcontinue

        query_str = urllib.parse.urlencode(params)
        full_url = f"{api_url}?{query_str}" if "?" not in api_url else f"{api_url}&{query_str}"

        req = urllib.request.Request(full_url, headers={"User-Agent": "AgoraBridge/1.0"})
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            L.error(f"Failed API request to {full_url}: {e}")
            break

        query = data.get("query", {})
        pages = query.get("allpages", [])

        if not pages:
            break

        # Fetch revision contents in batches
        page_ids = [str(p["pageid"]) for p in pages]
        fetch_page_contents(api_url, page_ids, output_dir, ctx)
        page_count += len(pages)

        if "continue" in data and "apcontinue" in data["continue"]:
            apcontinue = data["continue"]["apcontinue"]
        else:
            break

    L.info(f"Successfully processed {page_count} pages via API into {output_dir}")

def fetch_page_contents(api_url: str, page_ids: list, output_dir: str, ctx: ssl.SSLContext):
    """Fetches content for a list of page_ids and writes them to output_dir."""
    ids_str = "|".join(page_ids)
    params = {
        "action": "query",
        "pageids": ids_str,
        "prop": "revisions",
        "rvslots": "main",
        "rvprop": "content",
        "format": "json"
    }
    query_str = urllib.parse.urlencode(params)
    full_url = f"{api_url}?{query_str}" if "?" not in api_url else f"{api_url}&{query_str}"

    req = urllib.request.Request(full_url, headers={"User-Agent": "AgoraBridge/1.0"})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            pages_dict = data.get("query", {}).get("pages", {})
            for pid, pdata in pages_dict.items():
                title = pdata.get("title", f"Page-{pid}")
                revisions = pdata.get("revisions", [])
                if not revisions:
                    continue
                
                rev = revisions[0]
                slots = rev.get("slots", {})
                main_slot = slots.get("main", {})
                wikitext = main_slot.get("*") or rev.get("*", "")

                markdown = wikitext_to_markdown(wikitext)
                fname = sanitize_filename(title) + ".md"
                fpath = os.path.join(output_dir, fname)

                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(markdown)
    except Exception as e:
        L.error(f"Error fetching page contents: {e}")

def parse_xml_dump(dump_path: str, output_dir: str):
    """Parses a MediaWiki XML dump file and saves pages to output_dir."""
    L.info(f"Parsing MediaWiki XML dump: {dump_path}")
    os.makedirs(output_dir, exist_ok=True)

    try:
        tree = ET.parse(dump_path)
        root = tree.getroot()
    except Exception as e:
        L.error(f"Failed to parse XML dump {dump_path}: {e}")
        return

    # Strip XML namespace if present
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    page_count = 0
    for page in root.findall(f"{ns}page"):
        title_elem = page.find(f"{ns}title")
        if title_elem is None or not title_elem.text:
            continue
        title = title_elem.text

        rev = page.find(f"{ns}revision")
        if rev is None:
            continue
        text_elem = rev.find(f"{ns}text")
        wikitext = text_elem.text if text_elem is not None and text_elem.text else ""

        markdown = wikitext_to_markdown(wikitext)
        fname = sanitize_filename(title) + ".md"
        fpath = os.path.join(output_dir, fname)

        with open(fpath, "w", encoding="utf-8") as f:
            f.write(markdown)
        page_count += 1

    L.info(f"Successfully imported {page_count} pages from XML dump into {output_dir}")

def main():
    parser = argparse.ArgumentParser(description="MediaWiki Importer for Agora Bridge")
    parser.add_argument("--url", help="MediaWiki API URL (e.g., https://wiki.sgmk-ssam.ch/api.php)")
    parser.add_argument("--dump-file", help="Path to MediaWiki XML export dump")
    parser.add_argument("--output-dir", required=True, help="Directory to save converted markdown files")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.verbose:
        L.setLevel(logging.DEBUG)

    if not args.url and not args.dump_file:
        L.error("Must provide either --url or --dump-file")
        sys.exit(1)

    if args.dump_file:
        parse_xml_dump(args.dump_file, args.output_dir)
    elif args.url:
        fetch_api_pages(args.url, args.output_dir)

if __name__ == "__main__":
    main()
