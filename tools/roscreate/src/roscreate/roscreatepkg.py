#!/usr/bin/env python
# Software License Agreement (BSD License)
#
# Copyright (c) 2008, Willow Garage, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of Willow Garage, Inc. nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# Revision $Id$

import roslib; roslib.load_manifest('roscreate')

NAME='roscreatepkg'

import os
import sys
import roslib.packages

from roscreate.core import read_template, author_name

def get_templates():
    templates = {}
    templates['CMakeLists.txt'] = read_template('CMakeLists.tmpl')
    templates['manifest.xml'] = read_template('manifest.tmpl')
    templates['mainpage.dox'] = read_template('mainpage.tmpl')
    templates['Makefile'] = read_template('Makefile.tmpl')
    return templates

def instantiate_template(template, package, brief, description, author, depends):
    return template%locals()

def create_package(package, author, depends, uses_roscpp=False, uses_rospy=False):
    p = os.path.abspath(package)
    if os.path.exists(p):
        print >> sys.stderr, "%s already exists, aborting"%p
        sys.exit(1)
    print "Creating package directory", p
    os.makedirs(p)

    if uses_roscpp:
        # create package/include/package and package/src for roscpp code
        cpp_path = os.path.join(p, 'include', package)
        print "Creating include directory", cpp_path
        os.makedirs(cpp_path)
        cpp_path = os.path.join(p, 'src')
        print "Creating cpp source directory", cpp_path
        os.makedirs(cpp_path)
    if uses_rospy:
        # create package/src/package for rospy
        py_path = os.path.join(p, 'src', package)
        print "Creating python source directory", py_path
        os.makedirs(py_path)
        
    templates = get_templates()
    for filename, template in templates.iteritems():
        contents = instantiate_template(template, package, package, package, author, depends)
        try:
            p = os.path.abspath(os.path.join(package, filename))
            print "Creating package file", p
            f = open(p, 'w')
            f.write(contents)
        finally:
            f.close()
    print "\nPlease edit %s/manifest.xml and mainpage.dox to finish creating your package"%package

def roscreatepkg_main():
    from optparse import OptionParser    
    parser = OptionParser(usage="usage: %prog <package-name> [dependencies...]", prog=NAME)
    options, args = parser.parse_args()
    if not args:
        parser.error("you must specify a package name and optionally also list package dependencies")
    package = args[0]

    # validate dependencies and turn into XML
    depends = args[1:]
    uses_roscpp = 'roscpp' in depends
    uses_rospy = 'rospy' in depends
    
    for d in depends:
        try:
            roslib.packages.get_pkg_dir(d)
        except roslib.packages.InvalidROSPkgException:
            print >> sys.stderr, "ERROR: dependency [%s] cannot be found"%d
            sys.exit(1)
    depends = ''.join(['  <depend package="%s"/>\n'%d for d in depends])

    create_package(package, author_name(), depends, uses_roscpp=uses_roscpp, uses_rospy=uses_rospy)

if __name__ == "__main__":
    roscreatepkg_main()
