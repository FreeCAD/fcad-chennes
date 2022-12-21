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

"""Addon Manager Local Cache Data Source"""

import json
import os

from PySide import QtCore

import FreeCAD

from Addon import Addon

import addonmanager_utilities as utils

translate = FreeCAD.Qt.translate

# pylint: disable=too-few-public-methods


class AddonFactory:
    """Wrapper class for constructing addons. Used to allow test code to provide a mock version."""

    def create_from_cache(self, item):
        """Create an addon from a cache dictionary entry"""
        return Addon.from_cache(item)


class SourceLocalCache(QtCore.QObject):
    """Data source that uses entirely local data."""

    addon_found = QtCore.Signal(object)
    finished = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self.addon_factory = AddonFactory()
        self.cache_file = utils.get_cache_file_name("package_cache.json")
        self.metadata_cache_path = os.path.join(
            FreeCAD.getUserCachePath(), "AddonManager", "PackageMetadata"
        )

    def run(self):
        """Load local data for each addon source. Does not use any remote data."""
        try:
            with open(self.cache_file, encoding="utf-8") as f:
                data = f.read()
            from_json = json.loads(data)
            if len(from_json) == 0:
                raise RuntimeError("No JSON cache data")
            self.process_cache_data(from_json)
        except (OSError, json.JSONDecodeError, RuntimeError) as e:
            # If something went wrong we simply don't have any cache data: this is probably not
            # even an error. Log the situation and carry on.
            FreeCAD.Console.PrintLog(str(e) + "\n")
        self.finished.emit()

    def process_cache_data(self, cache_data):
        """Take data read in from a cache and process it into actual addons."""
        for item in cache_data.values():
            if QtCore.QThread.currentThread().isInterruptionRequested():
                return
            addon = self.addon_factory.create_from_cache(item)
            self.load_metadata(addon)
            self.addon_found.emit(addon)

    def load_metadata(self, addon: Addon):
        """Locate and load the package.xml metadata file"""
        repo_metadata_cache_path = os.path.join(
            self.metadata_cache_path, addon.name, "package.xml"
        )
        if os.path.isfile(repo_metadata_cache_path):
            # pylint: disable=broad-except
            try:
                addon.load_metadata_file(repo_metadata_cache_path)
            except Exception as e:
                FreeCAD.Console.PrintLog(f"Failed loading {repo_metadata_cache_path}\n")
                FreeCAD.Console.PrintLog(str(e) + "\n")
