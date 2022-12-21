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

from html import escape
import unittest
import os
import tempfile
import FreeCAD

from typing import Dict

from addonmanager_macro import Macro


class TestMacro(unittest.TestCase):

    MODULE = "test_macro"  # file name without extension

    def setUp(self):
        self.test_dir = os.path.join(
            FreeCAD.getHomePath(), "Mod", "AddonManager", "AddonManagerTest", "data"
        )
        self.test_object = Macro("Unit Test Macro")

    def test_basic_metadata(self):
        """All basic metadata entries are parsed"""
        replacements = {
            "COMMENT": "test comment",
            "WEB": "https://test.url",
            "VERSION": "1.2.3",
            "AUTHOR": "Test Author",
            "DATE": "2022-03-09",
            "ICON": "testicon.svg",
        }
        m = self.generate_macro(replacements)
        self.assertEqual(m.comment, replacements["COMMENT"])
        self.assertEqual(m.url, replacements["WEB"])
        self.assertEqual(m.version, replacements["VERSION"])
        self.assertEqual(m.author, replacements["AUTHOR"])
        self.assertEqual(m.date, replacements["DATE"])
        self.assertEqual(m.icon, replacements["ICON"])

    def test_other_files_no_spaces(self):
        """ "other files" list is extracted with comma separating entries"""
        replacements = {
            "FILES": "file_a,file_b,file_c",
        }
        m = self.generate_macro(replacements)
        self.assertEqual(len(m.other_files), 3)
        self.assertEqual(m.other_files[0], "file_a")
        self.assertEqual(m.other_files[1], "file_b")
        self.assertEqual(m.other_files[2], "file_c")

    def test_other_files_spaces(self):
        """Spaces after the commas are stripped from the "other files" list"""
        replacements = {
            "FILES": "file_a, file_b, file_c",
        }
        m = self.generate_macro(replacements)
        self.assertEqual(len(m.other_files), 3)
        self.assertEqual(m.other_files[0], "file_a")
        self.assertEqual(m.other_files[1], "file_b")
        self.assertEqual(m.other_files[2], "file_c")

    def test_other_files_no_commas(self):
        """Spaces are not delimiters for the "other files" list"""
        replacements = {
            "FILES": "file_a file_b file_c",
        }
        m = self.generate_macro(replacements)
        self.assertEqual(len(m.other_files), 1)
        self.assertEqual(m.other_files[0], "file_a file_b file_c")

    def test_version_from_string(self):
        """Version is extracted from a simple string"""
        replacements = {
            "VERSION": "1.2.3",
        }
        m = self.generate_macro(replacements)
        self.assertEqual(m.version, "1.2.3")

    def test_version_from_date(self):
        """Version is correctly extracted from a date"""
        replacements = {
            "DATE": "2022-03-09",
        }
        outfile = self.generate_macro_file(replacements)
        with open(outfile) as f:
            lines = f.readlines()
            output_lines = []
            for line in lines:
                if "VERSION" in line:
                    line = "__Version__ = __Date__"
                output_lines.append(line)
        with open(outfile, "w") as f:
            f.write("\n".join(output_lines))
        m = self.test_object
        m.fill_details_from_file(outfile)
        self.assertEqual(m.version, "2022-03-09")

    def test_version_from_float(self):
        """Version is correctly extracted from a float"""
        outfile = self.generate_macro_file()
        with open(outfile) as f:
            lines = f.readlines()
            output_lines = []
            for line in lines:
                if "VERSION" in line:
                    line = "__Version__ = 1.23"
                output_lines.append(line)
        with open(outfile, "w") as f:
            f.write("\n".join(output_lines))
        m = self.test_object
        m.fill_details_from_file(outfile)
        self.assertEqual(m.version, "1.23")

    def test_version_from_int(self):
        """Version is correctly extracted from an integer"""
        outfile = self.generate_macro_file()
        with open(outfile) as f:
            lines = f.readlines()
            output_lines = []
            for line in lines:
                if "VERSION" in line:
                    line = "__Version__ = 1"
                output_lines.append(line)
        with open(outfile, "w") as f:
            f.write("\n".join(output_lines))
        m = self.test_object
        m.fill_details_from_file(outfile)
        self.assertEqual(m.version, "1")

    def test_xpm(self):
        """XPM data is recognized and stored"""
        outfile = self.generate_macro_file()
        xpm_data = """/* XPM */
static char * blarg_xpm[] = {
"16 7 2 1",
"* c #000000",
". c #ffffff",
"**..*...........",
"*.*.*...........",
"**..*..**.**..**",
"*.*.*.*.*.*..*.*",
"**..*..**.*...**",
"...............*",
".............**."
};"""
        with open(outfile) as f:
            contents = f.read()
            contents += f'\n__xpm__ = """{xpm_data}"""\n'

        with open(outfile, "w") as f:
            f.write(contents)
        m = self.test_object
        m.fill_details_from_file(outfile)
        self.assertEqual(m.xpm, xpm_data)

    def generate_macro_file(self, replacements: Dict[str, str] = {}) -> os.PathLike:
        with open(os.path.join(self.test_dir, "macro_template.FCStd")) as f:
            lines = f.readlines()
            outfile = tempfile.NamedTemporaryFile(mode="wt", delete=False)
            for line in lines:
                for key, value in replacements.items():
                    line = line.replace(key, value)

                outfile.write(line)
            outfile.close()
            return outfile.name

    def generate_macro(self, replacements: Dict[str, str] = {}) -> Macro:
        outfile = self.generate_macro_file(replacements)
        m = self.test_object
        m.fill_details_from_file(outfile)
        os.unlink(outfile)
        return m

    def test_parse_wiki_page_for_icon_with_icon(self):
        """A wiki page with icon data correctly extracts the URL"""
        icon_path = "file://localhost/some/icon.svg"
        page_data = f"<a class=\"external text\" href=\"{icon_path}\">ToolBar Icon</a>"
        self.test_object._parse_wiki_page_for_icon(page_data)
        self.assertEqual(self.test_object.icon, icon_path)

    def test_parse_wiki_page_for_icon_without_icon(self):
        """A wiki page with icon data correctly extracts the URL"""
        icon_path = "file://localhost/some/icon.svg"
        page_data = f"<a class=\"external text\" href=\"{icon_path}\">Not the magic phrase</a>"
        self.test_object._parse_wiki_page_for_icon(page_data)
        self.assertEqual(self.test_object.icon, "")

    def test_extract_item_from_description_good(self):
        """A given item is found from the wiki page and extracted"""

        self.given_description()
        result = self.test_object._extract_item_from_description("Author: ")
        self.assertEqual(result, "Some great macro author")

    def test_extract_item_from_description_bad(self):
        """A given item is not found from the wiki page and returns None"""

        self.given_description()
        result = self.test_object._extract_item_from_description("Not in there: ")
        self.assertIsNone(result)

    def given_description(self):
        page_data = """
<td class="ctEven left macro-description">
    <p>
        This is some macro descriptive text.
        <br/>
        <br/>
        Macro version: 2020-05-17
        <br/>
        FreeCAD version: 0.19
        <br/>
        Download: 
        <a class="external text" href="https://someurl.com/Thing.svg">ToolBar Icon</a>
        <br/>
        Author: Some great macro author
        <br/>
    </p>
</td>
"""
        description = page_data.replace("\n", " ")
        self.test_object.desc = description

    def test_read_code_from_wiki_simple(self):
        """Given a simple wiki page, extract the pre block as wiki code"""
        html = "<html><body><pre>Some simple code</pre></body></html>"
        self.test_object._read_code_from_wiki(html)
        self.assertEqual(self.test_object.code, "Some simple code")
        
    def test_read_code_from_wiki_largest_block(self):
        """The code read extracts the largest of all found <pre> blocks"""
        html = "<html><body><pre>Short block</pre><pre>Longer block</pre></body></html>"
        self.test_object._read_code_from_wiki(html)
        self.assertEqual(self.test_object.code, "Longer block")

    def test_read_code_from_wiki_replaces_html_entities(self):
        """HTML entities are converted back into the unicode elements"""
        html = "<html><body><pre>" + escape("This & that") + "</pre></body></html>"
        self.test_object._read_code_from_wiki(html)
        self.assertEqual(self.test_object.code, "This & that")

    def test_read_code_from_wiki_replace_nonbreaking_space(self):
        """Unicode non-breaking space (\xc2\xa0) is replaced by space"""
        html = "<html><body><pre>Some" + b"\xc2\xa0".decode("utf-8") + "Code</pre></body></html>"
        self.test_object._read_code_from_wiki(html)
        self.assertEqual(self.test_object.code, "Some Code")
