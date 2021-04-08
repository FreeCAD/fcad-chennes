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

#include "MetadataReader.h"

#include <xercesc/parsers/XercesDOMParser.hpp>
#include <xercesc/dom/DOM.hpp>
#include <xercesc/sax/HandlerBase.hpp>
#include <xercesc/util/XMLString.hpp>
#include <xercesc/util/PlatformUtils.hpp>

using namespace Base;
namespace fs = boost::filesystem;
XERCES_CPP_NAMESPACE_USE


Metadata::Metadata(const boost::filesystem::path& metadataFile)
{
    // Any exception thrown by the XML code propagates out and prevents object creation
    XMLPlatformUtils::Initialize();

    auto parser = std::make_unique<XercesDOMParser> ();
    parser->setValidationScheme(XercesDOMParser::Val_Never);
    parser->setDoNamespaces(true);

    auto errHandler = std::make_unique<HandlerBase>();
    parser->setErrorHandler(errHandler.get());

    parser->parse(metadataFile.string().c_str());

    auto doc = parser->getDocument();
    _dom = doc->getDocumentElement();

    auto tempString = XMLString::transcode("package");
    auto rootTagName = _dom->getTagName();
    if (XMLString::compareString(rootTagName, tempString) != 0)
        throw std::exception("package.xml must contain one, and only one, <package> element.");
    XMLString::release(&tempString);

    tempString = XMLString::transcode("format");
    auto formatString = _dom->getAttribute(tempString);
    if (XMLString::stringLen(formatString) == 0)
        throw std::exception("<package> must contain the 'format' attribute");
    auto format = XMLString::parseInt(formatString);
    XMLString::release(&tempString);
    
    switch (format) {
    case 3:
        parseVersion3();
        break;
    default:
        throw std::exception("pacakge.xml format version is not supported by this version of FreeCAD");
    }
}

Base::Metadata::~Metadata()
{
    XMLPlatformUtils::Terminate();
}

std::string Metadata::name() const
{
    return _name;
}

std::string Metadata::version() const
{
    return _version;
}

std::string Metadata::description() const
{
    return _description;
}

std::vector<Meta::Contact> Metadata::maintainer() const
{
    return _maintainer;
}

std::vector<Meta::License> Metadata::license() const
{
    return _license;
}

std::vector<Meta::Url> Metadata::url() const
{
    return _url;
}

std::vector<Meta::Contact> Metadata::author() const
{
    return _author;
}

std::vector<Meta::Dependency> Metadata::depend() const
{
    return _depend;
}

std::vector<Meta::Dependency> Metadata::conflict() const
{
    return _conflict;
}

std::vector<Meta::Dependency> Metadata::replace() const
{
    return _replace;
}

std::vector<Meta::GenericMetadata> Metadata::operator[](const std::string tag) const
{
    return _genericMetadata;
}

XERCES_CPP_NAMESPACE::DOMElement* Metadata::dom() const
{
    return _dom;
}

std::string transcodeToString(const XMLCh* xml)
{
    auto temp = XMLString::transcode(xml);
    auto s = std::string(temp);
    XMLString::release(&temp);
    return s;
}

void Metadata::parseVersion3()
{
    auto children = _dom->getChildNodes();

    for (int i = 0; i < children->getLength(); ++i) {
        auto child = children->item(i);
        auto element = dynamic_cast<DOMElement*>(child);
        if (!element)
            continue;

        auto tag = element->getNodeName();
        auto tagCString = XMLString::transcode(tag);
        std::string tagString(tagCString);
        XMLString::release(&tagCString);

        /*
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
         */

        if (tagString == "name")
            _name = transcodeToString(element->getTextContent());
        else if (tagString == "version")
            _version = transcodeToString(element->getTextContent());
        else if (tagString == "description")
            _description = transcodeToString(element->getTextContent());
        else if (tagString == "maintainer")
            _maintainer.emplace_back(element);
        else if (tagString == "license")
            _license.emplace_back(element);
        else if (tagString == "url")
            _url.emplace_back(element);
        else if (tagString == "author")
            _author.emplace_back(element);
        else if (tagString == "depend")
            _depend.emplace_back(element);
        else if (tagString == "conflict")
            _conflict.emplace_back(element);
        else if (tagString == "replace")
            _replace.emplace_back(element);
        else if (child->getChildNodes()->getLength() == 0)
            _genericMetadata.emplace_back(element);
        // else we don't recognize this tag, just ignore it, but leave it in the DOM tree
    }
}

Meta::Contact::Contact(XERCES_CPP_NAMESPACE::DOMElement* e)
{
    auto emailXmlCh = XMLString::transcode("email");
    auto emailAttribute = e->getAttribute(emailXmlCh);
    XMLString::release(&emailXmlCh);
    name = transcodeToString(e->getTextContent());
    email = transcodeToString(emailAttribute);
}

Meta::License::License(XERCES_CPP_NAMESPACE::DOMElement* e)
{
    auto fileXmlCh = XMLString::transcode("file");
    auto fileAttribute = e->getAttribute(fileXmlCh);
    XMLString::release(&fileXmlCh);
    if (XMLString::stringLen(fileAttribute) > 0) {
        file = fs::path(transcodeToString(fileAttribute));
    }
    name = transcodeToString(e->getTextContent());
}

Meta::Url::Url(XERCES_CPP_NAMESPACE::DOMElement* e)
{
    auto typeXmlCh = XMLString::transcode("type");
    auto typeAttribute = transcodeToString(e->getAttribute(typeXmlCh));
    XMLString::release(&typeXmlCh);
    if (typeAttribute.empty() || typeAttribute == "website")
        type = UrlType::website;
    else if (typeAttribute == "bugtracker")
        type = UrlType::bugtracker;
    else if (typeAttribute == "repository")
        type = UrlType::repository;
    location = transcodeToString(e->getTextContent());
}

Meta::Dependency::Dependency(XERCES_CPP_NAMESPACE::DOMElement* e)
{
    auto ltXmlCh = XMLString::transcode("version_lt");
    auto lteXmlCh = XMLString::transcode("version_lte");
    auto eqXmlCh = XMLString::transcode("version_eq");
    auto gteXmlCh = XMLString::transcode("version_gte");
    auto gtXmlCh = XMLString::transcode("version_gt");
    auto conditionXmlCh = XMLString::transcode("condition");

    version_lt = transcodeToString(e->getAttribute(ltXmlCh));
    version_lte = transcodeToString(e->getAttribute(lteXmlCh));
    version_eq = transcodeToString(e->getAttribute(eqXmlCh));
    version_gte = transcodeToString(e->getAttribute(gteXmlCh));
    version_gt = transcodeToString(e->getAttribute(gtXmlCh));
    condition = transcodeToString(e->getAttribute(conditionXmlCh));

    XMLString::release(&ltXmlCh);
    XMLString::release(&lteXmlCh);
    XMLString::release(&eqXmlCh);
    XMLString::release(&gteXmlCh);
    XMLString::release(&gtXmlCh);
    XMLString::release(&conditionXmlCh);

    package = transcodeToString(e->getTextContent());
}

Meta::GenericMetadata::GenericMetadata(XERCES_CPP_NAMESPACE::DOMElement* e)
{
    contents = transcodeToString(e->getTextContent());
    for (int i = 0; i < e->getAttributes()->getLength(); ++i) {
        auto a = e->getAttributes()->item(i);
        attributes.insert(std::make_pair(transcodeToString(a->getNodeName()), 
                                         transcodeToString(a->getTextContent())));
    }
}
