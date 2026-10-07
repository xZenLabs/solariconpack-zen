"""Run with python3 -m unittest discover -s scripts -p 'test_*.py'."""

import importlib.util
from io import BytesIO
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image, PngImagePlugin


spec = importlib.util.spec_from_file_location("builder", Path(__file__).with_name("build-zen-packs.py"))
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><path d="M0 0h48v48z"/></svg>'


class BuildPacksTest(unittest.TestCase):
    def test_repository_variants_preserve_koreader_names_and_build_zen_aliases(self):
        koreader_names = set("""
            align.auto align.center align.justify align.left align.right appbar.contrast appbar.crop
            appbar.filebrowser appbar.menu appbar.navigation appbar.pagefit appbar.pageview
            appbar.pokeball appbar.rotation appbar.search appbar.settings appbar.textsize
            appbar.tools appbar.typeset back.top back.top.rtl book.opened bookmark cancel check
            chevron.first chevron.last chevron.left chevron.right chevron.up close column.one
            column.three column.two control.collapse control.expand control.expand.alpha
            cre.render.partial cre.render.ready cre.render.reload cre.render.reload.alpha
            cre.render.working direction.BTLR direction.BTRL direction.LRBT direction.LRTB
            direction.RLBT direction.RLTB direction.TBLR direction.TBRL dogear.abandoned
            dogear.abandoned.rtl dogear.alpha dogear.complete dogear.complete.rtl dogear.opaque
            dogear.reading edit exit home info move.down move.up notice-info notice-question
            notice-warning plus position.marker position.marker.top rotation.0UR rotation.180UD
            rotation.90CCW rotation.90CW rotation.L.0UR rotation.L.180UD rotation.L.90CCW
            rotation.L.90CW rotation.P.0UR rotation.P.180UD rotation.P.90CCW rotation.P.90CW
            star.empty star.full star.white texture-box triangle wifi wifi.open.0 wifi.open.100
            wifi.open.25 wifi.open.50 wifi.open.75 wifi.secure.0 wifi.secure.100 wifi.secure.25
            wifi.secure.50 wifi.secure.75 zoom.column zoom.content zoom.manual zoom.page zoom.row
        """.split())
        required = set("""
            app_launcher app_menu book_open calendar cloud restart sleep quicksettings
            archive atom avatar battery battery_full battery_half battery_low battery_charging
            blocks book_closed bookshelf calculator close close_light compass coverflow cpu database
            education flame folder folder_open globe grid grid_slide lightning
            lookup.dictionary lookup_dictionary lookup.highlight lookup_highlight
            lookup.vocab_remove lookup_vocab_remove more_vertical network share skip_left
            skip_right speed sun tablet terminal timer toc usb warmth
            appbar.menu appbar.search book.opened home library star.empty
            quick_aa quick_battery quick_bluetooth quick_calibre quick_calibre_dark
            quick_cloud quick_crossword quick_exit quick_filebrowser quick_incognito
            quick_localsend quick_lockdown quick_nightmode quick_opds quick_puzzle
            quick_restart quick_rotate quick_screenshot quick_search quick_sleep
            quick_stats_calendar quick_stats_progress quick_streak quick_sync
            quick_usb quick_wifi quick_zen quick_zlib
            tab_authors tab_books tab_collections tab_continue tab_exit tab_favorites
            tab_filebrowser tab_fm_settings tab_folder tab_history tab_left tab_manga
            appbar.navigation appbar.typeset tab_news tab_right tab_series tab_stats
            tab_tags tab_to_be_read tab_tools tab_translate tab_vocab
        """.split())
        skipped = {"quick_chess", "quick_connections", "quick_notion", "quick_quickrss",
                   "tab_spacer"}
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            packs = list(builder.pack_sources(builder.ROOT, output))
            self.assertEqual(len(packs), 2)
            for pack, directories in packs:
                with self.subTest(pack=pack):
                    sources = {path.name: path for directory in directories
                               for path in directory.rglob("*.svg")}
                    metadata = json.loads((pack / "pack.json").read_text())
                    self.assertFalse(list(pack.rglob("pack.lua")))
                    koreader = next(directory for directory in directories
                                    if directory.name.startswith("KOReader Icons"))
                    self.assertEqual({path.stem for path in koreader.glob("*.svg")}, koreader_names)
                    zen_sources = [path for path in sources.values() if path.parent != koreader]
                    self.assertEqual(len(zen_sources), len({path.read_bytes() for path in zen_sources}))
                    destination = builder.build_pack(pack, directories, builder.ROOT,
                                                     output, None, metadata)
                    with zipfile.ZipFile(destination) as archive:
                        names = {Path(name).stem for name in archive.namelist()
                                 if name.endswith(".svg")}
                        self.assertFalse(required - names, sorted(required - names))
                        self.assertFalse(skipped & names, sorted(skipped & names))
                        prefix = destination.stem + "/"
                        self.assertEqual(len(names), 227)
                        self.assertFalse(any(name.endswith(".lua") for name in archive.namelist()))
                        self.assertEqual(len(archive.namelist()), len(set(archive.namelist())))
                        for name, path in sources.items():
                            self.assertEqual(archive.read(prefix + name), path.read_bytes())
                        for target, source in builder.ALIASES.items():
                            if target + ".svg" not in sources and source in names:
                                self.assertEqual(archive.read(prefix + target + ".svg"),
                                                 archive.read(prefix + source + ".svg"))
                        self.assertEqual(json.loads(archive.read(prefix + "pack.json")), metadata)
                        self.assertFalse({"reading_progress", "zen_mode", "series", "instapaper"}
                                         & names)
                    with patch("sys.argv", ["build-zen-packs.py", str(pack),
                                            "--output", str(output), "--version", "2.3.4"]):
                        builder.main()
                    with zipfile.ZipFile(destination) as archive:
                        self.assertEqual(json.loads(archive.read(prefix + "pack.json")),
                                         dict(metadata, version="2.3.4"))
                        self.assertEqual({Path(name).stem for name in archive.namelist()
                                          if name.endswith((".svg", ".png"))}, names)

    def test_repository_pack_json_metadata_and_cli_override(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pack, output = root / "Pack", root / "output"
            pack.mkdir()
            (pack / "sui_menu.svg").write_bytes(SVG)
            (pack / "pack.lua").write_text(
                'return { name = "Pack", version = "1.0.0", author = "Old artist", }')
            manifest = {"schema_version": 1, "id": "zen-example", "name": "Example for ZenOS",
                        "version": "2.3.4", "author": "Repository artist"}
            (root / "pack.json").write_text(json.dumps(manifest))
            for options, expected in (([], "2.3.4"), (["--version", "3.0.0"], "3.0.0")):
                with self.subTest(options=options), patch("sys.argv", [
                        "build-zen-packs.py", str(root), "--output", str(output), *options]):
                    builder.main()
                    with zipfile.ZipFile(output / "zen-pack.zip") as archive:
                        metadata = json.loads(archive.read("zen-pack/pack.json"))
                        self.assertEqual(metadata, dict(manifest, id="zen-pack",
                                                        name="Pack for ZenOS", version=expected))
            (pack / "pack.json").write_text(json.dumps(manifest))
            with patch("sys.argv", ["build-zen-packs.py", str(pack), "--output", str(output)]):
                builder.main()
            with zipfile.ZipFile(output / "zen-example.zip") as archive:
                self.assertEqual(json.loads(archive.read("zen-example/pack.json")), manifest)
            (pack / "pack.json").write_text(json.dumps(dict(manifest, id="../unsafe")))
            with patch("sys.argv", ["build-zen-packs.py", str(pack), "--output", str(output)]):
                with self.assertRaises(SystemExit), patch("sys.stderr"):
                    builder.main()

    def test_custom_png_map_strips_metadata_and_appended_zip_preserving_pixels(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pack, output = root / "input", root / "output"
            pack.mkdir()
            output.mkdir()
            marker = root / "must-not-exist"
            (pack / "pack.lua").write_text(
                f'os.execute("touch {marker}")\n'
                'return { name = "Night Owl", author = "Test artist", version = "2.3.4",\n'
                'map = { ["sui_action_homescreen"] = "house image.png", sui_search = "lens.svg", }, }\n')
            (pack / "lens.svg").write_bytes(SVG)
            pixels = Image.new("RGBA", (2, 2), (12, 34, 56, 128))
            pixels.putpixel((1, 1), (200, 150, 100, 0))
            metadata = PngImagePlugin.PngInfo()
            metadata.add_text("payload", "metadata must be discarded")
            metadata.add(b"ruSt", b"hidden private chunk")
            original = BytesIO()
            pixels.save(original, format="PNG", pnginfo=metadata, icc_profile=b"fake ICC payload")
            appended = BytesIO()
            with zipfile.ZipFile(appended, "w") as archive:
                archive.writestr("hidden.lua", "untrusted appended file")
            source = original.getvalue() + appended.getvalue()
            (pack / "house image.png").write_bytes(source)

            destination = builder.build_pack(pack, [pack], pack, output, None)

            self.assertFalse(marker.exists())
            self.assertEqual((pack / "house image.png").read_bytes(), source)
            with zipfile.ZipFile(destination) as archive:
                prefix = "zen-night-owl/"
                manifest = json.loads(archive.read(prefix + "pack.json"))
                self.assertEqual(manifest["id"], "zen-night-owl")
                self.assertEqual(manifest["version"], "2.3.4")
                self.assertEqual(manifest["author"], "Test artist")
                self.assertEqual(archive.read(prefix + "appbar.search.svg"), SVG)
                clean = archive.read(prefix + "home.png")
                self.assertEqual(clean, archive.read(prefix + "house-image.png"))
                self.assertNotIn(prefix + "pack.lua", archive.namelist())
            with Image.open(BytesIO(clean)) as image:
                self.assertEqual(image.info, {})
                self.assertEqual(image.convert("RGBA").tobytes(), pixels.tobytes())
            offset, chunks = 8, []
            while offset < len(clean):
                size = struct.unpack_from(">I", clean, offset)[0]
                chunks.append(clean[offset + 4:offset + 8])
                offset += size + 12
            self.assertEqual(offset, len(clean))
            self.assertEqual(chunks, [b"IHDR", b"IDAT", b"IEND"])

    def test_flat_pack_without_manifest_uses_svg_and_png_slot_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary) / "Minimal"
            output = Path(temporary) / "output"
            pack.mkdir()
            output.mkdir()
            (pack / "sui_menu.svg").write_bytes(SVG)
            Image.new("P", (1, 1)).save(pack / "sui_action_wifi_toggle.png")
            Image.new("RGBA", (1, 1)).save(pack / "HOME.PNG")
            self.assertEqual(list(builder.pack_sources(pack, output)), [(pack, [pack])])
            destination = builder.build_pack(pack, [pack], pack, output, "9.0")
            with zipfile.ZipFile(destination) as archive:
                self.assertIn("zen-minimal/appbar.menu.svg", archive.namelist())
                self.assertIn("zen-minimal/quick_wifi.png", archive.namelist())
                self.assertIn("zen-minimal/home.png", archive.namelist())
                self.assertNotIn("zen-minimal/HOME.png", archive.namelist())
                self.assertEqual(json.loads(archive.read("zen-minimal/pack.json"))["version"], "9.0")

    def test_bad_pngs_are_rejected_without_replacing_a_zip(self):
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary) / "Broken"
            output = Path(temporary) / "output"
            pack.mkdir()
            output.mkdir()
            destination = output / "zen-broken.zip"
            destination.write_bytes(b"previous release")
            valid = BytesIO()
            Image.new("RGBA", (2, 2)).save(valid, format="PNG")
            animated = BytesIO()
            Image.new("RGBA", (2, 2), "red").save(
                animated, format="PNG", save_all=True,
                append_images=[Image.new("RGBA", (2, 2), "blue")])
            for name, data in {"empty": b"", "renamed SVG": SVG,
                               "truncated": valid.getvalue()[:24], "animated": animated.getvalue()}.items():
                with self.subTest(name=name):
                    (pack / "icon.png").write_bytes(data)
                    with self.assertRaises((ValueError, OSError, SyntaxError)):
                        builder.build_pack(pack, [pack], pack, output, None)
                    self.assertEqual(destination.read_bytes(), b"previous release")
            (pack / "icon.png").write_bytes(valid.getvalue())
            with patch.object(Image, "MAX_IMAGE_PIXELS", 3):
                with self.assertRaises(Image.DecompressionBombWarning):
                    builder.clean_icon(pack / "icon.png")

    def test_duplicates_missing_maps_and_symlinks_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary) / "Bad"
            output = Path(temporary) / "output"
            pack.mkdir()
            output.mkdir()
            (pack / "home.svg").write_bytes(SVG)
            second = pack / "second"
            second.mkdir()
            (second / "HOME.svg").write_bytes(SVG)
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                builder.build_pack(pack, [pack], pack, output, None)
            (second / "HOME.svg").unlink()
            (pack / "pack.lua").write_text('return { map = { sui_menu = "missing.svg", }, }')
            with self.assertRaisesRegex(ValueError, "missing mapped icon"):
                builder.build_pack(pack, [pack], pack, output, None)
            (pack / "pack.lua").unlink()
            (pack / "linked.svg").symlink_to(pack / "home.svg")
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                builder.build_pack(pack, [pack], pack, output, None)

    def test_discovers_mixed_variants_and_ignores_generated_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            named, plain, output = root / "Named", root / "Plain", root / "output"
            for directory in (named, plain, output):
                directory.mkdir()
                (directory / "sui_menu.svg").write_bytes(SVG)
            (named / "pack.lua").write_text('return { name = "Named", }')
            (output / "pack.lua").write_text('return { name = "Generated", }')
            self.assertEqual(list(builder.pack_sources(root, output)),
                             [(named, [named]), (plain, [plain])])
            (named / "pack.lua").write_text('return { name = computed_name(), }')
            with self.assertRaisesRegex(ValueError, "literal quoted string"):
                builder.lua_strings(named / "pack.lua")
            self.assertEqual(builder.zen_id("Lumière"), "zen-lumiere")
            self.assertRegex(builder.zen_id("夜猫"), r"^zen-[a-f0-9]{12}$")


if __name__ == "__main__":
    unittest.main()
