#! /usr/bin/env python

# Copyright (c) 2008, Willow Garage, Inc.
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of Willow Garage, Inc. nor the names of its
#       contributors may be used to endorse or promote products derived from
#       this software without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from __future__ import with_statement

import os
import re
import distutils.version
import sys, string
import subprocess
import getopt
import roslib
import roslib.rospack
import roslib.rosenv
import random
import tempfile
import shutil

from math import sqrt
from optparse import OptionParser


license_map = {
    "bsd": "green",
    "zlib": "green",
    "apache": "green",
    "free": "green",
    "bsl1.0": "green",
    "lgpl": "dodgerblue",
    "mit": "dodgerblue",
    "gpl": "orange",
    "research-only": "red",
    }

status_map = {
    "doc reviewed": "green",
    "api cleared": "dodgerblue",
    "api conditionally cleared": "orange",
    "proposal cleared": "pink",
    "unreviewed": "red",
    "experimental": "yellow",
    "3rdparty": "white",
    "3rdparty doc reviewed": "green",
    "na": "gray85",
    "test": "gray85",
    "deprecated": "magenta",        
    "ROS_BUILD_BLACKLIST": "black"
}


class PackageCharacteristics:
    def __init__(self):
        self.color_by = None
        
        self._file_colors = None
        self._status_colors = {}
        self._rosmake_result_colors = {}
        self._license_color = {}
        self._license = {}
        self._review_status = {}
        self._review_notes = {}
        

    def set_color_by(self, method, option=None):
        self.color_by = method
        if self.color_by == "file":
            self._color_filename = option

    def load_color_from_file(self):
        if self._file_colors:
            return True
        with open(self._color_filename,'r') as color_file:
            self._file_colors = {}
            for line in color_file:
                try:
                    k, v = line.split()
                    self.file_colors[k] = v
                except:
                    print "ERROR: badly formatted color line: %s"%line

    def get_file_color(self, pkg):
        self.load_color_from_file()
        return self._file_colors.get(pkg, 'purple')

    def get_license(self, pkg):
        if pkg in self._license:
            return self._license[pkg]
        self._license[pkg] = roslib.manifest.parse_file(roslib.manifest.manifest_file(pkg)).license.lower()
        return self._license[pkg]

    def get_license_color(self, pkg):
        if pkg in self._license_color:
            return self._license_color[pkg]

        license = self.get_license(pkg)
        self._license_color[pkg] = license_map.get(license, 'purple')

        if not license in license_map:
            print "Unknown: ", pkg, license

        return self._license_color[pkg]
        
    def get_review_status(self, pkg):
        if pkg in self._review_status:
            return self._review_status[pkg]
        f = roslib.manifest.manifest_file(pkg)
        try:
            self._review_status[pkg] = roslib.manifest.parse_file(f).status.lower()
        except:
            print "error parsing manifest '%s'"%f
            
        # show blacklisting
        if os.path.exists(os.path.join(os.path.dirname(f), "ROS_BUILD_BLACKLIST")):
            #print f, "is blacklisted"
            self._review_status[pkg] = "ROS_BUILD_BLACKLIST"
        return self._review_status[pkg]
        
    def get_review_notes(self, pkg):
        if pkg in self._review_notes:
            return self._review_notes[pkg]
        f = roslib.manifest.manifest_file(pkg)
        try:
            self._review_notes[pkg] = roslib.manifest.parse_file(f).notes
        except:
            print "error parsing manifest '%s'"%f
            
        # show blacklisting
        if os.path.exists(os.path.join(os.path.dirname(f), "ROS_BUILD_BLACKLIST")):
            #print f, "is blacklisted"
            self._review_notes[pkg] +=" ROS_BUILD_BLACKLIST"
        # show ROS_NOBUILD flag
        if os.path.exists(os.path.join(os.path.dirname(f), "ROS_NOBUILD")):
            print f, "is installed"
            self._review_notes[pkg] +=" ROS_NOBUILD"
        return self._review_notes[pkg]
        
    def get_review_color(self, pkg):
        status = self.get_review_status(pkg)
        return status_map.get(status, 'purple')
            

    def get_color(self, pkg):
        if self.color_by == "file":
            return self.get_file_color(pkg)
        if self.color_by == "review":
            return self.get_review_color(pkg)
        if self.color_by == "license":
            return self.get_license_color(pkg)
        else:
            return "gainsboro"

    def get_color_palate(self):
        if self.color_by == "review":
            return status_map
        if self.color_by == "license":
            return license_map
        else:
            return None

rosmakeall_color_map = { "rosmakeall-testfailures.txt": "orange", "rosmakeall-buildfailures.txt": "red"}

def get_rosmakeall_color():
    path = roslib.rosenv.get_ros_root()
    color_dict = {}
    for f in rosmakeall_color_map:
        c = rosmakeall_color_map[f]
        try:
            with open(path+"/"+f) as input:
                for l in input:
                    color_dict[l.strip()] = c
        except IOError:
            print >> sys.stderr, "Couldn't find %s"%f
            sys.exit(1)
    return color_dict



class HelperMethods:
    def __init__(self):
        self._stack_of = {}
        self._packages_of = {}
        self._deps = {}
        self._deps1 = {}
        self._stack_deps = {}
        self._stack_deps1 = {}
        self._deps_on = {}
        self._deps_on1 = {}
        self.verbose = False
        self.display_test_packages = True

    def get_stack_of(self, pkg):
        if pkg not in self._stack_of:
            stack = roslib.stacks.stack_of(pkg)
            if not stack:
                stack = "None"
            self._stack_of[pkg] = stack
            #print "hit cache"
        return  self._stack_of[pkg]

    def get_packages_of(self, stack):
        if stack == "None":
            return set()
        if stack not in self._packages_of:
            packages = roslib.stacks.packages_of(stack)
            self._packages_of[stack] = packages
            #print "hit cache"
        return  self._packages_of[stack]

    def get_deps(self, pkg):
        if pkg not in self._deps:
            stack = roslib.rospack.rospack_depends(pkg)
            self._deps[pkg] = stack
            #print "hit cache"
        return  self._deps[pkg]

    def get_deps1(self, pkg):
        if pkg not in self._deps1:
            stack = roslib.rospack.rospack_depends_1(pkg)
            self._deps1[pkg] = stack
            #print "hit cache"
        return  self._deps1[pkg]

    def get_stack_deps(self, stack):
        if stack not in self._stack_deps:
            deps = roslib.rospack.rosstack_depends(stack)
            self._stack_deps[stack] = deps
            #print "hit cache"
        return  self._stack_deps[stack]

    def get_stack_deps1(self, stack):
        if stack not in self._stack_deps1:
            deps = roslib.rospack.rosstack_depends_1(stack)
            self._stack_deps1[stack] = deps
            #print "hit cache"
        return  self._stack_deps1[stack]

    def get_deps_on(self, pkg):
        if pkg not in self._deps_on:
            stack = roslib.rospack.rospack_depends_on(pkg)
            self._deps_on[pkg] = stack
            #print "hit cache"
        return  self._deps_on[pkg]

    def get_deps_on1(self, pkg):
        if pkg not in self._deps_on1:
            stack = roslib.rospack.rospack_depends_on_1(pkg)
            self._deps_on1[pkg] = stack
            #print "hit cache"
        return  self._deps_on1[pkg]

    ## Get all the dependencies of dependent packages (deduplicated)
    def get_child_deps(self, pkg):
        accum = set()
        for dep in self.get_deps1(pkg):
            accum.update(self.get_deps(dep))
        return accum

    ## Get all the dependencies of dependent packages (deduplicated)
    def get_child_stack_deps(self, stack):
        accum = set()
        for dep in self.get_stack_deps1(stack):
            accum.update(self.get_stack_deps(dep))
        return accum

    def get_internal_child_deps(self, pkg, stack = None):
        if stack == "None":
            return set()
        if not stack:
            stack = self.get_stack_of(pkg)
            if not stack or stack == "None": 
                return set()

        internal_deps = self.get_internal_pkg_dependencies(pkg, stack)
        accum = set()
        for dep in internal_deps:
            accum.update(self.get_deps1(dep))

        return accum

    def get_depth(self, all_pkgs, pkg, depth):
        for pkg_dep in (set(self.get_deps1(pkg)) & all_pkgs):
            depth = max(depth, self.get_depth(all_pkgs, pkg_dep, depth + 1))
        return depth

    def build_rank(self, all_pkgs):
        rank = {}
        for pkg in all_pkgs:
            depth = self.get_depth(all_pkgs, pkg, 0)
            if depth in rank:
               rank[depth].append(pkg)
            else:
               rank[depth] = [pkg]

        return rank

    def get_external_pkg_dependencies(self, pkg, stack=None):
        if not stack:
            stack = self.get_stack_of(pkg)
        dependent_pkgs = self.get_deps1(pkg)
        return [ext for ext in dependent_pkgs if not self.get_stack_of(ext) == stack]

    def get_internal_pkg_dependencies(self, pkg, stack = None):
        if not stack:
            stack = self.get_stack_of(pkg)
        dependent_pkgs = self.get_deps1(pkg)
        return [ext for ext in dependent_pkgs if self.get_stack_of(ext) == stack]


    def group_pkgs_by_stack(self, pkgs):
        stacks = {}
        for p in pkgs:
            stack = self.get_stack_of(p)
            if not stack:
                continue
            if stack in stacks:
                stacks[stack].add(p)
            else:
                stacks[stack] = set([p])
        return stacks

    def get_stack_depth(self, pkg, depth):
        for stack_dep in self.get_deps1(pkg):
            depth = max(depth, get_stack_depth(stack_dep, depth + 1))
        return depth

    def compute_stack_ranks(self):
        rank = {}
        for stack in roslib.stacks.list_stacks():
            depth = self.get_stack_depth(stack, 0)
            if depth in rank:
               rank[depth].append(stack)
            else:
               rank[depth] = [stack]

        return rank


    # cluster definitons
    def build_stack_list(self, stack):#, include, exclude):
        if stack == "None":
            stack_contents = set()
        else:
            stack_contents = set(roslib.stacks.packages_of(stack))

        external_dependencies = set()
        for pkg in stack_contents:
            external_dependencies.update(self.get_external_pkg_dependencies(pkg))

        external_stack_dependencies = self.group_pkgs_by_stack(external_dependencies)

        return stack_contents, external_stack_dependencies


    def dict_to_set(self, dict):
        accum = set()
        for key, val in dict.iteritems():
            accum.update(val)
        return accum

    def generate_stack(self, stack, type, pkg_characterists):

        print "Generating Graphviz Intermediate"
        outfile = tempfile.NamedTemporaryFile()
        outfile.write( """digraph ros {
    //size="11,8";
    //size="100,40";
    //clusterrank=global;
      node [color=gainsboro, style=filled];
      ranksep = 2.0;
      compound=true;

    """)
        colors = ['red', 'blue', 'green', 'yellow', 'gold', 'orange','chocolate', 'gray44', 'deeppink', 'black']
        # create the legend
        color_palate = pkg_characterists.get_color_palate()
        if False and color_palate:
            outfile.write(' subgraph cluster__legend { style=bold; color=black; label = "Color Legend"; ')
            for type in color_palate:
                text_color="black"
                bg_color = color_palate[type]
                if bg_color == "black":
                    text_color = "white"  
                outfile.write('"%s" [color="%s", fontcolor="%s"];\n '%(type, bg_color, text_color))
            outfile.write('}\n')
        base_color = colors[random.randrange(0, len(colors))]
        try:
            stack_dir = roslib.stacks.get_stack_dir(stack)
        except  roslib.exceptions.ROSLibException, ex:
            stack_dir = "None"
        outfile.write(' subgraph cluster__%s { style=bold; color=%s; label = "%s \\n (%s)"; '%(stack, base_color, stack, stack_dir))
        internal, external = self.build_stack_list(stack)
        if not self.display_test_packages:
            internal = set([p for p in internal if not p.startswith("test_")])
            for s in external:
                external[s] = set([p for p in external[s] if not p.startswith("test_")])


        for pkg in internal:
            outfile.write(' "%s" ;'%pkg)
        for s in external:
            try:
                stack_dir = roslib.stacks.get_stack_dir(s)
            except  roslib.exceptions.ROSLibException, ex:
                stack_dir = "None"
            outfile.write(' subgraph cluster__%s_%s { style=bold; color=%s; label = "Stack: %s \\n (%s)"; '%(stack, s, base_color, s, stack_dir))
            for p in external[s]:
                outfile.write(' "%s.%s.%s" [ label = "%s"];'%(stack, s, p, p))
            outfile.write('}\n')
        outfile.write('}\n')

        external_deps_connected = set()
        for pkg in internal:
            deps = self.get_deps1(pkg)
            node_args = []
            ##Coloring
            color = pkg_characterists.get_color(pkg)
            node_args.append("color=%s"%color)
            if color == 'black':
                node_args.append("fontcolor=white")

            notes = pkg_characterists.get_review_notes(pkg)
            if len(notes) > 0:
              node_args.append('label="%s\\n(%s)"' % (pkg, notes))

            if pkg in internal:
                outfile.write('  "%s" [%s];\n'%(pkg, ', '.join(node_args)))




            ## Edges
            for dep in deps:
                if not self.verbose and dep in (self.get_internal_child_deps(pkg)):# & (internal | self.dict_to_set(external))): 
                    #print "Failed to find", dep, "in ", self.get_internal_child_deps(pkg)
                    continue

                if dep in (internal | self.dict_to_set(external)): #Draw edges to all dependencies
                    local_stack = self.get_stack_of(pkg)
                    dependent_stack = self.get_stack_of(dep)
                    #if local_stack not in args or not local_stack:
                    #    continue
                    if  dependent_stack == local_stack:
                        outfile.write( '  "%s" -> "%s";\n' % (pkg, dep))
                    elif dependent_stack:
                        intermediate = "%s.%s.%s"%(local_stack, dependent_stack, dep)
                        outfile.write( '  "%s" -> "%s"[color="blue", style="dashed"];\n' % (pkg, intermediate))
        #	outfile.write('}\n')

        if False:
            rank = self.build_rank(internal)
            print rank
            for key in rank:
                if len(rank[key]) > 1:
                    outfile.write('{ rank = same;')    
                    print "key", key
                    for pkg_rank in rank[key]:
                        #if pkg_rank in rank.keys():
                        outfile.write(' "%s" ;'%pkg_rank)
                    outfile.write('}\n')

            outfile.write( '}\n')
            outfile.flush() # write to disk, but don't delete 

            #shutil.copyfile(outfile.name, "NO#COMMIT.gv")

        
        try:
            output_filename = "stack_%s.%s"%(stack, type)
            print "Generating output %s"%output_filename
            subprocess.check_call(["dot", "-T%s"%type, outfile.name, "-o", output_filename])
            print "%s generated"%output_filename
        except subprocess.CalledProcessError:
            print >> sys.stderr, "failed to generate %s"%output_filename

        return output_filename

    def generate_composite(self, stacks, type, pkg_characterists, display_image = True):
        stack_files = {}
        if display_image:
            for s in stacks:
                stack_files[s] = self.generate_stack(s, type, pkg_characterists)

        print "Generating Graphviz Intermediate"
        outfile = tempfile.NamedTemporaryFile()
        outfile.write( """digraph ros {
    //size="11,8";
    //size="100,40";
    //clusterrank=global;
      node [color=gainsboro, style=filled, shape=box];
      ranksep = 2.0;
      compound=true;

    """)
        colors = ['red', 'blue', 'green', 'yellow', 'gold', 'orange','chocolate', 'gray44', 'deeppink', 'black']
        # create the legend
        color_palate = pkg_characterists.get_color_palate()
        if False and color_palate:
            outfile.write(' subgraph cluster__legend { style=bold; color=black; label = "Color Legend"; ')
            for type in color_palate:
                text_color="black"
                bg_color = color_palate[type]
                if bg_color == "black":
                    text_color = "white"  
                outfile.write('"%s" [color="%s", fontcolor="%s"];\n '%(type, bg_color, text_color))
            outfile.write('}\n')
        #base_color = colors[random.randrange(0, len(colors))]
        #try:
        #    stack_dir = roslib.stacks.get_stack_dir(stack)
        #except  roslib.exceptions.ROSLibException, ex:
        #    stack_dir = "None"
        
        if False:
            outfile.write(' subgraph cluster__%s { style=bold; color=%s; label = "%s \\n (%s)"; '%(stack, base_color, stack, stack_dir))
            internal, external = self.build_stack_list(stack)
            for pkg in internal:
                outfile.write(' "%s" ;'%pkg)
            for s in external:
                try:
                    stack_dir = roslib.stacks.get_stack_dir(s)
                except  roslib.exceptions.ROSLibException, ex:
                    stack_dir = "None"
                outfile.write(' subgraph cluster__%s_%s { style=bold; color=%s; label = "Stack: %s \\n (%s)"; '%(stack, s, base_color, s, stack_dir))
                for p in external[s]:
                    outfile.write(' "%s.%s.%s" [ label = "%s"];'%(stack, s, p, p))
                outfile.write('}\n')
            outfile.write('}\n')

        for stack in stacks:
            #deps = self.get_deps1(pkg)
            deps = roslib.rospack.rosstack_depends_1(stack)
            node_args = []


            if stack in stack_files and display_image:
                node_args.append('image="%s"'%stack_files[stack])
            ##Coloring
            #color = pkg_characterists.get_color(pkg)
            #node_args.append("color=%s"%color)
            #if color == 'black':
            #    node_args.append("fontcolor=white")

            #notes = pkg_characterists.get_review_notes(pkg)
            #if len(notes) > 0:
            #  node_args.append('label="%s\\n(%s)"' % (pkg, notes))

            #if pkg in all_pkgs:
            #    outfile.write('  "%s" [%s];\n'%(pkg, ', '.join(node_args)))
            outfile.write('  "%s" [%s];\n'%(stack, ', '.join(node_args)))




            ## Edges
            for dep in deps:
                if not self.verbose and dep in self.get_child_stack_deps(stack): 
                    #print "Failed to find", dep, "in ", self.get_child_stack_deps(stack)
                    continue
                if dep in stacks:
                    outfile.write( '  "%s" -> "%s";\n' % (stack, dep))
                if False:#dep in all_pkgs_plus_1: #Draw edges to all dependencies
                    local_stack = self.get_stack_of(pkg)
                    dependent_stack = self.get_stack_of(dep)
                    #if local_stack not in args or not local_stack:
                    #    continue
                    if  dependent_stack == local_stack:
                        outfile.write( '  "%s" -> "%s";\n' % (pkg, dep))
                    elif dependent_stack:
                        intermediate = "%s.%s.%s"%(local_stack, dependent_stack, dep)
                        outfile.write( '  "%s" -> "%s"[color="blue", style="dashed"];\n' % (pkg, intermediate))
        #	outfile.write('}\n')



        outfile.write( '}\n')
        outfile.flush() # write to disk, but don't delete 

        try:
            output_filename = "%s_deps.%s"%("composite", type)
            print "Generating output %s"%output_filename
            subprocess.check_call(["dot", "-T%s"%type, outfile.name, "-o", output_filename])
            print "%s generated"%output_filename
        except subprocess.CalledProcessError:
            print >> sys.stderr, "failed to generate %s"%output_filename

        return output_filename


def vdmain():
    parser = OptionParser(usage="usage: %prog [options]", prog='rxdeps')
    #parser.add_option("-r", "--rosmake", dest="rosmake", default=False,
    #                  action="store_true", help="color by rosmakeall results")
    parser.add_option("-s", "--review", dest="review_status", default=False,
                      action="store_true", help="color by review status")
    parser.add_option("--size", dest="size_by_deps", default=False,
                      action="store_true", help="whether to size by number of depends on 1")
    parser.add_option("-l", "--license", dest="license", default=False,
                      action="store_true", help="color by license type")
    parser.add_option("-v", dest="verbose", default=False,
                      action="store_true", help="don't deduplicate dependencies")
    parser.add_option("--one", dest="target1", default=False,
                      action="store_true", help="only draw one away from target")
    parser.add_option("-q", "--quiet", dest="quiet", default=False,
                      action="store_true", help="quiet (remove links to common packages)")
    parser.add_option("--hide_single", dest="hide", default=False,
                      action="store_true", help="hide (remove packages without links)")
    parser.add_option("--rank", dest="rank", default=False,
                      action="store_true", help="layer by maximum dependency depth")
    parser.add_option("--cluster", dest="cluster", default=False,
                      action="store_true", help="group by main subdir")
    parser.add_option("--color", metavar="FILENAME",
                      dest="color_file", default=None, 
                      type="string", help="use color file") 
    parser.add_option("-o", metavar="FILENAME",
                      dest="output_filename", default=None, 
                      type="string", help="output_filename") 
    parser.add_option("--graphviz-output", metavar="FILENAME",
                      dest="graphviz_output_filename", default=None, 
                      type="string", help="Save the intermediate output to this filename.") 
    parser.add_option("--target", metavar="PKG_NAMES_LIST,COMMA_SEPERATED",
                      dest="targets", default='', 
                      type="string", help="target packages")
    parser.add_option("--stack", metavar="STACK_NAMES_LIST,COMMA_SEPERATED",
                      dest="stacks", default='', 
                      type="string", help="target stacks")
    parser.add_option("--exclude", metavar="PKG_NAMES_LIST,COMMA_SEPERATED",
                      dest="exclude", default='', 
                      type="string", help="exclude packages")
    parser.add_option("--message", metavar="full_message_name",
                      dest="message", default='', 
                      type="string", help="target_message")
    parser.add_option("-T", metavar="File Type",
                      dest="output_type", default="png", 
                      type="string", help="output file type") 
    parser.add_option("--no-stack-details",
                      dest="display_image", default=True, 
                      action="store_false", help="Do Not display stack details")
    parser.add_option("--new",
                      dest="use_new_version", default=False, 
                      action="store_true", help="Use the new version")
    


    options, args = parser.parse_args()
    if options.exclude:
        exclude = options.exclude.split(',')
    else:
        exclude = []
    if options.targets:
        targets = options.targets.split(',')
        all_pkgs = roslib.packages.list_pkgs()
        invalidtarget = [t for t in targets if t not in all_pkgs]
        if invalidtarget:
            parser.error("Invalid packages set as targets, %s"%invalidtarget)
    else:
        targets = []

    if options.stacks:
        stacks = options.stacks.split(',')
    else:
        stacks = []
    if options.quiet:
        exclude.extend(['roscpp','std_msgs', 'rospy', 'std_srvs', 'robot_msgs', 'robot_srvs', 'rosconsole', 'tf'])
        
    pkg_characterists = PackageCharacteristics()
    if options.review_status:
        pkg_characterists.set_color_by("review")
    elif options.license:
        pkg_characterists.set_color_by("license")
    elif options.color_file:
        pkg_characterists.set_color_by("file", options.color_file)
        

    if False:
        if options.rosmake:
            print "Coloring by rosmakeall results"
            color_dict = get_rosmakeall_color()
            color_palate = rosmakeall_color_map

    if options.output_filename:
        output_filename = os.path.realpath(options.output_filename)
    else:
        output_filename = "deps.pdf"
        
    helper = HelperMethods()
    helper.verbose = options.verbose
    helper.display_test_packages = not options.quiet

    all_stacks = roslib.stacks.list_stacks()
    invalid_args = set([stack for stack in args if stack not in all_stacks])
    if invalid_args:
        parser.error("Invalid stacks passed as arguments %s"%invalid_args)
        
    if not args and options.use_new_version:
        helper.generate_composite(roslib.stacks.list_stacks(), options.output_type, pkg_characterists, options.display_image)
    elif options.use_new_version:
        helper.generate_composite(args,  options.output_type, pkg_characterists, options.display_image)

    all_pkgs = set(targets)
    args = set(args)
    args.update([helper.get_stack_of(p) for p in targets])
    if not args and options.cluster:
        parser.error("Cluster option requires stacks as arguments or --target options")
    for s in args:
        all_pkgs.update(helper.get_packages_of(s))
    all_pkgs_plus_1 = set()
    for p in all_pkgs:
        all_pkgs_plus_1.update(helper.get_deps1(p))
    
    
    print "Generating Graphviz Intermediate"
    outfile = tempfile.NamedTemporaryFile()
    outfile.write( """digraph ros {
  //size="11,8";
  size="100,40";
//clusterrank=global;
  node [color=gainsboro, style=filled];
  ranksep = 2.0;
  compound=true;
  
""")
    colors = ['red', 'blue', 'green', 'yellow', 'gold', 'orange','chocolate', 'gray44', 'deeppink', 'black']
    # create the legend
    color_palate = pkg_characterists.get_color_palate()
    if color_palate:
        outfile.write(' subgraph cluster__legend { style=bold; color=black; label = "Color Legend"; ')
        for type in color_palate:
            text_color="black"
            bg_color = color_palate[type]
            if bg_color == "black":
                text_color = "white"  
            outfile.write('"%s" [color="%s", fontcolor="%s"];\n '%(type, bg_color, text_color))
        outfile.write('}\n')
    for cl in args:#roslib.stacks.list_stacks():
        if options.cluster:
            base_color = colors[random.randrange(0, len(colors))]
            try:
                stack_dir = roslib.stacks.get_stack_dir(cl)
            except  roslib.exceptions.ROSLibException, ex:
                stack_dir = "None"
            outfile.write(' subgraph cluster__%s { style=bold; color=%s; label = "%s \\n (%s)"; '%(cl, base_color, cl, stack_dir))
            internal, external = helper.build_stack_list(cl)
            for pkg in internal:
                outfile.write(' "%s" ;'%pkg)
            for s in external:
                try:
                    stack_dir = roslib.stacks.get_stack_dir(s)
                except  roslib.exceptions.ROSLibException, ex:
                    stack_dir = "None"
                outfile.write(' subgraph cluster__%s_%s { style=bold; color=%s; label = "Stack: %s \\n (%s)"; '%(cl, s, base_color, s, stack_dir))
                for p in external[s]:
                    outfile.write(' "%s.%s.%s" [ label = "%s"];'%(cl, s, p, p))
                outfile.write('}\n')
            outfile.write('}\n')

    external_deps_connected = set()
    for pkg in all_pkgs:
        deps = helper.get_deps1(pkg)
        node_args = []
        ##Coloring
        color = pkg_characterists.get_color(pkg)
        node_args.append("color=%s"%color)
        if color == 'black':
            node_args.append("fontcolor=white")

        ## Shape
        if pkg in exclude:
            node_args.append("shape=box")

        # Size
        if options.size_by_deps:
            num_deps = len(roslib.rospack.rospack_depends_on(pkg))
            node_args.append("width=%s,height=%s"%(.75 + .1 * sqrt(num_deps), .5 + .1* sqrt(num_deps)))

        ##Perimeter 
        if pkg in targets:
            node_args.append('peripheries=6, style=bold')
        elif pkg in exclude: 
            node_args.append('peripheries=3, style=dashed')

        notes = pkg_characterists.get_review_notes(pkg)
        if len(notes) > 0:
          node_args.append('label="%s\\n(%s)"' % (pkg, notes))

        if options.hide:
           if len(roslib.rospack.rospack_depends_on(pkg)) == 0 and len(helper.get_deps(pkg)) == 0: #TODO: This is pretty slow
              print "Hiding unattached package %s"%pkg
              continue

        if pkg in all_pkgs:
            outfile.write('  "%s" [%s];\n'%(pkg, ', '.join(node_args)))




        ## Edges
        for dep in deps:
            if not options.verbose and dep in helper.get_internal_child_deps(pkg): 
                continue
            if dep in all_pkgs_plus_1: #Draw edges to all dependencies
                local_stack = helper.get_stack_of(pkg)
                dependent_stack = helper.get_stack_of(dep)
                if local_stack not in args or not local_stack:
                    continue
                if not (options.cluster and not dependent_stack == local_stack):
                    outfile.write( '  "%s" -> "%s";\n' % (pkg, dep))
                elif options.cluster and dependent_stack:
                    intermediate = "%s.%s.%s"%(local_stack, dependent_stack, dep)
                    deduplication = "%s.%s"%(local_stack, dependent_stack)
                    outfile.write( '  "%s" -> "%s"[color="blue", style="dashed"];\n' % (pkg, intermediate))
                    if not deduplication in external_deps_connected and dependent_stack in args:
                        outfile.write( '  "%s" -> "%s"[color="red", style="dashed", ltail=cluster__%s_%s, lhead=cluster__%s];\n' % (intermediate, dep, local_stack, dependent_stack, dependent_stack))
                        external_deps_connected.add(deduplication)
    #	outfile.write('}\n')
    ## rank
    if options.rank:	
        rank = helper.build_rank(all_pkgs)
        for key in rank:
            if len(rank[key]) > 1:
                outfile.write('{ rank = same;')    
                for pkg_rank in rank[key]:
                    if pkg_rank in all_pkgs:
                        outfile.write(' "%s" ;'%pkg_rank)
                outfile.write('}\n')
    outfile.write( '}\n')
    outfile.flush() # write to disk, but don't delete 

    if options.graphviz_output_filename:
        graphviz_output_filename = os.path.realpath(options.graphviz_output_filename)
        shutil.copyfile(outfile.name, graphviz_output_filename)

    try:
        print "Generating output %s"%output_filename
        # Check version, make postscript if too old to make pdf
        args = ["dot", "-V"]
        vstr = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[1]
        v = distutils.version.StrictVersion('2.16')
        r = re.compile(".*version ([^ ]*).*")
        print vstr
        m = r.search(vstr)
        if not m or not m.group(1):
          print 'Warning: failed to determine your version of dot.  Assuming v2.16'
        else:
          version = distutils.version.StrictVersion(m.group(1))
          print 'Detected dot version %s' % (version)
        if version > distutils.version.StrictVersion('2.8'):
          subprocess.check_call(["dot", "-Tpdf", outfile.name, "-o", output_filename])
          print "%s generated"%output_filename
        else:
          orig = output_filename
          if output_filename.lower().endswith('.pdf'):
            output_filename = output_filename[:-3]+'ps'
          else:
            print "ERROR", output_filename
          subprocess.check_call(["dot", "-Tps2", outfile.name, "-o", output_filename])
          print "%s generated"%output_filename
          
          print "Trying to create %s..."%orig
          subprocess.check_call(["ps2pdf", output_filename, orig])
          print "%s generated"%orig
    except subprocess.CalledProcessError:
        print >> sys.stderr, "failed to generate %s"%output_filename

if __name__ == '__main__':
    random.seed()
    vdmain()
