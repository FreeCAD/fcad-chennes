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

import os
import random
import tempfile
import unittest
import zipfile
from time import sleep
from typing import List
from urllib.parse import urlparse

import FreeCAD
import addonmanager_utilities as utils
from Addon import Addon  # For integration tests
from AddonManagerTest.app.mocks import MockAddon, MockMacro, SignalCatcher, CallCatcher, MockByteArray, \
    MockNetworkManager, MockConsole, MockSignal
from AddonManagerTest.gui.gui_mocks import AsynchronousMonitor
from PySide import QtCore, QtGui
from addonmanager_icon_source import (
    IconSource,
    CacheUpdater,
    DirectUpdater,
    IndividualDirectUpdater,
    MacroDirectUpdater,
)


class MockIcon:
    pass


class MockIconFactory:
    def __init__(self, fail=False):
        self.accessed_resource = None
        self.accessed_file = None
        self.call_count = 0
        self.fail = fail

    def get_icon_from_file(self, path: os.PathLike):
        self.accessed_file = path
        self.call_count += 1
        if self.fail:
            return None
        return MockIcon()

    def get_icon_from_resource(self, resource_name: str):
        self.accessed_resource = resource_name
        self.call_count += 1
        if self.fail:
            return None
        return MockIcon


def given_addons(temp_dir) -> List[Addon]:
    """Create a set of fake addons and the local data to support them. Used by several integration
    tests below."""

    def given_url_from_temp_file(temp_file_name):
        return f"file://localhost/" + os.path.join(temp_dir, temp_file_name)

    for name in ["test-icon-a.svg", "test-icon-b.svg", "test-icon-c.svg", "test-icon-d.svg"]:
        with open(os.path.join(temp_dir, name), "w") as f:
            f.write(given_svg_data())
    names = [f"test-icon-{letter}" for letter in "abcdef"]
    addons = []
    for name in names:
        addons.append(Addon(name=name, url=given_url_from_temp_file("")))
    addons[0].repo_type = Addon.Kind.PACKAGE
    addons[0].get_best_icon_relative_path = lambda: "test-icon-a.svg"
    addons[1].repo_type = Addon.Kind.PACKAGE
    addons[1].get_best_icon_relative_path = lambda: "test-icon-b.svg"
    addons[2].repo_type = Addon.Kind.MACRO
    addons[2].macro = MockMacro("test-icon-c")
    addons[2].macro.icon = given_url_from_temp_file("test-icon-c.svg")
    addons[3].repo_type = Addon.Kind.MACRO
    addons[3].macro = MockMacro("test-icon-d")
    addons[3].macro.icon = given_url_from_temp_file("test-icon-d.svg")
    return addons


def given_svg_data() -> str:
    return """<svg version="1.1"
     width="100" height="100"
     xmlns="http://www.w3.org/2000/svg">
  <circle cx="50" cy="50" r="80" fill="green" />
</svg>
    """


class TestIconSource(unittest.TestCase):
    MODULE = "test_icon_source"  # file name without extension

    def setUp(self):
        self.test_object = IconSource()
        self.test_object.icon_factory = MockIconFactory()
        self.cache_dir = tempfile.mkdtemp()
        self.temp_dir = tempfile.mkdtemp()
        self.test_data_dir = os.path.join(
            FreeCAD.getHomePath(), "Mod", "AddonManager", "AddonManagerTest", "data"
        )
        self.signal_catcher = SignalCatcher()
        self.kill_timer = QtCore.QTimer()
        self.kill_timer.setSingleShot(True)
        self.kill_timer.timeout.connect(self.signal_catcher.die)

    def tearDown(self):
        utils.rmdir(self.cache_dir)
        utils.rmdir(self.temp_dir)

    def test_get_icon_for_old_style_workbench_normal(self):
        """Provided a simple name, the appropriate resource is accessed"""
        self.test_object.get_icon_for_old_style_workbench("wb_name")
        self.assertEqual(
            self.test_object.icon_factory.accessed_resource,
            "wb_name_workbench_icon.svg",
        )

    def test_get_icon_for_old_style_workbench_with_space(self):
        """Provided a name with spaces, the appropriate resource is accessed"""
        self.test_object.get_icon_for_old_style_workbench("wb name")
        self.assertEqual(
            self.test_object.icon_factory.accessed_resource,
            "wb_name_workbench_icon.svg",
        )

    @unittest.skipUnless(FreeCAD.GuiUp, "No event loop running")
    def test_asynchronous_cache_update(self):
        """A QThread is created and the update run in it."""

        class MockCacheUpdater(QtCore.QObject):
            finished = QtCore.Signal()

            def __init__(self):
                super().__init__()
                self.run_complete = False

            def run(self):
                sleep(0.05)
                self.run_complete = True
                self.finished.emit()

        signal_catcher = SignalCatcher()
        kill_timer = QtCore.QTimer()
        kill_timer.setSingleShot(True)
        kill_timer.setInterval(100)
        kill_timer.timeout.connect(signal_catcher.die)
        self.test_object.cache_updater = MockCacheUpdater()
        self.test_object.cache_updater.finished.connect(signal_catcher.catch_signal)
        self.test_object.begin_asynchronous_cache_update()
        kill_timer.start()
        while not signal_catcher.caught and not signal_catcher.killed:
            QtCore.QCoreApplication.processEvents(QtCore.QEventLoop.AllEvents, 10)
        kill_timer.stop()
        self.assertTrue(signal_catcher.caught)
        self.assertFalse(signal_catcher.killed)

    def test_create_cache_index(self):
        """The local cache directory is loaded into an index"""
        names = ["test_file1", "testFile2", "test file 3", "tf4", "tf5.not_extension"]
        extensions = [".svg", ".bmp", ".png", ".jpeg", ".svg"]
        self.given_directory_with_cache_files(names, extensions)
        cache_index = self.test_object._create_cache_index()
        self.assert_index_matches_file_list(cache_index, names)

    def given_directory_with_cache_files(self, names, extensions):
        self.test_object.icon_cache_location = self.cache_dir
        for part1, part2 in zip(names, extensions):
            with open(
                    os.path.join(self.cache_dir, part1 + part2), "w", encoding="utf-8"
            ) as f:
                f.write("Fake data")

    def assert_index_matches_file_list(self, cache_index, names):
        for name in names:
            with self.subTest(name=name):
                self.assertIn(name, cache_index)

    #####################
    # INTEGRATION TESTS #
    #####################

    def test_full_asynchronous_cache_update(self):
        """INTEGRATION TEST: Asynchronous cache functionality works as expected"""
        self.given_cache_setup()
        monitor = AsynchronousMonitor(self.test_object.cache_update_complete)
        self.test_object.begin_asynchronous_cache_update()
        monitor.wait_for_at_most(1000)
        self.assertTrue(monitor.good())
        self.assert_expected_cache_exists()

    def given_cache_setup(self):
        self.test_object.remote_cache_url = "file://localhost/" + os.path.join(self.test_data_dir, "icon_cache.zip")
        self.test_object.icon_cache_location = self.cache_dir

    def assert_expected_cache_exists(self):
        self.assertTrue(os.path.isdir(self.cache_dir))
        cache_contents = os.listdir(self.cache_dir)
        self.assertIn("test-icon-a.svg", cache_contents)
        self.assertIn("test-icon-b.png", cache_contents)
        self.assertIn("test-icon-c.jpg", cache_contents)
        self.assertIn("test-icon-d.bmp", cache_contents)
        self.assertIn("test-icon-e.webp", cache_contents)
        self.assertIn("cache_hash.txt", cache_contents)

    def test_asynchronous_direct_update_no_cache(self):
        """INTEGRATION TEST: Call to asynchronous_direct_update() loads icons and emits signal"""
        addons = given_addons(self.temp_dir)
        self.given_cache_setup()
        monitor = AsynchronousMonitor(self.test_object.direct_update_complete)
        self.test_object.begin_asynchronous_direct_update(addons)
        monitor.wait_for_at_most(1000)
        self.assertTrue(monitor.good())
        self.assert_local_cache_contains_addon_icons()

    def assert_local_cache_contains_addon_icons(self):
        icons = os.listdir(self.cache_dir)
        self.assertIn("test-icon-a.svg", icons)
        self.assertIn("test-icon-b.svg", icons)
        self.assertIn("test-icon-c.svg", icons)
        self.assertIn("test-icon-d.svg", icons)


class TestCacheUpdater(unittest.TestCase):
    def setUp(self):
        self.test_object = CacheUpdater("", "", False)
        self.cache_dir = tempfile.mkdtemp()
        self.test_data_dir = os.path.join(
            FreeCAD.getHomePath(), "Mod", "AddonManager", "AddonManagerTest", "data"
        )
        self.signal_catcher = SignalCatcher()
        self.kill_timer = QtCore.QTimer()
        self.kill_timer.setSingleShot(True)
        self.kill_timer.timeout.connect(self.signal_catcher.die)

    def tearDown(self):
        utils.rmdir(self.cache_dir)

    def test_cache_needs_to_be_updated_hashes_match(self):
        """When the local and remote hashes match, no update is required"""
        test_hash_data = "abcdef0123456789abcdef0123456789abcdef0123456789"
        with tempfile.TemporaryDirectory() as temp_dir:
            self.given_remote_and_local_hashes(temp_dir, test_hash_data, test_hash_data)
            needs_update = self.test_object._cache_needs_to_be_updated()
            self.assertFalse(needs_update, "Matching hashes should not need an update")

    def test_cache_needs_to_be_updated_hashes_do_not_match(self):
        """When the local and remote hashes do not match, an update is required"""
        test_hash_data1 = "abcdef0123456789abcdef0123456789abcdef0123456789"
        test_hash_data2 = "bcdef0123456789abcdef0123456789abcdef0123456789a"
        with tempfile.TemporaryDirectory() as temp_dir:
            self.given_remote_and_local_hashes(
                temp_dir, test_hash_data1, test_hash_data2
            )
            needs_update = self.test_object._cache_needs_to_be_updated()
            self.assertTrue(needs_update, "Non-matching hashes should need an update")

    def test_cache_needs_to_be_updated_no_local_cache(self):
        """When there is no local hash data, an update is required"""
        test_hash_data = "abcdef0123456789abcdef0123456789abcdef0123456789"
        with tempfile.TemporaryDirectory() as temp_dir:
            self.given_remote_and_local_hashes(temp_dir, test_hash_data, None)
            needs_update = self.test_object._cache_needs_to_be_updated()
            self.assertTrue(needs_update, "Missing local hash should need an update")

    def test_cache_needs_to_be_updated_no_remote_hash(self):
        """When there is no remote hash data, an update is required"""
        test_hash_data = "abcdef0123456789abcdef0123456789abcdef0123456789"
        with tempfile.TemporaryDirectory() as temp_dir:
            self.given_remote_and_local_hashes(temp_dir, None, test_hash_data)
            needs_update = self.test_object._cache_needs_to_be_updated()
            self.assertTrue(needs_update, "Missing remote hash should need an update")

    def given_remote_and_local_hashes(self, temp_dir, remote, local):
        self.test_object.remote_cache_url = (
                "file://localhost/" + temp_dir + "/icon_cache.zip"
        )
        self.test_object.remote_hash_url = self.test_object.remote_cache_url + ".sha1"
        self.test_object.icon_cache_location = temp_dir
        self.test_object.local_hash_file = os.path.join(temp_dir, "cache_hash.txt")
        if local is not None:
            with open(self.test_object.local_hash_file, "w", encoding="utf-8") as f:
                f.write(local)
        if remote is not None:
            remote_hash_file = os.path.join(temp_dir, "icon_cache.zip.sha1")
            with open(remote_hash_file, "w", encoding="utf-8") as f:
                f.write(remote)

    def test_get_cache_normal(self):
        """ZIP data is downloaded and extracted to the local cache path"""
        with tempfile.TemporaryDirectory() as temp_dir:
            self.given_remote_zip_cache(temp_dir)
            self.test_object._download_cache()
            self.assert_local_cache_exists(temp_dir)

    def test_get_cache_no_cache(self):
        """When the remote cache is missing an exception is raised"""
        with tempfile.TemporaryDirectory() as temp_dir:
            self.given_remote_zip_cache(temp_dir, create_cache=False, create_hash=True)
            with self.assertRaises(utils.UrlExceptionType):
                self.test_object._download_cache()

    def test_get_cache_no_hash(self):
        """When the remote hash is missing no exception is raised"""
        with tempfile.TemporaryDirectory() as temp_dir:
            self.given_remote_zip_cache(temp_dir, create_cache=True, create_hash=False)
            self.test_object._download_cache()

    def test_get_hash_no_hash(self):
        """When the remote hash is missing an exception is raised"""
        with tempfile.TemporaryDirectory() as temp_dir:
            self.given_remote_zip_cache(temp_dir, create_cache=True, create_hash=False)
            with self.assertRaises(utils.UrlExceptionType):
                self.test_object._download_hash()

    def test_get_hash_normal(self):
        """Hash data is downloaded and placed in the local cache path"""
        with tempfile.TemporaryDirectory() as temp_dir:
            self.given_remote_zip_cache(temp_dir)
            self.test_object._download_hash()
            self.assert_local_hash_exists(temp_dir)

    def given_remote_zip_cache(self, temp_dir, create_cache=True, create_hash=True):
        filename = os.path.join(temp_dir, "icon_cache.zip")
        self.test_object.remote_cache_url = "file://localhost/" + filename
        self.test_object.remote_hash_url = self.test_object.remote_cache_url + ".sha1"
        self.test_object.icon_cache_location = temp_dir
        self.test_object.local_hash_file = os.path.join(temp_dir, "cache_hash.txt")
        if create_cache:
            with zipfile.ZipFile(filename, "w") as zip_file:
                with zip_file.open("addon_icon.svg", "w") as f:
                    f.write("Fake SVG data".encode("utf-8"))
            self.assertTrue(os.path.exists(filename))  # Self-test
            with zipfile.ZipFile(filename, "r") as f:
                self.assertIsNone(f.testzip())  # Self-test
        if create_hash:
            filename = os.path.join(temp_dir, "icon_cache.zip.sha1")
            with open(filename, "w", encoding="utf-8") as f:
                f.write("abcdef0123456789abcdef0123456789abcdef0123456789")
            self.assertTrue(os.path.exists(filename))  # Self-test

    def assert_local_cache_exists(self, temp_dir):
        self.assertTrue(os.path.exists(os.path.join(temp_dir, "addon_icon.svg")))

    def assert_local_hash_exists(self, temp_dir):
        self.assertTrue(os.path.exists(os.path.join(temp_dir, "cache_hash.txt")))

    #####################
    # INTEGRATION TESTS #
    #####################

    def test_run(self):
        """INTEGRATION TEST: run() completes successfully"""
        self.given_cache_setup()
        monitor = AsynchronousMonitor(self.test_object.finished)
        self.test_object.run()
        monitor.wait_for_at_most(1000)
        self.assertTrue(monitor.good())

    def given_cache_setup(self):
        remote_cache_url = "file://localhost/" + os.path.join(self.test_data_dir, "icon_cache.zip")
        icon_cache_location = self.cache_dir
        self.test_object = CacheUpdater(remote_cache_url, icon_cache_location)


class TestDirectUpdater(unittest.TestCase):
    def setUp(self):
        self.cache_dir = tempfile.mkdtemp()
        self.addon = MockAddon()
        self.test_object = DirectUpdater(self.cache_dir)
        self.call_catcher = CallCatcher()
        self.signal_catcher = SignalCatcher()

    def tearDown(self):
        utils.rmdir(self.cache_dir)

    def test_check_for_completion_not_complete(self):
        """When the counter is less than the size of the array, do not indicate completion"""
        self.test_object.finished.connect(self.signal_catcher.catch_signal)
        self.test_object.updaters = ["Updater1", "Updater2", "Updater3"]
        self.test_object._increment_and_check_for_completion()
        self.assertFalse(
            self.signal_catcher.caught, "finished() should not have been emitted"
        )

    def test_check_for_completion_complete(self):
        """When the counter equal to the size of the array, indicate completion"""
        self.test_object.finished.connect(self.signal_catcher.catch_signal)
        self.test_object.addons = ["Updater1", "Updater2", "Updater3"]
        self.test_object._increment_and_check_for_completion()
        self.test_object._increment_and_check_for_completion()
        self.test_object._increment_and_check_for_completion()
        self.assertTrue(
            self.signal_catcher.caught, "finished() should have been emitted"
        )

    def test_update_failed_callback(self):
        """A failed update sets the icon to None, but still increments the call count"""
        self.test_object._increment_and_check_for_completion = (
            self.call_catcher.catch_call
        )
        self.test_object._update_failed_callback(self.addon)
        self.assertIsNone(self.addon.icon_file, "Icon file should be None")
        self.assertTrue(self.call_catcher.called, "Incrementer should have been called")

    def test_update_succeeded_callback(self):
        """A failed update sets the icon to None, but still increments the call count"""
        self.test_object._increment_and_check_for_completion = (
            self.call_catcher.catch_call
        )
        self.addon.icon_file = "This is not None"
        self.test_object._update_complete_callback(self.addon)
        self.assertIsNotNone(self.addon.icon_file, "Icon file should not be None")
        self.assertTrue(self.call_catcher.called, "Incrementer should have been called")

    def test_start_updater_for(self):
        """An updater is connected and launched for the specified addon"""

        class FakeSignal:
            def __init__(self):
                self.connections = 0

            def connect(self, _):
                self.connections += 1

        class FakeUpdater:
            update_complete = FakeSignal()
            update_failed = FakeSignal()

            def __init__(self, *_):
                super().__init__()
                self.called = False

            def run(self):
                self.called = True

        self.test_object.UpdaterType = FakeUpdater
        self.test_object._start_updater_for(self.addon)
        self.assertTrue(len(self.test_object.updaters), 1)
        self.assertTrue(self.test_object.updaters[0].called)
        self.assertEqual(self.test_object.updaters[0].update_complete.connections, 1)
        self.assertEqual(self.test_object.updaters[0].update_failed.connections, 1)

    def test_icon_does_not_exist_none(self):
        """When the icon file is None, return True"""
        self.addon.icon_file = None
        self.assertTrue(self.test_object._icon_does_not_exist(self.addon))

    def test_icon_does_not_exist_bad_file(self):
        """When the icon file is non-existent, return True"""
        self.addon.icon_file = "/no/such/file"
        self.assertTrue(self.test_object._icon_does_not_exist(self.addon))

    def test_icon_does_not_exist_good_file(self):
        """When the icon file is None, return True"""
        icon_file = os.path.join(self.cache_dir, "some_icon.svg")
        with open(icon_file, "w", encoding="utf-8") as f:
            f.write("Some data")
        self.addon.icon_file = icon_file
        self.assertFalse(self.test_object._icon_does_not_exist(self.addon))

    def test_prepare_for_run(self):
        """prepare_for_run() stores the list of addons"""
        addons = ["Addon1", "Addon2", "Addon3"]
        self.test_object.prepare_for_run(addons)
        self.assertListEqual(self.test_object.addons, addons)

    def test_run_no_addons(self):
        """If prepare_for_run() was not called first, an exception is raised"""
        with self.assertRaises(RuntimeError):
            self.test_object.run()

    def test_run_not_forced_icons_exist(self):
        """When unforced, if all icons exist, nothing new is downloaded"""
        self.test_object.force_update = False
        self.test_object.addons = [MockAddon(name="Addon1"), MockAddon(name="Addon2"), MockAddon(name="Addon3")]
        self.test_object._icon_does_not_exist = lambda _: False
        self.test_object._start_updater_for = self.call_catcher.catch_call
        self.test_object.run()
        self.assertFalse(self.call_catcher.called)

    def test_run_not_forced_no_icons_exist(self):
        """When unforced, if no icons exist, all icons are downloaded"""
        self.test_object.force_update = False
        self.test_object.addons = [MockAddon(name="Addon1"), MockAddon(name="Addon2"), MockAddon(name="Addon3")]
        self.test_object._icon_does_not_exist = lambda _: True
        self.test_object._start_updater_for = self.call_catcher.catch_call
        self.test_object.run()
        self.assertEqual(self.call_catcher.call_count, len(self.test_object.addons))

    def test_run_forced_icons_exist(self):
        """When forced, even if all icons exist, all icons are downloaded"""
        self.test_object.force_update = True
        self.test_object.addons = [MockAddon(name="Addon1"), MockAddon(name="Addon2"), MockAddon(name="Addon3")]
        self.test_object._icon_does_not_exist = lambda _: False
        self.test_object._start_updater_for = self.call_catcher.catch_call
        self.test_object.run()
        self.assertEqual(self.call_catcher.call_count, len(self.test_object.addons))

    #####################
    # INTEGRATION TESTS #
    #####################

    def test_run(self):
        """INTEGRATION TEST: run() creates the icons and emits the signal"""
        with tempfile.TemporaryDirectory() as temp_dir:
            addons = given_addons(temp_dir)
            self.test_object.prepare_for_run(addons)
            monitor = AsynchronousMonitor(self.test_object.finished)
            self.test_object.run()
            monitor.wait_for_at_most(1000)
            self.assertTrue(monitor.good())


class TestIndividualDirectUpdater(unittest.TestCase):
    def setUp(self):
        self.cache_dir = tempfile.mkdtemp()
        self.addon = MockAddon()
        self.test_object = IndividualDirectUpdater(self.cache_dir, self.addon)
        self.call_catcher = CallCatcher()

    def tearDown(self):
        utils.rmdir(self.cache_dir)

    def test_store_icon_data_svg(self):
        """SVG data is stored in a .svg file and is readable"""
        svg_data = QtCore.QByteArray(given_svg_data().encode("utf-8"))
        signal_catcher = SignalCatcher()
        self.test_object.update_complete.connect(signal_catcher.catch_signal)
        self.test_object._store_icon_data(svg_data)
        expected_filename = os.path.join(self.cache_dir, self.addon.name + ".svg")
        self.assertTrue(os.path.exists(expected_filename))
        image = QtGui.QImage(expected_filename, "svg")
        self.assertFalse(image.isNull())
        self.assertTrue(signal_catcher.caught)

    def test_download_complete_good_index_good_response(self):
        """With a matching index and HTTP response of 200, the icon storage function is called"""
        self.test_object._store_icon_data = self.call_catcher.catch_call
        index = random.randint(1, 9999)
        self.test_object.download_identifier = index
        self.test_object._download_complete(index, 200, None)
        self.assertTrue(self.call_catcher.called)

    def test_download_complete_good_index_bad_response(self):
        """With a matching index but HTTP response >200, the icon storage function is not called"""
        self.test_object._store_icon_data = self.call_catcher.catch_call
        index = random.randint(1, 9999)
        self.test_object.download_identifier = index
        for http_response in [
            201,
            202,
            203,
            204,
            205,
            206,
            300,
            301,
            302,
            303,
            304,
            307,
            308,
            400,
            401,
            403,
            404,
        ]:
            self.test_object._download_complete(index, http_response, None)
            self.assertFalse(self.call_catcher.called)

    def test_download_complete_bad_index(self):
        """With a non-matching index, the icon storage function is not called"""
        self.test_object._store_icon_data = self.call_catcher.catch_call
        for _ in range(100):
            # Try fuzzing it
            self.call_catcher.called = False
            index1 = random.randint(1, 9999)
            index2 = random.randint(1, 9999)
            self.test_object.download_identifier = index1
            self.test_object._download_complete(index2, 200, None)
            if index1 != index2:
                self.assertFalse(self.call_catcher.called)
            else:
                self.assertTrue(self.call_catcher.called)

    def test_enqueue_download(self):
        """A download calls the submit_unmonitored_get function of the download manager"""

        class MockDownloadManager:
            def __init__(self):
                self.url = None
                self.called = False
                self.index = random.randint(1, 9999)

            def submit_unmonitored_get(self, url):
                self.url = url
                self.called = True
                return self.index

        download_manager = MockDownloadManager()
        self.test_object.download_manager = download_manager
        url_to_test = "https://some.test.url"
        self.test_object._enqueue_download(url_to_test)
        self.assertTrue(download_manager.called)
        self.assertEqual(download_manager.url, url_to_test)
        self.assertEqual(self.test_object.download_identifier, download_manager.index)

    #####################
    # INTEGRATION TESTS #
    #####################

    def test_run_with_workbench(self):
        """INTEGRATION TEST: run() completes as expected for a workbench"""
        with tempfile.TemporaryDirectory() as temp_dir:
            addon = Addon("test-icon-a.svg", "file://localhost/" + temp_dir)
            self.test_object = IndividualDirectUpdater(self.cache_dir, addon)
            catch_failed_signal = SignalCatcher()
            catch_complete_signal = SignalCatcher()
            self.test_object.update_failed.connect(catch_failed_signal.catch_signal)
            self.test_object.update_complete.connect(catch_complete_signal.catch_signal)
            self.test_object.run()
            while not catch_failed_signal.caught and not catch_complete_signal.caught:
                QtCore.QCoreApplication.processEvents(QtCore.QEventLoop.AllEvents, 10)
            self.assertTrue(catch_complete_signal.caught)

    def test_run_with_package(self):
        """INTEGRATION TEST: run() completes as expected for a package"""
        with tempfile.TemporaryDirectory() as temp_dir:
            addon = Addon("test-icon-a", "file://localhost/" + temp_dir)
            with open(os.path.join(temp_dir, "test-icon-a.svg"), "w") as f:
                f.write(given_svg_data())
            addon.repo_type = Addon.Kind.PACKAGE
            addon.get_best_icon_relative_path = lambda: "test-icon-a.svg"
            self.test_object = IndividualDirectUpdater(self.cache_dir, addon)
            catch_failed_signal = SignalCatcher()
            catch_complete_signal = SignalCatcher()
            self.test_object.update_failed.connect(catch_failed_signal.catch_signal)
            self.test_object.update_complete.connect(catch_complete_signal.catch_signal)
            self.test_object.run()
            while not catch_failed_signal.caught and not catch_complete_signal.caught:
                QtCore.QCoreApplication.processEvents(QtCore.QEventLoop.AllEvents, 10)
            self.assertTrue(catch_complete_signal.caught)
            self.assertTrue(os.path.exists(os.path.join(self.cache_dir, "test-icon-a.svg")))

    def test_run_with_macro(self):
        """INTEGRATION TEST: run() completes as expected for a macro"""
        with tempfile.TemporaryDirectory() as temp_dir:
            addon = Addon("MockMacro", "file://localhost/" + temp_dir)
            with open(os.path.join(temp_dir, "test-icon-a.svg"), "w") as f:
                f.write(given_svg_data())
            addon.repo_type = Addon.Kind.MACRO
            addon.macro = MockMacro()
            addon.macro.icon = "file://localhost/" + temp_dir.replace(os.path.sep, "/") + "/test-icon-a.svg"
            self.test_object = IndividualDirectUpdater(self.cache_dir, addon)
            catch_complete_signal = AsynchronousMonitor(self.test_object.update_complete)
            self.test_object.run()
            catch_complete_signal.wait_for_at_most(1000)
            self.assertTrue(catch_complete_signal.good())
            self.assertTrue(os.path.exists(os.path.join(self.cache_dir, addon.name + ".svg")))


class TestMacroDirectUpdater(unittest.TestCase):
    def setUp(self) -> None:
        self.cache_location = tempfile.mkdtemp()
        self.temp_dir = tempfile.mkdtemp()
        self.addon = MockAddon("MockMacro")
        self.addon.macro = MockMacro("MockMacro")
        self.test_object = MacroDirectUpdater(self.cache_location, self.addon)
        self.test_object.console = MockConsole()

    def tearDown(self) -> None:
        utils.rmdir(self.temp_dir)
        utils.rmdir(self.cache_location)

    def test_run_with_icon(self):
        """Given an icon, the appropriate handler is called"""
        self.addon.macro.icon = "file://localhost/some/path.png"
        self.addon.macro.xpm = ""
        icon_catcher, xpm_catcher, signal_catcher = self.given_instrumented_run()
        self.test_object._run()
        self.assertTrue(icon_catcher.called)
        self.assertFalse(xpm_catcher.called)
        self.assertFalse(signal_catcher.caught)

    def test_run_with_xpm(self):
        """Given an icon, the appropriate handler is called"""
        self.addon.macro.icon = ""
        self.addon.macro.xpm = "Some fake XPM data"
        icon_catcher, xpm_catcher, signal_catcher = self.given_instrumented_run()
        self.test_object._run()
        self.assertFalse(icon_catcher.called)
        self.assertTrue(xpm_catcher.called)
        self.assertFalse(signal_catcher.caught)

    def test_run_with_none(self):
        """Given an icon, the appropriate handler is called"""
        self.addon.macro.icon = ""
        self.addon.macro.xpm = ""
        icon_catcher, xpm_catcher, signal_catcher = self.given_instrumented_run()
        self.test_object._run()
        self.assertFalse(icon_catcher.called)
        self.assertFalse(xpm_catcher.called)
        self.assertTrue(signal_catcher.caught)

    def given_instrumented_run(self):
        icon_catcher = CallCatcher()
        xpm_catcher = CallCatcher()
        signal_catcher = SignalCatcher()
        self.test_object.finished.connect(signal_catcher.catch_signal)
        self.test_object._handle_icon_entry = icon_catcher.catch_call
        self.test_object._handle_xpm_data = xpm_catcher.catch_call
        return icon_catcher, xpm_catcher, signal_catcher

    @unittest.expectedFailure
    def test_handle_icon_entry_git(self):
        """The git handling code is not written yet"""
        self.addon.macro.on_git = True
        self.addon.macro.on_wiki = False
        self.test_object._handle_icon_entry()

    def test_handle_icon_entry_git(self):
        """The git handling code is not written yet"""
        self.addon.macro.on_git = False
        self.addon.macro.on_wiki = True
        catcher = CallCatcher()
        self.test_object._create_wiki_icon = catcher.catch_call
        self.test_object._handle_icon_entry()
        self.assertTrue(catcher.called)

    def test_handle_xpm_data(self):
        """An xpm file is created"""
        self.addon.macro.xpm = "Fake XPM data"
        self.test_object._handle_xpm_data()
        self.assertTrue(os.path.exists(os.path.join(self.cache_location, self.addon.name + ".xpm")))

    def test_create_wiki_icon_relative_path(self):
        """With a relative path, bypass normal access and call the handlers"""
        relative, asynch, synch = self.given_instrumented_create_wiki_icon()
        self.test_object.macro.raw_code_url = ""
        self.test_object.macro.icon = "some/relative/path"
        self.test_object._create_wiki_icon()
        self.assertTrue(relative.called)
        self.assertFalse(asynch.called)
        self.assertFalse(synch.called)
        self.assertEqual(self.test_object.macro.icon,
                         "https://wiki.freecad.org/some/relative/path")

    def test_create_wiki_icon_relative_path_rawcode(self):
        """With a relative path, bypass normal access and call the handlers"""
        relative, asynch, synch = self.given_instrumented_create_wiki_icon()
        self.test_object.macro.raw_code_url = "https://some.url/and/more/code.FCMacro"
        self.test_object.macro.icon = "some/relative/path"
        self.test_object._create_wiki_icon()
        self.assertTrue(relative.called)
        self.assertFalse(asynch.called)
        self.assertFalse(synch.called)
        self.assertEqual(self.test_object.macro.icon,
                         "https://some.url/and/more/some/relative/path")

    def test_create_wiki_icon_non_gui(self):
        """With a non-gui call, use a synchronous fetch"""
        relative, asynch, synch = self.given_instrumented_create_wiki_icon()
        self.test_object.macro.icon = "file://localhost/some/path.png"
        self.test_object.gui_up = False
        self.test_object._create_wiki_icon()
        self.assertFalse(relative.called)
        self.assertFalse(asynch.called)
        self.assertTrue(synch.called)

    def test_create_wiki_icon_gui(self):
        """When the GUI is up, use the Network Manager and an asynchronous access"""
        relative, asynch, synch = self.given_instrumented_create_wiki_icon()
        self.test_object.macro.icon = "file://localhost/some/path.png"
        self.test_object.gui_up = True
        self.test_object.network_manager = MockNetworkManager()
        self.test_object._create_wiki_icon()
        self.assertFalse(relative.called)
        self.assertTrue(asynch.called)
        self.assertFalse(synch.called)

    def given_instrumented_create_wiki_icon(self):
        """Fake the three required function calls in _create_wiki_icon"""
        relative = CallCatcher()
        asynch = CallCatcher()
        synch = CallCatcher()
        self.test_object._create_wiki_icon_from_relative_path = relative.catch_call
        self.test_object._begin_asynchronous_fetch = asynch.catch_call
        self.test_object._run_synchronous_fetch = synch.catch_call
        return relative, asynch, synch

    def test_icon_is_file_page_link_true(self):
        """File page links are correctly detected"""
        test_links = [
            "https://wiki.freecad.org/File:some_icon.png",
            "https://wiki.freecad.org/File:some_icon.png?param=1",
            "https://wiki.freecad.org/File:some_icon.png?param=1&param2=2"
            "file://localhost/File:some_icon.png"
        ]
        for test in test_links:
            self.test_object.macro.icon = test
            self.assertTrue(self.test_object._icon_is_file_page_link())

    def test_icon_is_file_page_link_false(self):
        """Non-file page links are correctly detected"""
        test_links = [
            "https://wiki.freecad.org/a/b/c/some_icon.png",
            "https://wiki.freecad.org/file/some_icon.png?param=file",
            "https://wiki.freecad.org/file/some_icon.png?param=file&param2=file"
            "file://localhost/file/some_icon.png"
        ]
        for test in test_links:
            self.test_object.macro.icon = test
            self.assertFalse(self.test_object._icon_is_file_page_link())

    def test_begin_asynchronous_fetch_direct_download(self):
        """With a direct download, the correct function is attached, and an unmonitored get is submitted"""
        self.test_object.network_manager = MockNetworkManager()
        self.test_object._begin_asynchronous_fetch("https://some.url", is_file_page=False)
        self.assertEqual(
            self.test_object.network_manager.completed.connections[0],
            self.test_object._handle_asynchronous_icon
        )
        self.assertIn("submit_unmonitored_get", self.test_object.network_manager.called_methods)

    def test_begin_asynchronous_fetch_file_page(self):
        """With a file page download, the correct function is attached, and an unmonitored get is submitted"""
        self.test_object.network_manager = MockNetworkManager()
        self.test_object._begin_asynchronous_fetch("https://some.url", is_file_page=True)
        self.assertEqual(
            self.test_object.network_manager.completed.connections[0],
            self.test_object._handle_asynchronous_file_page
        )
        self.assertIn("submit_unmonitored_get", self.test_object.network_manager.called_methods)

    def test_handle_asynchronous_file_page_not_index(self):
        """When the index doesn't match, nothing happens"""
        data, store, catch = self.given_data_and_asynch_harness("_parse_wiki_file_page")
        self.test_object._handle_asynchronous_file_page(-1, 200, data)
        self.assertFalse(store.called)
        self.assertFalse(catch.caught)

    def test_handle_asynchronous_file_page_bad_response(self):
        """When the index doesn't match, nothing happens"""
        data, store, catch = self.given_data_and_asynch_harness("_parse_wiki_file_page")
        self.test_object._handle_asynchronous_file_page(1, 404, data)
        self.assertFalse(store.called)
        self.assertTrue(catch.caught)

    def test_handle_asynchronous_file_page_good_response(self):
        """When the response is good, the data is dispatched for processing"""
        data, store, catch = self.given_data_and_asynch_harness("_parse_wiki_file_page")
        self.test_object._handle_asynchronous_file_page(1, 200, data)
        self.assertTrue(store.called)
        self.assertFalse(catch.caught)

    def test_handle_asynchronous_icon_not_index(self):
        """When the index doesn't match, nothing happens"""
        data, store, catch = self.given_data_and_asynch_harness("_store_icon_data")
        self.test_object._handle_asynchronous_icon(-1, 200, data)
        self.assertFalse(store.called)
        self.assertFalse(catch.caught)

    def test_handle_asynchronous_icon_bad_response(self):
        """When the response is bad, finished() is emitted and nothing else happens"""
        data, store, catch = self.given_data_and_asynch_harness("_store_icon_data")
        self.test_object._handle_asynchronous_icon(1, 404, data)
        self.assertFalse(store.called)
        self.assertTrue(catch.caught)

    def test_handle_asynchronous_icon_good_response(self):
        """When the response is good, the data is dispatched for processing"""
        data, store, catch = self.given_data_and_asynch_harness("_store_icon_data")
        self.test_object._handle_asynchronous_icon(1, 200, data)
        self.assertTrue(store.called)
        self.assertFalse(catch.caught)

    def given_data_and_asynch_harness(self, name_of_handler: str):
        """Generates fake data and creates a harness to detect a signal emission and a
        single function call."""
        data = MockByteArray()
        store_function = CallCatcher()
        signal_catcher = SignalCatcher()
        self.test_object.finished.connect(signal_catcher.catch_signal)
        self.test_object.async_index = 1
        self.test_object.__dict__[name_of_handler] = store_function.catch_call
        return [data, store_function, signal_catcher]

    def test_run_synchronous_fetch_file_page(self):
        """Given a file page URL, the data is fetched and dispatched"""
        filename = os.path.join(self.temp_dir, "some_path.txt")
        with open(filename, "w", encoding="utf-8") as f:
            f.write("Some fake testing data")
        file_page_catcher = CallCatcher()
        store_icon_catcher = CallCatcher()
        self.test_object._parse_wiki_file_page = file_page_catcher.catch_call
        self.test_object._store_icon_data = store_icon_catcher.catch_call
        self.test_object._run_synchronous_fetch("file://localhost/"+filename, is_file_page=True)
        self.assertTrue(file_page_catcher.called)
        self.assertFalse(store_icon_catcher.called)

    def test_run_synchronous_fetch_direct_link(self):
        """Given a direct download URL, the data is fetched and dispatched"""
        filename = os.path.join(self.temp_dir, "some_path.txt")
        with open(filename, "w", encoding="utf-8") as f:
            f.write("Some fake testing data")
        file_page_catcher = CallCatcher()
        store_icon_catcher = CallCatcher()
        self.test_object._parse_wiki_file_page = file_page_catcher.catch_call
        self.test_object._store_icon_data = store_icon_catcher.catch_call
        self.test_object._run_synchronous_fetch("file://localhost/"+filename, is_file_page=False)
        self.assertFalse(file_page_catcher.called)
        self.assertTrue(store_icon_catcher.called)

    def test_store_icon_data_known_extensions(self):
        """Given a URL with a known extension, the data is stored in a file"""
        good_extensions = [".svg", ".png", ".jpg", ".bmp", ".gif", ".webp", ".xpm"]
        for ext in good_extensions:
            with self.subTest(msg=f"Test extension {ext}", ext=ext):
                data = self.given_icon_with_extension(ext)
                self.test_object.finished = MockSignal()
                self.test_object._store_icon_data(data)
                self.assertTrue(self.test_object.finished.emitted)
                self.assert_icon_exists(os.path.join(self.cache_location, self.addon.name + ext))

    def given_icon_with_extension(self, ext: str) -> bytes:
        svg_file = os.path.join(self.temp_dir, "dummy_icon.svg")
        with open(svg_file, "w") as f:
            f.write(given_svg_data())
        icon = QtGui.QIcon(svg_file)
        if ext.lower() != ".svg":
            ext_file = os.path.join(self.temp_dir, f"dummy_icon{ext}")
            icon.pixmap(32, 32).save(ext_file)
        else:
            ext_file = svg_file
        self.addon.macro.icon = "file://localhost/" + ext_file
        with open(ext_file, "rb") as f:
            data = f.read()
            return data

    def assert_icon_exists(self, icon_file: str) -> None:
        self.assertTrue(os.path.exists(icon_file))

    def test_store_icon_data_unknown_extension(self):
        """Given an unknown image extension, no data is stored"""
        data = self.given_bad_image_data()
        self.test_object.finished = MockSignal()
        self.test_object._store_icon_data(data)
        self.assertTrue(self.test_object.finished.emitted)
        self.assertFalse(os.path.exists(os.path.join(self.cache_location, self.addon.name + ".txt")))

    def given_bad_image_data(self) -> bytes:
        bad_file = os.path.join(self.temp_dir, "dummy_icon.txt")
        with open(bad_file, "w", encoding="utf-8") as f:
            f.write("This is not image data")
        self.addon.macro.icon = "file://localhost/" + bad_file
        return "This is not image data".encode("utf-8")

    def test_parse_wiki_file_page_with_icon(self):
        """Icon URL is extracted from wiki page data"""
        html = self.given_wiki_html_with_icon()
        self.test_object._parse_wiki_file_page(html.encode("utf-8"))
        self.assert_url_matches(self.addon.macro.icon, "https://wiki.freecad.org/images/a/a2/Bevel.svg")

    @staticmethod
    def given_wiki_html_with_icon() -> str:
        return """
<div class="fullImageLink" id="file">
    <a href="/images/a/a2/Bevel.svg">
        <img alt="File:Bevel.svg" src="/images/a/a2/Bevel.svg" width="64" height="64"/>
    </a>
</div>
        """

    def assert_url_matches(self, first: str, second: str):
        parsed_first = urlparse(first)
        parsed_second = urlparse(second)
        self.assertEqual(parsed_first.scheme, parsed_second.scheme)
        self.assertEqual(parsed_first.netloc, parsed_second.netloc)
        self.assertEqual(parsed_first.path.replace("//", "/"), parsed_second.path.replace("//", "/"))

    def test_parse_wiki_file_page_no_icon(self):
        """Page data with no icon does not raise an exception"""
        html = "<html>\n<body>\n<h1>Blank page</h1>\n</body>\n</html>\n"
        self.test_object._parse_wiki_file_page(html.encode("utf-8"))
        self.assertEqual(self.addon.macro.icon, "")

    #####################
    # INTEGRATION TESTS #
    #####################

    @unittest.skipUnless(FreeCAD.GuiUp, "Synchronous test requires event loop")
    def test_run_integration_icon(self):
        """INTEGRATION TEST: Given icon data, run() gets the data and emits finished()"""
        signal_catcher = self.given_integration_test_setup()
        monitor = AsynchronousMonitor(self.test_object.finished)
        self.test_object.run()
        monitor.wait_for_at_most(1000)
        self.assertTrue(signal_catcher.caught)
        expected_icon_file = os.path.join(self.cache_location, self.addon.name + ".svg")
        if self.test_object.console.warnings or self.test_object.console.errors:
            print(self.test_object.console.warnings)
            print(self.test_object.console.errors)
            self.fail("Unexpected error output during run")
        self.assertTrue(os.path.exists(expected_icon_file), f"{expected_icon_file} does not exist")

    def test_run_integration_icon_synchronous(self):
        """INTEGRATION TEST: Given icon data, run() gets the data and emits finished()"""
        signal_catcher = self.given_integration_test_setup()
        self.test_object.gui_up = False
        self.test_object.run()
        self.assertTrue(signal_catcher.caught)
        expected_icon_file = os.path.join(self.cache_location, self.addon.name + ".svg")
        self.assertTrue(os.path.exists(expected_icon_file), f"{expected_icon_file} does not exist")

    def given_integration_test_setup(self):
        signal_catcher = SignalCatcher()
        self.test_object.finished.connect(signal_catcher.catch_signal)
        filename = os.path.join(self.temp_dir, "test_icon.svg")
        with open(filename, "w", encoding="utf-8") as f:
            f.write(given_svg_data())
        self.test_object.macro.icon = "file://localhost/" + filename
        return signal_catcher
