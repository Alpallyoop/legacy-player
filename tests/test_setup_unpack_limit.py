import unittest
from unittest import mock

from launcher import setup


def listing(*sizes):
    blocks = "\n\n".join(f"Path = f{i}.bin\nSize = {n}\nAttributes = A" for i, n in enumerate(sizes))
    return "7-Zip\n\nPath = a.7z\nType = 7z\n----------\n" + blocks + "\n"


class UnpackLimit(unittest.TestCase):
    def test_total_is_the_sum_of_the_entries(self):
        self.assertEqual(600, setup._total_size_7z(listing(100, 200, 300)))
        self.assertEqual(0, setup._total_size_7z("nothing useful"))

    def test_a_7z_that_unpacks_to_tens_of_gigabytes_is_refused_before_anything_is_written(self):
        import tempfile
        from pathlib import Path
        big = listing(30 * 1024 ** 3)
        ran = []

        def run(command):
            ran.append(command)
            return mock.Mock(returncode=0, stdout=big, stderr="")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(setup, "_seven_zip_tools", return_value=[("7z", "7z")]), \
             mock.patch.object(setup, "_run_tool", run):
            with self.assertRaises(setup.SetupError) as ctx:
                setup.extract_7z(Path(tmp) / "a.7z", Path(tmp) / "out", "Test")
        self.assertIn("far more", str(ctx.exception))
        self.assertEqual(1, len(ran))                                  # only the listing ran, never the extraction


if __name__ == "__main__":
    unittest.main()
