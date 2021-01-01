#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2020 Chris Hennes <chennes@pioneerlibrarysystem.org>    *
#*                                                                         *
#*   This program is free software; you can redistribute it and/or modify  *
#*   it under the terms of the GNU Lesser General Public License (LGPL)    *
#*   as published by the Free Software Foundation; either version 2 of     *
#*   the License, or (at your option) any later version.                   *
#*   for detail see the LICENCE text file.                                 *
#*                                                                         *
#*   This program is distributed in the hope that it will be useful,       *
#*   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
#*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
#*   GNU Library General Public License for more details.                  *
#*                                                                         *
#*   You should have received a copy of the GNU Library General Public     *
#*   License along with this program; if not, write to the Free Software   *
#*   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
#*   USA                                                                   *
#*                                                                         *
#***************************************************************************

import FreeCADGui,sys,urllib

# This script is called from StartPage.py with the variable "arg" set to some quoted path.

filename=urllib.parse.unquote(arg)

recentFilesGroup = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/RecentFiles")
recentFilesEntries = recentFilesGroup.GetStrings()

# Create a list of all the files we are keeping, and remove all of the old MRU entries so
# they can be renumbered
recentFiles = []
for entry in recentFilesEntries:
    recent = recentFilesGroup.GetString(entry)
    recentFilesGroup.RemString(entry)
    if recent != filename:
        recentFiles.append(recent)


# Recreate the whole list so the numbering stays consistent, but don't use Clear(),
# which would cause the Start page to be re-rendered because it's watching that group.
counter = 0
for recent in recentFiles:
    parameterName = "MRU" + str(counter)
    recentFilesGroup.SetString(parameterName, recent)
    counter += 1


# Now do the exact same thing with our pins, in case this was also a pinned file

pinnedFilesGroup = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/PinnedFiles")
pinnedFilesEntries = pinnedFilesGroup.GetStrings()

# Create a list of all the files we are keeping, and remove all of the old MRU entries so
# they can be renumbered
pinnedFiles = []
for entry in pinnedFilesEntries:
    pinned = pinnedFilesGroup.GetString(entry)
    pinnedFilesGroup.RemString(entry)
    if pinned != filename:
        pinnedFiles.append(pinned)


# Recreate the whole list so the numbering stays consistent, but don't use Clear(),
# which would cause the Start page to be re-rendered because it's watching that group.
counter = 0
for pinned in pinnedFiles:
    parameterName = "MRU" + str(counter)
    pinnedFilesGroup.SetString(parameterName, pinned)
    counter += 1