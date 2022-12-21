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

"""Contains the IconAdapter class for fetching and generating icon data for addons."""

import io
import os
import re
from typing import List, Dict
import urllib.parse
import zipfile

try:
    import FreeCAD
except ImportError:
    FreeCAD = None

from PySide import QtCore, QtGui

from Addon import Addon
from addonmanager_macro import Macro
import addonmanager_utilities as utils
from NetworkManager import GetNetworkManager

if not FreeCAD:
    def translate(param):
        return param
else:
    translate = FreeCAD.Qt.translate


class IconFactory:
    """A factory class for creating icons: exists primarily so that unit testing code
    doesn't have to actually create the real icons, but can mock the system."""

    @classmethod
    def get_icon_from_file(cls, path: str):
        return cls._get_icon(path)

    @classmethod
    def get_icon_from_resource(cls, resource_name: str):
        resource_path = ":/icons/" + resource_name
        return cls._get_icon(resource_path)

    @classmethod
    def _get_icon(cls, resource_path):
        if QtCore.QFile.exists(resource_path):
            return QtGui.QIcon(resource_path)
        else:
            return None


class IconSource(QtCore.QObject):
    """Given an addon of any type, attempt to create or load icon data for it. This
    class's public functions are considered part of the Addon Manager's stable public
    API:

    * cache_update_complete [Signal]
    * direct_update_complete [Signal]
    * begin_asynchronous_cache_update()
    * begin_asynchronous_direct_update(addons)
    * get_icon(addon)

    In most cases begin_asynchronous_cache_update() should be called and allowed to run
    to completion, then begin_asynchronous_direct_update() should be called and allowed
    to run, and only after those two have completed should the GUI be shown and
    get_icon() used to access the icons. If either or both update calls are omitted,
    the displayed icon may be out-of-date.

    NOTE: Asynchronous operations require a running event loop (e.g. FreeCAD.GuiUp is
    True). If run from a non-GUI instance, only pre-existing icons will be used, and no
    cache update should be attempted.
    """

    cache_update_complete = QtCore.Signal()
    direct_update_complete = QtCore.Signal()

    def __init__(self):
        super().__init__()
        pref = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Addons")
        self.icon_factory = IconFactory()
        self.icon_cache_location = os.path.join(
            FreeCAD.getUserCachePath(), "AddonManager", "icons"
        )
        self.remote_cache_url = pref.GetString(
            "RemoteIconCacheURL", "https://addons.freecad.org/icon_cache.zip"
        )
        self.cache_updater = None
        self.direct_updater = None
        self.cache_update_thread = None
        self.direct_update_thread = None
        self.addons = []
        self.q_icons: Dict[str, QtGui.QIcon] = {}
        self.console = None if FreeCAD is None else self.console

    def __del__(self):
        self._quit_thread(self.cache_update_thread)
        self._quit_thread(self.direct_update_thread)

    def begin_asynchronous_cache_update(self, force_update=False):
        """Begin an asynchronous cache update. May or may not actually download new
        cache data, based on whether the current local hash matches the current
        remote hash. Regardless of whether new data is downloaded,
        the cache_update_complete signal is emitted either when icon data is ready
        for use, or when downloads have failed. In the event that no icon data is
        available, all calls to get_icon() will return a generic default icon."""

        local_hash_file = os.path.join(self.icon_cache_location, "cache_hash.txt")
        if force_update and os.path.exists(local_hash_file):
            os.unlink(local_hash_file)  # Deleting the local hash will force an update
        if self.cache_updater is None:
            self.cache_updater = CacheUpdater(
                self.remote_cache_url, self.icon_cache_location
            )
            self.cache_updater.finished.connect(self._cache_update_complete_callback)
        self._quit_thread(self.cache_update_thread)
        self.cache_update_thread = QtCore.QThread()
        self.cache_updater.moveToThread(self.cache_update_thread)
        self.cache_update_thread.started.connect(self.cache_updater.run)
        self.cache_update_thread.start()

    def begin_asynchronous_direct_update(self, addons: List[Addon], force_update=False):
        """Given a list of addons, for any addon in the list that does not have a
        locally-cached icon, download a new copy of the icon directly from the
        addon's source. If force_update is True, then new icons are downloaded for
        every addon, regardless of whether a local copy already exists."""
        self.addons = addons
        if self.direct_updater is None:
            self.direct_updater = DirectUpdater(self.icon_cache_location)
            self.direct_updater.finished.connect(self._direct_update_complete_callback)
        if not force_update:
            self._update_addon_cache_information()
        self._quit_thread(self.direct_update_thread)
        self.direct_update_thread = QtCore.QThread()
        self.direct_updater.prepare_for_run(addons)
        self.direct_updater.moveToThread(self.direct_update_thread)
        self.direct_updater.finished.connect(self._direct_update_complete_callback)
        self.direct_update_thread.started.connect(self.direct_updater.run)
        self.direct_update_thread.start()

    def _cache_update_complete_callback(self):
        self._quit_thread(self.cache_update_thread)
        self.q_icons.clear()
        self.cache_update_complete.emit()

    def _direct_update_complete_callback(self):
        self._quit_thread(self.direct_update_thread)
        self.q_icons.clear()
        self.direct_update_complete.emit()

    @classmethod
    def _quit_thread(cls, thread):
        if thread and thread.isRunning():
            thread.quit()
            thread.wait()

    def _update_addon_cache_information(self):
        cache_index = self._create_cache_index()
        for addon in self.addons:
            if addon.name in cache_index:
                addon.icon_file = cache_index[addon.name]

    def _create_cache_index(self):
        """Create a map from addon name to cache file path based on the basename (
        minus extension) of the files in the cache path."""
        if not os.path.isdir(self.icon_cache_location):
            return {}
        cache_files = os.listdir(self.icon_cache_location)
        cache_index = {}
        for cache_file in cache_files:
            base = os.path.basename(cache_file)
            filename, _ = os.path.splitext(base)
            cache_index[filename] = os.path.join(self.icon_cache_location, cache_file)
        return cache_index

    def get_icon(self, addon: Addon) -> QtGui.QIcon:
        """Gets an icon for the addon. Caches the result in memory so that further
        requests for the same addon name get a pre-created QIcon. If no icon is
        available a suitable default icon is returned."""
        icon = None

        # Short-circuit if the icon is already created and cached:
        if addon.name in self.q_icons:
            return self.q_icons[addon.name]

        if not icon and addon.repo_type == Addon.Kind.WORKBENCH:
            icon = self.get_icon_for_old_style_workbench(addon.name)
        if not icon and addon.icon_file:
            icon = QtGui.QIcon(addon.icon_file)
            if not icon:
                self.console.PrintError(
                    f"Failed to create icon from {addon.icon_file}\n"
                )
        if not icon:
            icon = self._get_default_icon_for(addon)
        self.q_icons[addon.name] = icon
        return self.q_icons[addon.name]

    def get_icon_for_old_style_workbench(self, addon_name: str) -> QtGui.QIcon:
        resource_name = addon_name.replace(" ", "_") + "_workbench_icon.svg"
        return self.icon_factory.get_icon_from_resource(resource_name)

    @classmethod
    def _get_default_icon_for(cls, addon: Addon) -> QtGui.QIcon:
        if addon.contains_workbench():
            return QtGui.QIcon(":/icons/document-package.svg")
        if addon.contains_macro():
            return QtGui.QIcon(":/icons/document-python.svg")
        return QtGui.QIcon(":/icons/document-package.svg")

    def _get_icon_cache_path(self, addon: Addon) -> str:
        icon_relative_path = addon.get_best_icon_relative_path()
        _, icon_extension = os.path.splitext(icon_relative_path)
        return os.path.join(
            self.icon_cache_location,
            addon.name.replace(" ", "_") + "_workbench_icon." + icon_extension,
        )

    def _update_icon_cache(self):
        if self._cache_needs_to_be_updated():
            try:
                self._get_cache()
            except utils.UrlExceptionType:
                self.console.PrintLog(
                    "Could not download cache from {self.remote_cache_url}"
                )
            except zipfile.BadZipFile:
                self.console.PrintLog(
                    "Corrupt ZIP data from {self.remote_cache_url}"
                )
            except zipfile.LargeZipFile:
                self.console.PrintLog(
                    "Too much ZIP data from {self.remote_cache_url}"
                )

    def _get_cache(self):
        self.cache_updater.run()


class CacheUpdater(QtCore.QObject):
    """Cache updater, designed for use with QThread. Downloads the cache and hash
    files and unzips them into the specified cache location. Intended to be moved
    into a QThread and run from within, but may be run directly by calling its run()
    function."""

    finished = QtCore.Signal()

    def __init__(
            self,
            remote_cache_url: str,
            icon_cache_location: str,
            force: bool = False,
    ):
        """If force is True, then the cache is downloaded even if the local and
        remote hashes match."""
        super().__init__()
        self.remote_cache_url = remote_cache_url
        self.icon_cache_location = icon_cache_location
        self.remote_hash_url = self.remote_cache_url + ".sha1"
        self.local_hash_file = os.path.join(self.icon_cache_location, "cache_hash.txt")
        self.force = force

    def run(self):
        if self.force or self._cache_needs_to_be_updated():
            self._download_cache()
            self._download_hash()
        self.finished.emit()

    def _cache_needs_to_be_updated(self):
        """The remote hash should consist of both a ZIP file and a file containing
        just the SHA1 hash of that ZIP file. Download the hash file and compare it to
        the last hash we downloaded. If they match, we don't need to re-download the
        cache, ours is up-to-date. If they don't match, or if one or the other file
        doesn't exist or can't be accessed, we assume the local cache is out-of-date."""
        try:
            remote_hash = utils.blocking_get(self.remote_hash_url)
        except utils.UrlExceptionType:
            return True
        if remote_hash is None:
            return True
        remote_hash = remote_hash.decode("utf-8")
        if not os.path.exists(self.local_hash_file):
            return True
        with open(self.local_hash_file, encoding="utf-8") as f:
            local_hash = f.read().strip()
        return local_hash != remote_hash

    def _download_cache(self):
        zip_data = utils.blocking_get(self.remote_cache_url)
        if zip_data:
            zip_file_like = io.BytesIO(zip_data)
            with zipfile.ZipFile(zip_file_like) as zip_file:
                zip_file.extractall(self.icon_cache_location)

    def _download_hash(self):
        hash_data = utils.blocking_get(self.remote_hash_url)
        if hash_data:
            with open(self.local_hash_file, "wb") as f:
                f.write(hash_data)


class DirectUpdater(QtCore.QObject):
    """Worker object for downloading a large collection of icons directly from their
    individual sources."""

    finished = QtCore.Signal()

    def __init__(self, cache_location: str, force_update: bool = False):
        super().__init__()
        self.force_update = force_update
        self.cache_location = cache_location
        self.addons = []
        self.updaters = []
        self.completed_count = 0
        self.UpdaterType = IndividualDirectUpdater  # For testing, override this type

    def prepare_for_run(self, addons: List[Addon]):
        self.addons = addons

    def run(self):
        if not self.addons:
            raise RuntimeError(
                translate(
                    "AddonsInstaller",
                    "No addons configured. Did you call prepare_for_run()?",
                )
                + "\n"
            )
        try:
            self._run()
        except Exception as e:
            self.console.PrintError(str(e))
            self.finished.emit()

    def _run(self):
        for addon in self.addons:
            if self.force_update or self._icon_does_not_exist(addon):
                self._start_updater_for(addon)

    @classmethod
    def _icon_does_not_exist(cls, addon: Addon) -> bool:
        filename = addon.icon_file
        return filename is None or not os.path.isfile(filename)

    def _start_updater_for(self, addon: Addon):
        updater = self.UpdaterType(self.cache_location, addon)
        updater.update_complete.connect(self._update_complete_callback)
        updater.update_failed.connect(self._update_failed_callback)
        self.updaters.append(updater)
        updater.run()  # Enqueues the network query and returns immediately

    def _update_complete_callback(self, _: Addon):
        self._increment_and_check_for_completion()

    def _update_failed_callback(self, addon: Addon):
        addon.icon_file = None
        self._increment_and_check_for_completion()

    def _increment_and_check_for_completion(self):
        self.completed_count += 1
        if self.completed_count == len(self.addons):
            self.finished.emit()


class IndividualDirectUpdater(QtCore.QObject):
    """Individually download a necessary icon from its primary source, bypassing any
    locally or remotely cached copy of the file."""

    update_complete = QtCore.Signal(object)
    update_failed = QtCore.Signal(object)

    def __init__(self, cache_location: str, addon: Addon):
        super().__init__()
        self.addon = addon
        self.download_identifier = None
        self.cache_location = cache_location
        self.download_manager = GetNetworkManager()
        if self.download_manager is not None:
            self.download_manager.completed.connect(self._download_complete)
        self.macro_icon_updater = None

    def run(self):
        if self.addon.repo_type == Addon.Kind.PACKAGE:
            self._get_icon_for_package()
        elif self.addon.repo_type == Addon.Kind.MACRO:
            self._get_icon_for_macro()
        elif self.addon.repo_type == Addon.Kind.WORKBENCH:
            self.update_complete.emit(self.addon)  # Nothing to fetch, icon is built-in
        else:
            self.console.PrintError("Unknown addon type when fetching icons")
            self.update_failed.emit(self.addon)

    def _get_icon_for_package(self):
        icon_url = utils.construct_git_url(
            self.addon, self.addon.get_best_icon_relative_path()
        )
        self._enqueue_download(icon_url)

    def _get_icon_for_macro(self):
        if not self.addon.macro.icon:
            self.update_failed.emit(self.addon)
            return
        self.macro_icon_updater = MacroDirectUpdater(self.cache_location, self.addon)
        self.macro_icon_updater.finished.connect(self._macro_icon_finished)
        self.macro_icon_updater.run()

    def _enqueue_download(self, url):
        if self.download_manager is not None:
            self.download_identifier = self.download_manager.submit_unmonitored_get(url)
        else:
            data = utils.blocking_get(url)
            if data is not None:
                self._store_icon_data(QtCore.QByteArray(data))
            else:
                self.update_failed.emit(self.addon)

    def _download_complete(self, index: int, response: int, data: QtCore.QByteArray):
        if index == self.download_identifier:
            if response == 200:
                self._store_icon_data(data)
            else:
                self.update_failed.emit(self.addon)

    def _macro_icon_finished(self):
        if self.addon.icon_file:
            self.console.PrintLog(f"Created {self.addon.icon_file}\n")
        else:
            self.console.PrintWarning(
                f"Failed to create macro icon from {self.addon.macro.icon}\n"
            )
        self.update_complete.emit(self.addon)

    def _store_icon_data(self, data: QtCore.QByteArray):
        """The icon is stored as addon_name.ext where the extension is determined
        automatically from the incoming byte data."""
        buffer = QtCore.QBuffer(data)
        reader = QtGui.QImageReader(buffer)
        extension = reader.format().data().decode("utf-8")
        if not extension:
            if self._looks_like_svg(data):
                extension = "svg"
            else:
                raise RuntimeError("Cannot determine the type of data for the icon")
        os.makedirs(self.cache_location, exist_ok=True)
        filename = os.path.join(self.cache_location, self.addon.name + "." + extension)
        with open(filename, "wb") as f:
            f.write(buffer.data().data())
        self.addon.icon_file = filename
        self.update_complete.emit(self.addon)

    @staticmethod
    def _looks_like_svg(data: QtCore.QByteArray):
        try:
            data.data().decode("utf-8")
            return True
        except UnicodeError:
            return False


class MacroDirectUpdater(QtCore.QObject):
    """Helper class to deal with the myriad ways that a Macro icon might be
    specified."""

    finished = QtCore.Signal()

    def __init__(self, cache_location: str, addon: Addon):
        super().__init__()
        self.cache_location = cache_location
        os.makedirs(self.cache_location, exist_ok=True)
        self.addon: Addon = addon
        self.macro: Macro = self.addon.macro
        self.gui_up = FreeCAD.GuiUp  # Can be overridden for testing
        self.network_manager = GetNetworkManager()  # Likewise
        self.async_index = None
        self.console = self.console

    def run(self):
        try:
            self._run()
        except Exception as e:
            self.console.PrintError(e)
            self.finished.emit()

    def _run(self):
        """Create the local cached icon for this macro. May be asynchronous, the data
        is not guaranteed to be available until finished() is emitted."""
        if self.macro.icon:
            self._handle_icon_entry()
        elif self.macro.xpm:
            self._handle_xpm_data()
        else:
            self.finished.emit()

    def _handle_icon_entry(self):
        """Create an icon file in the cache location with whatever icon data we can
        locate"""
        if self.macro.on_git:
            # TODO: Write Git macro icon fetch code
            raise RuntimeError("Code not written yet")
        else:  # on_wiki
            self._create_wiki_icon()

    def _handle_xpm_data(self):
        """Create a .xpm file in the cache location with the macro's XPM data"""
        path = os.path.join(self.cache_location, self.addon.name + ".xpm")
        os.makedirs(self.cache_location, exist_ok=True)
        with open(path, "w") as f:
            f.write(self.addon.macro.xpm)
        self.addon.icon_file = path
        self.finished.emit()

    def _create_wiki_icon(self):
        """Create an icon for a macro that is obtained from the Wiki"""
        if "://" not in self.macro.icon:
            self._create_wiki_icon_from_relative_path()
        else:
            if self.gui_up and self.network_manager:
                self._begin_asynchronous_fetch(
                    self.macro.icon, self._icon_is_file_page_link()
                )
            else:
                self._run_synchronous_fetch(
                    self.macro.icon, self._icon_is_file_page_link()
                )

    def _create_wiki_icon_from_relative_path(self):
        if self.macro.raw_code_url and "/" in self.macro.raw_code_url:
            base = self.macro.raw_code_url.rsplit("/", 1)[0]
        else:
            base = "https://wiki.freecad.org"
        self.macro.icon = base + "/" + self.macro.icon
        self._create_wiki_icon()

    def _icon_is_file_page_link(self) -> bool:
        if self.macro.icon is None:
            return False
        components = urllib.parse.urlparse(self.macro.icon)
        path_elements = components.path.split("/")
        if path_elements[-1].startswith("File:"):
            return True
        return False

    def _begin_asynchronous_fetch(self, url: str, is_file_page: bool):
        if is_file_page:
            self.network_manager.completed.connect(self._handle_asynchronous_file_page)
        else:
            self.network_manager.completed.connect(self._handle_asynchronous_icon)
        self.async_index = self.network_manager.submit_unmonitored_get(url)

    def _handle_asynchronous_file_page(
            self, index: int, response: int, data: QtCore.QByteArray
    ):
        if index == self.async_index:
            if response != 200:
                self.finished.emit()
                return
            self._parse_wiki_file_page(data.data())

    def _handle_asynchronous_icon(
            self, index: int, response: int, data: QtCore.QByteArray
    ):
        if index == self.async_index:
            if response != 200:
                self.finished.emit()
            else:
                self._store_icon_data(data.data())

    def _run_synchronous_fetch(self, url: str, is_file_page: bool):
        data = utils.blocking_get(url)
        if not data:
            self.console.PrintWarning(f"Failed to get data from {url}\n")
            self.finished.emit()
        elif is_file_page:
            self._parse_wiki_file_page(data)
        else:
            self._store_icon_data(data)

    def _store_icon_data(self, data):
        """Store the data in the cache location in a file called addon_name.ext,
        where ext is determined by the extension of the original icon URL. TODO: if
        there is no extension, try to use QImageReader to figure it out."""
        components = urllib.parse.urlparse(self.macro.icon)
        extension = os.path.splitext(components.path)[-1].lower()
        known_extensions = [".svg", ".png", ".jpg", ".xpm", ".bmp", ".gif", ".webp"]
        final_filename = os.path.join(self.cache_location, self.addon.name + extension)
        if extension in known_extensions:
            filename = final_filename
            with open(filename, "wb") as f:
                f.write(data)
            self.addon.icon_file = filename
        else:
            self.console.PrintWarning(
                f"Unknown image extension {extension} for macro {self.addon.name}\n"
            )
        self.finished.emit()

    def _parse_wiki_file_page(self, data):
        html = data.decode("utf-8")
        f = io.StringIO(html)
        lines = f.readlines()
        trigger = False
        icon_regex = re.compile(r'.*img.*?src="(.*?)"', re.IGNORECASE)
        for line in lines:
            if trigger:
                match = icon_regex.match(line)
                if match:
                    wiki_icon = match.group(1)
                    self.macro.icon = "https://wiki.freecad.org/" + wiki_icon
                    break
            elif "fullImageLink" in line:
                trigger = True
        if self.macro.icon:
            self._create_wiki_icon()
        else:
            self.console.PrintWarning(
                f"Unable to locate the icon data for {self.addon.name}. "
                f"Given URL was {self.macro.icon}\n"
            )
            self.finished.emit()

        # The data we are looking for looks like this:
        # <div class="fullImageLink" id="file">
        #     <a href="/images/a/a2/Bevel.svg">
        #         <img alt="File:Bevel.svg" src="Bevel.svg" width="64" height="64"/>
        #     </a>
