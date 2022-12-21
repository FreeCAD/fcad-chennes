# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2022-2023 FreeCAD Project Association                   *
# *                                                                         *
# *   This file is part of FreeCAD.                                         *
# *                                                                         *
# *   FreeCAD is free software: you can redistribute it and/or modify it    *
# *   under the terms of the GNU Lesser General Public License as           *
# *   published by the Free Software Foundation, either version 2.1 of the  *
# *   License, or (at your option) any later version.                       *
# *                                                                         *
# *   FreeCAD is distributed in the hope that it will be useful, but        *
# *   WITHOUT ANY WARRANTY; without even the implied warranty of            *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU      *
# *   Lesser General Public License for more details.                       *
# *                                                                         *
# *   You should have received a copy of the GNU Lesser General Public      *
# *   License along with FreeCAD. If not, see                               *
# *   <https://www.gnu.org/licenses/>.                                      *
# *                                                                         *
# ***************************************************************************

import importlib
import io
import tempfile
import unittest
import os
import zipfile
import FreeCAD

from Addon import Addon

from addonmanager_utilities import (
    recognized_git_location,
    get_readme_url,
    get_assigned_string_literal,
    get_macro_version_from_file,
    blocking_get,
    clean_git_url,
    extract_git_repo_zipfile,
    construct_git_url,
)

do_network_tests = False


class TestUtilities(unittest.TestCase):

    MODULE = "test_utilities"  # file name without extension

    def setUp(self):
        self.test_dir = os.path.join(
            FreeCAD.getHomePath(), "Mod", "AddonManager", "AddonManagerTest", "data"
        )

    def test_recognized_git_location(self):
        recognized_urls = [
            "https://github.com/FreeCAD/FreeCAD",
            "https://gitlab.com/freecad/FreeCAD",
            "https://framagit.org/freecad/FreeCAD",
            "https://salsa.debian.org/science-team/freecad",
        ]
        for url in recognized_urls:
            with self.subTest(url=url):
                repo = Addon("Test Repo", url, Addon.Status.NOT_INSTALLED, "branch")
                self.assertTrue(
                    recognized_git_location(repo),
                    f"{url} was unexpectedly not recognized",
                )

        unrecognized_urls = [
            "https://google.com",
            "https://freecad.org",
            "https://not.quite.github.com/FreeCAD/FreeCAD",
            "https://github.com.malware.com/",
        ]
        for url in unrecognized_urls:
            with self.subTest(url=url):
                repo = Addon("Test Repo", url, Addon.Status.NOT_INSTALLED, "branch")
                self.assertFalse(
                    recognized_git_location(repo), f"{url} was unexpectedly recognized"
                )

    def test_get_readme_url(self):
        github_urls = [
            "https://github.com/FreeCAD/FreeCAD",
        ]
        gitlab_urls = [
            "https://gitlab.com/freecad/FreeCAD",
            "https://framagit.org/freecad/FreeCAD",
            "https://salsa.debian.org/science-team/freecad",
            "https://unknown.location/and/path",
        ]

        # GitHub and Gitlab have two different schemes for file URLs: unrecognized URLs are
        # presumed to be local instances of a GitLab server. Note that in neither case does this
        # take into account the redirects that are used to actually fetch the data.

        for url in github_urls:
            branch = "branchname"
            expected_result = f"{url}/raw/{branch}/README.md"
            repo = Addon("Test Repo", url, Addon.Status.NOT_INSTALLED, branch)
            actual_result = get_readme_url(repo)
            self.assertEqual(actual_result, expected_result)

        for url in gitlab_urls:
            branch = "branchname"
            expected_result = f"{url}/-/raw/{branch}/README.md"
            repo = Addon("Test Repo", url, Addon.Status.NOT_INSTALLED, branch)
            actual_result = get_readme_url(repo)
            self.assertEqual(actual_result, expected_result)

    def test_get_assigned_string_literal(self):
        good_lines = [
            ["my_var = 'Single-quoted literal'", "Single-quoted literal"],
            ['my_var = "Double-quoted literal"', "Double-quoted literal"],
            ["my_var   =  \t 'Extra whitespace'", "Extra whitespace"],
            ["my_var   =  42", "42"],
            ["my_var   =  1.23", "1.23"],
        ]
        for line in good_lines:
            with self.subTest(line=line):
                result = get_assigned_string_literal(line[0])
                self.assertEqual(result, line[1])

        bad_lines = [
            "my_var = __date__",
            "my_var 'No equals sign'",
            "my_var = 'Unmatched quotes\"",
            "my_var = No quotes at all",
            "my_var = 1.2.3",
        ]
        for line in bad_lines:
            with self.subTest(line=line):
                result = get_assigned_string_literal(line)
                self.assertIsNone(result)

    def test_get_macro_version_from_file(self):
        good_file = os.path.join(self.test_dir, "good_macro_metadata.FCStd")
        version = get_macro_version_from_file(good_file)
        self.assertEqual(version, "1.2.3")

        bad_file = os.path.join(self.test_dir, "bad_macro_metadata.FCStd")
        version = get_macro_version_from_file(bad_file)
        self.assertEqual(version, "", "Bad version did not yield empty string")

        empty_file = os.path.join(self.test_dir, "missing_macro_metadata.FCStd")
        version = get_macro_version_from_file(empty_file)
        self.assertEqual(version, "", "Missing version did not yield empty string")

    @unittest.skipUnless(do_network_tests, "Network-accessing tests disabled")
    def test_blocking_get_returns_bytes_qnam(self):
        """QNAM network access should give an object that can be decoded"""
        if not FreeCAD.GuiUp:
            self.skipTest(
                "GUI is not up, cannot test QtNetworkAccessManager-based code"
            )

        binary_data = blocking_get(
            "https://api.github.com/zen", method="networkmanager"
        )
        self.assertTrue(hasattr(binary_data, "decode"))

    @unittest.skipUnless(do_network_tests, "Network-accessing tests disabled")
    def test_blocking_get_returns_bytes_requests(self):
        """requests lib network access should give an object that can be decoded"""
        try:
            loader = importlib.find_loader("requests")
            if not loader:
                self.skipTest("No requests import available")
        except:
            self.skipTest("No requests import available")

        binary_data = blocking_get("https://api.github.com/zen", method="requests")
        self.assertTrue(hasattr(binary_data, "decode"))

    @unittest.skipUnless(do_network_tests, "Network-accessing tests disabled")
    def test_blocking_get_returns_bytes_urllib(self):
        """urllib network access should give an object that can be decoded"""
        binary_data = blocking_get("https://api.github.com/zen", method="urllib")
        self.assertTrue(hasattr(binary_data, "decode"))

    def test_clean_url_no_change(self):
        """Test that an already clean URL is unaltered, and the name is extracted"""
        test_data = {"url": "https://github.com/Test/TestRepo"}
        clean_git_url(test_data)
        self.assertEqual(test_data["url"], "https://github.com/Test/TestRepo")
        self.assertIn("name", test_data)
        self.assertEqual(test_data["name"], "TestRepo")

    def test_clean_url_remove_git(self):
        """Test that .git URL is changed to remove the extensions, and the name is extracted"""
        test_data = {"url": "https://github.com/Test/TestRepo.git"}
        clean_git_url(test_data)
        self.assertEqual(test_data["url"], "https://github.com/Test/TestRepo")
        self.assertIn("name", test_data)
        self.assertEqual(test_data["name"], "TestRepo")

    def test_clean_url_remove_trailing_slash(self):
        """Test that a trailing slash is removed, and the name is extracted"""
        test_data = {"url": "https://github.com/Test/TestRepo/"}
        clean_git_url(test_data)
        self.assertEqual(test_data["url"], "https://github.com/Test/TestRepo")
        self.assertIn("name", test_data)
        self.assertEqual(test_data["name"], "TestRepo")

    def test_extract_git_repo_zipfile_fromfile_nobranch(self):
        """ZIP data in a file is extracted when the branch is non-existent"""
        with tempfile.TemporaryDirectory() as temp_dir:
            filename = os.path.join(temp_dir, "test.zip")
            with zipfile.ZipFile(filename, "w") as zf:
                with zf.open("testfile.txt", "w") as f:
                    f.write("This is test data for unit testing".encode("utf-8"))
            extract_git_repo_zipfile(filename, temp_dir, "this_is_not_a_real_branch")
            self.assertTrue(os.path.exists(os.path.join(temp_dir, "testfile.txt")))

    def test_extract_git_repo_zipfile_fromdata_nobranch(self):
        """ZIP data in a bytes object is extracted when the branch is non-existent"""
        with tempfile.TemporaryDirectory() as temp_dir:
            byte_stream = io.BytesIO()
            with zipfile.ZipFile(byte_stream, "w") as zf:
                with zf.open("testfile.txt", "w") as f:
                    f.write("This is test data for unit testing".encode("utf-8"))
            extract_git_repo_zipfile(
                byte_stream.getbuffer(), temp_dir, "this_is_not_a_real_branch"
            )
            self.assertTrue(os.path.exists(os.path.join(temp_dir, "testfile.txt")))

    def test_extract_git_repo_zipfile_fromfile_branch(self):
        """ZIP data in a file is extracted when the branch matches"""
        with tempfile.TemporaryDirectory() as temp_dir:
            target_dir = os.path.join(temp_dir, "extracted_data")
            filename = os.path.join(temp_dir, "test.zip")
            with zipfile.ZipFile(filename, "w") as zf:
                with zf.open("main/testfile.txt", "w") as f:
                    f.write("This is test data for unit testing".encode("utf-8"))
            extract_git_repo_zipfile(filename, target_dir, "main")
            self.assertTrue(os.path.exists(os.path.join(target_dir, "testfile.txt")))

    def test_extract_git_repo_zipfile_fromdata_branch(self):
        """ZIP data in a bytes object is extracted when the branch matches"""
        with tempfile.TemporaryDirectory() as temp_dir:
            byte_stream = io.BytesIO()
            with zipfile.ZipFile(byte_stream, "w") as zf:
                with zf.open("main/testfile.txt", "w") as f:
                    f.write("This is test data for unit testing".encode("utf-8"))
            extract_git_repo_zipfile(byte_stream.getbuffer(), temp_dir, "main")
            self.assertTrue(os.path.exists(os.path.join(temp_dir, "testfile.txt")))

    def test_construct_git_url_localhost(self):
        """Local file git url generates unmodified url"""
        local_path_base = "file://localhost/some/local/path"
        addon = self.given_fake_addon_with_url(local_path_base)
        returned_url = construct_git_url(addon, "basic_test.txt")
        self.assertEqual(returned_url, f"{local_path_base}/basic_test.txt")

    def test_construct_git_url_github(self):
        """GitHub addon generates url with the form base/raw/branch/filename"""
        path_base = "https://github.com/some/repo/"
        addon = self.given_fake_addon_with_url(path_base)
        returned_url = construct_git_url(addon, "basic_test.txt")
        self.assertEqual(returned_url, f"{path_base}/raw/test_branch/basic_test.txt")

    def test_construct_git_url_known_gitlab_hosts(self):
        """Gitlab-style hosts generate url with the form base/raw/branch/filename"""
        known_hosts = ["gitlab.com", "framagit.org", "salsa.debian.org"]
        for host in known_hosts:
            with self.subTest(host=host):
                path_base = f"https://{host}/some/repo/"
                addon = self.given_fake_addon_with_url(path_base)
                returned_url = construct_git_url(addon, "basic_test.txt")
                self.assertEqual(returned_url, f"{path_base}/-/raw/test_branch/basic_test.txt")

    def test_construct_git_url_unknown_host(self):
        """Unrecognized locations are treated as Gitlab instances"""
        path_base = f"https://some.fake.server.com/some/repo/"
        addon = self.given_fake_addon_with_url(path_base)
        returned_url = construct_git_url(addon, "basic_test.txt")
        self.assertEqual(returned_url, f"{path_base}/-/raw/test_branch/basic_test.txt")

    def given_fake_addon_with_url(self, url) -> object:
        class FakeAddon:
            def __init__(self, url):
                self.url = url
                self.branch = "test_branch"
        return FakeAddon(url)