"""Ensure optional React frontend installation remains reversible and idempotent."""
import tempfile
import unittest
from pathlib import Path

from scripts.install_upgrade import integrate


class WebIntegrationTests(unittest.TestCase):
    def test_idempotent_patch_and_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            server = root / 'dashboard_server.py'
            server.write_text('ASSETS = ROOT / "dashboard"\n'
                              '        static = {"/": ("index.html", "text/html; charset=utf-8"),\n')
            (root / '.gitignore').write_text('__pycache__/\n')
            integrate(root)
            first = server.read_text()
            integrate(root)
            self.assertEqual(first, server.read_text())
            self.assertIn('WEB_DIST =', first)
            self.assertIn('if WEB_DIST.is_dir()', first)
            self.assertIn('web/dist/', (root / '.gitignore').read_text())

    def test_refuses_unknown_server_code(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'dashboard_server.py').write_text('print("unrelated application")')
            with self.assertRaises(ValueError):
                integrate(root)

if __name__ == '__main__':
    unittest.main()