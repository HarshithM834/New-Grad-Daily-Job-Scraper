"""Apply the optional React dashboard integration to an existing CareerOps checkout.

Does not modify the tracker CSV or credentials. Refuses unknown server layouts
rather than risk replacing unrelated source code.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ASSETS_LINE = 'ASSETS = ROOT / "dashboard"'
STATIC_LINE = '''        static = {"/": ("index.html", "text/html; charset=utf-8"),'''

ADD_BUILD = '''ASSETS = ROOT / "dashboard"
WEB_DIST = ROOT / "web" / "dist"
'''

ADD_ROUTE = '''        # Optional Vite production build. Keep the dependency-free UI as a fallback.
        if WEB_DIST.is_dir() and (route == "/" or route.startswith("/assets/")):
            candidate = (WEB_DIST / ("index.html" if route == "/" else route.lstrip("/"))).resolve()
            if candidate.is_relative_to(WEB_DIST.resolve()) and candidate.is_file():
                from mimetypes import guess_type
                mime = guess_type(candidate.name)[0] or "application/octet-stream"
                if mime == "text/javascript":
                    mime = "application/javascript"
                self.send_headers(200, mime, candidate.read_bytes())
                return
            self.reply(404, {"error": "Asset not found"})
            return
'''


def integrate(root: Path) -> list[str]:
    server = root / "dashboard_server.py"
    if not server.exists():
        raise ValueError("dashboard_server.py is missing; run this from the repository root")
    text = server.read_text(encoding="utf-8")
    if "WEB_DIST =" not in text:
        if text.count(ASSETS_LINE) != 1 or text.count(STATIC_LINE) != 1:
            raise ValueError("Unknown dashboard_server.py layout; integration not applied")
        text = text.replace(ASSETS_LINE, ADD_BUILD, 1).replace(STATIC_LINE, ADD_ROUTE + STATIC_LINE, 1)
        server.write_text(text, encoding="utf-8")
        updated = [str(server)]
    else:
        updated = []
    ignore = root / ".gitignore"
    old = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
    extra = "\n# Optional React dashboard build and dependency cache\nweb/node_modules/\nweb/dist/\nweb/.vite/\n"
    if "web/node_modules/" not in old:
        ignore.write_text(old.rstrip() + "\n" + extra, encoding="utf-8")
        updated.append(str(ignore))
    return updated


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path("."))
    root = p.parse_args().root.resolve()
    try:
        touched = integrate(root)
    except ValueError as exc:
        p.error(str(exc))
    print("Updated: " + (", ".join(touched) if touched else "nothing (already integrated)"))