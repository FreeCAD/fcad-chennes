# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2022-2023 FreeCAD Project Association                   *
# *   Copyright (c) 2019 Yorik van Havre <yorik@uncreated.net>              *
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

""" Worker thread classes for Addon Manager startup """

import hashlib
import json
import os
import queue
import re
import shutil
import stat
import threading
import time
from typing import List

from PySide import QtCore

import FreeCAD
import addonmanager_utilities as utils
from addonmanager_macro import Macro
from Addon import Addon
import NetworkManager
from addonmanager_git import initialize_git, GitFailed

translate = FreeCAD.Qt.translate

# Workers only have one public method by design
# pylint: disable=c-extension-no-member,too-few-public-methods,too-many-instance-attributes


class CheckSingleUpdateWorker(QtCore.QObject):
    """This worker is a little different from the others: the actual recommended way of
    running in a QThread is to make a worker object that gets moved into the thread."""

    update_status = QtCore.Signal(int)

    def __init__(self, repo: Addon, parent: QtCore.QObject = None):
        super().__init__(parent)
        self.repo = repo

    def do_work(self):
        """Use the UpdateChecker class to do the work of this function, depending on the
        type of Addon"""

        checker = UpdateChecker()
        if self.repo.repo_type == Addon.Kind.WORKBENCH:
            checker.check_workbench(self.repo)
        elif self.repo.repo_type == Addon.Kind.MACRO:
            checker.check_macro(self.repo)
        elif self.repo.repo_type == Addon.Kind.PACKAGE:
            checker.check_package(self.repo)

        self.update_status.emit(self.repo.update_status)


class CheckWorkbenchesForUpdatesWorker(QtCore.QThread):
    """This worker checks for available updates for all workbenches"""

    update_status = QtCore.Signal(Addon)
    progress_made = QtCore.Signal(int, int)

    def __init__(self, repos: List[Addon]):
        QtCore.QThread.__init__(self)
        self.repos = repos
        self.current_thread = None
        self.basedir = FreeCAD.getUserAppDataDir()
        self.moddir = os.path.join(self.basedir, "Mod")

    def run(self):
        """Rarely called directly: create an instance and call start() on it instead to
        launch in a new thread"""

        self.current_thread = QtCore.QThread.currentThread()
        checker = UpdateChecker()
        count = 1
        for repo in self.repos:
            if self.current_thread.isInterruptionRequested():
                return
            self.progress_made.emit(count, len(self.repos))
            count += 1
            if repo.status() == Addon.Status.UNCHECKED:
                if repo.repo_type == Addon.Kind.WORKBENCH:
                    checker.check_workbench(repo)
                    self.update_status.emit(repo)
                elif repo.repo_type == Addon.Kind.MACRO:
                    checker.check_macro(repo)
                    self.update_status.emit(repo)
                elif repo.repo_type == Addon.Kind.PACKAGE:
                    checker.check_package(repo)
                    self.update_status.emit(repo)


class UpdateChecker:
    """A utility class used by the CheckWorkbenchesForUpdatesWorker class. Each function is
    designed for a specific Addon type, and modifies the passed-in Addon with the determined
    update status."""

    def __init__(self):
        self.basedir = FreeCAD.getUserAppDataDir()
        self.moddir = os.path.join(self.basedir, "Mod")
        self.git_manager = initialize_git()

    def override_mod_directory(self, moddir):
        """Primarily for use when testing, sets an alternate directory to use for mods"""
        self.moddir = moddir

    def check_workbench(self, wb):
        """Given a workbench Addon wb, check it for updates using git. If git is not
        available, does nothing."""
        if not self.git_manager:
            wb.set_status(Addon.Status.CANNOT_CHECK)
            return
        clonedir = os.path.join(self.moddir, wb.name)
        if os.path.exists(clonedir):
            # mark as already installed AND already checked for updates
            if not os.path.exists(os.path.join(clonedir, ".git")):
                with wb.git_lock:
                    self.git_manager.repair(wb.url, clonedir)
            with wb.git_lock:
                try:
                    status = self.git_manager.status(clonedir)
                    if "(no branch)" in self.git_manager.status(clonedir):
                        # By definition, in a detached-head state we cannot
                        # update, so don't even bother checking.
                        wb.set_status(Addon.Status.NO_UPDATE_AVAILABLE)
                        wb.branch = self.git_manager.current_branch(clonedir)
                        return
                except GitFailed as e:
                    FreeCAD.Console.PrintWarning(
                        "AddonManager: "
                        + translate(
                            "AddonsInstaller",
                            "Unable to fetch git updates for workbench {}",
                        ).format(wb.name)
                        + "\n"
                    )
                    FreeCAD.Console.PrintWarning(str(e) + "\n")
                    wb.set_status(Addon.Status.CANNOT_CHECK)
                else:
                    try:
                        if self.git_manager.update_available(clonedir):
                            wb.set_status(Addon.Status.UPDATE_AVAILABLE)
                        else:
                            wb.set_status(Addon.Status.NO_UPDATE_AVAILABLE)
                    except GitFailed:
                        FreeCAD.Console.PrintWarning(
                            translate(
                                "AddonsInstaller", "git status failed for {}"
                            ).format(wb.name)
                            + "\n"
                        )
                        wb.set_status(Addon.Status.CANNOT_CHECK)

    def check_package(self, package: Addon) -> None:
        """Given a packaged Addon package, check it for updates. If git is available that is
        used. If not, the package's metadata is examined, and if the metadata file has changed
        compared to the installed copy, an update is flagged."""

        clonedir = self.moddir + os.sep + package.name
        if os.path.exists(clonedir):
            # First, try to just do a git-based update, which will give the most accurate results:
            if self.git_manager:
                self.check_workbench(package)
                if package.status() != Addon.Status.CANNOT_CHECK:
                    # It worked, just exit now
                    return

            # If we were unable to do a git-based update, try using the package.xml file instead:
            installed_metadata_file = os.path.join(clonedir, "package.xml")
            if not os.path.isfile(installed_metadata_file):
                # If there is no package.xml file, then it's because the package author added it
                # after the last time the local installation was updated. By definition, then,
                # there is an update available, if only to download the new XML file.
                package.set_status(Addon.Status.UPDATE_AVAILABLE)
                package.installed_version = None
                return
            package.updated_timestamp = os.path.getmtime(installed_metadata_file)
            try:
                installed_metadata = FreeCAD.Metadata(installed_metadata_file)
                package.installed_version = installed_metadata.Version
                # Packages are considered up-to-date if the metadata version matches. Authors
                # should update their version string when they want the addon manager to alert
                # users of a new version.
                if package.metadata.Version != installed_metadata.Version:
                    package.set_status(Addon.Status.UPDATE_AVAILABLE)
                else:
                    package.set_status(Addon.Status.NO_UPDATE_AVAILABLE)
            except Exception:
                FreeCAD.Console.PrintWarning(
                    translate(
                        "AddonsInstaller",
                        "Failed to read metadata from {name}",
                    ).format(name=installed_metadata_file)
                    + "\n"
                )
                package.set_status(Addon.Status.CANNOT_CHECK)

    def check_macro(self, macro_wrapper: Addon) -> None:
        """Check to see if the online copy of the macro's code differs from the local copy."""

        # Make sure this macro has its code downloaded:
        try:
            if not macro_wrapper.macro.parsed and macro_wrapper.macro.on_git:
                macro_wrapper.macro.fill_details_from_file(
                    macro_wrapper.macro.src_filename
                )
            elif not macro_wrapper.macro.parsed and macro_wrapper.macro.on_wiki:
                mac = macro_wrapper.macro.name.replace(" ", "_")
                mac = mac.replace("&", "%26")
                mac = mac.replace("+", "%2B")
                url = "https://wiki.freecad.org/Macro_" + mac
                macro_wrapper.macro.fill_details_from_wiki(url)
        except Exception:
            FreeCAD.Console.PrintWarning(
                translate(
                    "AddonsInstaller",
                    "Failed to fetch code for macro '{name}'",
                ).format(name=macro_wrapper.macro.name)
                + "\n"
            )
            macro_wrapper.set_status(Addon.Status.CANNOT_CHECK)
            return

        hasher1 = hashlib.sha1()
        hasher2 = hashlib.sha1()
        hasher1.update(macro_wrapper.macro.code.encode("utf-8"))
        new_sha1 = hasher1.hexdigest()
        test_file_one = os.path.join(
            FreeCAD.getUserMacroDir(True), macro_wrapper.macro.filename
        )
        test_file_two = os.path.join(
            FreeCAD.getUserMacroDir(True), "Macro_" + macro_wrapper.macro.filename
        )
        if os.path.exists(test_file_one):
            with open(test_file_one, "rb") as f:
                contents = f.read()
                hasher2.update(contents)
                old_sha1 = hasher2.hexdigest()
        elif os.path.exists(test_file_two):
            with open(test_file_two, "rb") as f:
                contents = f.read()
                hasher2.update(contents)
                old_sha1 = hasher2.hexdigest()
        else:
            return
        if new_sha1 == old_sha1:
            macro_wrapper.set_status(Addon.Status.NO_UPDATE_AVAILABLE)
        else:
            macro_wrapper.set_status(Addon.Status.UPDATE_AVAILABLE)


class CacheMacroCodeWorker(QtCore.QThread):
    """Download and cache the macro code, and parse its internal metadata"""

    status_message = QtCore.Signal(str)
    update_macro = QtCore.Signal(Addon)
    progress_made = QtCore.Signal(int, int)

    def __init__(self, repos: List[Addon]) -> None:
        QtCore.QThread.__init__(self)
        self.repos = repos
        self.workers = []
        self.terminators = []
        self.lock = threading.Lock()
        self.failed = []
        self.counter = 0
        self.repo_queue = None

    def run(self):
        """Rarely called directly: create an instance and call start() on it instead to
        launch in a new thread"""

        self.status_message.emit(translate("AddonsInstaller", "Caching macro code..."))

        self.repo_queue = queue.Queue()
        num_macros = 0
        for repo in self.repos:
            if repo.macro is not None:
                self.repo_queue.put(repo)
                num_macros += 1

        interrupted = self._process_queue(num_macros)
        if interrupted:
            return

        # Make sure all of our child threads have fully exited:
        for worker in self.workers:
            worker.wait(50)
            if not worker.isFinished():
                # The Qt Python translation extractor doesn't support splitting this string (yet)
                # pylint: disable=line-too-long
                FreeCAD.Console.PrintError(
                    translate(
                        "AddonsInstaller",
                        "Addon Manager: a worker process failed to complete while fetching {name}",
                    ).format(name=worker.macro.name)
                    + "\n"
                )

        self.repo_queue.join()
        for terminator in self.terminators:
            if terminator and terminator.isActive():
                terminator.stop()

        if len(self.failed) > 0:
            num_failed = len(self.failed)
            FreeCAD.Console.PrintWarning(
                translate(
                    "AddonsInstaller",
                    "Out of {num_macros} macros, {num_failed} timed out while processing",
                ).format(num_macros=num_macros, num_failed=num_failed)
            )

    def _process_queue(self, num_macros) -> bool:
        """Spools up six network connections and downloads the macro code. Returns True if
        it was interrupted by user request, or False if it ran to completion."""

        # Emulate QNetworkAccessManager and spool up six connections:
        for _ in range(6):
            self.update_and_advance(None)

        current_thread = QtCore.QThread.currentThread()
        while True:
            if current_thread.isInterruptionRequested():
                for worker in self.workers:
                    worker.blockSignals(True)
                    worker.requestInterruption()
                    if not worker.wait(100):
                        FreeCAD.Console.PrintWarning(
                            translate(
                                "AddonsInstaller",
                                "Addon Manager: a worker process failed to halt ({name})",
                            ).format(name=worker.macro.name)
                            + "\n"
                        )
                return True
            # Ensure our signals propagate out by running an internal thread-local event loop
            QtCore.QCoreApplication.processEvents()
            with self.lock:
                if self.counter >= num_macros:
                    break
            time.sleep(0.1)
        return False

    def update_and_advance(self, repo: Addon) -> None:
        """Emit the updated signal and launch the next item from the queue."""
        if repo is not None:
            if repo.macro.name not in self.failed:
                self.update_macro.emit(repo)
            self.repo_queue.task_done()
            with self.lock:
                self.counter += 1

        if QtCore.QThread.currentThread().isInterruptionRequested():
            return

        self.progress_made.emit(
            len(self.repos) - self.repo_queue.qsize(), len(self.repos)
        )

        try:
            next_repo = self.repo_queue.get_nowait()
            worker = GetMacroDetailsWorker(next_repo)
            worker.finished.connect(lambda: self.update_and_advance(next_repo))
            with self.lock:
                self.workers.append(worker)
                self.terminators.append(
                    QtCore.QTimer.singleShot(10000, lambda: self.terminate(worker))
                )
            self.status_message.emit(
                translate(
                    "AddonsInstaller",
                    "Getting metadata from macro {}",
                ).format(next_repo.macro.name)
            )
            worker.start()
        except queue.Empty:
            pass

    def terminate(self, worker) -> None:
        """Shut down all running workers and exit the thread"""
        if not worker.isFinished():
            macro_name = worker.macro.name
            FreeCAD.Console.PrintWarning(
                translate(
                    "AddonsInstaller",
                    "Timeout while fetching metadata for macro {}",
                ).format(macro_name)
                + "\n"
            )
            worker.blockSignals(True)
            worker.requestInterruption()
            worker.wait(100)
            if worker.isRunning():
                FreeCAD.Console.PrintError(
                    translate(
                        "AddonsInstaller",
                        "Failed to kill process for macro {}!\n",
                    ).format(macro_name)
                )
            with self.lock:
                self.failed.append(macro_name)


class GetMacroDetailsWorker(QtCore.QThread):
    """Retrieve the macro details for a macro"""

    status_message = QtCore.Signal(str)
    readme_updated = QtCore.Signal(str)

    def __init__(self, repo):
        QtCore.QThread.__init__(self)
        self.macro = repo.macro

    def run(self):
        """Rarely called directly: create an instance and call start() on it instead to
        launch in a new thread"""

        self.status_message.emit(
            translate("AddonsInstaller", "Retrieving macro description...")
        )
        if not self.macro.parsed and self.macro.on_git:
            self.status_message.emit(
                translate("AddonsInstaller", "Retrieving info from git")
            )
            self.macro.fill_details_from_file(self.macro.src_filename)
        if not self.macro.parsed and self.macro.on_wiki:
            self.status_message.emit(
                translate("AddonsInstaller", "Retrieving info from wiki")
            )
            mac = self.macro.name.replace(" ", "_")
            mac = mac.replace("&", "%26")
            mac = mac.replace("+", "%2B")
            url = "https://wiki.freecad.org/Macro_" + mac
            self.macro.fill_details_from_wiki(url)
        message = (
            "<h1>"
            + self.macro.name
            + "</h1>"
            + self.macro.desc
            + '<br/><br/>Macro location: <a href="'
            + self.macro.url
            + '">'
            + self.macro.url
            + "</a>"
        )
        if QtCore.QThread.currentThread().isInterruptionRequested():
            return
        self.readme_updated.emit(message)
