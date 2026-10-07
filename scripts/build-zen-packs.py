#!/usr/bin/env python3
"""Build standalone Solar icon packs for Zen UI using Python's standard library."""

import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ALIASES = {
    "brightness": "frontlight",
    "large_chevron_up": "chevron.up",
    "lookup.ai": "ai_assistant",
    "lookup_ai": "ai_assistant",
    "lookup.search": "search",
    "lookup_search": "search",
    "lookup.vocab": "vocabulary_builder",
    "lookup_vocab": "vocabulary_builder",
    "quick_aa": "ai_assistant",
    "quick_cloud": "cloud_storage",
    "quick_crossword": "crossword",
    "quick_exit": "power",
    "quick_filebrowser": "folder",
    "quick_localsend": "localsend",
    "quick_nightmode": "night_mode",
    "quick_opds": "storefront",
    "quick_puzzle": "sudoku",
    "quick_rotate": "rotate",
    "quick_screenshot": "screenshots",
    "quick_search": "search",
    "quick_sleep": "sleep",
    "quick_stats_calendar": "stats_calendar",
    "quick_streak": "streak",
    "quick_sync": "syncthing",
    "quick_usb": "usb_storage",
    "quick_wifi": "wifi_toggle",
    "quick_zlib": "zlibrary",
    "tab_authors": "authors",
    "tab_collections": "collections",
    "tab_exit": "power",
    "tab_folder": "folder",
    "tab_history": "history",
    "tab_left": "chevron_left",
    "tab_manga": "rakuyomi",
    "tab_news": "instapaper",
    "tab_right": "chevron_right",
    "tab_series": "series",
    "tab_stats": "stats_calendar",
    "tab_tags": "tags",
    "tab_to_be_read": "bookmark_browser",
}


def main():
    version = re.search(r'^\s*version\s*=\s*"([^"]+)"',
                        (ROOT / "_meta.lua").read_text(), re.MULTILINE).group(1)
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    for style in ("Colour", "Mono"):
        pack_id = f"zen-solar-{style.lower()}"
        paths = sorted((ROOT / f"Solar {style}").glob("*/*.svg"))
        files = {path.name: path.read_bytes() for path in paths}
        assert len(files) == len(paths) == 160, "Expected 160 uniquely named source icons"
        for name, data in files.items():
            assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.svg", name), name
            svg = ET.fromstring(data)
            assert svg.tag == "{http://www.w3.org/2000/svg}svg", name
            assert svg.get("viewBox") == "0 0 24 24", name
        for alias, source in ALIASES.items():
            files[f"{alias}.svg"] = files[f"{source}.svg"]
        icon_count = len(files)
        metadata = {
            "schema_version": 1,
            "id": pack_id,
            "name": f"Solar {style} for Zen UI",
            "version": version,
            "author": "480 Design; adapted by pxlflux; packaged by xZenLabs",
        }
        files["pack.json"] = (json.dumps(metadata, indent=2) + "\n").encode()
        files["LICENSE-ICONS.txt"] = (ROOT / "LICENSE-ICONS.txt").read_bytes()
        files["README.md"] = (
            f"# Solar {style} for Zen UI\n\n"
            "Copy this folder or its ZIP into `koreader/icons/zen/`.\n"
            "Enable Custom icons, select this pack under Custom icon pack,\n"
            "and restart KOReader. Zen UI automatically extracts pack ZIPs.\n\n"
            "Missing icons use Zen UI and KOReader's bundled artwork.\n"
            "See LICENSE-ICONS.txt for attribution and licensing.\n"
        ).encode()
        assert len(files) <= 512 and sum(map(len, files.values())) <= 50 * 1024 * 1024
        destination = output / f"{pack_id}.zip"
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(files.items()):
                assert len(data) <= 5 * 1024 * 1024, name
                info = zipfile.ZipInfo(f"{pack_id}/{name}", (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data, compresslevel=9)
        assert destination.stat().st_size <= 25 * 1024 * 1024
        with zipfile.ZipFile(destination) as archive:
            assert archive.testzip() is None, "Archive failed its CRC check"
        print(f"Built {destination.relative_to(ROOT)} ({icon_count} icons)")


if __name__ == "__main__":
    main()
