"""Preview cells must contain one icon and its exact lookup name."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET


spec = importlib.util.spec_from_file_location("previews", Path(__file__).with_name("build-previews.py"))
previews = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previews)


class BuildPreviewsTest(unittest.TestCase):
    def test_each_lookup_has_one_rendering_and_one_label(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = [Path(temporary) / name for name in ("tab_left.svg", "tab_right.svg", "toc.svg")]
            for path in paths:
                path.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"/>')
            root = ET.fromstring(previews.overview_svg(paths, 2))
            namespace = {"svg": previews.SVG_NS}
            self.assertEqual(len(root.findall("svg:svg", namespace)), len(paths))
            self.assertEqual([label.text for label in root.findall("svg:text", namespace)],
                             [path.stem for path in paths])
            self.assertEqual(root.attrib["viewBox"], "0 0 360 288")


if __name__ == "__main__":
    unittest.main()
