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

#ifndef BASE_METADATAREADER_H 
#define BASE_METADATAREADER_H 

#include <boost/filesystem.hpp>

#include <string>
#include <vector>
#include <map>

#include <xercesc/dom/DOM.hpp>

namespace Base {

    namespace Meta {

        struct Contact {
            Contact(XERCES_CPP_NAMESPACE::DOMElement*e);
            std::string name;
            std::string email;
        };

        struct License {
            License(XERCES_CPP_NAMESPACE::DOMElement* e);
            std::string name;
            boost::filesystem::path file;
        };

        enum class UrlType {
            website,
            repository,
            bugtracker
        };

        struct Url {
            Url(XERCES_CPP_NAMESPACE::DOMElement* e);
            std::string location;
            UrlType type;
        };

        struct Dependency {
            Dependency(XERCES_CPP_NAMESPACE::DOMElement* e);
            std::string package; //< Required
            std::string version_lt; //< Optional: The dependency to the package is restricted to versions less than the stated version number.
            std::string version_lte; //< Optional: The dependency to the package is restricted to versions less or equal than the stated version number.
            std::string version_eq; //< Optional: The dependency to the package is restricted to a version equal than the stated version number.
            std::string version_gte; //< Optional: The dependency to the package is restricted to versions greater or equal than the stated version number.
            std::string version_gt; //< Optional: The dependency to the package is restricted to versions greater than the stated version number.
            std::string condition; //< Optional: Conditional expression as documented in REP149.

            /**
             * Check a version string against this dependency: if the string meets the dependency, 
             * true is returned. If not, false is returned. In general this operates on standard-format
             * version triplets, and ignores any information that does not meet that format. The exceptions
             * are if the dependency specifies "version_eq" then an exact string match is performed, and if
             * "condition" is specified, then that code is executed with this string provided as the variable
             * "$VERSION".
             */
            bool matchesDependency(const std::string version) const;
        };

        /**
         * \struct GenericMetadata
         * A structure to hold unrecognized single-level metadata.
         * 
         * Most unrecognized metadata is simple: when parsing the XML, if the parser finds a tag it
         * does not recognize, and that tag has no children, it is parsed into this data structure
         * for convenient access by client code.
         */
        struct GenericMetadata {
            GenericMetadata(XERCES_CPP_NAMESPACE::DOMElement* e);
            std::string contents;
            std::map<std::string,std::string> attributes;
        };

    }

    /**
     * \class Metadata 
     * \brief Reads data from a metadata file.
     * 
     * The metadata format is based on https://ros.org/reps/rep-0149.html
     * 
     * The following metadata is required, and guaranteed to exist upon class creation:
     * <name>
     * <version>
     * <description>
     * <maintainer> (multiple, but at least one: "email" attribute is required)
     * <license> (multiple, but at least one: "file" attribute may contain path to full license)
     * 
     * The following is recognized (but not required) metadata:
     * <url> (multiple: "type" attribute may be website (default), bugtracker or repository)
     * <author> (multiple: "email" attribute is optional)
     * <depend> (multiple: attributes described in Depend struct declaration)
     * <conflict> (multiple: see depend)
     * <replace> (multiple: see depend)
     * 
     * Any unrecognized metadata can be accessed by accessing the DOM tree directly using the 
     * provided member function, or (in the case of simple single-level metadata) by using
     * operator[].
     */
    class Metadata {
    public:

        /**
         * Read the data from a file on disk
         * 
         * This constructor takes a path to an XML file and loads the XML from that file as
         * metadata.
         */
        explicit Metadata(const boost::filesystem::path& metadataFile);		
        
        ~Metadata();

        // Required metadata: these functions always return valid data
        std::string name() const;
        std::string version() const;
        std::string description() const;
        std::vector<Meta::Contact> maintainer() const;
        std::vector<Meta::License> license() const;

        // Optional recognized metadata: these functions may return empty vectors
        std::vector<Meta::Url> url() const;
        std::vector<Meta::Contact> author() const;
        std::vector<Meta::Dependency> depend() const;
        std::vector<Meta::Dependency> conflict() const;
        std::vector<Meta::Dependency> replace() const;

        /**
         * Convenience accessor for unrecognized simple metadata.
         * 
         * If the XML parser encounters tags that it does not recognize, and those tags have
         * no children, a GenericMetadata object is created. Those objects can be accessed using
         * operator[], which returns a (potentially empty) vector containing all instances of the
         * given tag.
         */
        std::vector<Meta::GenericMetadata> operator[] (const std::string tag) const;
        
        /**
         * Directly access the DOM tree to support unrecognized multi-level metadata
         */
        XERCES_CPP_NAMESPACE::DOMElement* dom() const;

    private:

        std::string _name;
        std::string _version;
        std::string _description;
        std::vector<Meta::Contact> _maintainer;
        std::vector<Meta::License> _license;

        // Optional recognized metadata: these functions may return empty vectors
        std::vector<Meta::Url> _url;
        std::vector<Meta::Contact> _author;
        std::vector<Meta::Dependency> _depend;
        std::vector<Meta::Dependency> _conflict;
        std::vector<Meta::Dependency> _replace;

        std::vector<Meta::GenericMetadata> _genericMetadata;

        XERCES_CPP_NAMESPACE::DOMElement* _dom;

        void parseVersion3();
    };

}

#endif