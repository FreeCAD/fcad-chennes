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

import datetime
import json
import os
import tempfile
import unittest

import FreeCAD

from PySide import QtCore

from addonmanager_source import AddonManagerSource, BlockStatus
from AddonManagerTest.app.mocks import (
    MockAddon,
    MockMacro,
    CallCatcher,
    SignalCatcher
)
import addonmanager_utilities as utils

from Addon import Addon

run_slow_tests = False


class TestSource(unittest.TestCase):
    def setUp(self):
        self.test_object = AddonManagerSource()
        self.test_dir = os.path.join(
            FreeCAD.getHomePath(), "Mod", "AddonManager", "AddonManagerTest", "data"
        )

    def tearDown(self):
        pass

    ###############################################################################################
    #                                                                                             #
    #                                         UNIT TESTS                                          #
    #                                                                                             #
    ###############################################################################################

    # Test:
    # _get_freecad_addon_repo_data

    def test_addon_block_status_obsolete_match(self):
        """The addon is marked obsolete"""
        self.test_object.addon_flags["obsolete"] = ["TestAddon"]
        test_addon = MockAddon()
        test_addon.name = "TestAddon"
        result = self.test_object._addon_block_status(test_addon)
        self.assertEqual(result, BlockStatus.OBSOLETE)

    def test_addon_block_status_obsolete_no_match(self):
        """The match is case-sensitive and does not match different cases"""
        self.test_object.addon_flags["obsolete"] = ["TestAddon"]
        test_addon = MockAddon()
        test_addon.name = "testaddon"  # Match should be case sensitive
        result = self.test_object._addon_block_status(test_addon)
        self.assertEqual(result, BlockStatus.NOT_BLOCKED)

    def test_addon_block_status_python2_match(self):
        """The addon is marked python 2-only"""
        self.test_object.addon_flags["python2_only"] = ["TestAddon"]
        test_addon = MockAddon()
        test_addon.name = "TestAddon"
        result = self.test_object._addon_block_status(test_addon)
        self.assertEqual(result, BlockStatus.PYTHON2)

    def test_addon_block_status_macro_with_macro(self):
        """The addon with a macro is rejected"""
        self.test_object.addon_flags["macro_reject_list"] = ["TestAddon"]
        test_addon = MockAddon()
        test_addon.macro = MockMacro()
        test_addon.name = "TestAddon"
        result = self.test_object._addon_block_status(test_addon)
        self.assertEqual(result, BlockStatus.REJECT_LIST)

    def test_addon_block_status_macro_without_macro(self):
        """The addon without a macro is not rejected"""
        self.test_object.addon_flags["macro_reject_list"] = ["TestAddon"]
        test_addon = MockAddon()
        test_addon.name = "TestAddon"
        result = self.test_object._addon_block_status(test_addon)
        self.assertEqual(result, BlockStatus.NOT_BLOCKED)

    def test_addon_block_status_addon_without_macro(self):
        """The addon without a macro is rejected"""
        self.test_object.addon_flags["addon_reject_list"] = ["TestAddon"]
        test_addon = MockAddon()
        test_addon.name = "TestAddon"
        result = self.test_object._addon_block_status(test_addon)
        self.assertEqual(result, BlockStatus.REJECT_LIST)

    def test_addon_block_status_macro_without_macro(self):
        """The addon with a macro is not rejected"""
        self.test_object.addon_flags["addon_reject_list"] = ["TestAddon"]
        test_addon = MockAddon()
        test_addon.macro = MockMacro()
        test_addon.name = "TestAddon"
        result = self.test_object._addon_block_status(test_addon)
        self.assertEqual(result, BlockStatus.NOT_BLOCKED)

    def test_handle_new_addon_normal(self):
        """A new addon with a unique, non-blocked name is added"""
        cc = CallCatcher()
        addon = MockAddon()
        self.test_object._update_addon_install_details = cc.catch_call
        self.test_object._handle_new_addon(addon)
        self.assertListEqual(self.test_object.addons, [addon])
        self.assertIn(addon.name, self.test_object._addon_name_cache)
        self.assertTrue(cc.called)

    def test_handle_new_addon_blocked(self):
        """A blocked addon is not added"""
        cc = CallCatcher()
        addon = MockAddon()
        self.test_object.addon_flags["addon_reject_list"] = [addon.name]
        self.test_object._update_addon_install_details = cc.catch_call
        self.test_object._handle_new_addon(addon)
        self.assertListEqual(self.test_object.addons, [])
        self.assertFalse(cc.called)

    def test_handle_new_addon_repeated(self):
        """A second addon with the same name is not added"""
        cc = CallCatcher()
        addon = MockAddon()
        self.test_object._addon_name_cache.add(addon.name)
        self.test_object._update_addon_install_details = cc.catch_call
        self.test_object._handle_new_addon(addon)
        self.assertListEqual(self.test_object.addons, [])
        self.assertFalse(cc.called)

    def test_update_macro_install_details_not_installed(self):
        """An uninstalled macro is marked that way"""
        addon = MockAddon()
        addon.macro = MockMacro()
        with tempfile.TemporaryDirectory() as temp_dir:
            self.test_object.macro_dir = temp_dir
            self.test_object._update_macro_install_details(addon)
            self.assertEqual(addon.update_status, Addon.Status.NOT_INSTALLED)

    def test_update_macro_install_details_installed(self):
        """An installed macro is marked that way"""
        addon = MockAddon()
        addon.macro = MockMacro()
        with tempfile.TemporaryDirectory() as temp_dir:
            self.test_object.macro_dir = temp_dir
            with open(
                os.path.join(temp_dir, addon.macro.filename), "w", encoding="utf-8"
            ) as f:
                f.write("# Fake macro data")
            self.test_object._update_macro_install_details(addon)
            self.assertEqual(addon.update_status, Addon.Status.UNCHECKED)

    def test_process_package_xml(self):
        """For an installed macro, package.xml is used to set the installed version"""
        addon = MockAddon()
        with tempfile.TemporaryDirectory() as temp_dir:
            self.test_object.mod_dir = temp_dir
            os.mkdir(os.path.join(temp_dir, addon.name))
            package_xml_path = os.path.join(temp_dir, addon.name, "package.xml")
            with open(package_xml_path, "w", encoding="utf-8") as f:
                f.write(
                    """<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<package format="1" xmlns="https://wiki.freecad.org/Package_Metadata">
</package>
"""
                )
            self.test_object._process_package_xml(package_xml_path, addon)
            self.assertEqual(addon.installed_version, "1.2.3beta")
            self.assertEqual(
                addon.updated_timestamp, os.path.getmtime(package_xml_path)
            )

    def test_process_manifest(self):
        """The manifest is processed and the updated timestamp set to the last entry"""
        addon = MockAddon()
        with tempfile.TemporaryDirectory() as temp_dir:
            self.test_object.mod_dir = temp_dir
            os.mkdir(os.path.join(temp_dir, addon.name))
            manifest_path = os.path.join(temp_dir, addon.name, "MANIFEST.txt")
            with open(manifest_path, "w", encoding="utf-8") as f:
                f.write("# FreeCAD Addon Manager installation log\n")
                date1 = datetime.datetime(2000, 1, 1, 1, 2, 3, 4, datetime.timezone.utc)
                date2 = datetime.datetime(2010, 2, 2, 2, 3, 4, 5, datetime.timezone.utc)
                date3 = datetime.datetime(2020, 3, 3, 3, 4, 5, 6, datetime.timezone.utc)
                f.write(date1.isoformat() + ", installed using git\n")
                f.write(date2.isoformat() + ", updated using git\n")
                f.write(date3.isoformat() + ", updated using git\n")
            self.test_object._process_manifest(manifest_path, addon)
            self.assertEqual(addon.updated_timestamp, date3.timestamp())

    def test_process_deprecated_real_data(self):
        """Deprecation list is processed and stored"""

        deprecation_data = [
            {
                "name": "assembly2",
                "kind": "mod",
                "as_of": "0.19",
                "notes": "Replaced by A2plus, assembly3, and assembly4",
            },
            {
                "name": "Autoload",
                "kind": "mod",
                "as_of": "0.20",
                "notes": "Feature merged into FreeCAD",
            },
            {"name": "cura_engine", "kind": "mod", "as_of": "0.19", "notes": ""},
            {
                "name": "drawing_dimensioning",
                "kind": "mod",
                "as_of": "0.19",
                "notes": "",
            },
            {
                "name": "ExtMan",
                "kind": "mod",
                "as_of": "0.20",
                "notes": "Built-in Addon Manager adopted new layout and features",
            },
        ]
        self.test_object._process_deprecated(deprecation_data)
        self.assertSetEqual(
            self.test_object.addon_flags["obsolete"],
            set(
                [
                    "assembly2",
                    "Autoload",
                    "cura_engine",
                    "drawing_dimensioning",
                    "ExtMan",
                ]
            ),
        )

    def test_process_deprecated_fictitious_data(self):
        """Deprecation list is processed and stored for all data types"""

        deprecation_data = [
            {
                "name": "FakeAddonOld",
                "kind": "mod",
                "as_of": "0.19",
            },
            {
                "name": "FakeAddonNotOld",
                "kind": "mod",
                "as_of": "99.99",
            },
            {
                "name": "FakeMacroOld",
                "kind": "macro",
                "as_of": "0.19",
            },
            {
                "name": "FakeMacroNotOld",
                "kind": "macro",
                "as_of": "99.99",
            },
            {
                "name": "FakeOtherThing",
                "kind": "thing",
                "as_of": "0.19",
            },
        ]
        self.test_object._process_deprecated(deprecation_data)
        self.assertSetEqual(
            self.test_object.addon_flags["obsolete"], set(["FakeAddonOld"])
        )
        self.assertSetEqual(
            self.test_object.addon_flags["macro_reject_list"], set(["FakeMacroOld"])
        )

    @unittest.skipUnless(FreeCAD.GuiUp, "Requires a QApplication (e.g. GUI must be up)")
    def test_run_source_in_thread(self):
        """A new thread is spooled up and run to completion"""
        worker = self.given_worker()
        finished_handler = SignalCatcher()
        self.test_object._source_run_finished_callback = finished_handler.catch_signal
        self.test_object._run_source_in_thread(worker)
        self.wait_for_thread_to_exit(worker, finished_handler)
        self.assertTrue(finished_handler.caught)

    def given_worker(self) -> object:
        class WorkerClass(QtCore.QObject):
            finished = QtCore.Signal()
            def __init__(self):
                super().__init__()
                self.done = False
                self.iterations = 100
            def run(self):
                for _ in range(self.iterations):
                    if QtCore.QThread.currentThread().isInterruptionRequested():
                        return
                    QtCore.QThread.msleep(1)
                self.done = True
                self.finished.emit()
        return WorkerClass()

    def wait_for_thread_to_exit(self, worker, finished_handler):
        while not worker.done:
            QtCore.QThread.msleep(1)
        self.test_object.worker_thread.quit()
        self.test_object.worker_thread.wait()
        self.run_event_loop_for_signal_catcher(finished_handler)

    def run_event_loop_for_signal_catcher(self, signal_catcher):
        kill_timer = QtCore.QTimer()
        kill_timer.setSingleShot(True)
        kill_timer.setInterval(100)
        kill_timer.timeout.connect(signal_catcher.die)
        while not signal_catcher.caught and not signal_catcher.killed:
            QtCore.QCoreApplication.processEvents(QtCore.QEventLoop.AllEvents, 10)
        kill_timer.stop()

    ###############################################################################################
    #                                                                                             #
    #                                     INTEGRATION TESTS                                       #
    #                                                                                             #
    ###############################################################################################

    @unittest.skipUnless(
        run_slow_tests == True, "Slow tests disabled"
    )
    def test_get_freecad_addon_repo_data_good_data(self):
        """INTEGRATION TEST: addonflags.json file processed correctly when the data is good"""

        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = os.path.join(temp_dir, "addonflags.json")
            with open(json_path, "w", encoding="utf-8") as f:
                f.write(
                    """
{
    "obsolete" : {
        "name": "Obsolete",
        "Mod": [
            "assembly2",
            "drawing_dimensioning",
            "cura_engine"
        ]
    },
    "deprecated" : [
        {
            "name":"assembly2",
            "kind":"mod",
            "as_of":"0.19",
            "notes":"Replaced by A2plus, assembly3, and assembly4"
        },
        {
            "name":"Autoload",
            "kind":"mod",
            "as_of":"0.20",
            "notes":"Feature merged into FreeCAD"
        },
        {
            "name":"cura_engine",
            "kind":"mod",
            "as_of":"0.19",
            "notes":""
        },
        {
            "name":"drawing_dimensioning",
            "kind":"mod",
            "as_of":"0.19",
            "notes":""
        },
        {
            "name":"ExtMan",
            "kind":"mod",
            "as_of":"0.20",
            "notes":"Built-in Addon Manager adopted new layout and features"
        }
    ],
    "blacklisted" : {
        "name": "Blacklist",
        "Macro": [
            "BOLTS",
            "WorkFeatures",
            "how to install",
            "documentation",
            "PartsLibrary",
            "FCGear"
        ]
    },
    "py2only" : {
        "name": "Python 2 Only",
        "Mod": [
            "geodata",
            "GDT",
            "timber",
            "flamingo",
            "reconstruction",
            "animation"
        ]
    }
}
"""
                )
            self.test_object.addon_flags_url = "file://localhost/" + json_path
            self.test_object._get_freecad_addon_repo_data()
            self.assertSetEqual(
                self.test_object.addon_flags["obsolete"],
                set(
                    [
                        "assembly2",
                        "Autoload",
                        "cura_engine",
                        "drawing_dimensioning",
                        "ExtMan",
                    ]
                ),
            )
            self.assertSetEqual(
                self.test_object.addon_flags["macro_reject_list"],
                set(
                    [
                        "BOLTS",
                        "WorkFeatures",
                        "how to install",
                        "documentation",
                        "PartsLibrary",
                        "FCGear",
                    ]
                ),
            )
            self.assertSetEqual(
                self.test_object.addon_flags["python2_only"],
                set(
                    [
                        "geodata",
                        "GDT",
                        "timber",
                        "flamingo",
                        "reconstruction",
                        "animation",
                    ]
                ),
            )

    def test_update_no_gui(self):
        """INTEGRATION TEST: Non-GUI update calls all sources and emits finished() (synchronous)"""
        self.given_mock_source_factory()
        self.test_object.gui_up = False
        self.test_object.update()
        self.assert_all_sources_called()

    @unittest.skipUnless(FreeCAD.GuiUp, "Requires FreeCAD.GuiUp")
    def test_update_with_gui(self):
        """INTEGRATION TEST: GUI-up update calls all sources and emits finished() (asynchronous)"""
        self.given_mock_source_factory()
        self.assertTrue(self.test_object.gui_up) # Make sure the test itself is valid
        signal_catcher = SignalCatcher()
        self.test_object.update_complete.connect(signal_catcher.catch_signal)
        self.test_object.update()
        self.run_event_loop_for_signal_catcher(signal_catcher)
        self.assert_all_sources_called()

    def given_mock_source_factory(self):
        class MockSource(QtCore.QObject):
            finished = QtCore.Signal()
            addon_found = QtCore.Signal(object)
            def __init__(self, skip_cache=False):
                super().__init__()
                self.called = False
                self.skip_cache = skip_cache
            def run(self):
                self.called = True
                self.finished.emit()
        class MockSourceFactory:
            def create_sources(self, skip_cache):
                return [MockSource(),MockSource(),MockSource()]
        self.test_object.source_factory = MockSourceFactory()

    def assert_all_sources_called(self):
        self.assertEqual(len(self.test_object.used_sources), 3)
        for source in self.test_object.used_sources:
            self.assertTrue(source.called)