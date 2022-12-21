# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2022 FreeCAD Project Association                        *
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

"""Tests for adonmanager_macro_source_git.py"""

import os
from pickle import NONE
import tempfile
from datetime import datetime, timezone, timedelta
import time
import unittest
import zipfile

import FreeCAD

from addonmanager_macro_source_git import MacroDataSourceGit
from AddonManagerTest.app.mocks import (
    AddonSignalCatcher,
    MockMacro,
    MockAddon,
    MockGitManager,
)


class MockAddonFactory:
    @classmethod
    def from_macro(cls, macro):
        addon = MockAddon(name=macro.name)
        addon.macro = macro
        addon.name = macro.name
        return addon


class MockMacroFactory:
    def create_macro(self, name):
        return MockMacro(name)


class TestMacroSourceGit(unittest.TestCase):
    def setUp(self):
        self.test_object = MacroDataSourceGit()
        self.test_object.addon_factory = MockAddonFactory()
        self.test_object.macro_factory = MockMacroFactory()
        self.test_dir = os.path.join(
            FreeCAD.getHomePath(), "Mod", "AddonManager", "AddonManagerTest", "data"
        )
        self.signal_catcher = AddonSignalCatcher()
        self.test_object.addon_found.connect(self.signal_catcher.catch_signal)

    def tearDown(self):
        pass

    ###############################################################################################
    #                                                                                             #
    #                                         UNIT TESTS                                          #
    #                                                                                             #
    ###############################################################################################

    def test_should_update_forced(self):
        """When an update is forced, the should_update function returns True"""
        self.test_object.force_update = True
        self.assertTrue(self.test_object.should_update())

    def test_should_update_git(self):
        """When git is available, should_update always returns True"""
        self.test_object.git_manager = (
            True  # Any non-none value should work for the test
        )
        self.assertTrue(self.test_object.should_update())

    def test_should_update_no_cache(self):
        """When there is no local cache, should_update returns True"""
        self.test_object.macro_cache_location = "/some/path/that/does/not/exist"
        self.assertTrue(self.test_object.should_update())

    def test_should_update_latest_update_long_ago(self):
        """If the latest macro update was not recent, no update is requested"""
        self.test_object.git_manager = None
        self.test_object.force_update = False
        self.test_object.macro_update_stats = {
            "Addon1": datetime(1999, 12, 28, 19, 5, tzinfo=timezone.utc).timestamp(),
            "Addon2": datetime(1989, 11, 27, 18, 4, tzinfo=timezone.utc).timestamp(),
            "Addon3": datetime(1979, 12, 31, 18, 4, tzinfo=timezone.utc).timestamp(),
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(os.path.join(temp_dir, "README.md"), "w", encoding="utf-8") as f:
                f.write("## Fake README file for unit testing")  # Timestamp is now
            self.test_object.macro_cache_location = temp_dir
            self.assertFalse(self.test_object.should_update())

    def test_should_update_latest_update_now(self):
        """If the latest macro update was recent, an update is requested"""
        self.test_object.git_manager = None
        self.test_object.force_update = False
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(os.path.join(temp_dir, "README.md"), "w", encoding="utf-8") as f:
                f.write("## Fake README file for unit testing")  # Timestamp is now
            self.test_object.macro_update_stats = {
                "Addon1": datetime.now(tz=timezone.utc).timestamp()
                + 10.0  # The future!
            }
            self.test_object.macro_cache_location = temp_dir
            self.assertTrue(self.test_object.should_update())

    def test_should_update_zero_increment(self):
        """If the update frequency is zero, an update is always requested"""
        self.test_object.git_manager = None
        self.test_object.force_update = False
        self.test_object.update_frequency = 0  # Days
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(os.path.join(temp_dir, "README.md"), "w", encoding="utf-8") as f:
                f.write("## Fake README file for unit testing")  # Timestamp is now
            self.test_object.macro_cache_location = temp_dir
            self.assertTrue(self.test_object.should_update())

    def test_should_update_after_seven_days(self):
        """If the update frequency is seven, and the file age is over that, an update is requested"""
        self.test_object.git_manager = None
        self.test_object.force_update = False
        self.test_object.update_frequency = 7  # Days
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(os.path.join(temp_dir, "README.md"), "w", encoding="utf-8") as f:
                f.write("## Fake README file for unit testing")  # Timestamp is now

            system_tz = datetime.now().astimezone().tzinfo
            one_week_ago = datetime.now(tz=system_tz) - timedelta(days=7)
            mod_time = time.mktime(one_week_ago.timetuple())
            os.utime(os.path.join(temp_dir, "README.md"), (mod_time, mod_time))
            self.test_object.macro_cache_location = temp_dir
            self.assertTrue(self.test_object.should_update())

    def test_should_update_after_almost_freq_days(self):
        """If the frequency rounds to freq, and the file age is over that, an update is requested"""
        self.test_object.git_manager = None
        self.test_object.force_update = False
        self.test_object.update_frequency = 4  # Days
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(os.path.join(temp_dir, "README.md"), "w", encoding="utf-8") as f:
                f.write("## Fake README file for unit testing")  # Timestamp is now
            system_tz = datetime.now().astimezone().tzinfo
            almost_four_days_ago = datetime.now(tz=system_tz) - timedelta(
                days=3, hours=13
            )
            mod_time = time.mktime(almost_four_days_ago.timetuple())
            os.utime(os.path.join(temp_dir, "README.md"), (mod_time, mod_time))
            self.test_object.macro_cache_location = temp_dir
            self.assertTrue(self.test_object.should_update())

    def test_get_latest_update_from_stats_normal(self):
        """For a normal dictionary, we get the largest time"""
        test_data = {
            "Addon1": datetime(2022, 12, 28, 19, 5, tzinfo=timezone.utc).timestamp(),
            "Addon2": datetime(2021, 11, 27, 18, 4, tzinfo=timezone.utc).timestamp(),
            "Addon3": datetime(2020, 12, 31, 18, 4, tzinfo=timezone.utc).timestamp(),
        }
        latest = self.test_object.get_latest_update_from_stats(test_data)
        self.assertEqual(latest, datetime(2022, 12, 28, 19, 5, tzinfo=timezone.utc))

    def test_get_latest_update_from_stats_empty(self):
        """If the last_update array is empty, we get the equivalent of the epoch"""
        test_data = {}
        latest = self.test_object.get_latest_update_from_stats(test_data)
        self.assertEqual(latest, datetime.fromtimestamp(0.0, tz=timezone.utc))

    def test_get_latest_update_from_stats_bad_type(self):
        """If the data passed into the function is not a dict, we raise a TypeError"""
        with self.assertRaises(TypeError):
            test_data = "What is this??"
            self.test_object.get_latest_update_from_stats(test_data)

    def test_get_latest_update_from_stats_bad_content(self):
        """If the data passed into the function is not a float, we raise a TypeError"""
        with self.assertRaises(TypeError):
            test_data = {"Key": "Not a float"}
            self.test_object.get_latest_update_from_stats(test_data)

    def test_create_addon_for_macro_normal(self):
        """A macro-type Addon is created for a FCMacro file, and it is set up correctly"""
        self.test_object.macro_git_address = "TestAddress"
        self.test_object.macro_git_branch = "test_branch"
        with tempfile.TemporaryDirectory() as temp_dir:
            with open("UnitTestMacro.FCMacro", "w", encoding="utf-8") as f:
                f.write(
                    "# Fake macro for unit testing\n"
                    "import FreeCAD\n"
                    "FreeCAD.Console.Print('Hello, world')\n"
                )
            test_macro = self.test_object.create_addon_for_macro(
                os.path.join(temp_dir, "UnitTestMacro.FCMacro")
            )
            self.assertEqual(test_macro.url, "TestAddress")
            self.assertEqual(test_macro.branch, "test_branch")
            self.assertIsNotNone(test_macro.macro)
            self.assertTrue(test_macro.macro.details_filled_from_file)

    def test_scan_for_macros_normal(self):
        """A folder full of macros returns all FCMacro file paths, and nothing else"""
        macro_files = ["TestMacro1.FCMacro", "TestMacro2.FCMacro", "TestMacro3.FCMacro"]
        other_files = ["NotAMacro.txt", "NotAMacroEither.FCStd", "StillNotAMacro.py"]
        subdir_macro_files = ["TestMacroA.FCMacro", "TestMacroB.FCMacro"]
        git_dir_macro_files = ["GitdirMacroA.FCMacro", "GitdirMacroB.FCMacro"]
        with tempfile.TemporaryDirectory() as temp_dir:
            os.mkdir(os.path.join(temp_dir, "sub"))
            os.mkdir(os.path.join(temp_dir, ".git"))
            expected_results = []
            for m in macro_files:
                with open(os.path.join(temp_dir, m), "w", encoding="utf-8") as f:
                    f.write("# Fake macro file for unit testing: should be found")
                expected_results.append(os.path.join(temp_dir, m))
            for m in other_files:
                with open(os.path.join(temp_dir, m), "w", encoding="utf-8") as f:
                    f.write(
                        "# Fake non-macro file for unit testing: should NOT be found"
                    )
            for m in subdir_macro_files:
                with open(os.path.join(temp_dir, "sub", m), "w", encoding="utf-8") as f:
                    f.write("# Fake macro file for unit testing: should be found")
                expected_results.append(os.path.join(temp_dir, "sub", m))
            for m in git_dir_macro_files:
                with open(
                    os.path.join(temp_dir, ".git", m), "w", encoding="utf-8"
                ) as f:
                    f.write(
                        "# Fake macro file for unit testing, located in .git: should NOT be found"
                    )

            self.test_object.macro_cache_location = temp_dir
            results = self.test_object.scan_for_macros()
            self.assertListEqual(results, expected_results)

    def test_scan_for_macros_no_such_path(self):
        self.test_object.macro_cache_location = "/no/such/path"
        with self.assertRaises(OSError):
            self.test_object.scan_for_macros()

    def test_get_zipped_data_with_zip(self):
        test_file = os.path.join(self.test_dir, "test_repo.zip")
        url = "file://localhost/" + test_file.replace(os.path.sep, "/")
        self.test_object.macro_git_address = url
        actual_data = self.test_object.get_zipped_data()
        self.assertEqual(len(actual_data), 23052)

    def test_update_with_git_new_clone(self):
        """When no local cache exists, git clones a new copy"""
        self.test_object.git_manager = MockGitManager()
        self.test_object.macro_cache_location = os.path.join("Non", "Existant", "Path")
        self.test_object.update_with_git()
        self.assertListEqual(self.test_object.git_manager.called_methods, ["clone"])

    def test_update_with_git_update_normal(self):
        """When a local cache exists, git uses pull to update it"""
        with tempfile.TemporaryDirectory() as temp_dir:
            os.mkdir(os.path.join(temp_dir, ".git"))
            self.test_object.git_manager = MockGitManager()
            self.test_object.macro_cache_location = temp_dir
            self.test_object.update_with_git()
            self.assertListEqual(
                self.test_object.git_manager.called_methods, ["update"]
            )

    def test_update_with_git_non_git_cache(self):
        """When the current cache has no .git, it is repaired and updated"""
        with tempfile.TemporaryDirectory() as temp_dir:
            self.test_object.git_manager = MockGitManager()
            self.test_object.macro_cache_location = temp_dir
            self.test_object.update_with_git()
            self.assertListEqual(
                self.test_object.git_manager.called_methods, ["repair", "update"]
            )

    def test_update_with_git_broken_repo(self):
        """When the local repo is damaged, git re-clones"""
        with tempfile.TemporaryDirectory() as temp_dir:
            self.test_object.macro_cache_location = os.path.join(
                temp_dir, "cache_test_dir"
            )
            os.mkdir(self.test_object.macro_cache_location)
            os.mkdir(os.path.join(self.test_object.macro_cache_location, ".git"))
            self.test_object.git_manager = MockGitManager()
            self.test_object.git_manager.should_fail = True
            self.test_object.git_manager.fail_once = True
            self.test_object.update_with_git()
            self.assertListEqual(
                self.test_object.git_manager.called_methods, ["update", "clone"]
            )

    def test_update_with_git_broken_repo_deep_fail(self):
        """When the damaged repo recloning fails, False is returned"""
        with tempfile.TemporaryDirectory() as temp_dir:
            self.test_object.macro_cache_location = os.path.join(
                temp_dir, "cache_test_dir"
            )
            os.mkdir(self.test_object.macro_cache_location)
            os.mkdir(os.path.join(self.test_object.macro_cache_location, ".git"))
            self.test_object.git_manager = MockGitManager()
            self.test_object.git_manager.should_fail = True
            self.test_object.git_manager.fail_once = (
                False  # Fail on the re-clone as well
            )
            result = self.test_object.update_with_git()
            self.assertFalse(
                result, "update_with_git returned True even after a total failure"
            )

    ###############################################################################################
    #                                                                                             #
    #                                     INTEGRATION TESTS                                       #
    #                                                                                             #
    ###############################################################################################
