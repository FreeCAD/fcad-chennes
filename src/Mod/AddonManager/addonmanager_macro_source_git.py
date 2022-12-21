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

"""Addon Manager Data Source: Git repository of macros."""

from datetime import datetime, timezone
import json
from typing import List
import os

import FreeCAD
from PySide import QtCore

import addonmanager_utilities as utils
from addonmanager_git import initialize_git, GitFailed
from addonmanager_macro import Macro
from Addon import Addon

translate = FreeCAD.Qt.translate

# pylint: disable=too-few-public-methods,too-many-instance-attributes


class AddonFactory:
    """Factory class for creating addons from macros. Provided so that testing code can override
    it and provide a Mock for the addons."""

    def from_macro(self, macro: Macro):
        """Create an Addon from a Macro"""
        return Addon.from_macro(macro)


class MacroFactory:
    """Factory class for creating macros.Provided so that testing code can override it and provide
    a Mock for the macros."""

    def create_macro(self, filename: os.PathLike) -> Macro:
        """Create a Macro object from an on-disk macro file."""
        return Macro(filename[:-8])  # Remove ".FCMacro"


class MacroDataSourceGit(QtCore.QObject):
    """Pull data from FreeCAD's GitHub macro repository. Uses git if possible, otherwise downloads
    the repository as a Zip file."""

    addon_found = QtCore.Signal(object)
    finished = QtCore.Signal()

    def __init__(self, force_update: bool = False):
        super().__init__()
        self.addon_factory = AddonFactory()
        self.macro_factory = MacroFactory()
        self.git_manager = initialize_git()
        pref = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Addons")
        self.macro_git_address: str = pref.GetString(
            "MacroGitURL",
            "https://github.com/FreeCAD/FreeCAD-Macros",
        )
        self.macro_git_branch = "master"

        self.update_stats_url = pref.GetString(
            "MacroUpdateStatsURL", "https://addons.freecad.org/macro_update_stats.json"
        )
        self.update_frequency = pref.GetInt("MacroCacheUpdateFrequency", 7)  # In days
        self.macro_update_stats = []
        self.force_update = force_update
        self.macro_cache_location = utils.get_cache_file_name("Macros")

    def run(self):
        """Get all of the macros from the git repository and emit a signal for each one found."""
        # self.fetch_last_updated_information()
        if self.should_update():
            if self.git_manager is not None:
                self.update_with_git()
            else:
                self.update_with_zip()
        macro_list = self.scan_for_macros()
        for macro in macro_list:
            addon = self.create_addon_for_macro(macro)
            self.addon_found.emit(addon)
        self.finished.emit()

    def process_git_preference(self):
        """Determine from the stored user preference string some of the basic information about the
        git repository we are accessing."""

        if self.macro_git_address.lower().endswith(".zip"):
            # We allow direct-download links to a zipfile: in that case, bypass git
            self.git_manager = None
        elif " " in self.macro_git_address:
            # It contains branch information:
            url_and_branch = self.macro_git_address.split(" ", 1)
            self.macro_git_address = url_and_branch[0]
            self.macro_git_branch = url_and_branch[1]
        else:
            self.macro_git_branch = "master"

    def fetch_last_updated_information(self, max_size=1000000):
        """Attempt to download the last-updated information for the git macros."""
        data: bytes = utils.blocking_get(self.update_stats_url)
        if not data:
            return
        if len(data) > max_size:
            # As recommended by the Python JSON documentation, sanity-check the size of the input
            # data and don't try to JSON decode if it's too large. Use 1000kb as the max size by
            # default (it's a parameter to test code can override it).
            FreeCAD.PrintWarning(
                translate(
                    "AddonsInstaller",
                    "Unexpectedly large amount of data received for Macro update stats",
                )
                + "\n"
            )
            return
        try:
            self.macro_update_stats = json.loads(data)
        except json.JSONDecodeError as e:
            FreeCAD.PrintWarning(
                translate(
                    "AddonsInstaller", "Error parsing macro last-update information."
                )
                + "\n"
            )
            FreeCAD.PrintLog(e.msg)

    def should_update(self) -> bool:
        """Run a series of tests to see if we should perform an update of the local copy of the
        macros repository."""

        # Trivial cases first: either we've been told from outside that updates are being forced,
        # we are using git (so updating is itself trivial), or we don't have a local copy yet at
        # all. In those cases, always update.
        if (
            self.force_update
            or self.git_manager is not None
            or not os.path.exists(self.macro_cache_location)
        ):
            return True

        # After this, everything assumes that the local cache was a downloaded zip, and that we do
        # not have git. So the task is to determine if the local cache needs to be re-downloaded.

        # Get the modification time of a known local file for comparison purposes. If this file
        # does not exist, then there is something wrong with the local cache, in which case we
        # should rebuild it (e.g. return True)
        path_to_readme = os.path.join(self.macro_cache_location, "README.md")
        try:
            modified = datetime.fromtimestamp(
                os.path.getmtime(path_to_readme), tz=timezone.utc
            )
        except OSError:
            FreeCAD.Console.PrintWarning(
                translate(
                    "AddonsInstaller",
                    "Could not get modification time for cache file {}",
                ).format(path_to_readme)
            )
            return True

        # See if the FreeCAD Addons server can provide us with a "last updated" time for the git
        # macros:
        if self.macro_update_stats:
            latest_update = self.get_latest_update_from_stats(self.macro_update_stats)
            if latest_update > modified:
                return True
            return False

        # Finally, if we just don't know, then only try to update once per N days, where N is
        # a user-configurable option. Use the modification time of README.md as the standard, since
        # when we uncompressed the files we reset the current modification time to the time of
        # extraction.
        now = datetime.now(tz=timezone.utc)
        difference = now - modified
        days = max(difference.total_seconds() / (24.0 * 60.0 * 60.0), 0)
        # Round it so that we really check up to a half day early (e.g. 6.5 days rounds to 7 days)
        if round(days) >= self.update_frequency:
            return True
        return False

    def get_latest_update_from_stats(self, update_stats) -> datetime:
        """Scan the update stats data and find the most recently-updated macro's update time and
        return it."""
        if not isinstance(update_stats, dict):
            raise TypeError(
                "Expected update_stats to be a dictionary of name:timestamp pairs"
            )
        latest_update_time = 0
        for time in update_stats.values():
            latest_update_time = max(latest_update_time, time)
        return datetime.fromtimestamp(latest_update_time, timezone.utc)

    def update_with_git(self) -> bool:
        """If git exists, and the repository has already been cloned, this runs git pull on it. If
        git is installed but the repository has not been cloned, this runs git clone."""
        try:
            if os.path.exists(self.macro_cache_location):
                # So we have some kind of cache... is it a git repo?
                if not os.path.exists(os.path.join(self.macro_cache_location, ".git")):
                    # We created a cache in the past without git, but now we have git. Convert that
                    # cache into a git repo:
                    self.git_manager.repair(
                        self.macro_git_address, self.macro_cache_location
                    )
                # If the code reaches this point, there is a git repo in place, update it
                self.git_manager.update(self.macro_cache_location)
            else:
                # The cache location does not exist, so we need to clone a new copy
                self.git_manager.clone(
                    self.macro_git_address, self.macro_cache_location
                )
        except GitFailed as e:
            FreeCAD.Console.PrintLog(
                "An error occurred updating the local checkout of the macros repository. Deleting "
                f"it and checking it out again...\n\nThe error message was:\n{e}\n\n"
            )
            try:
                original_wd = os.getcwd()
                os.chdir(
                    os.path.join(self.macro_cache_location, "..")
                )  # Make sure we are not IN this directory
                utils.rmdir(self.macro_cache_location)
                self.git_manager.clone(
                    self.macro_git_address,
                    self.macro_cache_location,
                )
                os.chdir(original_wd)
                FreeCAD.Console.PrintLog("Clean checkout succeeded\n")
            except GitFailed as e2:
                phrase1 = translate(
                    "AddonsInstaller", "Failed to update macros from GitHub"
                )
                phrase2 = translate(
                    "AddonsInstaller", "try clearing the Addon Manager's cache"
                )
                FreeCAD.Console.PrintWarning(f"{phrase1} -- {phrase2}:\n{str(e2)}\n")
                if os.path.exists(original_wd):
                    os.chdir(original_wd)
                return False
        return True

    def update_with_zip(self) -> bool:
        """Download and unzip a new copy of the zipfile version of the git repository"""
        zip_data = self.get_zipped_data()
        utils.extract_git_repo_zipfile(
            zip_data, self.macro_cache_location, self.macro_git_branch
        )

    def get_zipped_data(self) -> bytes:
        """Download the zipfile and return its contents as bytes"""
        url = None
        if self.macro_git_address.lower().endswith(".zip"):
            url = self.macro_git_address
        else:

            class DataHolder:
                """Interface class that mimics the needed data for an Addon"""

                def __init__(self, url, branch):
                    self.url = url
                    self.branch = branch

            dh = DataHolder(self.macro_git_address, self.macro_git_branch)
            url = utils.get_zip_url(dh)
        zip_data = utils.blocking_get(url)
        if not zip_data:
            raise RuntimeError(f"Failed to download ZIP data from {url}")
        return zip_data

    def scan_for_macros(self) -> List[str]:
        """Look through the cache directory and find all the FCMacro files"""
        results = []
        for dirpath, _, filenames in os.walk(
            self.macro_cache_location, onerror=self._walk_error
        ):
            if QtCore.QThread.currentThread().isInterruptionRequested():
                return []
            if ".git" in dirpath:
                continue
            for filename in filenames:
                if QtCore.QThread.currentThread().isInterruptionRequested():
                    return []
                if filename.lower().endswith(".fcmacro"):
                    results.append(os.path.join(dirpath, filename))
        return results

    def _walk_error(self, err: OSError):
        """Callback for an error during the os.walk call: since there shouldn't be one, raise it"""
        raise err

    def create_addon_for_macro(self, filename: os.PathLike) -> Addon:
        """Create a Macro-type Addon for the given FCMacro file"""
        macro = self.macro_factory.create_macro(filename)
        macro.on_git = True
        macro.src_filename = filename
        macro.fill_details_from_file(macro.src_filename)
        addon = self.addon_factory.from_macro(macro)
        FreeCAD.Console.PrintLog(f"Found macro {addon.name}\n")
        addon.url = self.macro_git_address
        addon.branch = self.macro_git_branch
        utils.update_macro_installation_details(addon)
        return addon
