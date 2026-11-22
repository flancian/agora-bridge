import os
import ssl
import tempfile
import unittest
from unittest.mock import patch

import import_website


class TestRssAndSitemap(unittest.TestCase):
    def test_parse_sitemap_urlset_and_prefix_filter(self):
        xml = b"""<?xml version="1.0" encoding="utf-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://www.ccczh.ch/news/</loc><lastmod>2026-09-21T00:00:00+00:00</lastmod></url>
            <url><loc>https://www.ccczh.ch/news/2026-09-19_chaosseminar/</loc><lastmod>2026-09-21T00:00:00+00:00</lastmod></url>
            <url><loc>https://www.ccczh.ch/protokolle/vorstand/2026_10_26/</loc><lastmod>2026-10-26</lastmod></url>
            <url><loc>https://www.ccczh.ch/news/feed.xml</loc></url>
        </urlset>"""

        all_urls = import_website.parse_sitemap_xml(xml, prefix=None, limit=50)
        self.assertEqual(len(all_urls), 3)  # skips feed.xml

        news_urls = import_website.parse_sitemap_xml(
            xml, prefix="https://www.ccczh.ch/news/", limit=50
        )
        self.assertEqual(
            [u for u, _ in news_urls],
            ["https://www.ccczh.ch/news/2026-09-19_chaosseminar/"],
        )
        self.assertIsNotNone(news_urls[0][1])

    def test_parse_sitemapindex_recursion(self):
        index_xml = b"""<?xml version="1.0" encoding="utf-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap><loc>https://example.org/sitemap-posts.xml</loc></sitemap>
        </sitemapindex>"""
        child_xml = b"""<?xml version="1.0" encoding="utf-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.org/posts/hello-world/</loc><lastmod>2026-11-01T12:00:00Z</lastmod></url>
        </urlset>"""

        class DummyResp:
            def __init__(self, data):
                self._data = data

            def read(self):
                return self._data

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        ctx = ssl.create_default_context()
        with patch("urllib.request.urlopen", return_value=DummyResp(child_xml)):
            urls = import_website.parse_sitemap_xml(
                index_xml, prefix=None, limit=10, ctx=ctx, max_depth=2
            )
        self.assertEqual(len(urls), 1)
        self.assertEqual(urls[0][0], "https://example.org/posts/hello-world/")
        self.assertIsNotNone(urls[0][1])

    def test_parse_feed_bytes_rss_and_atom(self):
        rss_bytes = b"""<?xml version="1.0" encoding="UTF-8" ?>
        <rss version="2.0"><channel><title>Test</title>
            <item>
                <title>First Post</title>
                <link>https://example.org/posts/first-post</link>
                <pubDate>Sun, 15 Nov 2026 10:00:00 GMT</pubDate>
                <description><![CDATA[<p>Hello <b>Agora</b> world from RSS feed.</p>]]></description>
            </item>
        </channel></rss>"""

        entries = import_website.parse_feed_bytes(rss_bytes, limit=10)
        self.assertEqual(len(entries), 1)
        link, title, content, updated_epoch = entries[0]
        self.assertEqual(link, "https://example.org/posts/first-post")
        self.assertEqual(title, "First Post")
        self.assertIn("Agora", content)
        self.assertIsNotNone(updated_epoch)

    def test_discover_alternate_feeds(self):
        html = """<html><head>
        <link href="/feed.xml" type="application/rss+xml" rel="alternate" title="RSS">
        <link rel="alternate" type="application/atom+xml" href="https://other.example/atom.xml">
        <link rel="stylesheet" href="/style.css">
        </head></html>"""
        feeds = import_website.discover_alternate_feeds(html, "https://example.org/blog/")
        self.assertEqual(
            feeds,
            ["https://example.org/feed.xml", "https://other.example/atom.xml"],
        )

    def test_feed_only_saves_without_http_and_updates_on_newer_mtime(self):
        ctx = ssl.create_default_context()
        long_html = (
            "<p>This is a full-content RSS entry with plenty of meaningful text "
            "and an internal <a href='/about'>About</a> link for Agora conversion.</p>"
            * 3
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("urllib.request.urlopen", side_effect=AssertionError("Should not fetch HTTP")):
                ok = import_website.fetch_and_save_page(
                    "https://example.org/posts/test-note",
                    tmpdir,
                    ctx,
                    "example.org",
                    fallback_title="Test Note",
                    feed_content=long_html,
                    remote_mtime=1700000000.0,
                    feed_only=True,
                )
            self.assertTrue(ok)
            md_path = os.path.join(tmpdir, "test-note.md")
            self.assertTrue(os.path.exists(md_path))
            with open(md_path, "r", encoding="utf-8") as f:
                text = f.read()
            self.assertIn("# Test Note", text)
            self.assertIn("[[about]]", text)

            # Same or older remote_mtime should skip without touching file
            with open(md_path, "w", encoding="utf-8") as f:
                f.write("SENTINEL")
            os.utime(md_path, (1700000000.0, 1700000000.0))
            ok_skip = import_website.fetch_and_save_page(
                "https://example.org/posts/test-note",
                tmpdir,
                ctx,
                "example.org",
                fallback_title="Test Note",
                feed_content=long_html,
                remote_mtime=1700000000.0,
                feed_only=True,
            )
            self.assertTrue(ok_skip)
            with open(md_path, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), "SENTINEL")

            # Newer remote_mtime should refresh content
            with patch("urllib.request.urlopen", side_effect=AssertionError("Should not fetch HTTP")):
                ok_refresh = import_website.fetch_and_save_page(
                    "https://example.org/posts/test-note",
                    tmpdir,
                    ctx,
                    "example.org",
                    fallback_title="Test Note",
                    feed_content=long_html,
                    remote_mtime=1700005000.0,
                    feed_only=True,
                )
            self.assertTrue(ok_refresh)
            with open(md_path, "r", encoding="utf-8") as f:
                self.assertIn("# Test Note", f.read())


if __name__ == "__main__":
    unittest.main()
