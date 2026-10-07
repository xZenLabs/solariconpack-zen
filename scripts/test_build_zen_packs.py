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
