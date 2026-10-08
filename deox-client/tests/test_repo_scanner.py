import os
import tempfile
import unittest
from unittest import mock

from src.database import Database
from src.repo_scanner import parse_deb_filename, scan_deb, scan_pool


class ParseDebFilenameTests(unittest.TestCase):
    def test_parses_package_version_and_architecture(self):
        self.assertEqual(
            parse_deb_filename("demo-tool_1:2.0~rc1-3_amd64.deb"),
            {"name": "demo-tool", "version": "1:2.0~rc1-3",
             "architecture": "amd64"},
        )

    def test_rejects_malformed_names(self):
        for filename in ("demo-tool.deb", "demo_tool_1.0_amd64.deb",
                         "demo-tool_1.0_bad_arch.deb", "demo-tool_1.0_amd64.zip"):
            with self.subTest(filename=filename):
                self.assertIsNone(parse_deb_filename(filename))


class ScanDebTests(unittest.TestCase):
    def test_filename_is_authoritative_and_control_fields_are_optional(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "demo-tool_2.4-1_all.deb")
            contents = b"not a real deb, but the filename can still be indexed"
            with open(path, "wb") as package_file:
                package_file.write(contents)

            control = (
                "Package: different-control-name\n"
                "Version: 9.9\n"
                "Architecture: arm64\n"
                "Installed-Size: 3\n"
                "Depends: libc6 (>= 2.34)\n"
                "Description: Example package\n"
                " Longer package description\n"
            )
            with mock.patch("src.repo_scanner.utils.run_cmd",
                            return_value=(0, control, "")):
                package, dependencies = scan_deb(path)

        self.assertEqual(package["name"], "demo-tool")
        self.assertEqual(package["version"], "2.4-1")
        self.assertEqual(package["architecture"], "all")
        self.assertEqual(package["filename"], "demo-tool_2.4-1_all.deb")
        self.assertEqual(package["description"], "Example package")
        self.assertEqual(package["long_description"], "Longer package description")
        self.assertEqual(package["installed_size"], 3 * 1024)
        self.assertEqual(len(package["sha256"]), 64)
        self.assertEqual(len(package["md5sum"]), 32)
        self.assertEqual(dependencies[0]["dep_name"], "libc6 (>= 2.34)")
        self.assertEqual(dependencies[0]["dep_version"], "2.34")

    def test_lfs_pointer_creates_a_database_row_without_reading_deb_contents(self):
        expected_sha256 = "a" * 64
        pointer = (
            "version https://git-lfs.github.com/spec/v1\n"
            "oid sha256:%s\n"
            "size 79541548\n" % expected_sha256
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            pool_dir = os.path.join(temp_dir, "deoxpool")
            os.makedirs(pool_dir)
            package_path = os.path.join(
                pool_dir, "absolute-browser_1.0.0_amd64.deb")
            with open(package_path, "w", encoding="ascii") as package_file:
                package_file.write(pointer)
            db_path = os.path.join(temp_dir, "db", "deox.db")

            with mock.patch("src.repo_scanner.utils.run_cmd") as run_cmd:
                summary = scan_pool(pool_dir, db_path)

            run_cmd.assert_not_called()
            self.assertEqual(summary["scanned"], 1)
            self.assertEqual(summary["skipped"], [])
            package = Database(db_path).get_package("absolute-browser")

        self.assertEqual(package["version"], "1.0.0")
        self.assertEqual(package["architecture"], "amd64")
        self.assertEqual(package["filename"], "absolute-browser_1.0.0_amd64.deb")
        self.assertEqual(package["size"], 79541548)
        self.assertEqual(package["sha256"], expected_sha256)
        self.assertIsNone(package["md5sum"])
        self.assertEqual(package["description"], "absolute-browser")


if __name__ == "__main__":
    unittest.main()
