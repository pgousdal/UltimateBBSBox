import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class SchemaValidationTests(unittest.TestCase):
    def test_example_manifests_validate(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "ubb-schema.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
