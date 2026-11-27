"""The host pages must load their scripts and styles from this server, not public CDNs (#143)."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = sorted((ROOT / "static").glob("*.html"))
TAG = re.compile(r"<(?:script|link)\b[^>]*\b(?:src|href)\s*=\s*[\"']([^\"']+)[\"']", re.I)


def asset_urls(page):
    return TAG.findall(page.read_text(encoding="utf-8"))


class LocalPageAssetsTest(unittest.TestCase):
    def test_pages_exist(self):
        self.assertTrue(any(p.name == "index.html" for p in PAGES))

    def test_no_external_scripts_or_styles(self):
        for page in PAGES:
            for url in asset_urls(page):
                with self.subTest(page=page.name, url=url):
                    self.assertNotRegex(url, r"^(?:https?:)?//", "load this from the app's own server")

    def test_training_vendor_files_exist(self):
        for page in PAGES:
            for url in asset_urls(page):
                if url.startswith("/training/static/vendor/"):
                    with self.subTest(page=page.name, url=url):
                        path = ROOT / "rackbook" / "static" / url[len("/training/static/"):].split("?")[0]
                        self.assertTrue(path.is_file(), f"{path} is missing")

    def test_dashboard_loads_chart_and_markdown_locally(self):
        urls = asset_urls(ROOT / "static" / "index.html")
        self.assertIn("/training/static/vendor/chart-4.4.0.umd.js", urls)
        self.assertTrue(any(u.startswith("/training/static/vendor/marked-") for u in urls))


if __name__ == "__main__":
    unittest.main()
