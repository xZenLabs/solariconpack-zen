#!/usr/bin/env python3
"""Render Solar contact sheets with one SVG and lookup name per cell."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SVG_NS = "http://www.w3.org/2000/svg"
NAVBAR = """
    library archive tab_folder tab_books tab_manga tab_news tab_continue tab_history
    tab_favorites tab_collections tab_authors tab_series tab_translate tab_tags
    tab_to_be_read home appbar.search quick_search tab_stats tab_exit tab_left tab_right
    appbar.menu
""".split()
UTILITIES = """
    archive atom avatar book_closed calculator compass cpu database education folder_open
    globe network lightning share skip_left skip_right speed sun tablet terminal timer toc
    warmth battery_full battery_half battery_low battery_charging more_vertical coverflow
    grid_slide blocks lookup_highlight lookup_vocab_remove usb quick_bluetooth
    quick_incognito app_launcher quick_lockdown restart tab_stats quick_zen library
    tab_series tab_tags tab_news folder
""".split()


def overview_svg(paths, columns):
    ET.register_namespace("", SVG_NS)
    width = columns * 180
    height = ((len(paths) + columns - 1) // columns) * 144
    root = ET.Element(f"{{{SVG_NS}}}svg", {
        "width": str(width), "height": str(height), "viewBox": f"0 0 {width} {height}",
    })
    ET.SubElement(root, f"{{{SVG_NS}}}rect", {
        "width": "100%", "height": "100%", "fill": "white",
    })
    for index, path in enumerate(paths):
        x, y = (index % columns) * 180, (index // columns) * 144
        icon = ET.fromstring(path.read_bytes())
        icon.attrib.update(x=str(x + 42), y=str(y + 8), width="96", height="96")
        root.append(icon)
        label = ET.SubElement(root, f"{{{SVG_NS}}}text", {
            "x": str(x + 90), "y": str(y + 128), "text-anchor": "middle",
            "font-family": "sans-serif", "font-size": "14", "fill": "black",
        })
        label.text = path.stem
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    renderer = shutil.which("rsvg-convert")
    if not renderer:
        parser.error("rsvg-convert (librsvg) is required to render previews")
    args.output.mkdir(parents=True, exist_ok=True)
    for style in ("Solar Colour", "Solar Mono"):
        pack = ROOT / style
        pack_id = json.loads((pack / "pack.json").read_text())["id"]
        sources = {path.stem: path for path in pack.rglob("*.svg")}
        for group, names, columns in (("navbar", NAVBAR, 6), ("utilities", UTILITIES, 8)):
            destination = args.output / f"{pack_id}-{group}.png"
            svg = overview_svg([sources[name] for name in names], columns)
            subprocess.run([renderer, "--output", str(destination)], input=svg, check=True)
            print(f"Built {destination}")


if __name__ == "__main__":
    main()
