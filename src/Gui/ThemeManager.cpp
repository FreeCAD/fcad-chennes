/***************************************************************************
 *   Copyright (c) 2021 Chris Hennes <chennes@pioneerlibrarysystem.org>    *
 *                                                                         *
 *   This file is part of the FreeCAD CAx development system.              *
 *                                                                         *
 *   This library is free software; you can redistribute it and/or         *
 *   modify it under the terms of the GNU Library General Public           *
 *   License as published by the Free Software Foundation; either          *
 *   version 2 of the License, or (at your option) any later version.      *
 *                                                                         *
 *   This library  is distributed in the hope that it will be useful,      *
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
 *   GNU Library General Public License for more details.                  *
 *                                                                         *
 *   You should have received a copy of the GNU Library General Public     *
 *   License along with this library; see the file COPYING.LIB. If not,    *
 *   write to the Free Software Foundation, Inc., 59 Temple Place,         *
 *   Suite 330, Boston, MA  02111-1307, USA                                *
 *                                                                         *
 ***************************************************************************/


#include "PreCompiled.h"

#ifndef _PreComp_
# include <memory>
#endif

#include <boost/filesystem.hpp>

#include "ThemeManager.h"
#include "MetadataReader.h"

using namespace Base;
using namespace xercesc;
namespace fs = boost::filesystem;


Theme::Theme(const fs::path& themeFile)
{
	if (!fs::exists(themeFile)) {
		throw std::runtime_error{ "Cannot access " + themeFile.string() };
	}
	_path = themeFile;
	loadMetadata();
}

std::string Theme::name() const
{
	return std::string();
}

void Theme::apply() const
{
	if (fs::is_directory(_path)) {
	}
	else {
	}
}

void Base::Theme::loadMetadata()
{
	if (fs::is_directory(_path)) {
		auto metadataFile = _path / "metadata.xml";
		if (!fs::exists(metadataFile))
			throw std::runtime_error("Cannot find " + metadataFile.string());
		_metadata = std::make_unique<Metadata>(metadataFile);
	}
	else {
		// This is a zipped archive: create the internal zipios stream
	}
}



ThemeManager::ThemeManager()
{
}

void ThemeManager::rescan()
{
}

std::vector<std::string> ThemeManager::themeNames() const
{
	return std::vector<std::string>();
}

std::vector<const Theme *> ThemeManager::themes() const
{
	return std::vector<const Theme *>();
}

void ThemeManager::apply(const std::string& themeName) const
{
}

void ThemeManager::apply(const Theme& theme) const
{
}

void ThemeManager::save(const std::string& name, const std::string& templateFile, bool compress)
{
}

