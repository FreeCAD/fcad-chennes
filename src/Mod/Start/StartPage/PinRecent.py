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
recent_files=FreeCAD.ParamGet("User parameter:BaseApp/Preferences/RecentFiles")

pinnedFilesGroup = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/PinnedFiles")
pinnedFilesEntries = pinnedFilesGroup.GetStrings()

found = False
pinnedFiles = []
for entry in pinnedFilesEntries:
    pin = pinnedFilesGroup.GetString(entry)
    pinnedFiles.append(pin)
    if pin == filename:
        found = True
        break

if not found:
    pinnedFiles.append(filename)

# Recreate the whole list so we don't have to worry about the numbering (which is never used
# except to give each parameter entry a unique name)
pinnedFilesGroup.Clear()
counter = 0
for pin in pinnedFiles:
    parameterName = "PIN" + str(counter)
    pinnedFilesGroup.SetString(parameterName, pin)
    counter += 1

pinnedFilesGroup.NotifyAll()