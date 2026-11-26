import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

import import_mediawiki
import import_dokuwiki


class TestGentleMediaWiki(unittest.TestCase):
    def test_incremental_sync_uses_recentchanges_after_initial_import(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            calls = []

            def fake_api_get(api_url, params, ctx, retries=2):
                calls.append(params.copy())
                if params.get("list") == "allpages":
                    return {"query": {"allpages": [{"pageid": 1, "title": "Hello"}]}}
                if params.get("prop") == "revisions":
                    return {
                        "query": {
                            "pages": {
                                "1": {
                                    "title": "Hello",
                                    "revisions": [{"slots": {"main": {"*": "== Hello ==\nWorld"}}}],
                                }
                            }
                        }
                    }
                if params.get("list") == "recentchanges":
                    return {"query": {"recentchanges": []}}
                return {}

            with patch.object(import_mediawiki, "_api_get_json", side_effect=fake_api_get):
                # 1. Initial full import
                import_mediawiki.fetch_api_pages("https://example.org/api.php", tmpdir, delay=0)
                self.assertTrue(os.path.exists(os.path.join(tmpdir, "Hello.md")))
                self.assertTrue(os.path.exists(os.path.join(tmpdir, import_mediawiki.STATE_FILENAME)))
                self.assertEqual(len(calls), 2)
                self.assertEqual(calls[0]["list"], "allpages")

                # 2. Second run should ONLY make 1 recentchanges API call!
                calls.clear()
                import_mediawiki.fetch_api_pages("https://example.org/api.php", tmpdir, delay=0)
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0]["list"], "recentchanges")
                self.assertIn("rcend", calls[0])

    def test_write_if_changed_preserves_mtime(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fpath = os.path.join(tmpdir, "Test.md")
            self.assertTrue(import_mediawiki._write_if_changed(fpath, "hello"))
            os.utime(fpath, (1000000, 1000000))
            self.assertFalse(import_mediawiki._write_if_changed(fpath, "hello"))
            self.assertEqual(int(os.path.getmtime(fpath)), 1000000)
            self.assertTrue(import_mediawiki._write_if_changed(fpath, "hello updated"))


class TestGentleDokuWiki(unittest.TestCase):
    def test_feed_url_and_link_extraction(self):
        base = "https://brain4free.org/wiki/doku.php"
        self.assertEqual(
            import_dokuwiki._doku_feed_url(base),
            "https://brain4free.org/wiki/feed.php?type=rss2&num=50",
        )
        self.assertEqual(
            import_dokuwiki._extract_page_id_from_link("https://brain4free.org/wiki/doku.php/elektronik:ctrl_m", base),
            "elektronik:ctrl_m",
        )
        self.assertEqual(
            import_dokuwiki._extract_page_id_from_link("https://brain4free.org/wiki/doku.php?id=blog:qmk", base),
            "blog:qmk",
        )

    def test_check_feed_changes_filters_old_entries(self):
        base = "https://brain4free.org/wiki/doku.php"
        sample_rss = """<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0"><channel><title>brain4free</title>
          <item>
            <title>New Note</title>
            <link>https://brain4free.org/wiki/doku.php/blog:new_note</link>
            <pubDate>Thu, 26 Nov 2026 20:00:00 +0000</pubDate>
          </item>
          <item>
            <title>Old Note</title>
            <link>https://brain4free.org/wiki/doku.php/blog:old_note</link>
            <pubDate>Mon, 01 Jan 2024 12:00:00 +0000</pubDate>
          </item>
        </channel></rss>"""

        # Cutoff in 2026-11-26 19:00 UTC -> only blog:new_note should match
        since_epoch = 1795633200.0
        with patch.object(import_dokuwiki, "fetch_text", return_value=sample_rss):
            changed = import_dokuwiki._check_feed_changes(base, since_epoch, ctx=None)
            self.assertEqual(changed, ["blog:new_note"])


if __name__ == "__main__":
    unittest.main()
