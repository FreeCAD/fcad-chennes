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

#ifndef BASE_THEMEMANAGER_H 
#define BASE_THEMEMANAGER_H 

#include <vector>
#include <string>


namespace Base {

	class Metadata;

	/**
	 * \class Theme A collection of user preferences stored in files on disk
	 */
	class Theme {

	public:

		/**
		 * Construct a theme from a file/directory
		 * 
		 * \param themeFile A path to either a *.FCTheme file (which is a zipped FCTheme directory),
		 * or to a decompressed FCTheme directory.
		 */
		Theme(const boost::filesystem::path& themeFile);

		~Theme() = default;

		/**
		 * Get the name of the theme 
		 */
		std::string name() const;

		/**
		 * Apply the theme over the top of the current preferences set
		 */
		void apply() const;

	private:

		std::unique_ptr<Metadata> _metadata;
		boost::filesystem::path _path;

		/**
		 * Opens the theme archive (if needed) and reads in the metadata.xml file
		 */
		void loadMetadata();

		void parseMetadataFile(const boost::filesystem::path &file);
	};




	/**
	 * \class ThemeManager handles storable and loadable collections of user preferences
	 */
	class ThemeManager {
	public:
		ThemeManager();
		~ThemeManager() = default;

		/**
		 * Rescan the theme directory and update the available themes
		 */
		void rescan();

		/**
		 * Get an alphabetical list of names of all installed themes
		 */
		std::vector<std::string> themeNames() const;

		/**
		 * Get a list of installed themes
		 */
		std::vector<const Theme *> themes() const;

		/**
		 * Apply the named theme
		 */
		void apply(const std::string & themeName) const;

		/**
		 * Apply the referenced theme
		 */
		void apply(const Theme& theme) const;

		/**
		 * Save current settings as a (possibly new) theme
		 * 
		 * If the named theme does not exist, this creates it on disk. If it does exist, this overwrites the original.
		 */
		void save(const std::string& name, const std::string &templateFile = std::string(), bool compress = true);

	};

}

#endif