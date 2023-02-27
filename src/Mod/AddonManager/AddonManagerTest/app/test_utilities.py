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

import unittest
import os
import sys

sys.path.append("../../")  # So the IDE can find the imports below when running tests

from addonmanager_utilities import (
    recognized_git_location,
    get_readme_url,
    get_assigned_string_literal,
    get_macro_version_from_file,
)

from mocks import MockAddon


class TestUtilities(unittest.TestCase):
    MODULE = "test_utilities"  # file name without extension

    def setUp(self):
        self.test_dir = os.path.join(os.path.dirname(__file__), "..", "data")

    def test_recognized_git_location_good(self):
        recognized_urls = [
            "https://github.com/FreeCAD/FreeCAD",
            "https://gitlab.com/freecad/FreeCAD",
            "https://framagit.org/freecad/FreeCAD",
            "https://salsa.debian.org/science-team/freecad",
        ]
        for url in recognized_urls:
            with self.subTest(url=url):
                repo = MockAddon("Test Repo", url=url, branch="main")
                self.assertTrue(
                    recognized_git_location(repo),
                    f"{url} was unexpectedly not recognized",
                )

    def test_recognized_git_location_bad(self):
        unrecognized_urls = [
            "https://google.com",
            "https://freecad.org",
            "https://not.quite.github.com/FreeCAD/FreeCAD",
            "https://github.com.malware.com/",
        ]
        for url in unrecognized_urls:
            with self.subTest(url=url):
                repo = MockAddon("Test Repo", url=url, branch="main")
                self.assertFalse(
                    recognized_git_location(repo), f"{url} was unexpectedly recognized"
                )

    def test_get_readme_url_github(self):
        github_urls = [
            "https://github.com/FreeCAD/FreeCAD",
        ]
        for url in github_urls:
            with self.subTest(url=url):
                branch = "branchname"
                expected_result = f"{url}/raw/{branch}/README.md"
                repo = MockAddon("Test Repo", url=url, branch=branch)
                actual_result = get_readme_url(repo)
                self.assertEqual(actual_result, expected_result)

    def test_get_readme_url_gitlab(self):
        gitlab_urls = [
            "https://gitlab.com/freecad/FreeCAD",
            "https://framagit.org/freecad/FreeCAD",
            "https://salsa.debian.org/science-team/freecad",
            "https://unknown.location/and/path",
        ]

        for url in gitlab_urls:
            with self.subTest(url=url):
                branch = "branchname"
                expected_result = f"{url}/-/raw/{branch}/README.md"
                repo = MockAddon("Test Repo", url=url, branch=branch)
                actual_result = get_readme_url(repo)
                self.assertEqual(actual_result, expected_result)

    def test_get_assigned_string_literal_good(self):
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

    def test_get_assigned_string_literal_bad(self):
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

    def test_get_macro_version_from_file_good(self):
        good_file = os.path.join(self.test_dir, "good_macro_metadata.FCStd")
        version = get_macro_version_from_file(good_file)
        self.assertEqual(version, "1.2.3")

    def test_get_macro_version_from_file_bad(self):
        bad_file = os.path.join(self.test_dir, "bad_macro_metadata.FCStd")
        version = get_macro_version_from_file(bad_file)
        self.assertEqual(version, "", "Bad version did not yield empty string")

    def test_get_macro_version_from_file_missing(self):
        empty_file = os.path.join(self.test_dir, "missing_macro_metadata.FCStd")
        version = get_macro_version_from_file(empty_file)
        self.assertEqual(version, "", "Missing version did not yield empty string")
