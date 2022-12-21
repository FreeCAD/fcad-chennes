# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2022-2023 FreeCAD Project Association                   *
# *   Copyright (c) 2018 Gaël Écorchard <galou_breizh@yahoo.fr>             *
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

""" Utilities to work across different platforms, providers and python versions """

import io
import os
import platform
import shutil
import stat
import subprocess
import re
import ctypes
from typing import Optional, Any
import zipfile

from urllib.parse import urlparse

from PySide import QtCore, QtWidgets

import FreeCAD

if FreeCAD.GuiUp:
    import FreeCADGui

    # If the GUI is up, we can use the NetworkManager to handle our downloads. If there is no event
    # loop running this is not possible, so fall back to requests (if available), or the native
    # Python urllib.request (if requests is not available).
    import NetworkManager  # Requires an event loop, so is only available with the GUI

    UrlExceptionType = Exception
else:
    try:
        import requests
<<<<<<< HEAD
    except ImportError:
        requests = None
        import urllib.request
        import ssl

=======

        has_requests = True
        UrlExceptionType = requests.RequestException
    except ImportError:
        has_requests = False
        import urllib.request, urllib.error
        import ssl

        UrlExceptionType = urllib.error.URLError


>>>>>>> 2ed2581bbe (App: Add metadata construct from buffer)
#  @package AddonManager_utilities
#  \ingroup ADDONMANAGER
#  \brief Utilities to work across different platforms, providers and python versions
#  @{


translate = FreeCAD.Qt.translate


class ProcessInterrupted(RuntimeError):
    """An interruption request was received and the process killed because of it."""


def symlink(source, link_name):
    """Creates a symlink of a file, if possible. Note that it fails on most modern Windows
    installations"""

    if os.path.exists(link_name) or os.path.lexists(link_name):
        pass
    else:
        os_symlink = getattr(os, "symlink", None)
        if callable(os_symlink):
            os_symlink(source, link_name)
        else:
            # NOTE: This does not work on most normal Windows 10 and later installations, unless
            # developer mode is turned on. Make sure to catch any exception thrown and have a
            # fallback plan.
            csl = ctypes.windll.kernel32.CreateSymbolicLinkW
            csl.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32)
            csl.restype = ctypes.c_ubyte
            flags = 1 if os.path.isdir(source) else 0
            # set the SYMBOLIC_LINK_FLAG_ALLOW_UNPRIVILEGED_CREATE flag
            # (see https://blogs.windows.com/buildingapps/2016/12/02/symlinks-windows-10)
            flags += 2
            if csl(link_name, source, flags) == 0:
                raise ctypes.WinError()


def rmdir(path: os.PathLike) -> bool:
    try:
        shutil.rmtree(path, onerror=remove_readonly)
    except (WindowsError, PermissionError, OSError):
        return False
    return True


def remove_readonly(func, path, _) -> None:
    """Remove a read-only file."""

    os.chmod(path, stat.S_IWRITE)
    func(path)


def update_macro_details(old_macro, new_macro):
    """Update a macro with information from another one

    Update a macro with information from another one, supposedly the same but
    from a different source. The first source is supposed to be git, the second
    one the wiki.
    """

    if old_macro.on_git and new_macro.on_git:
        FreeCAD.Console.PrintLog(
            f'The macro "{old_macro.name}" is present twice in github, please report'
        )
    # We don't report macros present twice on the wiki because a link to a
    # macro is considered as a macro. For example, 'Perpendicular To Wire'
    # appears twice, as of 2018-05-05).
    old_macro.on_wiki = new_macro.on_wiki
    for attr in ["desc", "url", "code"]:
        if not hasattr(old_macro, attr):
            setattr(old_macro, attr, getattr(new_macro, attr))


def remove_directory_if_empty(dir_to_remove):
    """Remove the directory if it is empty, with one exception: the directory returned by
    FreeCAD.getUserMacroDir(True) will not be removed even if it is empty."""

    if dir_to_remove == FreeCAD.getUserMacroDir(True):
        return
    if not os.listdir(dir_to_remove):
        os.rmdir(dir_to_remove)


def restart_freecad():
    """Shuts down and restarts FreeCAD"""

    args = QtWidgets.QApplication.arguments()[1:]
    if FreeCADGui.getMainWindow().close():
        QtCore.QProcess.startDetached(
            QtWidgets.QApplication.applicationFilePath(), args
        )


def get_zip_url(repo):
    """Returns the location of a zip file from a repo, if available"""

    parsed_url = urlparse(repo.url)
    if parsed_url.netloc == "github.com":
        return f"{repo.url}/archive/{repo.branch}.zip"
    if parsed_url.netloc in ["gitlab.com", "framagit.org", "salsa.debian.org"]:
        return f"{repo.url}/-/archive/{repo.branch}/{repo.name}-{repo.branch}.zip"
    FreeCAD.Console.PrintLog(
        "Debug: addonmanager_utilities.get_zip_url: Unknown git host fetching zip URL:"
        + parsed_url.netloc
        + "\n"
    )
    return f"{repo.url}/-/archive/{repo.branch}/{repo.name}-{repo.branch}.zip"


def recognized_git_location(repo) -> bool:
    """Returns whether this repo is based at a known git repo location: works with github, gitlab,
    framagit, and salsa.debian.org"""

    parsed_url = urlparse(repo.url)
    return parsed_url.netloc in [
        "github.com",
        "gitlab.com",
        "framagit.org",
        "salsa.debian.org",
    ]


def construct_git_url(repo, filename):
    """Returns a direct download link to a file in a Git repo"""

    url = repo.url.replace(os.path.sep, "/")
    parsed_url = urlparse(url)
    filename = filename.replace(os.path.sep, "/")
    if parsed_url.scheme == "file":
        # Handle file:// URLs
        return f"{url}/{filename}"
    if parsed_url.netloc == "github.com":
        return f"{url}/raw/{repo.branch}/{filename}"
    if parsed_url.netloc in ["gitlab.com", "framagit.org", "salsa.debian.org"]:
        return f"{url}/-/raw/{repo.branch}/{filename}"
    FreeCAD.Console.PrintLog(
        "Debug: addonmanager_utilities.construct_git_url: Unknown git host:"
        + parsed_url.netloc
        + f" for file {filename}\n"
    )
    # Assume it's some kind of GitLab instance...
    return f"{url}/-/raw/{repo.branch}/{filename}"


def get_readme_url(repo):
    """Returns the location of a readme file"""

    return construct_git_url(repo, "README.md")


def get_metadata_url(url):
    """Returns the location of a package.xml metadata file"""

    return construct_git_url(url, "package.xml")


def get_desc_regex(repo):
    """Returns a regex string that extracts a WB description to be displayed in the description
    panel of the Addon manager, if the README could not be found"""

    parsed_url = urlparse(repo.url)
    if parsed_url.netloc == "github.com":
        return r'<meta property="og:description" content="(.*?)"'
    if parsed_url.netloc in ["gitlab.com", "salsa.debian.org", "framagit.org"]:
        return r'<meta.*?content="(.*?)".*?og:description.*?>'
    FreeCAD.Console.PrintLog(
        "Debug: addonmanager_utilities.get_desc_regex: Unknown git host:",
        repo.url,
        "\n",
    )
    return r'<meta.*?content="(.*?)".*?og:description.*?>'


def get_readme_html_url(repo):
    """Returns the location of a html file containing readme"""

    parsed_url = urlparse(repo.url)
    if parsed_url.netloc == "github.com":
        return f"{repo.url}/blob/{repo.branch}/README.md"
    if parsed_url.netloc in ["gitlab.com", "salsa.debian.org", "framagit.org"]:
        return f"{repo.url}/-/blob/{repo.branch}/README.md"
    FreeCAD.Console.PrintLog(
        "Unrecognized git repo location '' -- guessing it is a GitLab instance..."
    )
    return f"{repo.url}/-/blob/{repo.branch}/README.md"


def is_darkmode() -> bool:
    """Heuristics to determine if we are in a darkmode stylesheet"""
    pl = FreeCADGui.getMainWindow().palette()
    return pl.color(pl.Background).lightness() < 128


def warning_color_string() -> str:
    """A shade of red, adapted to darkmode if possible. Targets a minimum 7:1 contrast ratio."""
    return "rgb(255,105,97)" if is_darkmode() else "rgb(215,0,21)"


def bright_color_string() -> str:
    """A shade of green, adapted to darkmode if possible. Targets a minimum 7:1 contrast ratio."""
    return "rgb(48,219,91)" if is_darkmode() else "rgb(36,138,61)"


def attention_color_string() -> str:
    """A shade of orange, adapted to darkmode if possible. Targets a minimum 7:1 contrast ratio."""
    return "rgb(255,179,64)" if is_darkmode() else "rgb(255,149,0)"


def get_assigned_string_literal(line: str) -> Optional[str]:
    """Look for a line of the form my_var = "A string literal" and return the string literal.
    If the assignment is of a floating point value, that value is converted to a string
    and returned. If neither is true, returns None."""

    string_search_regex = re.compile(r"\s*(['\"])(.*)\1")
    _, _, after_equals = line.partition("=")
    match = re.match(string_search_regex, after_equals)
    if match:
        return str(match.group(2))
    if is_float(after_equals):
        return str(after_equals).strip()
    return None


def get_macro_version_from_file(filename: str) -> str:
    """Get the version of the macro from a local macro file. Supports strings, ints, and floats,
    as well as a reference to __date__"""

    date = ""
    with open(filename, errors="ignore", encoding="utf-8") as f:
        line_counter = 0
        max_lines_to_scan = 200
        while line_counter < max_lines_to_scan:
            line_counter += 1
            line = f.readline()
            if not line:  # EOF
                break
            if line.lower().startswith("__version__"):
                match = get_assigned_string_literal(line)
                if match:
                    return match
                if "__date__" in line.lower():
                    # Don't do any real syntax checking, just assume the line is something
                    # like __version__ = __date__
                    if date:
                        return date
                    # pylint: disable=line-too-long,consider-using-f-string
                    FreeCAD.Console.PrintWarning(
                        translate(
                            "AddonsInstaller",
                            "Macro {} specified '__version__ = __date__' prior to setting a value for __date__".format(
                                filename
                            ),
                        )
                    )
            elif line.lower().startswith("__date__"):
                match = get_assigned_string_literal(line)
                if match:
                    date = match
    return ""


def update_macro_installation_details(repo) -> None:
    """Determine if a given macro is installed, either in its plain name,
    or prefixed with "Macro_" """
    if repo is None or not hasattr(repo, "macro") or repo.macro is None:
        FreeCAD.Console.PrintLog("Requested macro details for non-macro object\n")
        return
    test_file_one = os.path.join(FreeCAD.getUserMacroDir(True), repo.macro.filename)
    test_file_two = os.path.join(
        FreeCAD.getUserMacroDir(True), "Macro_" + repo.macro.filename
    )
    if os.path.exists(test_file_one):
        repo.updated_timestamp = os.path.getmtime(test_file_one)
        repo.installed_version = get_macro_version_from_file(test_file_one)
    elif os.path.exists(test_file_two):
        repo.updated_timestamp = os.path.getmtime(test_file_two)
        repo.installed_version = get_macro_version_from_file(test_file_two)
    else:
        return


# Borrowed from Stack Overflow:
# https://stackoverflow.com/questions/736043/checking-if-a-string-can-be-converted-to-float
def is_float(element: Any) -> bool:
    """Determine whether a given item can be converted to a floating-point number"""
    try:
        float(element)
        return True
    except ValueError:
        return False


#  @}


def get_python_exe() -> str:
    """Find Python. In preference order
    A) The value of the PythonExecutableForPip user preference
    B) The executable located in the same bin directory as FreeCAD and called "python3"
    C) The executable located in the same bin directory as FreeCAD and called "python"
    D) The result of an shutil search for your system's "python3" executable
    E) The result of an shutil search for your system's "python" executable"""
    prefs = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Addons")
    python_exe = prefs.GetString("PythonExecutableForPip", "Not set")
    fc_dir = FreeCAD.getHomePath()
    if not python_exe or python_exe == "Not set" or not os.path.exists(python_exe):
        python_exe = os.path.join(fc_dir, "bin", "python3")
        if "Windows" in platform.system():
            python_exe += ".exe"

    if not python_exe or not os.path.exists(python_exe):
        python_exe = os.path.join(fc_dir, "bin", "python")
        if "Windows" in platform.system():
            python_exe += ".exe"

    if not python_exe or not os.path.exists(python_exe):
        python_exe = shutil.which("python3")

    if not python_exe or not os.path.exists(python_exe):
        python_exe = shutil.which("python")

    if not python_exe or not os.path.exists(python_exe):
        return ""

    python_exe = python_exe.replace("/", os.path.sep)
    prefs.SetString("PythonExecutableForPip", python_exe)
    return python_exe


def get_pip_target_directory():
    # Get the default location to install new pip packages
    major, minor, _ = platform.python_version_tuple()
    vendor_path = os.path.join(
        FreeCAD.getUserAppDataDir(), "AdditionalPythonPackages", f"py{major}{minor}"
    )
    return vendor_path


def get_cache_file_name(file: str) -> str:
    """Get the full path to a cache file with a given name."""
    cache_path = FreeCAD.getUserCachePath()
    am_path = os.path.join(cache_path, "AddonManager")
    os.makedirs(am_path, exist_ok=True)
    return os.path.join(am_path, file)


def blocking_get(url: str, method=None) -> bytes:
    """Wrapper around three possible ways of accessing data, depending on the current run mode and
    Python installation. Blocks until complete, and returns the results of the call if it
    succeeded, or an empty bytes object if it failed, or returned no data. The method argument is
    provided mainly for testing purposes."""
<<<<<<< HEAD
    p = ""
    if FreeCAD.GuiUp and method is None or method == "networkmanager":
        NetworkManager.InitializeNetworkManager()
        p = NetworkManager.AM_NETWORK_MANAGER.blocking_get(url)
    elif requests and method is None or method == "requests":
=======
    p = bytes()
    parsed_url = urlparse(url)
    if parsed_url.scheme == "file":
        path = parsed_url.path
        if path.startswith("/"):
            path = path[1:]
        if not os.path.isfile(path):
            raise UrlExceptionType(f"No such file: {path}")
        with open(path, "rb") as f:
            p = f.read()
    elif FreeCAD.GuiUp and method is None or method == "networkmanager":
        nm = NetworkManager.GetNetworkManager()
        p = nm.blocking_get(url)
        if p is not None and hasattr(p, "data"):
            p = p.data()
    elif has_requests and method is None or method == "requests":
>>>>>>> 2ed2581bbe (App: Add metadata construct from buffer)
        response = requests.get(url)
        if response.status_code == 200:
            p = response.raw
    else:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(url, context=ctx) as f:
            p = f.read()
    return p


def run_interruptable_subprocess(args) -> subprocess.CompletedProcess:
    """Wrap subprocess call so it can be interrupted gracefully."""
    creation_flags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        # Added in Python 3.7 -- only used on Windows
        creation_flags = subprocess.CREATE_NO_WINDOW
    try:
        p = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creation_flags,
            text=True,
            encoding="utf-8",
        )
    except OSError as e:
        raise subprocess.CalledProcessError(-1, args, "", e.strerror)
    stdout = ""
    stderr = ""
    return_code = None
    while return_code is None:
        try:
            stdout, stderr = p.communicate(timeout=0.1)
            return_code = p.returncode
        except subprocess.TimeoutExpired:
            if QtCore.QThread.currentThread().isInterruptionRequested():
                p.kill()
                raise ProcessInterrupted()
    if return_code is None or return_code != 0:
        raise subprocess.CalledProcessError(return_code, args, stdout, stderr)
    return subprocess.CompletedProcess(args, return_code, stdout, stderr)


def get_main_am_window():
    windows = QtWidgets.QApplication.topLevelWidgets()
    for widget in windows:
        if widget.objectName() == "AddonManager_Main_Window":
            return widget
    # If there is no main AM window, we may be running unit tests: see if the Test Runner window
    # exists:
    for widget in windows:
        if widget.objectName() == "TestGui__UnitTest":
            return widget
    # If we still didn't find it, try to locate the main FreeCAD window:
    for widget in windows:
        if hasattr(widget, "centralWidget"):
            return widget.centralWidget()
    # Why is this code even getting called?
    return None


def clean_git_url(repo):
    """Strip trailing slashes, remove .git, and extract the name"""
    if repo["url"][-1] == "/":
        repo["url"] = repo["url"][0:-1]  # Strip trailing slash
    repo["url"] = repo["url"].split(".git")[0]  # Remove .git
    repo["name"] = repo["url"].split("/")[-1]


def extract_git_repo_zipfile(zip_data, destination: os.PathLike, branch: str = ""):
    """Extract a zipfile into a given destination, possibly moving its contents from a subdirectory
    called "branch" into the toplevel (used for sites like GitHub that place the data in a
    subdirectory named for the current branch). zip_data may be either a path to a local zipfile,
    or a bytes-like object containing zip data."""
    if isinstance(zip_data, str) and os.path.exists(zip_data):
        zip_file_like = io.FileIO(zip_data)
    else:
        zip_file_like = io.BytesIO(zip_data)
    with zipfile.ZipFile(zip_file_like, "r") as zfile:
        zfile.extractall(destination)

    # GitHub (and possibly other hosts) put all files in the zip into a subdirectory named
    # after the branch. If that is the setup that we just extracted, move all files out of
    # that subdirectory.
    directory_contents = os.listdir(destination)
    if len(directory_contents) == 1 and directory_contents[0].endswith(branch):
        subdirectory = directory_contents[0]
        for extracted_filename in os.listdir(os.path.join(destination, subdirectory)):
            shutil.move(
                os.path.join(destination, subdirectory, extracted_filename),
                os.path.join(destination, extracted_filename),
            )
        rmdir(os.path.join(destination, subdirectory))
