"""The front door: / sends you to the workout log; the original app is kept, unchanged, at /legacy."""
import json
import os
import shutil
import sys
import tempfile
import unittest
import warnings

warnings.filterwarnings("ignore", category=ResourceWarning)

_IMPORT_DIR = tempfile.mkdtemp()
os.environ.setdefault("RACKBOOK_DB_PATH", os.path.join(_IMPORT_DIR, "import.db"))

from fastapi.testclient import TestClient  # noqa: E402

from rackbook import main  # noqa: E402


class TestFrontDoor(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["RACKBOOK_DB_PATH"] = os.path.join(self.tmp, "test.db")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.client = TestClient(main.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_root_redirects_to_the_log_page(self):
        r = self.client.get("/", follow_redirects=False)
        self.assertIn(r.status_code, (302, 307))
        self.assertEqual("/training/log", r.headers["location"])

    def test_original_app_is_still_served_at_legacy(self):
        r = self.client.get("/legacy")
        self.assertEqual(200, r.status_code)
        self.assertIn("Hevy-Fatigue", r.text)

    def test_recent_page_links_to_the_log_page_and_back(self):
        # Pages draw their menu from one shared script, which must link both ways.
        menu = self.client.get("/static/app-menu.js").text
        for page in ("/recent", "/log"):
            html = self.client.get(page).text
            self.assertIn('/training/static/app-menu.js', html, page)
            self.assertIn('data-app-menu', html, page)
        self.assertIn("href: '/training/log'", menu)
        self.assertIn("href: '/training/recent'", menu)

    def test_pages_tell_browsers_to_recheck_instead_of_reusing_a_stored_copy(self):
        for path in ("/log", "/recent", "/legacy"):
            self.assertEqual("no-cache", self.client.get(path).headers["cache-control"], path)
        self.assertEqual("no-cache", self.client.get("/", follow_redirects=False).headers["cache-control"])

    # The pages can be added to a phone or tablet home screen and open like an app.
    def test_manifest_is_served_and_starts_on_the_log_page(self):
        r = self.client.get("/manifest.webmanifest")
        self.assertEqual(200, r.status_code)
        self.assertIn("manifest+json", r.headers["content-type"])
        manifest = json.loads(r.text)
        self.assertEqual(("/training/log", "standalone"), (manifest["start_url"], manifest["display"]))

    def test_every_icon_in_the_manifest_is_served_as_a_png(self):
        icons = json.loads(self.client.get("/manifest.webmanifest").text)["icons"]
        self.assertTrue({"192x192", "512x512"} <= {i["sizes"] for i in icons})
        for icon in icons:
            r = self.client.get(icon["src"].removeprefix("/training"))
            self.assertEqual(200, r.status_code, icon["src"])
            self.assertEqual("image/png", r.headers["content-type"])
            self.assertTrue(r.content.startswith(b"\x89PNG"), icon["src"])

    def test_the_pages_point_at_the_manifest_and_the_touch_icon(self):
        for path in ("/log", "/recent"):
            html = self.client.get(path).text
            self.assertIn('rel="manifest" href="/training/manifest.webmanifest"', html, path)
            self.assertIn('rel="apple-touch-icon" href="/training/static/apple-touch-icon.png"', html, path)
            # the browser bar follows the system light/dark setting, like the page itself
            self.assertIn('media="(prefers-color-scheme: light)" content="#f3f5f8"', html, path)
            self.assertIn('media="(prefers-color-scheme: dark)" content="#111923"', html, path)
        self.assertEqual(200, self.client.get("/static/apple-touch-icon.png").status_code)

    def test_a_service_worker_is_served_from_the_root_and_the_pages_register_it(self):
        r = self.client.get("/sw.js")
        self.assertEqual(200, r.status_code)
        self.assertIn("javascript", r.headers["content-type"])
        self.assertIn("fetch", r.text)
        self.assertEqual("no-cache", r.headers["cache-control"])
        for path in ("/log", "/recent"):
            self.assertIn('serviceWorker.register(trainingUrl("/sw.js"))', self.client.get(path).text, path)


if __name__ == "__main__":
    unittest.main()
