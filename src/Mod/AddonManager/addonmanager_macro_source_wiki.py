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

"""Addon Manager Data Source: Wiki macro source."""

import html
import os
import re
from typing import List, Optional, Set

from PySide import QtCore

import FreeCAD

import addonmanager_utilities as utils
from NetworkManager import GetNetworkManager
from addonmanager_macro import Macro
from Addon import Addon

translate = FreeCAD.Qt.translate

# pylint: disable=too-few-public-methods

Log = FreeCAD.Console.PrintLog
Warn = FreeCAD.Console.PrintWarning
Err = FreeCAD.Console.PrintLog


class MacroFactory:
    """A factory for producing macros. Can be replaced by testing code to produce
    mock Macros."""

    @staticmethod
    def create_macro(name):
        """Standard macro creation function"""
        return Macro(name)


class AddonFactory:
    """A factory for producing Addons. Can be replaced by testing code to produce
    mock Addons."""

    @staticmethod
    def create_addon_from_macro(macro: Macro):
        """Create an addon from the Macro wrapper"""
        return Addon.from_macro(macro)


class MacroDataSourceWiki(QtCore.QObject):
    """Pull data from FreeCAD's wiki page listing public macros."""

    addon_found = QtCore.Signal(object)
    finished = QtCore.Signal()

    def __init__(self, _=False):
        super().__init__()
        self.pref = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Addons")
        self.macro_wiki_address = self.pref.GetString(
            "MacroWikiURL",
            "https://wiki.freecad.org/Macros_recipes",
        )
        self.download_macros = self.pref.GetBool("DownloadMacros", False)
        self.macro_factory = MacroFactory()
        self.addon_factory = AddonFactory()
        prefs = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Addons")
        blocked_macros_string = prefs.GetString(
            "BlockedMacros",
            "BOLTS,WorkFeatures,how to install,documentation,PartsLibrary,FCGear",
        )
        self.blocked_macros = blocked_macros_string.split(",")

    def __del__(self):
        Log("Deleting the MacroDataSourceWiki object")

    def run(self):
        """Retrieve macros from the wiki. Synchronous, but can be run inside a
        QThread so it doesn't block the GUI while it fetches the data."""
        try:
            self._run()
        except Exception as e:
            # We cannot let any exceptions leave this method (if it is in a QThread
            # bad things happen) so just dump them out to the console and bail out
            Err("An exception was caught in MacroDataSourceWiki:\n")
            Err(str(e) + "\n")

    def _run(self):
        macro_names = self._get_macro_names_from_wiki()

        class Counter:
            def __init__(self):
                self.count = 0

            def inc(self):
                self.count += 1

            def dec(self):
                self.count -= 1

        macros = []
        for macro_name in macro_names:
            if QtCore.QThread.currentThread().isInterruptionRequested():
                return
            if macro_name in self.blocked_macros:
                continue
            macro = self.macro_factory.create_macro(macro_name)
            macro.on_wiki = True
            macro.parsed = False
            macros.append(macro)

        counter = Counter()
        downloaders = []
        if self.download_macros:
            for macro in macros:
                counter.inc()
                downloaders.append(WikiMacroDownloader(macro))
                downloaders[-1].finished.connect(counter.dec)
                downloaders[-1].run()

        while counter.count > 0:
            if QtCore.QThread.currentThread().isInterruptionRequested():
                return
            QtCore.QCoreApplication.processEvents(QtCore.QEventLoop.AllEvents, 10)

        for macro in macros:
            addon = self.addon_factory.create_addon_from_macro(macro)
            addon.url = self.macro_wiki_address
            utils.update_macro_installation_details(addon)
            self.addon_found.emit(addon)
        self.finished.emit()

    def _get_macro_names_from_wiki(self) -> Set[str]:
        """Get the cleaned macro names from the wiki page."""
        macro_names = set()
        lines = self._get_macro_lines_from_wiki()
        for line in lines:
            macro_name = self._clean_macro_line(line)
            if macro_name:
                macro_names.add(macro_name)
        return macro_names

    def _get_macro_lines_from_wiki(self) -> List[str]:
        """Download the specified wiki page and get a list of lines containing macro
        information"""
        wiki_data = None
        try:
            wiki_data = utils.blocking_get(self.macro_wiki_address)
        except utils.UrlExceptionType:
            pass
        if not wiki_data:
            FreeCAD.Console.PrintWarning(
                translate(
                    "AddonsInstaller", "Error connecting to the Wiki page at {}"
                ).format(self.macro_wiki_address)
                + ". "
                + translate(
                    "AddonsInstaller",
                    "FreeCAD cannot retrieve the Wiki macro list at this time.",
                )
                + "\n",
            )
            return []
        wiki_data = wiki_data.decode("utf-8")
        return re.findall('title="(Macro.*?)"', wiki_data)

    def _clean_macro_line(self, line) -> Optional[str]:
        """Clean a single macro line, filtering out translation and recipes pages,
        and parsing any HTML entities back into their Unicode equivalents. Strips the
        word "Macro " from the beginning of the name."""
        if "translated" in line.lower() or "recipes" in line.lower():
            return None
        macro_name = line[6:]  # Remove "Macro "
        return html.unescape(macro_name)


class WikiMacroDownloader(QtCore.QObject):
    """Helper class to download and parse data from the individual wiki pages of each
    macro. Typically used asynchronously when the GUI is up: data is not available
    until finished() is emitted, which may be after run() has returned."""

    finished = QtCore.Signal()

    def __init__(self, macro: Macro):
        super().__init__()
        self.macro = macro
        self.cache_location = os.path.join(
            FreeCAD.getUserCachePath(), "AddonManager", "wiki_macros"
        )
        self.network_manager = None
        if FreeCAD.GuiUp:
            self.network_manager = GetNetworkManager()
            self.index = None

    def run(self):
        """Begin the download process. Asynchronous if the GUI is up, wait for the
        finished() signal before using the fetched data."""
        self.macro.url = self._wiki_page_url()
        if self.network_manager is not None:
            self._begin_asynchronous_fetch_of_wiki_page()
        else:
            self._synchronous_fetch_of_wiki_page()

    def _begin_asynchronous_fetch_of_wiki_page(self):
        self.network_manager.completed.connect(
            self._finish_asynchronous_fetch_of_wiki_page
        )
        self.index = self.network_manager.submit_unmonitored_get(self._wiki_page_url())

    def _finish_asynchronous_fetch_of_wiki_page(
        self, index: int, code: int, data: QtCore.QByteArray
    ):
        if index == self.index:
            Log(f"Received wiki data for {self.macro.name}\n")
            self.network_manager.completed.disconnect(
                self._finish_asynchronous_fetch_of_wiki_page
            )
            self.index = None
            if code == 200:
                self._parse_wiki_page(data.data().decode("utf-8"))

    def _synchronous_fetch_of_wiki_page(self):
        wiki_page_data = utils.blocking_get(self._wiki_page_url())
        self._parse_wiki_page(wiki_page_data.decode("utf-8"))

    def _wiki_page_url(self) -> str:
        mac = self.macro.name.replace(" ", "_")
        mac = mac.replace("&", "%26")
        mac = mac.replace("+", "%2B")
        url = "https://wiki.freecad.org/Macro_" + mac
        return url

    def _parse_wiki_page(self, wiki_page_data):
        if wiki_page_data:
            self.macro.parse_wiki_page(wiki_page_data)
            if self.macro.raw_code_url:
                self._fetch_raw_code()
            else:
                self._finalize()
        else:
            self._finalize()

    def _fetch_raw_code(self):
        if self.network_manager is not None:
            self._begin_asynchronous_fetch_of_raw_code()
        else:
            self._synchronous_fetch_of_wiki_raw_code()

    def _begin_asynchronous_fetch_of_raw_code(self):
        self.network_manager.completed.connect(
            self._finish_asynchronous_fetch_of_raw_code
        )
        self.index = self.network_manager.submit_unmonitored_get(
            self.macro.raw_code_url
        )

    def _synchronous_fetch_of_wiki_raw_code(self):
        raw_code = None
        try:
            raw_code = utils.blocking_get(self.macro.raw_code_url)
        except utils.UrlExceptionType:
            pass
        if raw_code:
            self.macro.code = raw_code.decode("utf-8")
        self._finalize()

    def _finish_asynchronous_fetch_of_raw_code(
        self, index: int, code: int, data: QtCore.QByteArray
    ):
        if index == self.index:
            self.network_manager.completed.disconnect(
                self._finish_asynchronous_fetch_of_raw_code
            )
            Log(f"Received raw code data for {self.macro.name}\n")
            self.index = None
            if code == 200:
                self.macro.code = data.data().decode("utf-8")
            self._finalize()

    def _finalize(self):
        if self.macro.code:
            self.macro.fill_details_from_code(self.macro.code)
        self.finished.emit()
