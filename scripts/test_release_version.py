"""Run with python3 -m unittest discover -s scripts -p 'test_*.py'."""

import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location(
    "release_version", Path(__file__).with_name("next-release-version.py"))
release_version = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_version)


class ReleaseVersionTest(unittest.TestCase):
    def test_next_patch_uses_highest_numeric_version_and_rejects_invalid_baselines(self):
        for version, tags, expected in (
                ("1.0.0", [], "1.0.1"),
                ("1.0.0", ["v1.0.0", "v1.0.9", "v1.0.10"], "1.0.11"),
                ("2.0.0", ["v1.9.99"], "2.0.1"),
                ("1.0.0", ["v2.3.4"], "2.3.5"),
                ("1.0.0", ["v9.0.0-rc.1", "vnext", "v1.0", "1.0.99"], "1.0.1")):
            with self.subTest(version=version, tags=tags):
                self.assertEqual(release_version.next_version(version, tags), expected)
        for version in (None, 1, "1.0", "v1.0.0", "01.0.0", "1.0.0-rc.1"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                release_version.next_version(version, [])


if __name__ == "__main__":
    unittest.main()
