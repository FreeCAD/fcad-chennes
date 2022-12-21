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

"""Addon Manager Data Source consolidator: manages access to various data sources."""

import datetime
from enum import IntEnum, auto
import json
import os
from typing import List

from PySide import QtCore

import FreeCAD

from Addon import Addon

import addonmanager_utilities as utils

from addonmanager_source_local_cache import SourceLocalCache
from addonmanager_addon_source_git import AddonDataSourceGit
from addonmanager_macro_source_wiki import MacroDataSourceWiki
from addonmanager_macro_source_git import MacroDataSourceGit

translate = FreeCAD.Qt.translate


class BlockStatus(IntEnum):
    """The reason an addon is blocked (or not blocked)"""

    NOT_BLOCKED = auto()
    OBSOLETE = auto()
    REJECT_LIST = auto()
    PYTHON2 = auto()

    def __str__(self):
        if self.NOT_BLOCKED:
            return "not blocked"
        if self.OBSOLETE:
            return "marked as obsolete"
        if self.REJECT_LIST:
            return "on reject list"
        if self.PYTHON2:
            return "only supports Python 2"
        return "Unknown enum value"


class SourceFactory:
    """Factory class for creating the primary source list. Mainly for use with the testing code to
    inject mock sources."""

    @staticmethod
    def create_sources(skip_cache: bool = False):
        return [
            AddonDataSourceGit(skip_cache),
            # MacroDataSourceGit(skip_cache),
            MacroDataSourceWiki(skip_cache),
        ]


class AddonManagerSource(QtCore.QObject):
    """Manages access to all the data sources that the Addon Manager can pull Addon information
    from. Data may be cached locally, remotely, or not at all (direct access). It is designed to
    interact with classes derived from Qt's AbstractListItemModel, but does not itself derive from
    that class or provide any GUI functionality.

    Most of this class's internal workings are asynchronous when the GUI is running: calling code
    should not rely on data being available until the update_complete signal is emitted.

    This class is considered part of the Addon Manager's stable public API when used via the
    following methods, signals, and properties:
    * update (method, populates the list of addons with remote data)
    * load_local_cache (method, populates the list of addons with local cache data)
    * update_complete (signal, emitted when data is ready for use)
    * addons (property, the list of addons)
    """

    update_complete = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self.addons: List[Addon] = []
        self._addon_name_cache = set()

        self.source_factory = SourceFactory()
        self.source = None
        self.sources = []
        self.used_sources = []

        self.gui_up = FreeCAD.GuiUp  # So it can be switched off for testing

        prefs = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Addons")
        self.addon_flags_url = prefs.GetString(
            "AddonFlagsURL",
            "https://raw.githubusercontent.com/FreeCAD/FreeCAD-addons/master/addonflags.json",
        )
        self.addon_flags = {
            "obsolete": set(),
            "macro_reject_list": set(),
            "addon_reject_list": set(),
            "python2_only": set(),
        }
        self.mod_dir = os.path.join(FreeCAD.getUserAppDataDir(), "Mod")

        self.worker_thread = None

    def __del__(self):
        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait()

    def setup_sources(self, skip_cache):
        self.sources = self.source_factory.create_sources(skip_cache)

    def update(self):
        """Update the local addon list with remote data. It will emit the "update_complete"
        signal when updated data is ready for use. In some cases it will try to use remotely-cached
        data from FreeCAD's server: to prevent this set skip_cache to True (though note that
        updating will be much slower)."""
        if not self.sources:
            self.setup_sources(False)
        self._process_next_source()

    def _process_next_source(self):
        """Pop the next source off the front of the sources list and start it running in a new
        thread. Only do one source at a time so that the order the addons arrive is predictable.
        If the GUI is not running, instead of running it in a new thread, just run it right now,
        synchronously. To external code it should look the same."""
        if self.sources:
            source = self.sources.pop(0)
            source.addon_found.connect(self._handle_new_addon)
            FreeCAD.Console.PrintLog(f"Processing source {source.__class__.__name__}\n")
            self.used_sources.append(source)
            if self.gui_up:
                self._run_source_in_thread(source)
            else:
                source.run()
                self._process_next_source()
        else:
            self.update_complete.emit()

    def load_local_cache(self):
        """Load local data for each addon source. Does not use any remote data."""
        self.source = SourceLocalCache()
        self.source.addon_found.connect(self._handle_new_addon)
        if self.gui_up:
            self.worker_thread = QtCore.QThread()
            self.source.moveToThread(self.worker_thread)
            self.source.finished.connect(self._cache_load_complete)
            self.worker_thread.started.connect(self.source.run)
            self.worker_thread.start()
        else:
            self.source.run()
            self.update_complete.emit()

    def _cache_load_complete(self):
        if self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait()
            self.worker_thread = None
        self.update_complete.emit()

    def _run_source_in_thread(self, source):
        """Launch a new thread to run a source. Asynchronous, returns immediately."""
        self.worker_thread = QtCore.QThread()
        source.moveToThread(self.worker_thread)
        source.finished.connect(self._source_run_finished_callback)
        self.worker_thread.started.connect(source.run)
        self.worker_thread.start()

    def _source_run_finished_callback(self):
        self.worker_thread.quit()
        self.worker_thread.wait()
        self.worker_thread = None
        self._process_next_source()

    def _get_freecad_addon_repo_data(self):
        # update info lists
        p = utils.blocking_get(self.addon_flags_url)
        if p:
            j = json.loads(p.decode("utf-8"))
            if "obsolete" in j and "Mod" in j["obsolete"]:
                self.addon_flags["obsolete"] = set(j["obsolete"]["Mod"])

            if "blacklisted" in j and "Macro" in j["blacklisted"]:
                self.addon_flags["macro_reject_list"] = set(j["blacklisted"]["Macro"])

            if "blacklisted" in j and "Mod" in j["blacklisted"]:
                self.addon_flags["addon_reject_list"] = set(j["blacklisted"]["Mod"])

            if "py2only" in j and "Mod" in j["py2only"]:
                self.addon_flags["python2_only"] = set(j["py2only"]["Mod"])

            if "deprecated" in j:
                self._process_deprecated(j["deprecated"])

        else:
            message = translate(
                "AddonsInstaller",
                "Failed to connect to GitHub. Check your connection and proxy settings.",
            )
            FreeCAD.Console.PrintError(message + "\n")
            self.status_message.emit(message)
            raise ConnectionError

    def _process_deprecated(self, deprecated_addons):
        """Parse the section on deprecated addons"""
        for item in deprecated_addons:
            if "as_of" in item and "name" in item:
                try:
                    self._add_deprecation_entry(item)
                except ValueError:
                    FreeCAD.Console.PrintMessage(
                        f"Failed to parse version from {item['name']}, version {item['as_of']}"
                    )

    def _add_deprecation_entry(self, item):
        if self._version_lte_current_freecad_version(item["as_of"]):
            if "kind" not in item or item["kind"] == "mod":
                self.addon_flags["obsolete"].add(item["name"])
            elif item["kind"] == "macro":
                self.addon_flags["macro_reject_list"].add(item["name"])
            else:
                FreeCAD.Console.PrintMessage(
                    f'Unrecognized Addon kind {item["kind"]} in deprecation list.'
                )

    @staticmethod
    def _version_lte_current_freecad_version(as_of):
        fc_major = int(FreeCAD.Version()[0])
        fc_minor = int(FreeCAD.Version()[1])
        version_components = as_of.split(".")
        major = int(version_components[0])
        if len(version_components) > 1:
            minor = int(version_components[1])
        else:
            minor = 0
        if major < fc_major or (major == fc_major and minor <= fc_minor):
            return True
        return False

    def _update_install_details(self, addon: Addon):
        """If the addon is installed, set a few details about the installation"""
        if addon.macro is None:
            self._update_addon_install_details(addon)
        else:
            self._update_macro_install_details(addon)

    def _update_addon_install_details(self, addon: Addon):
        addon.set_status(self._get_addon_installation_state(addon.name))
        md_file = os.path.join(self.mod_dir, addon.name, "package.xml")
        if os.path.isfile(md_file):
            self._process_package_xml(md_file, addon)

        manifest = os.path.join(self.mod_dir, addon.name, "MANIFEST.txt")
        if os.path.isfile(manifest):
            self._process_manifest(manifest, addon)

    def _update_macro_install_details(self, addon: Addon):
        expected_file = os.path.join(self.macro_dir, addon.macro.filename)
        if os.path.exists(expected_file):
            addon.updated_timestamp = os.path.getmtime(expected_file)
            # TODO: Possibly determine the installed version by parsing the metadata from the on-disk file?
            addon.set_status(Addon.Status.UNCHECKED)
        else:
            addon.set_status(Addon.Status.NOT_INSTALLED)

    def _get_addon_installation_state(self, name):
        """Determine whether this addon is installed or not"""
        addon_dir = os.path.join(self.mod_dir, name)
        if os.path.exists(addon_dir) and os.listdir(addon_dir):
            return Addon.Status.UNCHECKED
        return Addon.Status.NOT_INSTALLED

    @staticmethod
    def _process_package_xml(file_path, addon):
        addon.load_metadata_file(file_path)
        addon.installed_version = addon.metadata.Version
        addon.updated_timestamp = os.path.getmtime(file_path)
        if hasattr(addon, "verify_url_and_branch"):
            addon.verify_url_and_branch(addon.url, addon.branch)

    @staticmethod
    def _process_manifest(file_path, addon):
        """Extract the last entry from the manifest file and set this addon's installation date to
        the date and time of that entry."""
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()
            last_line = lines[-1]
            date_string = last_line.split(",", 1)[0]
            timestamp = datetime.datetime.fromisoformat(date_string).timestamp()
            addon.updated_timestamp = timestamp

    def _handle_new_addon(self, addon: Addon):
        """If the new addon is not a repeat, add it to the list. Update its installation status.
        Log repeats."""
        block_status = self._addon_block_status(addon)
        if addon.name in self._addon_name_cache:
            source = addon.url
            addon_type = "macro" if addon.macro is not None else "addon"
            FreeCAD.Console.PrintLog(
                f"Additional copy of {addon_type} '{addon.name}' will be ignored "
                + f"(source of second copy is {source})\n"
            )
        elif block_status != BlockStatus.NOT_BLOCKED:
            FreeCAD.Console.PrintLog(
                f"Addon '{addon.name}' is blocked and will not be displayed ({block_status})"
            )
        else:
            FreeCAD.Console.PrintLog(f"Found new Addon '{addon.name}'\n")
            self._update_addon_install_details(addon)
            self._addon_name_cache.add(addon.name)
            self.addons.append(addon)

    def _addon_block_status(self, addon: Addon) -> BlockStatus:
        """Compare the addon against the various rejection lists"""
        if addon.name in self.addon_flags["obsolete"]:
            return BlockStatus.OBSOLETE
        if addon.name in self.addon_flags["python2_only"]:
            return BlockStatus.PYTHON2
        if (
            addon.macro is not None
            and addon.name in self.addon_flags["macro_reject_list"]
        ):
            return BlockStatus.REJECT_LIST
        if addon.macro is None and addon.name in self.addon_flags["addon_reject_list"]:
            return BlockStatus.REJECT_LIST
        return BlockStatus.NOT_BLOCKED
