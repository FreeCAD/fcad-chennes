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

"""Addon Manager Data Source: Git repository with submodules specifying individual Addons."""

from enum import IntEnum, auto
import io
import json
import os
import re
from typing import Dict, List
from threading import Lock
import zipfile

import FreeCAD

from PySide import QtCore

from Addon import Addon
import addonmanager_utilities as utils

translate = FreeCAD.Qt.translate

from NetworkManager import GetNetworkManager

# pylint: disable=too-few-public-methods


class AddonDataSourceGit(QtCore.QObject):
    """Pull data from FreeCAD's primary git repository. This repo is cached by a server at
    addons.freecad.org, but that cache can be omitted and the data pulled directly from the
    individual git repos if desired."""

    addon_found = QtCore.Signal(object)
    finished = QtCore.Signal()

    class RequestType(IntEnum):
        """The type of item being downloaded."""

        PACKAGE_XML = auto()
        METADATA_TXT = auto()
        REQUIREMENTS_TXT = auto()

    def __init__(self, skip_cache=False):
        super().__init__()
        self.skip_cache = skip_cache
        self.lock = Lock()
        self.addons = []
        self.custom_addons = []  # Subset of addons: only the user-defined custom repos
        self._addon_name_cache = set()
        self.pref = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Addons")
        self.submodules_url = self.pref.GetString(
            "PrimaryAddonsSubmoduleURL",
            "https://raw.githubusercontent.com/FreeCAD/FreeCAD-addons/master/.gitmodules",
        )
        self.cache_url = self.pref.GetString(
            "AddonsRemoteCacheURL", "https://addons.freecad.org/metadata.zip"
        )
        self.update_stats_url = self.pref.GetString(
            "AddonsUpdateStatsURL", "https://addons.freecad.org/addon_update_stats.json"
        )
        self.custom_addon_list = (
            FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Addons")
            .GetString("CustomRepositories", "")
            .split("\n")
        )
        self.addon_factory = GitAddonFactory()
        self.last_updated = {}
        self.cache_fetch_succeeded = False
        self.requests = {}
        self.store = os.path.join(
            FreeCAD.getUserCachePath(), "AddonManager", "PackageMetadata"
        )
        self.network_manager = None
        if FreeCAD.GuiUp:
            self.network_manager = GetNetworkManager()
            self.network_manager.completed.connect(self.download_completed)

    def __del__(self):
        if self.network_manager is not None:
            self.network_manager.completed.disconnect(self.download_completed)

    def run(self):
        """Update the list of addons. Synchronous, but may be run from within a QThread to avoid
        blocking the GUI. Passing skip_cache=True will cause the code to individually access each
        addon's git repository in turn to query for a metadata file."""
        call_sequence = [
            self.fetch_custom_repos,
            self.fetch_last_update_information,
            self.fetch_cache if not self.skip_cache else lambda: None,
            self.fetch_submodules,
            self.fetch_metadata,
            self.emit_signals,
        ]
        for func in call_sequence:
            if QtCore.QThread.currentThread().isInterruptionRequested():
                self.finished.emit()
                return
            func()
        self.finished.emit()

    def fetch_metadata(self):
        """Get the needed metadata files"""
        if not self.cache_fetch_succeeded:
            # Do the whole list
            self.update_metadata(self.addons)
        else:
            # Do only the custom addons
            self.update_metadata(self.custom_addons)

    def emit_signals(self):
        """Emit the necessary signal for each new addon."""
        for addon in self.addons:
            if QtCore.QThread.currentThread().isInterruptionRequested():
                return
            self.addon_found.emit(addon)

    def fetch_last_update_information(self):
        """Get the last-updated-time information from the addon cache maintained on FreeCAD's
        servers. Does nothing with the data until either the cache or the submodules data is found,
        at which point the updated information is added to the Addon object."""
        update_data = utils.blocking_get(self.update_stats_url)
        if not update_data:
            return
        self.last_updated = json.loads(update_data)

    def fetch_cache(self):
        """Get the remote cache file, process it."""

        try:
            zip_data = utils.blocking_get(self.cache_url)
            if not zip_data:
                return
        except utils.UrlExceptionType:
            FreeCAD.Console.PrintWarning(
                translate("AddonsInstaller", "Failed to get cache file from {}").format(
                    self.cache_url
                )
                + "\n"
            )
            return

        zip_file_like = io.BytesIO(zip_data)
        try:
            with zipfile.ZipFile(zip_file_like) as zip_file:
                if zip_file.testzip() is not None:
                    FreeCAD.Console.PrintWarning(
                        translate(
                            "AddonsInstaller",
                            "Downloaded cache file from {} was corrupted: ignoring it",
                        ).format(self.cache_url)
                        + "\n"
                    )
                    return
                root = zipfile.Path(zip_file, "metadata/")
                for mod_dir in root.iterdir():
                    if QtCore.QThread.currentThread().isInterruptionRequested():
                        return
                    new_addon = self.addon_factory.from_cache(mod_dir)
                    self.add_update_info_to_addon(new_addon)
                    self.addons.append(new_addon)
                    self._addon_name_cache.add(new_addon.name)
        except zipfile.BadZipFile:
            FreeCAD.Console.PrintWarning(
                translate(
                    "AddonsInstaller",
                    "Downloaded cache file from {} was corrupted: ignoring it",
                ).format(self.cache_url)
                + "\n"
            )
            return
        self.cache_fetch_succeeded = True

    def fetch_submodules(self):
        """Get the remote submodules file. If run after the cache is fetched, only examines non-
        cached entries. Process the submodules file, access each one in turn, download its metadata
        file (if it exists), and create an Addon object."""
        submodules_data = utils.blocking_get(self.submodules_url)
        submodules = self.parse_submodules(submodules_data.decode("utf-8"))
        self.create_addons_from_submodules(submodules)

    def fetch_custom_repos(self):
        """Create Addons for each of the entries in the custom repos list"""
        custom_repos = self.parse_custom_addons_list(self.custom_addon_list)
        for repo in custom_repos:
            if QtCore.QThread.currentThread().isInterruptionRequested():
                return
            addon = self.addon_factory.construct_addon(
                repo["name"], repo["url"], branch=repo["branch"]
            )
            self.addons.append(addon)
            self.custom_addons.append(addon)

    def parse_submodules(self, submodules_data: str):
        """Loop over the submodules file and create some ordered data from it."""
        submodules = {}
        regex_results = re.findall(
            (
                r'(?m)\[submodule\s*"(?P<name>.*)"\]\s*'
                r"path\s*=\s*(?P<path>.+)\s*"
                r"url\s*=\s*(?P<url>.*://.*)\s*"
                r"(branch\s*=\s*(?P<branch>[^\s]*)\s*)?"
            ),
            submodules_data,
        )
        for name, _, url, _, branch in regex_results:
            if QtCore.QThread.currentThread().isInterruptionRequested():
                return {}  # Don't return incomplete data
            if name in submodules:
                # We already have something with this name, skip this one, rather than overwriting
                # the old with the new. That is, the *first* time we encounter a name is the copy
                # we use, rather than the last.
                continue
            if branch is None or len(branch) == 0:
                branch = "master"
            repo = {"url": url, "branch": branch}
            utils.clean_git_url(repo)
            submodules[name] = repo
        return submodules

    def create_addons_from_submodules(self, submodules):
        """Create addons for each entry in the submodules file that was not in the cache."""
        for name, data in submodules.items():
            if QtCore.QThread.currentThread().isInterruptionRequested():
                return
            if name in self._addon_name_cache:
                continue
            new_addon = self.addon_factory.construct_addon(
                name, url=data["url"], branch=data["branch"]
            )
            self.add_update_info_to_addon(new_addon)
            self.addons.append(new_addon)
            self._addon_name_cache.add(name)

    def add_update_info_to_addon(self, addon):
        """If last updated info is present, add it to the addon"""
        if addon.name in self.last_updated:
            # The last_updated dictionary for each addon is a dictionary of git references as keys
            # with values containing the date and hash of the last commit to that ref. We want the
            # ref called "refs/remotes/origin/{branch}" for whatever branch we are on.
            ref = f"refs/remotes/origin/{addon.branch}"
            if ref in self.last_updated[addon.name]:
                date = self.last_updated[addon.name][ref][0]
                addon.last_updated = date

    def update_metadata(self, addons):
        """Individually fetch metadata files for the list of addons. Should be run after the
        lists of addons have been created, and in general should not be run if cached data was
        already found. This process is slow and network-intensive (unless the Addon URLs are local
        file URLs, which should be very fast)."""

        current_thread = QtCore.QThread.currentThread()

        for addon in addons:
            if current_thread.isInterruptionRequested():
                return

            files = {
                AddonDataSourceGit.RequestType.PACKAGE_XML: "package.xml",
                AddonDataSourceGit.RequestType.METADATA_TXT: "metadata.txt",
                AddonDataSourceGit.RequestType.REQUIREMENTS_TXT: "requirements.txt",
            }

            for kind_of_request, filename in files.items():
                self._create_network_request(addon, kind_of_request, filename)

        while self.requests:
            if current_thread.isInterruptionRequested():
                for request in self.requests:
                    self.network_manager.abort(request)
                return
            # 50 ms maximum between checks for interruption
            QtCore.QCoreApplication.processEvents(QtCore.QEventLoop.AllEvents, 50)

    def _create_network_request(self, addon, kind_of_request, filename):
        url = utils.construct_git_url(addon, filename)
        if self.network_manager is not None and not url.startswith("file://"):
            # Running with the GUI up and a remote URL
            index = self.network_manager.submit_unmonitored_get(url)
            self.requests[index] = (addon, kind_of_request)
        else:
            try:
                FreeCAD.Console.PrintError(f"Not an error: getting data from {url}\n")
                data = utils.blocking_get(url)
                self._dispatch_data(addon, kind_of_request, data)
            except utils.UrlExceptionType:
                return

    def _dispatch_data(self, addon, kind_of_request, data):
        if data is None:
            return
        if kind_of_request == AddonDataSourceGit.RequestType.PACKAGE_XML:
            self.process_package_xml(addon, data)
        elif kind_of_request == AddonDataSourceGit.RequestType.METADATA_TXT:
            self.process_metadata_txt(addon, data)
        elif kind_of_request == AddonDataSourceGit.RequestType.REQUIREMENTS_TXT:
            self.process_requirements_txt(addon, data)

    def download_completed(
        self, index: int, code: int, data: QtCore.QByteArray
    ) -> None:
        """Callback for handling a completed metadata file download."""
        if index in self.requests:
            request = self.requests.pop(index)
            if code == 200:  # HTTP success
                self._dispatch_data(request[0], request[1], data.data())

    def process_package_xml(self, addon: Addon, data: bytes):
        """Process the package.xml metadata file"""
        addon.repo_type = Addon.Kind.PACKAGE  # By definition
        package_cache_directory = os.path.join(self.store, addon.name)
        os.makedirs(package_cache_directory, exist_ok=True)
        new_xml_file = os.path.join(package_cache_directory, "package.xml")
        with open(new_xml_file, "wb") as f:
            f.write(data)
        metadata = FreeCAD.Metadata(new_xml_file)
        addon.set_metadata(metadata)
        FreeCAD.Console.PrintLog(f"Downloaded package.xml for {addon.name}\n")

    def _decode_data(self, byte_data, addon_name, file_name) -> str:
        """UTF-8 decode data, and print an error message if that fails"""

        # For review and debugging purposes, store the file locally
        package_cache_directory = os.path.join(self.store, addon_name)
        if not os.path.exists(package_cache_directory):
            os.makedirs(package_cache_directory)
        new_xml_file = os.path.join(package_cache_directory, file_name)
        with open(new_xml_file, "wb") as f:
            f.write(byte_data)

        f = ""
        try:
            f = byte_data.decode("utf-8")
        except UnicodeDecodeError as e:
            FreeCAD.Console.PrintWarning(
                translate(
                    "AddonsInstaller",
                    "Failed to decode {} file for Addon '{}'",
                ).format(file_name, addon_name)
                + "\n"
            )
            FreeCAD.Console.PrintWarning(str(e) + "\n")
            FreeCAD.Console.PrintWarning(
                translate(
                    "AddonsInstaller",
                    "Any dependency information in this file will be ignored",
                )
                + "\n"
            )
        return f

    def process_metadata_txt(self, repo: Addon, data: bytes):
        """Process the metadata.txt metadata file"""
        with self.lock:
            f = self._decode_data(data, repo.name, "metadata.txt")
            lines = f.splitlines()
            for line in lines:
                if line.startswith("workbenches="):
                    self._process_metadata_txt_line(line, repo.requires)
                elif line.startswith("pylibs="):
                    self._process_metadata_txt_line(line, repo.python_requires)
                elif line.startswith("optionalpylibs="):
                    self._process_metadata_txt_line(line, repo.python_optional)

    def _process_metadata_txt_line(self, line, set_to_add_to):
        """Process a single line of data in a metadata.txt format and add the information to the
        given set."""
        if not "=" in line:
            return
        split_data = line.split("=")[1].split(",")
        for pl in split_data:
            dep = pl.strip()
            if dep:
                set_to_add_to.add(dep)

    def process_requirements_txt(self, repo: Addon, data: bytes):
        """Process the requirements.txt metadata file"""
        with self.lock:
            f = self._decode_data(data, repo.name, "requirements.txt")
            lines = f.splitlines()
            for line in lines:
                self._extract_requirement_from_line(repo, line)

    def _extract_requirement_from_line(self, repo, line):
        break_chars = " <>=~!+#"
        package = line
        for n, c in enumerate(line):
            if c in break_chars:
                package = line[:n].strip()
                break
        if package:
            repo.python_requires.add(package)

    def construct_metadata_url(self, base_url: str, branch: str, metadata_file: str):
        """Construct a URL for a particular metadata file given a source repo's URL"""

        class Wrapper:
            """Simple class to hold a url and branch so it can be passed into the utils
            processor."""

            def __init__(self, url, branch):
                self.url = url
                self.branch = branch

        if base_url.startswith("file://"):
            # For local files, ignore the branch information and just get the file directly
            if base_url.endswith("/"):
                return base_url + metadata_file
            return base_url + "/" + metadata_file
        return utils.construct_git_url(Wrapper(base_url, branch), metadata_file)

    def parse_custom_addons_list(self, addons_list) -> List[Dict[str, str]]:
        """Convert the string into a list data structure"""
        custom_addons = []
        for addon_from_list in addons_list:
            if not addon_from_list:
                continue  # A blank line
            url_and_branch = addon_from_list.split(" ")
            repo = {}
            repo["url"] = url_and_branch[0]
            if len(url_and_branch) > 1:
                repo["branch"] = url_and_branch[1]
            else:
                repo["branch"] = "master"
            utils.clean_git_url(repo)
            custom_addons.append(repo)
        return custom_addons


class GitAddonFactory:

    """A factory class for creating addons. Exists mainly to enable testing of the
    above classes without actually creating a real Addon."""

    def from_cache(self, cache_dir: zipfile.ZipFile) -> Addon:
        """Create an addon from a piece of cache located in some zip stream cache_dir"""
        name = cache_dir.name
        new_addon = self.construct_addon(name)
        metadata_file = cache_dir.joinpath(
            "package.xml"
        )  # This should exist for everything in cache
        if not metadata_file.exists():
            raise RuntimeError(f"Cache is missing package.xml for {name}")
        with metadata_file.open() as package_xml:
            buffer_data = package_xml.read()
            md = self.construct_metadata(buffer_data)
            new_addon.set_metadata(md)
        return new_addon

    def construct_addon(
        self,
        name: str,
        url: str = "",
        status: Addon.Status = Addon.Status.UNKNOWN,
        branch: str = "",
    ):
        """Wrap addon construction so it can be overridden by test code"""
        return Addon(name, url, status, branch)

    def construct_metadata(self, buffer: bytes):
        """Wrap metadata construction so it can be overridden by test code"""
        return FreeCAD.Metadata(buffer)
