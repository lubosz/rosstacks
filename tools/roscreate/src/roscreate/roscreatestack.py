#!/usr/bin/env python
# Software License Agreement (BSD License)
#
# Copyright (c) 2009, Willow Garage, Inc.
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

"""
Implements the roscreate-stack tool.

The focus of this module is on supporting the command-line tool. The
code API of this module is *not* stable.
"""

from __future__ import with_statement
import roslib; roslib.load_manifest('roscreate')

NAME='roscreate-stack'

import os
import sys
import roslib.manifest
import roslib.packages
import roslib.stacks
import roslib.stack_manifest

from roscreate.core import read_template, author_name, print_warning

def get_templates():
    """
    @return: mapping of file names to templates to instantiate
    @rtype: {str: str}
    """
    templates = {}
    templates['stack.xml'] = read_template('stack.tmpl')
    templates['CMakeLists.txt'] = read_template('CMakeLists.stack.tmpl')
    templates['Makefile'] = read_template('Makefile.stack.tmpl')
    return templates

def instantiate_template(template, stack, brief, description, author, depends, licenses, review):
    """
    @return: template instantiated with properties
    @rtype: str
    """
    return template%locals()

def _update_depends(depends):
    new_depends = []
    for s, pkgs in depends.iteritems():
        d = roslib.stack_manifest.StackDepend(s)
        d.annotation = ', '.join(set(pkgs))
        new_depends.append(d)
        new_depends.sort(lambda x, y: -1 if x.stack < y.stack else 1)
    return ''.join(["  %s\n"%d.xml() for d in new_depends])
         
def create_stack(stack, stack_dir, stack_manifest, author, depends, licenses, show_deps):
    """
    @param stack: name of stack
    @type  stack: str
    @param stack_dir: path to stack
    @type  stack_dir: str
    @param stack_manifest: existing stack manifest or None
    @type  stack_manifest: L{roslib.stack_manifest.StackManifest}
    @param author: name of stack maintainer. Overrides stack_manifest.
    @type  author: str
    @param depends: map of stack name to packages that use that stack. Overrides stack_manifest.
    @type  depends: {str: [str]}
    @param licenses: list of licenses present in stack
    @type  licenses: set(str)
    """

    if show_deps:
      print ''.join(['  <depend stack="%s"/> <!-- %s --> \n'%(s, ', '.join(set(pkgs))) for s, pkgs in depends.iteritems()])
      return
    
    # load existing properties
    if stack_manifest is not None:
        try:
            licenses.update([l.strip() for l in stack_manifest.license.split(',')])
        except: pass
        brief = stack_manifest.brief or stack
        description = stack_manifest.description
        review = '  <review status="%s" notes="%s"/>'%(stack_manifest.status, stack_manifest.notes)        
    else:
        stack_manifest = roslib.stack_manifest.StackManifest()
        brief = description = stack
        review = '  <review status="unreviewed" notes=""/>'

    licenses = ','.join(licenses)
    depends = _update_depends(depends)
    
    p = os.path.abspath(stack_dir)
    if not os.path.exists(p):
        print "Creating stack directory", p
        os.makedirs(p)

    templates = get_templates()
    for filename, template in templates.iteritems():
        contents = instantiate_template(template, stack, brief, description, author, depends, licenses, review)
        p = os.path.abspath(os.path.join(stack_dir, filename))
        if not os.path.exists(filename) or filename == 'stack.xml':
            print "Creating stack file", p
            with open(p, 'w') as f:
                f.write(contents)
    print "\nPlease edit %s/stack.xml to finish creating your stack"%stack

def compute_stack_depends_and_licenses(stack_dir):
    """
    @return: depends, licenses
    @rtype: {str: [str]}, [str]
    @raise: roslib.packages.InvalidROSPkgException
    """
    stack = os.path.basename(os.path.abspath(stack_dir))    
    if os.path.exists(stack_dir):
        packages = roslib.packages.list_pkgs_by_path(os.path.abspath(stack_dir))
        depends, licenses = _compute_stack_depends_and_licenses(stack, packages)
    else:
        depends = dict()
        licenses = ['BSD']
    # add in bare ros dependency into any stack as an implicit depend
    if not 'ros' in depends:
        depends['ros'] = []
    return depends, licenses
    
def _compute_stack_depends_and_licenses(stack, packages):
    pkg_depends = []
    licenses = []
    for pkg in packages:
        m = roslib.manifest.parse_file(roslib.manifest.manifest_file(pkg))
        pkg_depends.extend([d.package for d in m.depends])
        licenses.append(m.license)
        
    stack_depends = {}
    for pkg in pkg_depends:
        if pkg in packages:
            continue
        st = roslib.stacks.stack_of(pkg)
        if not st:
            print_warning("WARNING: stack depends on [%s], which is not in a stack"%pkg)
            continue 
        if st == stack:
            continue
        if not st in stack_depends:
            stack_depends[st] = []            
        stack_depends[st].append(pkg)
    return stack_depends, set(licenses)

def roscreatestack_main():
    from optparse import OptionParser    
    parser = OptionParser(usage="usage: %prog <path-to-stack>", prog=NAME)
    parser.add_option("--show-deps", 
                      dest="show_deps", default=False,
                      action="store_true",
                      help="show stack dependencies, instead of generating stack.xml")
    options, args = parser.parse_args()
    if not args:
        parser.error("you must specify the path to a stack")
    stack_dir = args[0]
    stack = os.path.basename(os.path.abspath(stack_dir))

    try:
        depends, licenses = compute_stack_depends_and_licenses(stack_dir)
    except roslib.packages.InvalidROSPkgException, e:
        print >> sys.stderr, str(e)
        sys.exit(1)

    if not options.show_deps:
      # Check for existing stack.xml
      stack_xml_path = os.path.join(stack_dir, 'stack.xml')
      if os.path.exists(stack_xml_path):
          import shutil
          stack_xml_path_bak = os.path.join(stack_dir, 'stack.xml.bak')
          print 'Backing up existing stack.xml to %s'%stack_xml_path_bak
          shutil.copyfile(stack_xml_path, stack_xml_path_bak)

          # load existing stack.xml properties
          stack_manifest = roslib.stack_manifest.parse_file(stack_xml_path)
          author = stack_manifest.author
      else:
          stack_manifest = None
          author = "Maintained by %s"%author_name()
  
    create_stack(stack, stack_dir, stack_manifest, author, depends, licenses, options.show_deps)

if __name__ == "__main__":
    roscreatestack_main()
