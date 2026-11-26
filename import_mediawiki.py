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
import datetime
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
import xml.etree.ElementTree as ET

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
L = logging.getLogger("import_mediawiki")

DEFAULT_USER_AGENT = "AgoraBridge/1.0 (+https://anagora.org/agora-bridge)"
STATE_FILENAME = ".mediawiki_sync_state.json"


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


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def _write_if_changed(fpath: str, content: str) -> bool:
    """Writes content to fpath only if it differs from existing content, preserving mtimes."""
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                if f.read() == content:
                    return False
        except Exception:
            pass
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def _api_get_json(api_url: str, params: dict, ctx: ssl.SSLContext, retries: int = 2) -> dict:
    """Makes a polite MediaWiki API GET request with 429/503 Retry-After backoff."""
    query_str = urllib.parse.urlencode(params)
    full_url = f"{api_url}?{query_str}" if "?" not in api_url else f"{api_url}&{query_str}"
    req = urllib.request.Request(full_url, headers={"User-Agent": DEFAULT_USER_AGENT})

    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < retries:
                retry_after = e.headers.get("Retry-After")
                wait_s = 5.0
                if retry_after and retry_after.isdigit():
                    wait_s = min(float(retry_after), 60.0)
                else:
                    wait_s = 5.0 * (attempt + 1)
                L.warning(f"HTTP {e.code} from {api_url}; backing off {wait_s}s...")
                time.sleep(wait_s)
                continue
            raise


def fetch_recent_changes(api_url: str, since_ts: str, output_dir: str, ctx: ssl.SSLContext, delay: float = 0.5) -> int:
    """
    Incrementally fetches only pages edited or created since `since_ts`
    using MediaWiki's `list=recentchanges` API.
    """
    L.info(f"Checking MediaWiki recentchanges since {since_ts}: {api_url}")
    changed_page_ids = []
    seen_ids = set()
    rccontinue = None

    while True:
        params = {
            "action": "query",
            "list": "recentchanges",
            "rcnamespace": "0",
            "rctype": "edit|new",
            "rclimit": "500",
            "rcend": since_ts,
            "format": "json",
        }
        if rccontinue:
            params["rccontinue"] = rccontinue

        data = _api_get_json(api_url, params, ctx)
        changes = data.get("query", {}).get("recentchanges", [])
        for rc in changes:
            pid = rc.get("pageid")
            if pid and str(pid) not in seen_ids:
                seen_ids.add(str(pid))
                changed_page_ids.append(str(pid))

        if "continue" in data and "rccontinue" in data["continue"]:
            rccontinue = data["continue"]["rccontinue"]
            if delay > 0:
                time.sleep(delay)
        else:
            break

    if not changed_page_ids:
        L.info(f"No MediaWiki changes since {since_ts} for {api_url} (1 API call).")
        return 0

    L.info(f"Found {len(changed_page_ids)} changed pages since {since_ts}; fetching content in batches.")
    written = 0
    for i in range(0, len(changed_page_ids), 50):
        batch = changed_page_ids[i:i + 50]
        written += fetch_page_contents(api_url, batch, output_dir, ctx)
        if delay > 0 and i + 50 < len(changed_page_ids):
            time.sleep(delay)

    L.info(f"Incremental MediaWiki sync complete: {len(changed_page_ids)} checked, {written} updated in {output_dir}")
    return len(changed_page_ids)


def fetch_api_pages(api_url: str, output_dir: str, delay: float = 0.5, full: bool = False):
    """Fetches pages from a MediaWiki API (incrementally after initial import) and saves them to output_dir."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    os.makedirs(output_dir, exist_ok=True)
    sync_started_ts = _utc_now_iso()
    state = _load_sync_state(output_dir)

    # Check if we already have an initial import (either via state file or existing .md files + state)
    last_sync_ts = state.get("last_sync_ts")
    if last_sync_ts and not full:
        try:
            fetch_recent_changes(api_url, last_sync_ts, output_dir, ctx, delay=delay)
            state["last_sync_ts"] = sync_started_ts
            state["api_url"] = api_url
            _save_sync_state(output_dir, state)
            return
        except Exception as e:
            L.warning(f"Incremental recentchanges sync failed for {api_url} ({e}); falling back to full sync.")

    L.info(f"Running full MediaWiki API import: {api_url} (delay={delay}s)")
    apcontinue = None
    page_count = 0
    written_count = 0

    while True:
        params = {
            "action": "query",
            "list": "allpages",
            "aplimit": "50",
            "format": "json"
        }
        if apcontinue:
            params["apcontinue"] = apcontinue

        try:
            data = _api_get_json(api_url, params, ctx)
        except Exception as e:
            L.error(f"Failed API request to {api_url}: {e}")
            break

        query = data.get("query", {})
        pages = query.get("allpages", [])

        if not pages:
            break

        if delay > 0:
            time.sleep(delay)

        # Fetch revision contents in batches
        page_ids = [str(p["pageid"]) for p in pages]
        written_count += fetch_page_contents(api_url, page_ids, output_dir, ctx)
        page_count += len(pages)

        if "continue" in data and "apcontinue" in data["continue"]:
            apcontinue = data["continue"]["apcontinue"]
            if delay > 0:
                time.sleep(delay)
        else:
            break

    if page_count > 0:
        _save_sync_state(output_dir, {
            "last_sync_ts": sync_started_ts,
            "api_url": api_url,
            "total_pages": page_count,
        })

    L.info(f"Successfully processed {page_count} pages ({written_count} written/updated) via API into {output_dir}")


def fetch_page_contents(api_url: str, page_ids: list, output_dir: str, ctx: ssl.SSLContext) -> int:
    """Fetches content for a list of page_ids and writes changed files to output_dir."""
    ids_str = "|".join(page_ids)
    params = {
        "action": "query",
        "pageids": ids_str,
        "prop": "revisions",
        "rvslots": "main",
        "rvprop": "content",
        "format": "json"
    }
    written = 0
    try:
        data = _api_get_json(api_url, params, ctx)
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

            if _write_if_changed(fpath, markdown):
                written += 1
    except Exception as e:
        L.error(f"Error fetching page contents: {e}")
    return written


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

        _write_if_changed(fpath, markdown)
        page_count += 1

    L.info(f"Successfully imported {page_count} pages from XML dump into {output_dir}")


def main():
    parser = argparse.ArgumentParser(description="MediaWiki Importer for Agora Bridge")
    parser.add_argument("--url", help="MediaWiki API URL (e.g., https://wiki.sgmk-ssam.ch/api.php)")
    parser.add_argument("--dump-file", help="Path to MediaWiki XML export dump")
    parser.add_argument("--output-dir", required=True, help="Directory to save converted markdown files")
    parser.add_argument("--delay", type=float, default=0.5, help="Polite delay in seconds between API requests (default: 0.5)")
    parser.add_argument("--full", action="store_true", help="Force a full re-import instead of incremental recentchanges sync")
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
        fetch_api_pages(args.url, args.output_dir, delay=args.delay, full=args.full)


if __name__ == "__main__":
    main()
