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

"""Tests for adonmanager_source_git.py"""

import os
import pathlib
import tempfile
import unittest
import zipfile

import FreeCAD

from addonmanager_source_git import AddonManagerSourceGit, GitAddonFactory
from AddonManagerTest.app.mocks import MockAddon, MockMetadata, AddonSignalCatcher
import addonmanager_utilities as utils


class MockGitAddonFactory:
    def __init__(self):
        self.test_dir = os.path.join(
            FreeCAD.getHomePath(), "Mod", "AddonManager", "AddonManagerTest", "data"
        )

    def from_cache(self, cache: pathlib.Path):
        mock_addon = MockAddon()
        mock_addon.name = cache.name
        mock_addon.metadata = MockMetadata()
        if cache.exists() and cache.joinpath("package.xml").exists():
            with cache.joinpath("package.xml").open("r") as f:
                data = f.read()
                mock_addon.metadata.minimal_file_scan(data)
                mock_addon.set_metadata(mock_addon.metadata)
        else:
            raise RuntimeError("Mock cache file must be a real file")
        return mock_addon

    def construct_addon(
        self, name: str, url: str = "", status: int = 0, branch: str = "master"
    ):
        if not url:
            url = f"file://localhost/{self.test_dir}/"
        ao = MockAddon(name, url, status, branch)
        return ao

    def construct_metadata(self, _: bytes):
        return MockMetadata()


class TestSourceGit(unittest.TestCase):
    def setUp(self):
        self.test_object = AddonManagerSourceGit()
        self.test_object.addon_factory = MockGitAddonFactory()
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

    def test_fetch_last_update_info(self):
        """Test getting the last update info"""

    def test_fetch_cache_normal(self):
        """Test fetching a cache file"""

        # The test cache file has three addons in it: 3DfindIT, A2plus, and Curves. Each has a
        # package.xml metadata file and an icon file.
        self.test_object.cache_url = f"file://localhost/{self.test_dir}/metadata.zip"
        self.test_object.fetch_cache()

        self.assertEqual(len(self.test_object.addons), 3)
        expected_names = ["3DfindIT", "A2plus", "Curves"]
        for addon in self.test_object.addons:
            self.assertIn(addon.name, expected_names)
            expected_names.remove(addon.name)

    def test_fetch_cache_no_data(self):
        """Test that it is not an error if the cache is inaccessible"""
        self.test_object.cache_url = (
            f"file://localhost/{self.test_dir}/no_such_file.zip"
        )
        try:
            self.test_object.fetch_cache()  # Does not raise an exception
        except utils.UrlExceptionType as e:
            self.fail(
                f"Fetching cache from a bad URL should not have raised an exception:\n {str(e)}"
            )

    def test_fetch_cache_corrupted_zip(self):
        """Test that it is not an error if the cache is corrupted"""
        self.test_object.cache_url = (
            f"file://localhost/{self.test_dir}/corrupted_metadata.zip"
        )
        try:
            self.test_object.fetch_cache()  # Does not raise an exception
        except utils.UrlExceptionType as e:
            self.fail(
                f"Fetching cache from a bad file should not have raised an exception:\n {str(e)}"
            )
        self.assertEqual(len(self.test_object.addons), 0)

    def test_fetch_submodules_normal(self):
        """Test that fetching submodules works normally"""
        self.test_object.submodules_url = (
            f"file://localhost/{self.test_dir}/git_submodules.txt"
        )
        self.test_object.fetch_submodules()
        self.assertEqual(len(self.test_object.addons), 7)

    def test_fetch_submodules_bad_url(self):
        """Test that fetching submodules fails with a bad URL"""
        self.test_object.submodules_url = (
            f"file://localhost/{self.test_dir}/no_such_file.txt"
        )
        with self.assertRaises(Exception):
            self.test_object.fetch_submodules()

    def test_parse_submodules_normal(self):
        submodules_url = f"{self.test_dir}/git_submodules.txt"
        with open(submodules_url, encoding="utf-8") as f:
            data = f.read()
        parsed_submodules = self.test_object.parse_submodules(data)

        # We expect:
        # * Seven total submodules, as listed below
        # * Dictionary keys are the submodule names
        # * Default branch of "master" when it's not set otherwise
        # * No ".git" at the end of the URLs
        expected_submodules = {
            "3DfindIT": {
                "name":"3dfindit-freecad-integration",
                "url": "https://github.com/cadenasgmbh/3dfindit-freecad-integration",
                "branch": "master",
            },
            "A2plus": {
                "name":"A2plus",
                "url": "https://github.com/kbwbe/A2plus",
                "branch": "master",
            },
            "Behave-Dark-Colors": {
                "name":"FreeCAD-Behave-Dark-Preference-Pack",
                "url": "https://github.com/Chrismettal/FreeCAD-Behave-Dark-Preference-Pack",
                "branch": "main",
            },
            "Beltrami": {
                "name":"Beltrami",
                "url": "https://github.com/Simturb/Beltrami",
                "branch": "main",
            },
            "CurvedShapes": {
                "name":"CurvedShapesWorkbench",
                "url": "https://github.com/chbergmann/CurvedShapesWorkbench",
                "branch": "master",
            },
            "Curves": {
                "name":"CurvesWB",
                "url": "https://github.com/tomate44/CurvesWB",
                "branch": "master",
            },
            "Defeaturing": {
                "name":"Defeaturing_WB",
                "url": "https://github.com/easyw/Defeaturing_WB",
                "branch": "master",
            },
        }
        self.assertDictEqual(parsed_submodules, expected_submodules)

    def test_parse_submodules_duplicate(self):
        """Test that we accept only the first occurrence of a given name"""
        test_data = """
[submodule "TestSubmodule"]
	path = TestSubmodule
	url = https://test.url/1
[submodule "TestSubmodule"]
	path = TestSubmodule
	url = https://test.url/2
        """
        parsed_submodules = self.test_object.parse_submodules(test_data)
        self.assertIn("TestSubmodule", parsed_submodules)
        self.assertEqual(
            parsed_submodules["TestSubmodule"]["url"], "https://test.url/1"
        )

    def test_scan_submodules_no_cache(self):
        """Submodules but no cache add every submodule found"""
        submodules_data = {
            "3DfindIT": {
                "url": "https://github.com/cadenasgmbh/3dfindit-freecad-integration",
                "branch": "master",
            },
            "A2plus": {
                "url": "https://github.com/kbwbe/A2plus",
                "branch": "master",
            },
            "Behave-Dark-Colors": {
                "url": "https://github.com/Chrismettal/FreeCAD-Behave-Dark-Preference-Pack",
                "branch": "main",
            },
        }
        self.test_object.create_addons_from_submodules(submodules_data)
        self.assertEqual(len(submodules_data), len(self.test_object.addons))
        for submodule in submodules_data:
            found = False
            for addon in self.test_object.addons:
                if addon.name == submodule:
                    found = True
                    break
            self.assertTrue(found, "Expected addon not found in emitted signals")

    def test_scan_submodules_no_cache_misses(self):
        """Submodules that match cache perfectly should emit no signals"""
        mock_addons = [
            MockAddon("MockAddon1"),
            MockAddon("MockAddon2"),
            MockAddon("MockAddon3"),
        ]
        self.test_object.addons = mock_addons
        self.test_object._addon_name_cache.add("MockAddon1")
        self.test_object._addon_name_cache.add("MockAddon2")
        self.test_object._addon_name_cache.add("MockAddon3")
        submodules_data = {
            "MockAddon1": {
                "url": "https://github.com/mock_addon1/MockAddon1",
                "branch": "main",
            },
            "MockAddon2": {
                "url": "https://github.com/mock_addon2/MockAddon2",
                "branch": "main",
            },
            "MockAddon3": {
                "url": "https://github.com/mock_addon3/MockAddon3",
                "branch": "main",
            },
        }
        self.test_object.create_addons_from_submodules(submodules_data)
        self.assertEqual(len(self.test_object.addons), 3)

    def test_scan_submodules_with_cache_misses(self):
        """Submodules with sub cache overlap should only emit signals for the cache misses"""
        mock_addons = [MockAddon("MockAddon1")]
        self.test_object.addons = mock_addons
        self.test_object._addon_name_cache.add("MockAddon1")
        submodules_data = {
            "MockAddon1": {
                "url": "https://github.com/mock_addon1/MockAddon1",
                "branch": "main",
            },
            "MockAddon2": {
                "url": "https://github.com/mock_addon2/MockAddon2",
                "branch": "main",
            },
            "MockAddon3": {
                "url": "https://github.com/mock_addon3/MockAddon3",
                "branch": "main",
            },
        }
        self.test_object.create_addons_from_submodules(submodules_data)
        self.assertEqual(len(self.test_object.addons), 3)
        for submodule in ["MockAddon2", "MockAddon3"]:
            found = False
            for addon in self.test_object.addons:
                if addon.name == submodule:
                    found = True
                    break
            self.assertTrue(found, "Expected addon not found in addon list")

    def test_addon_factory_create_from_cache(self):
        """Make sure the addon factory can create an addon from the cache"""
        cache_file = os.path.join(self.test_dir, "metadata.zip")
        with zipfile.ZipFile(cache_file) as zip_file:
            mod_dir = zipfile.Path(zip_file, "metadata/A2plus")
            factory = GitAddonFactory()
            mock_factory = MockGitAddonFactory()
            factory.construct_addon = mock_factory.construct_addon
            factory.construct_metadata = mock_factory.construct_metadata
            created_addon = factory.from_cache(mod_dir)
            self.assertEqual(created_addon.name, "A2plus")
            self.assertIsNotNone(created_addon.metadata)

    def test_fetch_last_update_information_normal(self):
        """Last update should apply data to an addon in its cache"""
        addon = MockAddon("3DfindIT", branch="master")
        update_stats_url = f"file://localhost/{self.test_dir}/addon_update_stats.json"
        self.test_object.update_stats_url = update_stats_url
        self.test_object.fetch_last_update_information()
        self.test_object.add_update_info_to_addon(addon)
        self.assertTrue(addon.last_updated, "2022-09-08T13:58:17+02:00")

    def test_fetch_last_update_information_bad_branch(self):
        """Last update should not do anything for a branch it cannot find"""
        addon = MockAddon("3DfindIT", branch="no_such_branch")
        update_stats_url = f"file://localhost/{self.test_dir}/addon_update_stats.json"
        self.test_object.update_stats_url = update_stats_url
        self.test_object.fetch_last_update_information()
        self.test_object.add_update_info_to_addon(addon)
        self.assertIsNone(addon.last_updated)

    def test_fetch_last_update_information_bad_addon(self):
        """Last update should not do anything if it cannot find the addon"""
        addon = MockAddon("NoSuchAddon", branch="master")
        update_stats_url = f"file://localhost/{self.test_dir}/addon_update_stats.json"
        self.test_object.update_stats_url = update_stats_url
        self.test_object.fetch_last_update_information()
        self.test_object.add_update_info_to_addon(addon)
        self.assertIsNone(addon.last_updated)

    def test_add_update_info_no_data(self):
        """Last update should not do anything if it has no data"""
        addon = MockAddon("3DfindIT", branch="master")
        self.test_object.add_update_info_to_addon(addon)
        self.assertIsNone(addon.last_updated)

    def test_last_update_info_applied_to_submodules(self):
        """Test that when last update info is available, the addon has it"""
        update_stats_url = f"file://localhost/{self.test_dir}/addon_update_stats.json"
        self.test_object.update_stats_url = update_stats_url
        self.test_object.fetch_last_update_information()
        self.test_object.submodules_url = (
            f"file://localhost/{self.test_dir}/git_submodules.txt"
        )
        self.test_object.fetch_submodules()
        expected_last_update_for = ["3DfindIT", "A2plus", "Curves"]
        for addon in self.test_object.addons:
            if addon.name in expected_last_update_for:
                self.assertIsNotNone(
                    addon.last_updated,
                    f"Should have had last_updated data for {addon.name}",
                )
            else:
                self.assertIsNone(addon.last_updated)

    def test_last_update_info_applied_to_cache(self):
        """Test that when last update info is available, the cached addon has it"""
        update_stats_url = f"file://localhost/{self.test_dir}/addon_update_stats.json"
        self.test_object.update_stats_url = update_stats_url
        self.test_object.fetch_last_update_information()

        self.test_object.cache_url = f"file://localhost/{self.test_dir}/metadata.zip"
        self.test_object.fetch_cache()
        expected_last_update_for = ["3DfindIT", "A2plus", "Curves"]
        for addon in self.test_object.addons:
            if addon.name in expected_last_update_for:
                self.assertIsNotNone(
                    addon.last_updated,
                    f"Should have had last_updated data for {addon.name}",
                )
            else:
                self.assertIsNone(addon.last_updated)

    def test_construct_metadata_url_github(self):
        """Ensure that GitHub URLs result in the correct metadata URL"""
        base_url = "https://github.com/TestAddon/TestAddon"
        branch = "my_branch"
        filename = "package.xml"
        parsed_url = self.test_object.construct_metadata_url(base_url, branch, filename)
        self.assertEqual(parsed_url, f"{base_url}/raw/{branch}/{filename}")

    def test_construct_metadata_url_gitlab(self):
        """Ensure that Gitlab URLs result in the correct metadata URL"""
        base_url = "https://gitlab.com/TestAddon/TestAddon"
        branch = "my_branch"
        filename = "package.xml"
        parsed_url = self.test_object.construct_metadata_url(base_url, branch, filename)
        self.assertEqual(parsed_url, f"{base_url}/-/raw/{branch}/{filename}")

    def test_construct_metadata_url_framagit(self):
        """Ensure that Framagit URLs result in the correct metadata URL"""
        base_url = "https://framagit.com/TestAddon/TestAddon"
        branch = "my_branch"
        filename = "package.xml"
        parsed_url = self.test_object.construct_metadata_url(base_url, branch, filename)
        self.assertEqual(parsed_url, f"{base_url}/-/raw/{branch}/{filename}")

    def test_construct_metadata_url_salsa(self):
        """Ensure that Debian Salsa URLs result in the correct metadata URL"""
        base_url = "https://salsa.debian.org/TestAddon/TestAddon"
        branch = "my_branch"
        filename = "package.xml"
        parsed_url = self.test_object.construct_metadata_url(base_url, branch, filename)
        self.assertEqual(parsed_url, f"{base_url}/-/raw/{branch}/{filename}")

    def test_construct_metadata_url_unknown(self):
        """Ensure that unrecognized URLs result in the correct metadata URL"""
        base_url = "https://random.com/TestAddon/TestAddon"
        branch = "my_branch"
        filename = "package.xml"
        parsed_url = self.test_object.construct_metadata_url(base_url, branch, filename)
        self.assertEqual(parsed_url, f"{base_url}/-/raw/{branch}/{filename}")

    def test_construct_metadata_url_file(self):
        """Ensure that local file URLs result in the correct metadata URL"""
        base_url = "file://localhost/c:/not/a/real/url"
        branch = "my_branch"
        filename = "package.xml"
        parsed_url = self.test_object.construct_metadata_url(base_url, branch, filename)
        self.assertEqual(parsed_url, f"{base_url}/{filename}")

    def test_process_metadata_txt_file_wbs(self):
        """Test extracting workbench dependencies from metadata.txt data"""
        data = b"workbenches=Part,PartDesign,Sketcher"
        addon = MockAddon()
        self.test_object.process_metadata_txt(addon, data)
        self.assertIn("Part", addon.requires)
        self.assertIn("PartDesign", addon.requires)
        self.assertIn("Sketcher", addon.requires)

    def test_process_metadata_txt_file_py_deps(self):
        """Test extracting python dependencies from metadata.txt data"""
        data = b"pylibs=unittest,io,pathlib"
        addon = MockAddon()
        self.test_object.process_metadata_txt(addon, data)
        self.assertIn("unittest", addon.python_requires)
        self.assertIn("io", addon.python_requires)
        self.assertIn("pathlib", addon.python_requires)

    def test_process_metadata_txt_file_py_opts(self):
        """Test extracting optional python dependencies from metadata.txt data"""
        data = b"optionalpylibs=unittest,io,pathlib"
        addon = MockAddon()
        self.test_object.process_metadata_txt(addon, data)
        self.assertIn("unittest", addon.python_optional)
        self.assertIn("io", addon.python_optional)
        self.assertIn("pathlib", addon.python_optional)

    def test_process_requirements_txt(self):
        """Test extracting required python dependencies from requirements.txt data"""
        data = b"unittest>=1.2.3beta # Should only extract as unittest"
        addon = MockAddon()
        self.test_object.process_requirements_txt(addon, data)
        self.assertIn("unittest", addon.python_requires)

    def test_process_icon(self):
        """Test that an icon file is created"""
        with tempfile.TemporaryDirectory() as temp_dir:
            addon = MockAddon()
            icon_file = os.path.join(temp_dir, "icon.svg")
            addon.get_cached_icon_filename = lambda: icon_file
            byte_data = b"Fake icon data"
            self.test_object.process_icon(addon, byte_data)
            self.assertTrue(os.path.exists(icon_file))
            with open(icon_file, "rb") as f:
                comparison_data = f.read()
                self.assertEqual(byte_data, comparison_data)

    def test_decode_data_good_data(self):
        """Test that decoding well-formed UTF-8 data works"""
        with tempfile.TemporaryDirectory() as temp_dir:
            self.test_object.store = temp_dir
            data = b"This is good UTF-8-encoded data\n"
            f = self.test_object._decode_data(data, "MockAddon", "good_data.txt")
            self.assertEqual(f, "This is good UTF-8-encoded data\n")

    def test_decode_data_bad_data(self):
        """Test that decoding non-UTF-8 data does not crash (it only prints an error)"""
        with tempfile.TemporaryDirectory() as temp_dir:
            self.test_object.store = temp_dir
            data = "This is good UTF-8-encoded data\n".encode("utf-16")
            f = self.test_object._decode_data(data, "MockAddon", "bad_data.txt")
            self.assertEqual(f, "")

    def test_submit_icon_request_basic_icon(self):
        """Test fetching an icon with a toplevel icon in the metadata."""

        class IconProcessInterceptor:
            def __init__(self):
                self.called = False
                self.icon_data = None

            def process(self, addon, icon_data):
                self.called = True
                self.icon_data = icon_data

        interceptor = IconProcessInterceptor()
        with tempfile.TemporaryDirectory() as temp_dir:
            addon = MockAddon()
            addon.metadata = MockMetadata()
            addon.metadata.Icon = f"icon.svg"
            addon.url = f"file://localhost/{temp_dir}"
            icon_data = b"Some icon data"
            with open(os.path.join(temp_dir, "icon.svg"), "wb") as f:
                f.write(icon_data)
            self.test_object.process_icon = interceptor.process
            self.test_object.fetch_icon(addon)
            self.assertTrue(interceptor.called)
            self.assertEqual(interceptor.icon_data, icon_data)

    def test_submit_icon_request_content_icon(self):
        """Test asking for an icon when there is no toplevel, but there is in Content"""

        class IconProcessInterceptor:
            def __init__(self):
                self.called = False
                self.icon_data = None

            def process(self, addon, icon_data):
                self.called = True
                self.icon_data = icon_data

        interceptor = IconProcessInterceptor()
        with tempfile.TemporaryDirectory() as temp_dir:
            addon = MockAddon()
            addon.metadata = MockMetadata()
            wb = MockMetadata()
            wb.Icon = "icon.svg"
            wb.Subdirectory = "./"
            addon.metadata.Content = {"workbench": [wb]}
            addon.url = f"file://localhost/{temp_dir}"
            icon_data = b"Some icon data"
            with open(os.path.join(temp_dir, "icon.svg"), "wb") as f:
                f.write(icon_data)
            self.test_object.process_icon = interceptor.process
            self.test_object.fetch_icon(addon)
            self.assertTrue(interceptor.called)
            self.assertEqual(interceptor.icon_data, icon_data)

    def test_submit_icon_request_no_icon(self):
        """Test asking for an icon when there isn't one"""
        addon = MockAddon()
        addon.set_metadata(MockMetadata())
        self.test_object.fetch_icon(addon)  # Should not throw

    def test_parse_custom_addons_list(self):
        """Ensure the custom addons list data structure is generated correctly"""
        test_data = """https://github.com/FreeCAD/Test main
https://framagit.com/MyRepo/AnotherTest master
https://salsa.debian.org/TestRepo/ThirdTest
file://localhost/c:/users/test/FourthTest"""
        test_list = test_data.splitlines()
        expected_result = [
            {"name":"Test","url":"https://github.com/FreeCAD/Test","branch":"main"},
            {"name":"AnotherTest","url":"https://framagit.com/MyRepo/AnotherTest","branch":"master"},
            {"name":"ThirdTest","url":"https://salsa.debian.org/TestRepo/ThirdTest","branch":"master"},
            {"name":"FourthTest","url":"file://localhost/c:/users/test/FourthTest","branch":"master"},
        ]
        actual_result = self.test_object.parse_custom_addons_list(test_list)
        self.assertListEqual(actual_result, expected_result)

    def test_process_metadata_txt_line_normal(self):
        """Test that processing the line splits at = and , and puts the result in a set"""
        test_data = "something=thing1,thing2,thing3"
        set_result = set()
        self.test_object.process_metadata_txt_line(test_data, set_result)
        self.assertEqual(len(set_result), 3)
        self.assertIn("thing1", set_result)
        self.assertIn("thing2", set_result)
        self.assertIn("thing3", set_result)

    def test_process_metadata_txt_line_with_spaces(self):
        """Test that processing the line strips the spaces"""
        test_data = "something = thing1, thing2, thing3"
        set_result = set()
        self.test_object.process_metadata_txt_line(test_data, set_result)
        self.assertEqual(len(set_result), 3)
        self.assertIn("thing1", set_result)
        self.assertIn("thing2", set_result)
        self.assertIn("thing3", set_result)

    def test_process_metadata_txt_line_no_commas(self):
        """Test that processing the line doesn't split if there are no commas"""
        test_data = "something=thing1 thing2 thing3"
        set_result = set()
        self.test_object.process_metadata_txt_line(test_data, set_result)
        self.assertEqual(len(set_result), 1)
        self.assertIn("thing1 thing2 thing3", set_result)

    def test_process_metadata_txt_line_no_equals(self):
        """Test that processing the line does nothing if there is no equals sign"""
        test_data = "something thing1, thing2, thing3"
        set_result = set()
        self.test_object.process_metadata_txt_line(test_data, set_result)
        self.assertEqual(len(set_result), 0)




    ###############################################################################################
    #                                                                                             #
    #                                     INTEGRATION TESTS                                       #
    #                                                                                             #
    ###############################################################################################
        

    def test_run_normal(self):
        """Test that the run function integrates as expected"""

        self.test_object.update_stats_url = (
            f"file://localhost/{self.test_dir}/addon_update_stats.json"
        )
        self.test_object.cache_url = f"file://localhost/{self.test_dir}/metadata.zip"
        self.test_object.submodules_url = (
            f"file://localhost/{self.test_dir}/git_submodules.txt"
        )
        self.test_object.run()
        self.assertEqual(len(self.test_object.addons), 7)
        expected_metadata_for = ["3DfindIT", "A2plus", "Curves"]
        for addon in self.test_object.addons:
            if addon.name in expected_metadata_for:
                self.assertIsNotNone(addon.metadata)
            else:
                self.assertIsNone(addon.metadata)

    def test_update_metadata(self):
        """Test the integrated update_metadata function for local files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = "c:\\Users\\chennes\\Desktop\\"
            addons = []
            addon_names = [
                "TestAddon1HasMetadata",
                "TestAddon2",
                "TestAddon3HasMetadata",
                "TestAddon4",
                "TestAddon5HasMetadata",
            ]
            for name in addon_names:
                os.makedirs(os.path.join(temp_dir, name),exist_ok=True)
                if "HasMetadata" in name:
                    self.generate_fake_local_metadata_file(temp_dir, name)
                addons.append(MockAddon(name,url=f"file://localhost/{temp_dir}/{name}"))
            self.test_object.update_metadata(addons)
            for addon in addons:
                if "HasMetadata" in addon.name:
                    self.assertIsNotNone(addon.metadata, f"Metadata should exist for this the test addon {addon.name}")
                else:
                    self.assertIsNone(addon.metadata)

    def generate_fake_local_metadata_file(self, temp_dir, name):
        path_to_file = os.path.join(temp_dir, name, "package.xml")
        base_data = """<?xml version="1.0" encoding="utf-8" standalone="no" ?>
<package format="1" xmlns="https://wiki.freecad.org/Package_Metadata">
  <name>{}</name>
  <description>A package.xml file for unit testing.</description>
  <version>1.0.1</version>
  <date>2022-01-07</date>
  <url type="repository" branch="main">{}</url>
</package>
""".format(name, f"file://localhost/{temp_dir}/{name}")
        with open (path_to_file, "w", encoding = "utf-8") as f:
            f.write(base_data)
