import json
from pathlib import Path
import unittest
import yaml

class MetadataTests(unittest.TestCase):
    def test_release_metadata(self):
        root = Path(__file__).resolve().parents[1]
        cff = yaml.safe_load((root / "CITATION.cff").read_text())
        zenodo = json.loads((root / ".zenodo.json").read_text())
        self.assertEqual(cff["version"], zenodo["version"])
        self.assertEqual(cff["authors"][0]["name"], "LX20 Law Firm")
        self.assertNotIn("doi", cff)
        for name in ("LICENSE", "LICENSE-DATA", "README.md", "CONTRIBUTING.md"):
            self.assertTrue((root / name).read_text().strip())

    def test_ci_only_tests_and_lint(self):
        root = Path(__file__).resolve().parents[1]
        workflow = yaml.safe_load((root / ".github/workflows/tests.yml").read_text())
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertEqual(set(workflow["jobs"]), {"test"})
