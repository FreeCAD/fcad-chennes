# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2023 FreeCAD Project Association                        *
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

"""Tests for addonmanager_source_local_cache.py"""

import json
import os
import tempfile
import unittest

import FreeCAD

from addonmanager_source_local_cache import SourceLocalCache
from AddonManagerTest.app.mocks import (
    MockAddon,
    AddonSignalCatcher,
    CallCatcher,
    SignalCatcher,
)
import addonmanager_utilities as utils


class MockAddonFactory:
    """Pretend to create an addon for this cache item"""

    def create_from_cache(self, item):
        return MockAddon(item["name"])


class TestSourceLocalCache(unittest.TestCase):
    def setUp(self):
        self.test_object = SourceLocalCache()
        self.test_object.addon_factory = MockAddonFactory()
        self.test_dir = os.path.join(
            FreeCAD.getHomePath(), "Mod", "AddonManager", "AddonManagerTest", "data"
        )
        self.signal_catcher = AddonSignalCatcher()
        self.test_object.addon_found.connect(self.signal_catcher.catch_signal)
        self.temp_dir = tempfile.mkdtemp()
        self.call_catcher = CallCatcher()
        self.finished_signal_catcher = SignalCatcher()
        self.test_object.finished.connect(self.finished_signal_catcher.catch_signal)

    def tearDown(self):
        utils.rmdir(self.temp_dir)

    ###############################################################################################
    #                                                                                             #
    #                                         UNIT TESTS                                          #
    #                                                                                             #
    ###############################################################################################

    def test_process_cache_data_no_metadata_file(self):
        """Create a series of simple addons with no metadata files"""
        cache_data = {
            "TestAddon1": {"name": "TestAddon1"},
            "TestAddon2": {"name": "TestAddon2"},
            "TestAddon3": {"name": "TestAddon3"},
        }
        self.test_object.metadata_cache_path = self.temp_dir
        self.test_object.process_cache_data(cache_data)
        results = [addon.name for addon in self.signal_catcher.addons]
        self.assertListEqual(results, list(cache_data.keys()))

    def test_process_cache_data_with_metadata_files(self):
        """Create a series of simple addons with metadata files"""
        cache_data = {
            "TestAddon1": {"name": "TestAddon1"},
            "TestAddon2": {"name": "TestAddon2"},
            "TestAddon3": {"name": "TestAddon3"},
        }
        for addon in cache_data:
            os.mkdir(os.path.join(self.temp_dir, addon))
            with open(
                os.path.join(self.temp_dir, addon, "package.xml"), "w", encoding="utf-8"
            ) as f:
                f.write("<!--Dummy package.xml file: no metadata included-->/n")
        self.test_object.metadata_cache_path = self.temp_dir
        self.test_object.process_cache_data(cache_data)
        results = [addon.name for addon in self.signal_catcher.addons]
        self.assertListEqual(results, list(cache_data.keys()))
        for addon in self.signal_catcher.addons:
            self.assertIsNotNone(
                addon.metadata, "Failed to load existing metadata file"
            )

    def test_run_load_local_cache_normal(self):
        """When the local cache exists and is valid, it is loaded and processed."""

        self.test_object.process_cache_data = self.call_catcher.catch_call
        self.given_valid_json_data()
        self.test_object.run()
        self.assertTrue(
            self.call_catcher.called, "Local cache load never called the process function"
        )
        self.assertTrue(self.finished_signal_catcher.caught)

    def given_valid_json_data(self):
        cache_data = {
            "TestAddon1": {"name": "TestAddon1"},
            "TestAddon2": {"name": "TestAddon2"},
            "TestAddon3": {"name": "TestAddon3"},
        }
        cache_file = os.path.join(self.temp_dir, "cache.json")
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(cache_data))
        self.test_object.cache_file = cache_file

    def test_run_load_local_cache_no_such_file(self):
        """When no cache file exists, no error occurs, but no processing occurs either"""

        self.test_object.cache_file = "/no/such/file"
        self.test_object.process_cache_data = self.call_catcher.catch_call
        self.test_object.run()
        self.assertFalse(
            self.call_catcher.called, "With no data, the process function should not have been called"
        )
        self.assertTrue(self.finished_signal_catcher.caught)

    def test_run_load_local_cache_bad_json_data(self):
        """When the JSON data is invalid, no error occurs, but no processing occurs either"""

        cache_file = os.path.join(self.temp_dir, "cache.json")
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write("This isn't valid JSON data")
        self.test_object.cache_file = cache_file
        self.test_object.process_cache_data = self.call_catcher.catch_call
        self.test_object.run()
        self.assertFalse(
            self.call_catcher.called,
            "With bad data, the process function should not have been called",
        )
        self.assertTrue(self.finished_signal_catcher.caught)

    ###############################################################################################
    #                                                                                             #
    #                                     INTEGRATION TESTS                                       #
    #                                                                                             #
    ###############################################################################################
