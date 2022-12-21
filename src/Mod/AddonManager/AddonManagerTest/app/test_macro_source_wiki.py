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

"""Tests for adonmanager_source_wiki.py"""

import os
import tempfile
import unittest
import zipfile

from PySide import QtCore

import FreeCAD

from addonmanager_macro_source_wiki import MacroDataSourceWiki, WikiMacroDownloader
import addonmanager_utilities as utils
from AddonManagerTest.app.mocks import (
    AddonSignalCatcher,
    MockMacro,
    MockAddon,
    SignalCatcher,
    MockNetworkManager,
    CallCatcher,
)

do_slow_tests = False


class MockAddonFactory:
    @classmethod
    def create_addon_from_macro(cls, macro):
        return MockAddon(name=macro.name)


class MockMacroFactory:
    def create_macro(self, name):
        return MockMacro(name)


class TestMacroSourceWiki(unittest.TestCase):
    def setUp(self):
        self.test_object = MacroDataSourceWiki()
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

    def test_clean_macro_line_normal(self):
        """Ensure that a standard macro line is extracted correctly"""
        test_data = "Macro Snip"
        result = self.test_object._clean_macro_line(test_data)
        self.assertEqual(result, "Snip")

    def test_clean_macro_line_translation_line(self):
        """Ensure that a translated macro line is not extracted"""
        test_data = "Macros (1% translated)"
        result = self.test_object._clean_macro_line(test_data)
        self.assertIsNone(result, "result")

    def test_clean_macro_line_recipes_line(self):
        """Ensure that a recipes macro line is not extracted"""
        test_data = "Macros_recipes/es"
        result = self.test_object._clean_macro_line(test_data)
        self.assertIsNone(result, "result")

    def test_get_macro_lines_from_wiki_normal(self):
        """Ensure the correct information is extracted from the lines with title="Macro ..." """
        test_data = """
<a href="/Macro_Rotate_View_Free" title="Macro Rotate View Free">Macro Rotate View Free</a>
<a href="/Macro_Rotate_View" title="Macro Rotate View">Macro Rotate View</a>
<a href="/Macro_Snip" title="Macro Snip">Macro Snip</a>
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            filename = os.path.join(temp_dir, "wiki_data.html")
            with open(filename, "w", encoding="utf-8") as f:
                f.write(test_data)
            file_url = f"file://localhost/{filename}"
            self.test_object.macro_wiki_address = file_url
            result = self.test_object._get_macro_lines_from_wiki()
            expected_result = [
                "Macro Rotate View Free",
                "Macro Rotate View",
                "Macro Snip",
            ]
            self.assertListEqual(result, expected_result)

    def test_get_macro_lines_from_wiki_no_macros(self):
        """Ensure no macros are extracted when the title does not start with "Macro" """
        test_data = """
<a href="/Macro_Rotate_View_Free" title="Rotate View Free">Macro Rotate View Free</a>
<a href="/Macro_Rotate_View" title="Rotate View">Macro Rotate View</a>
<a href="/Macro_Snip" title="Snip">Macro Snip</a>
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            filename = os.path.join(temp_dir, "wiki_data.html")
            with open(filename, "w", encoding="utf-8") as f:
                f.write(test_data)
            file_url = f"file://localhost/{filename}"
            self.test_object.macro_wiki_address = file_url
            result = self.test_object._get_macro_lines_from_wiki()
            expected_result = []
            self.assertListEqual(result, expected_result)

    def test_get_macro_lines_from_wiki_bad_url(self):
        """Ensure no exception is thrown when the URL cannot be accessed"""
        file_url = f"file://localhost/no/such/file.html"
        self.test_object.macro_wiki_address = file_url
        result = self.test_object._get_macro_lines_from_wiki()  # Doesn't throw
        expected_result = []
        self.assertListEqual(result, expected_result)

    ###############################################################################################
    #                                                                                             #
    #                                     INTEGRATION TESTS                                       #
    #                                                                                             #
    ###############################################################################################

    @unittest.skipUnless(do_slow_tests, "Slow tests skipped")
    def test_run_basic(self):
        """Test that the run function emits signals for expected macros"""
        test_data = """
<a href="/Macro_Rotate_View_Free" title="Macro Rotate View Free">Macro Rotate View Free</a>
<a href="/Macro_Rotate_View" title="Macro Rotate View">Macro Rotate View</a>
<a href="/Macro_Snip" title="Macro Snip">Macro Snip</a>
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            filename = os.path.join(temp_dir, "wiki_data.html")
            with open(filename, "w", encoding="utf-8") as f:
                f.write(test_data)
            file_url = f"file://localhost/{filename}"
            self.test_object.macro_wiki_address = file_url
            self.test_object.run()

        self.assertEqual(len(self.signal_catcher.addons), 3)
        expected_result = ["Rotate View Free", "Rotate View", "Snip"]
        for addon in self.signal_catcher.addons:
            self.assertIn(addon.name, expected_result)
            expected_result.remove(addon.name)

    @unittest.skipUnless(do_slow_tests, "Slow tests skipped")
    def test_run_real_data(self):
        """Test that the run function works for a real wiki page full of macros"""
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_file = os.path.join(self.test_dir, "MacrosRecipesWikiPage.zip")
            with zipfile.ZipFile(zip_file, "r") as zf:
                zf.extractall(path=temp_dir)
            filename = os.path.join(
                temp_dir, "Macros recipes - FreeCAD Documentation.html"
            )
            file_url = f"file://localhost/{filename}"
            self.test_object.macro_wiki_address = file_url
            self.test_object.run()
        self.assertEqual(len(self.signal_catcher.addons), 205)


class TestWikiMacroDownloader(unittest.TestCase):
    def setUp(self):
        self.macro = MockMacro()
        self.temp_dir = tempfile.mkdtemp()
        self.test_object = WikiMacroDownloader(self.macro)
        self.call_catcher = CallCatcher()

    def tearDown(self):
        utils.rmdir(self.temp_dir)

    def test_run_with_network_manager(self):
        """Run is asynchronous if there is a network manager"""
        self.test_object._begin_asynchronous_fetch_of_wiki_page = (
            self.call_catcher.catch_call
        )
        self.test_object.network_manager = MockNetworkManager()
        self.test_object.run()
        self.assertTrue(self.call_catcher.called)

    def test_run_without_network_manager(self):
        """Run is synchronous if there is no network manager"""
        self.test_object._synchronous_fetch_of_wiki_page = self.call_catcher.catch_call
        self.test_object.network_manager = None
        self.test_object.run()
        self.assertTrue(self.call_catcher.called)

    def test_begin_asynchronous_fetch_of_wiki_page(self):
        """Aynchronous fetch sets up connection and asks for the correct URL"""
        self.test_object.network_manager = MockNetworkManager()
        self.test_object._wiki_page_url = lambda: "https://fake.url"
        self.test_object._begin_asynchronous_fetch_of_wiki_page()
        self.assertEqual(len(self.test_object.network_manager.completed.connections), 1)
        self.assertListEqual(
            self.test_object.network_manager.urls, ["https://fake.url"]
        )

    def test_finish_asynchronous_fetch_of_wiki_page_normal(self):
        """With matching index and 200 response code, page data is obtained"""
        index, code, data = self.given_wiki_page_network_response(
            1, 200, "Wiki page data"
        )
        self.test_object._finish_asynchronous_fetch_of_wiki_page(index, code, data)
        self.assertTrue(self.call_catcher.called)
        self.assertEqual(self.call_catcher.args[0], "Wiki page data")
        self.assertEqual(
            len(self.test_object.network_manager.completed.disconnections), 1
        )

    def test_finish_asynchronous_fetch_of_wiki_page_not_index(self):
        """With no matching index, nothing happens"""
        index, code, data = self.given_wiki_page_network_response(
            2, 200, "Wiki page data"
        )
        self.test_object._finish_asynchronous_fetch_of_wiki_page(index, code, data)
        self.assertFalse(self.call_catcher.called)
        self.assertEqual(
            len(self.test_object.network_manager.completed.disconnections), 0
        )

    def test_finish_asynchronous_fetch_of_wiki_page_bad_code(self):
        """With a matching index but no data, the disconnection happens, but the data parse doesn't"""
        index, code, data = self.given_wiki_page_network_response(
            1, 404, "Wiki page data"
        )
        self.test_object._finish_asynchronous_fetch_of_wiki_page(index, code, data)
        self.assertFalse(self.call_catcher.called)
        self.assertEqual(
            len(self.test_object.network_manager.completed.disconnections), 1
        )

    def given_wiki_page_network_response(self, index, code, data):
        self.test_object.network_manager = MockNetworkManager()
        self.test_object._parse_wiki_page = self.call_catcher.catch_call
        self.test_object.index = 1
        return index, code, QtCore.QByteArray(data.encode("utf-8"))

    def test_synchronous_fetch_of_wiki_page(self):
        """Synchronous wiki page fetch loads the given URL"""
        local_file = os.path.join(self.temp_dir, "wiki_page.html")
        with open(local_file, "w", encoding="utf-8") as f:
            f.write("Some fake wiki page data")
        url = "file://localhost/" + local_file
        self.test_object._parse_wiki_page = self.call_catcher.catch_call
        self.test_object._wiki_page_url = lambda: url
        self.test_object._synchronous_fetch_of_wiki_page()
        self.assertTrue(self.call_catcher.called)
        self.assertEqual(self.call_catcher.args[0], "Some fake wiki page data")

    def test_wiki_page_url(self):
        """Special characters are converted to the correct entities"""
        test_cases = {
            "NothingSpecial": "NothingSpecial",
            "With space": "With_space",
            "And & and": "And_%26_and",
            "Plus + plus": "Plus_%2B_plus",
        }
        for name, out in test_cases.items():
            with self.subTest(name=name, out=out):
                self.macro.name = name
                url = self.test_object._wiki_page_url()
                self.assertEqual(url, "https://wiki.freecad.org/Macro_" + out)

    def test_parse_wiki_page_no_page_data(self):
        """When there is no data, no error is raised, and finalize is called"""
        self.test_object._finalize = self.call_catcher.catch_call
        self.test_object._parse_wiki_page(None)
        self.assertTrue(self.call_catcher.called)

    def test_parse_wiki_page_no_raw_url(self):
        """When there is page data but no raw url, finalize is called"""
        self.test_object._finalize = self.call_catcher.catch_call
        self.test_object._parse_wiki_page("Page data")
        self.assertTrue(self.call_catcher.called)

    def test_parse_wiki_page_wth_raw_url(self):
        """When there is a raw_code_url, it is loaded, and finalize is not called"""
        self.test_object._fetch_raw_code = lambda: None
        self.macro.raw_code_url = "file://localhost/some/file"
        self.test_object._finalize = self.call_catcher.catch_call
        self.test_object._parse_wiki_page("Page data")
        self.assertFalse(self.call_catcher.called)

    def test_fetch_raw_code_asynchronous(self):
        """When there is a network manager, the asynchronous branch is executed"""
        self.test_object.network_manager = MockNetworkManager()
        self.test_object._begin_asynchronous_fetch_of_raw_code = (
            self.call_catcher.catch_call
        )
        self.test_object._fetch_raw_code()
        self.assertTrue(self.call_catcher.called)

    def test_fetch_raw_code_synchronous(self):
        """When there is no network manager, the synchronous branch is executed"""
        self.test_object.network_manager = None
        self.test_object._synchronous_fetch_of_wiki_raw_code = (
            self.call_catcher.catch_call
        )
        self.test_object._fetch_raw_code()
        self.assertTrue(self.call_catcher.called)

    def test_begin_asynchronous_fetch_of_raw_code(self):
        """A connection is established, and the request is submitted"""
        self.macro.raw_code_url = "/some/fake/url"
        self.test_object.network_manager = MockNetworkManager()
        self.test_object._begin_asynchronous_fetch_of_raw_code()
        self.assertEqual(len(self.test_object.network_manager.completed.connections), 1)
        self.assertIn(self.macro.raw_code_url, self.test_object.network_manager.urls)

    def test_synchronous_fetch_of_wiki_raw_code_bad_url(self):
        """If given a bad url finalize is still called, but no code is parsed"""
        self.macro.raw_code_url = "file://localhost/no/such/file"
        self.test_object._finalize = self.call_catcher.catch_call
        self.test_object._synchronous_fetch_of_wiki_raw_code()
        self.assertTrue(self.call_catcher.called, "finalize() was not called")
        self.assertEqual(self.macro.code, "")

    def test_synchronous_fetch_of_wiki_raw_code_empty_file(self):
        """If given a an empty code file finalize is still called, but no code is parsed"""
        local_file = os.path.join(self.temp_dir, "raw_code.py")
        with open(local_file, "w", encoding="utf-8") as f:
            f.write("")
        self.macro.raw_code_url = "file://localhost" + local_file.replace(
            os.path.sep, "/"
        )
        self.test_object._finalize = self.call_catcher.catch_call
        self.test_object._synchronous_fetch_of_wiki_raw_code()
        self.assertTrue(self.call_catcher.called, "finalize() was not called")
        self.assertEqual(self.macro.code, "")

    def test_synchronous_fetch_of_wiki_raw_code_normal(self):
        """When given good code, it is parsed, and finalize is called"""
        local_file = os.path.join(self.temp_dir, "raw_code.py")
        with open(local_file, "w", encoding="utf-8") as f:
            f.write("Test data")
        self.macro.raw_code_url = "file://localhost/" + local_file.replace(
            os.path.sep, "/"
        )
        self.test_object._finalize = self.call_catcher.catch_call
        self.test_object._synchronous_fetch_of_wiki_raw_code()
        self.assertTrue(self.call_catcher.called, "finalize() was not called")
        self.assertEqual(self.macro.code, "Test data")

    def test_finish_asynchronous_fetch_of_raw_code_not_index(self):
        """If the index is not from this call, do nothing"""
        index, code, data = self.given_raw_code_network_response(2, 200, "Fake data")
        self.test_object._finish_asynchronous_fetch_of_raw_code(index, code, data)
        self.assertEqual(
            len(self.test_object.network_manager.completed.disconnections),
            0,
            "Signal was disconnected",
        )
        self.assertFalse(
            self.call_catcher.called,
            "Called finalize() even though this request was irrelevant",
        )
        self.assertEqual(self.macro.code, "")

    def test_finish_asynchronous_fetch_of_raw_code_not_good(self):
        """If the index matches, but the response code is not 200, disconnect, but don't parse"""
        index, code, data = self.given_raw_code_network_response(1, 404, "Fake data")
        self.test_object._finish_asynchronous_fetch_of_raw_code(index, code, data)
        self.assertEqual(
            len(self.test_object.network_manager.completed.disconnections),
            1,
            "Signal was not disconnected",
        )
        self.assertTrue(
            self.call_catcher.called, "Failed to call finalize() when the data was bad"
        )
        self.assertEqual(self.macro.code, "")

    def test_finish_asynchronous_fetch_of_raw_code_normal(self):
        """If the index matches, and the response is good, parse and finalize"""
        index, code, data = self.given_raw_code_network_response(1, 200, "Fake data")
        self.test_object._finish_asynchronous_fetch_of_raw_code(index, code, data)
        self.assertEqual(
            len(self.test_object.network_manager.completed.disconnections),
            1,
            "Signal was not disconnected",
        )
        self.assertTrue(
            self.call_catcher.called, "Failed to call finalize() when the data was bad"
        )
        self.assertEqual(self.macro.code, "Fake data")

    def given_raw_code_network_response(self, index, code, data):
        self.test_object.network_manager = MockNetworkManager()
        self.test_object._finalize = self.call_catcher.catch_call
        self.test_object.index = 1
        return index, code, QtCore.QByteArray(data.encode("utf-8"))

    def test_finalize_with_code(self):
        """Finalize asks the macro to parse the code, and emits the finished signal"""
        catcher = SignalCatcher()
        self.macro.code = "Something that does not evaluate to False"
        self.test_object.finished.connect(catcher.catch_signal)
        self.test_object._finalize()
        self.assertTrue(catcher.caught, "finished() not emitted")
        self.assertTrue(self.macro.details_filled_from_code, "Macro code not parsed")

    def test_finalize_without_code(self):
        """Finalize does not try to parse the code, and emits the finished signal"""
        catcher = SignalCatcher()
        self.test_object.finished.connect(catcher.catch_signal)
        self.test_object._finalize()
        self.assertTrue(catcher.caught, "finished() not emitted")
        self.assertFalse(self.macro.details_filled_from_code, "Macro code parsed")
