#!/usr/bin/env python3
"""Convert extracted SimpleUI icon packs to standalone ZenOS ZIPs."""

import argparse
import ast
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import unicodedata
import warnings
import xml.etree.ElementTree as ET
import zipfile

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_SIZE = 5 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 12 * 1024 * 1024
SIMPLEUI_NAMES = {
    "sui_menu": "menu",
    "sui_search": "search",
    "sui_back": "chevron_left",
    "sui_browse_normal": "folder",
    "sui_browse_author": "authors",
    "sui_browse_series": "series",
    "sui_browse_tags": "tags",
    "sui_pager_prev": "chevron_left",
    "sui_pager_next": "chevron_right",
    "sui_pager_first": "pager_first",
    "sui_pager_last": "pager_last",
    "sui_navpager_prev": "chevron_left",
    "sui_navpager_next": "chevron_right",
    "sui_coll_back": "coll_back",
    "sui_qa_folder": "folder",
    "sui_qa_plugin": "qa_plugin",
    "sui_qa_system": "settings",
    "sui_qa_group": "qa_group",
    "sui_fc_empty": "folder",
    "sui_tab_main": "menu",
    "sui_tab_setting": "settings",
    "sui_tab_tools": "tab_tools",
    "sui_tab_search": "search",
    "sui_tab_fm_settings": "tab_fm_settings",
    "sui_tab_navigation": "tab_navigation",
    "sui_tab_typeset": "tab_typeset",
    "sui_tab_filebrowser": "tab_filebrowser",
    "sui_tab_qs_panel": "tab_qs_panel",
    "sui_action_library": "library",
    "sui_action_homescreen": "homescreen",
    "sui_action_collections": "collections",
    "sui_action_history": "history",
    "sui_action_continue": "continue",
    "sui_action_favorites": "favorites",
    "sui_action_bookmark_browser": "bookmark_browser",
    "sui_action_wifi_toggle": "wifi_toggle",
    "sui_action_frontlight": "frontlight",
    "sui_action_night_mode": "night_mode",
    "sui_action_stats_calendar": "stats_calendar",
    "sui_action_power": "power",
    "sui_action_browse_authors": "authors",
    "sui_action_browse_series": "series",
    "sui_action_browse_tags": "tags",
    "sui_action_settings": "settings",
    "sui_action_recent": "recent",
    "sui_action_random_document": "random_document",
}
ALIASES = {
    "appbar.menu": "menu",
    "appbar.search": "search",
    "appbar.settings": "settings",
    "appbar.tools": "tab_tools",
    "appbar.navigation": "tab_navigation",
    "appbar.typeset": "tab_typeset",
    "appbar.filebrowser": "tab_filebrowser",
    "book.opened": "continue",
    "brightness": "frontlight",
    "chevron.left": "chevron_left",
    "chevron.right": "chevron_right",
    "chevron.first": "pager_first",
    "chevron.last": "pager_last",
    "home": "homescreen",
    "large_chevron_up": "chevron.up",
    "lightbulb": "frontlight",
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
    "star.empty": "favorites",
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


def zen_id(name):
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    digest = hashlib.sha256(name.encode()).hexdigest()[:12]
    if not slug or len(slug) > 124:
        slug = slug[:111].rstrip("-") + ("-" if slug else "") + digest
    return "zen-" + slug


def lua_strings(path):
    """Read literal metadata and map entries without executing pack.lua."""
    if not path.exists():
        return {}
    if path.is_symlink() or path.stat().st_size > 64 * 1024:
        raise ValueError(f"Unsafe or oversized manifest: {path}")
    string = r'''(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')'''
    text = re.sub(rf'{string}|--\[(=*)\[.*?\]\1\]|--[^\n]*',
                  lambda match: "" if match[0].startswith("--") else match[0],
                  path.read_text(), flags=re.DOTALL)
    pairs = re.findall(rf'(\w+|\[\s*{string}\s*\])\s*=\s*({string})(?=\s*[,}};])', text)
    values = {}
    for key, value in pairs:
        if key.startswith("["):
            key = ast.literal_eval(key[1:-1].strip())
        values[key] = ast.literal_eval(value)
    for key in re.findall(r'\b(name|author|version|sui_\w+)\s*=', text):
        if key not in values:
            raise ValueError(f"{path}: {key} must be a literal quoted string")
    return values


def clean_icon(path):
    if path.is_symlink() or path.stat().st_size > MAX_FILE_SIZE:
        raise ValueError(f"Unsafe or oversized icon: {path}")
    data = path.read_bytes()
    if path.suffix.lower() == ".svg":
        if ET.fromstring(data).tag not in ("svg", "{http://www.w3.org/2000/svg}svg"):
            raise ValueError(f"Not an SVG document: {path}")
        return data
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(BytesIO(data), formats=["PNG"]) as image:
            image.verify()
        with Image.open(BytesIO(data), formats=["PNG"]) as image:
            if image.n_frames != 1:
                raise ValueError(f"Animated PNGs are not supported: {path}")
            pixels = image.convert("RGBA")
            # A new pixel-only image carries no source metadata or appended data.
            clean = Image.frombytes("RGBA", pixels.size, pixels.tobytes())
            output = BytesIO()
            clean.save(output, format="PNG", compress_level=9)
    return output.getvalue()


def pack_sources(root, output):
    def included(path):
        return path != output and output not in path.parents and not any(
            part.startswith(".") or part == "dist" for part in path.relative_to(root).parts)

    if (root / "pack.lua").is_file():
        yield root, [root]
        return
    manifests = [path for path in sorted(root.rglob("pack.lua")) if included(path)]
    if manifests:
        bundles = []
        for manifest in manifests:
            pack = manifest.parent
            bundle = pack.parent if pack != root and pack.name.startswith("Pack Icons") else pack
            directories = [path for path in bundle.iterdir() if path.is_dir()] if bundle != pack else [pack]
            bundles.append(bundle)
            yield pack, directories
        for child in sorted(root.iterdir()):
            if child.is_dir() and included(child) and not any(
                    child == bundle or child in bundle.parents for bundle in bundles) and any(
                    path.suffix.lower() in (".svg", ".png") for path in child.iterdir()):
                yield child, [child]
    elif any(path.suffix.lower() in (".svg", ".png") for path in root.iterdir()):
        yield root, [root]
    else:
        for child in sorted(root.iterdir()):
            if child.is_dir() and included(child) and any(
                    path.suffix.lower() in (".svg", ".png") for path in child.rglob("*")):
                yield child, [child]


def build_pack(pack, directories, root, output, version, metadata=None):
    fields = lua_strings(pack / "pack.lua")
    display_name = fields.get("name", pack.name)
    metadata = dict(metadata or {})
    if pack != root:
        metadata.update(id=zen_id(display_name), name=display_name + " for ZenOS")
    metadata.setdefault("id", zen_id(display_name))
    metadata.setdefault("name", display_name + " for ZenOS")
    metadata.setdefault("schema_version", 1)
    pack_id = metadata["id"]
    if not isinstance(pack_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", pack_id):
        raise ValueError(f"Invalid pack ID: {pack_id}")
    if not isinstance(metadata["name"], str) or not metadata["name"] or len(metadata["name"].encode()) > 160:
        raise ValueError("Pack name must be a nonempty string of at most 160 bytes")
    if type(metadata["schema_version"]) is not int or metadata["schema_version"] != 1:
        raise ValueError("Unsupported pack.json schema_version; expected 1")
    files, sources, seen = {}, {}, set()
    canonical_names = set(SIMPLEUI_NAMES) | set(SIMPLEUI_NAMES.values()) | set(ALIASES) | set(ALIASES.values())
    for directory in directories:
        if directory.is_symlink():
            raise ValueError(f"Symlinked icon directory: {directory}")
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in (".svg", ".png"):
                continue
            stem = re.sub(r"[^A-Za-z0-9._-]+", "-", path.stem).strip("._-")
            if stem.lower() in canonical_names:
                stem = stem.lower()
            name = (stem or f"icon-{len(sources) + 1}") + path.suffix.lower()
            if name.lower() in seen:
                raise ValueError(f"Duplicate icon filename: {name}")
            seen.add(name.lower())
            if len(seen) > 512:
                raise ValueError(f"{pack}: too many source icons")
            files[name] = clean_icon(path)
            sources[path.resolve()] = name
    if not files:
        raise ValueError(f"Pack contains no icons: {pack}")

    def alias(target, source):
        if source and not any(target + suffix in files for suffix in (".svg", ".png")):
            files[target + Path(source).suffix] = files[source]

    def icon(stem):
        return next((stem + suffix for suffix in (".svg", ".png") if stem + suffix in files), None)

    for slot, target in SIMPLEUI_NAMES.items():
        if slot in fields:
            source = sources.get((pack / fields[slot]).resolve())
            if not source:
                raise ValueError(f"{pack}: missing mapped icon for {slot}: {fields[slot]}")
        else:
            source = icon(slot)
        alias(target, source)
    for target, source in ALIASES.items():
        alias(target, icon(source))

    icon_count = len(files)
    version = version or metadata.get("version") or fields.get("version")
    if version:
        metadata["version"] = version
    if fields.get("author"):
        metadata.setdefault("author", fields["author"])
    files["pack.json"] = (json.dumps(metadata, indent=2) + "\n").encode()
    if len(files["pack.json"]) > 64 * 1024:
        raise ValueError(f"{pack}: metadata exceeds 64 KiB")
    for name in ("LICENSE-ICONS.txt", "LICENSE", "LICENSE.txt"):
        license_path = next((directory / name for directory in (pack, root)
                             if (directory / name).is_file()), None)
        if license_path:
            if license_path.is_symlink() or license_path.stat().st_size > MAX_FILE_SIZE:
                raise ValueError(f"Unsafe or oversized licence: {license_path}")
            files[name] = license_path.read_bytes()
    files["README.md"] = (
        f"# {metadata['name']}\n\n"
        "Copy this folder or its ZIP into `koreader/icons/zen/`.\n"
        "Under Zen Settings > Interface, enable Custom icons,\n"
        "select this pack under Custom icons > Custom icon pack,\n"
        "and restart KOReader. ZenOS automatically extracts pack ZIPs.\n\n"
        "Missing icons use ZenOS and KOReader's bundled artwork.\n"
    ).encode()
    if len(files) > 512 or sum(map(len, files.values())) > 50 * 1024 * 1024:
        raise ValueError(f"{pack}: pack exceeds ZenOS archive limits")
    data = BytesIO()
    with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            if len(content) > MAX_FILE_SIZE:
                raise ValueError(f"Oversized output file: {name}")
            info = zipfile.ZipInfo(f"{pack_id}/{name}", (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content, compresslevel=9)
    if data.tell() > 25 * 1024 * 1024:
        raise ValueError(f"{pack}: ZIP exceeds 25 MiB")
    with zipfile.ZipFile(data) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive failed its CRC check")
    destination = output / f"{pack_id}.zip"
    destination.write_bytes(data.getvalue())
    print(f"Built {destination} ({icon_count} icons)")
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=ROOT,
                        help="Extracted SimpleUI pack folder or repository (default: this repo)")
    parser.add_argument("--output", type=Path, default=Path("dist"), help="Output directory")
    parser.add_argument("--version", help="Override the pack or repository version")
    args = parser.parse_args()
    root, output = args.source.resolve(), args.output.resolve()
    try:
        if not root.is_dir():
            raise ValueError("Source must be an extracted pack folder or repository")
        packs = list(pack_sources(root, output))
        if not packs:
            raise ValueError(f"No icon packs found in {root}")
        metadata = {}
        manifest = root / "pack.json"
        if manifest.is_file():
            if manifest.is_symlink() or manifest.stat().st_size > 64 * 1024:
                raise ValueError(f"Unsafe or oversized manifest: {manifest}")
            metadata = json.loads(manifest.read_text())
            if not isinstance(metadata, dict):
                raise ValueError(f"{manifest}: metadata must be a JSON object")
            if any(key in metadata and not isinstance(metadata[key], str)
                   for key in ("id", "name", "version", "author")):
                raise ValueError(f"{manifest}: id, name, version and author must be strings")
        output.mkdir(parents=True, exist_ok=True)
        seen = set()
        for pack, directories in packs:
            name = lua_strings(pack / "pack.lua").get("name", pack.name)
            pack_id = zen_id(name)
            if pack_id in seen:
                raise ValueError(f"Multiple packs use the same ID: {pack_id}")
            seen.add(pack_id)
            build_pack(pack, directories, root, output, args.version, metadata)
    except (ValueError, OSError, SyntaxError, ET.ParseError, Image.DecompressionBombWarning,
            Image.DecompressionBombError) as error:
        parser.exit(1, f"Build failed: {error}\n")


if __name__ == "__main__":
    main()
