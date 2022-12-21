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

import addonmanager_freecad_interface as fci

# Unit test for the Addon Manager module GUI
from AddonManagerTest.gui.test_gui import TestGui as AddonManagerTestGui

from AddonManagerTest.gui.test_workers_utility import (
    TestWorkersUtility as AddonManagerTestWorkersUtility,
)
from AddonManagerTest.gui.test_installer_gui import (
    TestInstallerGui as AddonManagerTestInstallerGui,
)
from AddonManagerTest.gui.test_installer_gui import (
    TestMacroInstallerGui as AddonManagerTestMacroInstallerGui,
)
from AddonManagerTest.gui.test_update_all_gui import (
    TestUpdateAllGui as AddonManagerTestUpdateAllGui,
)
from AddonManagerTest.gui.test_uninstaller_gui import (
    TestUninstallerGUI as AddonManagerTestUninstallerGUI,
)
from AddonManagerTest.gui.test_icon_source import (
    TestIconSource as AddonManagerTestIconSource,
    TestCacheUpdater as AddonManagerTestCacheUpdater,
    TestDirectUpdater as AddonManagerTestDirectUpdater,
    TestIndividualDirectUpdater as AddonManagerTestIndividualDirectUpdater,
    TestMacroDirectUpdater as AddonManagerTestMacroDirectUpdater,
)

<<<<<<< HEAD

class TestListTerminator:
    pass


# Basic usage mostly to get static analyzers to stop complaining about unused imports
loaded_gui_tests = [
    AddonManagerTestGui,
    AddonManagerTestWorkersUtility,
    AddonManagerTestWorkersStartup,
=======
# Basic usage mostly to get static analyzers to stop complaining about unused imports
try:
    import FreeCAD

    print_func = FreeCAD.Console.PrintLog
except ImportError:
    FreeCAD = None
    print_func = print
loaded_gui_tests = [
    AddonManagerTestGui,
    AddonManagerTestWorkersUtility,
>>>>>>> 2ed2581bbe (App: Add metadata construct from buffer)
    AddonManagerTestInstallerGui,
    AddonManagerTestMacroInstallerGui,
    AddonManagerTestUpdateAllGui,
    AddonManagerTestUninstallerGUI,
<<<<<<< HEAD
    TestListTerminator  # Needed to prevent the last test from running twice
]
for test in loaded_gui_tests:
    fci.Console.PrintLog(f"Loaded tests from {test.__name__}\n")
=======
    AddonManagerTestIconSource,
    AddonManagerTestCacheUpdater,
    AddonManagerTestDirectUpdater,
    AddonManagerTestIndividualDirectUpdater,
    AddonManagerTestMacroDirectUpdater,
    None,  # Stop extractor from deciding to re-add the last item in this list as another test
]
if FreeCAD:
    for test in loaded_gui_tests:
        if test is not None:
            print_func(f"Loaded tests from {test.__name__}\n")
>>>>>>> 2ed2581bbe (App: Add metadata construct from buffer)
