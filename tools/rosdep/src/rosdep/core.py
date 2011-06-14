#!/usr/bin/env python
# Copyright (c) 2009, Willow Garage, Inc.
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
#     * Neither the name of the Willow Garage, Inc. nor the names of its
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

# Author Tully Foote/tfoote@willowgarage.com

#"""
#Library and command-line tool for calculating rosdeps.
#"""

from __future__ import with_statement

import roslib.rospack
import roslib.stacks
import roslib.manifest
import roslib.os_detect
import os
import sys
import subprocess
import types
import tempfile
import yaml
import time

  
import rosdep.base_rosdep
import rosdep.debian as debian
import rosdep.opensuse as opensuse
import rosdep.redhat as redhat
import rosdep.gentoo as gentoo
import rosdep.macports as macports
import rosdep.arch as arch
import rosdep.cygwin as cygwin
import rosdep.freebsd as freebsd


yaml.add_constructor(
    u'tag:yaml.org,2002:float',
    yaml.constructor.Constructor.construct_yaml_str)

class YamlCache:
    """ A class into which to load the yaml files for quicker access
    from repeated lookups """

    def __init__(self, os_name, os_version):
        self.os_name = os_name
        self.os_version = os_version
        self._yaml_cache = {}
        self._rosstack_depends_cache = {}
        self._expanded_rosdeps = {}
        # Cache the list of packages for quicker access
        self.cached_ros_package_list = roslib.packages.ROSPackages()
        
    def get_yaml(self, path):
        """ Get the yaml from a specific path.  Caching accelerated"""
        if path in self._yaml_cache:
            return self._yaml_cache[path]
        
        #print "parsing path", path
        if os.path.exists(path):
            try:
                f = open(path)
                yaml_text = f.read()
                f.close()
                self._yaml_cache[path] = yaml.load(yaml_text)
                return self._yaml_cache[path]

            except yaml.YAMLError, exc:
                print >> sys.stderr, "Failed parsing yaml while processing %s\n"%path, exc
                #sys.exit(1)        # not a breaking error
        self._yaml_cache[path] = {}
        return {}

    def get_rosstack_depends(self, stack):
        """ A caching query to get rosstack_depends(stack) """
        if stack in self._rosstack_depends_cache:
            return self._rosstack_depends_cache[stack]
        
        self._rosstack_depends_cache[stack] = roslib.rospack.rosstack_depends(stack)
        return self._rosstack_depends_cache[stack]
    
    def get_specific_rosdeps(self, path):
        """ Get the rosdeps for the active os"""
        if path in self._expanded_rosdeps:
            return self._expanded_rosdeps[path]

        yaml_dict = self.get_yaml(path)
        expanded_rosdeps = {}
        if not yaml_dict: # prevent exception below if rosdep.yaml file was empty #2762
            return expanded_rosdeps
        for key in yaml_dict:
            rosdep_entry = self.get_os_from_yaml(key, yaml_dict[key], path)
            if not rosdep_entry: # if no match don't do anything
                continue # matches for loop
            print "adding entry", rosdep_entry
            expanded_rosdeps[key] = rosdep_entry
        self._expanded_rosdeps[path] = expanded_rosdeps
        return expanded_rosdeps

    def get_os_from_yaml(self, rosdep_name, yaml_map, source_path): #source_path is for debugging where errors come from
        """
        @return The os (and version specific if required ) local package name
        """
        print "yaml map is", yaml_map
        # See if the version for this OS exists
        if self.os_name in yaml_map:
            return self.get_version_from_yaml(rosdep_name, yaml_map[self.os_name], source_path)
        else:
            #print >> sys.stderr, "failed to resolve a rule for rosdep(%s) on OS(%s)"%(rosdep_name, self.os_name)
            return False

    def get_version_from_yaml(self, rosdep_name, os_specific, source_path):
        """
        Helper function for get_os_from_yaml to parse if version is required.  
        @return The os (and version specific if required) local package name
        """
        print "os_specific ", os_specific
        if type(os_specific) == type("String"):
            return os_specific
        elif self.os_version in os_specific.keys(): # it must be a map of versions
            print "Found version", os_specific[self.os_version]
            return os_specific[self.os_version]
        elif type(os_specific) == type({}): # detected a map
            for k in os_specific.keys():
                if not k in rosdep.installers.reserved_installer_keys:
                    return False # If the map doesn't have a valid installer key reject it, it must be a version key
            # return the map 
            return os_specific
        else:
            return False                    



def create_tempfile_from_string_and_execute(string_script, path= tempfile.gettempdir()):
    result = 1

    try:
        fh = tempfile.NamedTemporaryFile('w', delete=False)
        fh.write(string_script)
        fh.close()
        print "Executing script below with cwd=%s\n{{{\n%s\n}}}\n"%(path, string_script)
        try:
            os.chmod(fh.name, 0700)
            result = subprocess.call(fh.name, cwd=path)
        except OSError, ex:
            print "Execution failed with OSError:", ex
        #print "Return code ", result

    finally:
        if os.path.exists(fh.name):
            os.remove(fh.name)
    return result == 0



class RosdepException(Exception):
    pass

class RosdepLookupPackage:
    """
    This is a class for interacting with rosdeps for a specific package.  It will
    load all rosdep.yaml files in the current configuration at
    startup.  It has accessors to allow lookups into the rosdep.yaml
    from rosdep name and returns the string from the yaml file for the
    appropriate OS/version.

    It uses the OSIndex class for OS detection.
    """
    
    def __init__(self, os_name, os_version, package, yaml_cache):
        """ Read all rosdep.yaml files found at the root of stacks in
        the current environment and build them into a map."""
        self.os_name = os_name
        self.os_version = os_version
        self.rosdep_map = {}
        self.rosdep_source = {}
        self.package = package
        self.yaml_cache = yaml_cache
        ## Find all rosdep.yamls here and load them into a map


        if not package:
            raise RosdepException("RosdepLookupPackage requires a package argument")
        self._load_for_package(package, yaml_cache.cached_ros_package_list)
        
        

    def _load_for_package(self, package, ros_package_proxy):
        """ Load into local structures the information for this
        specific package 

        Called in constructor. """

        try:
            rosdep_dependent_packages = ros_package_proxy.depends([package])[package]
            #print "package", package, "needs", rosdep_dependent_packages
        except KeyError, ex:
            print "Depends Failed on package", ex
            print " The errors was in ",  ros_package_proxy.depends([package])
            rosdep_dependent_packages = []
        #print "Dependents of", package, rosdep_dependent_packages
        rosdep_dependent_packages.append(package)


        paths = set()
        for p in rosdep_dependent_packages:
            stack = None
            try:
                stack = roslib.stacks.stack_of(p)
            except roslib.packages.InvalidROSPkgException, ex:
                print >> sys.stderr, "Failed to find stack for package [%s]"%p
                pass
            if stack:
                try:
                    paths.add( os.path.join(roslib.stacks.get_stack_dir(stack), "rosdep.yaml"))
                    if "ROSDEP_DEBUG" in os.environ:
                        print "loading rosdeps from", os.path.join(roslib.stacks.get_stack_dir(stack), "rosdep.yaml")
                except AttributeError, ex:
                    print "Stack [%s] could not be found"%(stack)
                for s in self.yaml_cache.get_rosstack_depends(stack):
                    try:
                        paths.add( os.path.join(roslib.stacks.get_stack_dir(s), "rosdep.yaml"))
                    except AttributeError, ex:
                        print "Stack [%s] dependency of [%s] could not be found"%(s, stack)
                        
            else:
                try:
                    paths.add( os.path.join(roslib.packages.get_pkg_dir(p), "rosdep.yaml"))
                    if "ROSDEP_DEBUG" in os.environ:
                        print "Package fallback, no parent stack found for package %s: loading rosdeps from"%p, os.path.join(roslib.packages.get_pkg_dir(p), "rosdep.yaml")
                except roslib.packages.InvalidROSPkgException, ex:
                    print >> sys.stderr, "Failed to load rosdep.yaml for package [%s]:%s"%(p, ex)
                    pass
        for path in paths:
            self._insert_map(self.parse_yaml(path), path)
            if "ROSDEP_DEBUG" in os.environ:
                print "rosdep loading from file: %s got"%path, self.parse_yaml(path)
        #print "built map", self.rosdep_map

        # Override with ros_home/rosdep.yaml if present
        ros_home = roslib.rosenv.get_ros_home()
        path = os.path.join(ros_home, "rosdep.yaml")
        self._insert_map(self.parse_yaml(path), path, override=True)


    def _insert_map(self, yaml_dict, source_path, override=False):
        """ Insert the current map into the full dictionary"""
        for key in yaml_dict:
            rosdep_entry = yaml_dict[key]
            if not rosdep_entry: # if no match don't do anything
                continue # matches for loop
            if key in self.rosdep_source:


                if override:
                    print >>sys.stderr, "ROSDEP_OVERRIDE: %s being overridden with %s from %s"%(key, yaml_dict[key], source_path)
                    self.rosdep_source[key].append("Overriding with "+source_path)
                    self.rosdep_map[key] = rosdep_entry
                else:
                    if self.rosdep_map[key] == rosdep_entry:
                        self.rosdep_source[key].append(source_path)
                        #print >> sys.stderr, "DEBUG: Same key found for %s: %s"%(key, self.rosdep_map[key])
                        pass
                    else:
                        cache_p = self.yaml_cache.get_os_from_yaml(key, yaml_dict[key], source_path)
                        raise RosdepException("""QUITTING: due to conflicting rosdep definitions, please resolve this conflict.
Rules for %s do not match:
\t%s [%s]
\t%s [%s]"""%(key, self.rosdep_map[key], self.rosdep_source[key][0], rosdep_entry, source_path))
                        
            else:
                self.rosdep_source[key] = [source_path]
                self.rosdep_map[key] = rosdep_entry
                #print "rosdep_map[%s] = %s"%(key, self.rosdep_map[key])


    def parse_yaml(self, path):
        """ Return the parsed yaml for this path.  Useing cached value
        in yaml_cache"""
        return self.yaml_cache.get_specific_rosdeps(path)
        


    def lookup_rosdep(self, rosdep):
        """ Lookup the OS specific packages or script from the
        prebuilt maps."""

        if rosdep in self.rosdep_map:
            return self.rosdep_map[rosdep]
        else:
            print >> sys.stderr, "Failed to find rosdep %s for package %s on OS:%s version:%s"%(rosdep, self.package, self.os_name, self.os_version)
            return False
                

    def get_sources(self, rosdep):
        if rosdep in self.rosdep_source:
            return self.rosdep_source[rosdep]
        else:
            return []




 

class Rosdep:
    def __init__(self, packages, command = "rosdep", robust = False):
        os_list = [debian.RosdepTestOS(), debian.Debian(), debian.Ubuntu(), debian.Mint(), opensuse.OpenSuse(), redhat.Fedora(), redhat.Rhel(), arch.Arch(), macports.Macports(), gentoo.Gentoo(), cygwin.Cygwin(), freebsd.FreeBSD()]
        # Make sure that these classes are all well formed.  
        for o in os_list:
            if not isinstance(o, rosdep.base_rosdep.RosdepBaseOS):
                raise RosdepException("Class [%s] not derived from RosdepBaseOS"%o.__class__.__name__)
        # Detect the OS on which this program is running. 
        self.osi = roslib.os_detect.OSDetect(os_list)
        self.yc = YamlCache(self.osi.get_name(), self.osi.get_version())
        self.packages = packages
        self.rosdeps = roslib.packages.rosdeps_of(packages)
        rp = roslib.packages.ROSPackages()
        self.rosdeps = rp.rosdeps(packages)
        self.robust = robust
        


    def get_rosdep0(self, package):
        m = roslib.manifest.load_manifest(package)
        return [d.name for d in m.rosdeps]
            

    def get_packages_and_scripts(self):
        if len(self.packages) == 0:
            return ([], [])
        native_packages = []
        scripts = []
        failed_rosdeps = []
        start_time = time.time()
        if "ROSDEP_DEBUG" in os.environ:
            print "Generating package list and scripts for %d rosdeps.  This may take a few seconds..."%len(self.packages)
        for p in self.packages:
            rdlp = RosdepLookupPackage(self.osi.get_name(), self.osi.get_version(), p, self.yc)
            for r in self.rosdeps[p]:
                #print "rosdep", r
                specific = rdlp.lookup_rosdep(r)
                #print "specific", specific
                if specific:
                    if type(specific) == type({}):
                        if "ROSDEP_DEBUG" in os.environ:
                            print "%s NEW TYPE, SKIPPING"%r
                    elif len(specific.split('\n')) == 1:
                        for pk in specific.split():
                            native_packages.append(pk)
                    else:
                        scripts.append(specific)
                else:
                    failed_rosdeps.append(r)

        if len(failed_rosdeps) > 0:
            if not self.robust:
                raise RosdepException("ABORTING: Rosdeps %s could not be resolved"%failed_rosdeps)
            else:
                print >> sys.stderr, "WARNING: Rosdeps %s could not be resolved"%failed_rosdeps

        time_delta = (time.time() - start_time)
        if "ROSDEP_DEBUG" in os.environ:
            print "Done loading rosdeps in %f seconds, averaging %f per rosdep."%(time_delta, time_delta/len(self.packages))

        return (list(set(native_packages)), list(set(scripts)))

    def get_native_packages(self):
        return get_packages_and_scripts()[0]

    def generate_script(self, include_duplicates=False, default_yes = False):
        native_packages, scripts = self.get_packages_and_scripts()
        undetected = native_packages if include_duplicates else \
            self.osi.get_os().strip_detected_packages(native_packages)
        return "#!/bin/bash\nset -o errexit\n" + self.osi.get_os().generate_package_install_command(undetected, default_yes) + \
            "\n".join(["\n%s"%sc for sc in scripts])
        
    def check(self):
        native_packages = []
        scripts = []
        try:
            native_packages, scripts = self.get_packages_and_scripts()
        except RosdepException, e:
            print >> sys.stderr, e
            pass
        undetected = self.osi.get_os().strip_detected_packages(native_packages)
        return_str = ""
        return_str_scripts = ""
        if len(undetected) > 0:
            return_str += "Did not detect packages: %s\n"%undetected
        if len(scripts) > 0:
            return_str_scripts += "The following scripts were not tested:\n"
        for s in scripts:
            return_str_scripts += s + '\n'
        return return_str, return_str_scripts

    def what_needs(self, rosdep_args):
        packages = []
        for p in roslib.packages.list_pkgs():
            rosdeps_needed = self.get_rosdep0(p)
            matches = [r for r in rosdep_args if r in rosdeps_needed]
            for r in matches:
                packages.append(p)
                
        return packages

    def install(self, include_duplicates, default_yes):
        success = self.NEW_install(default_yes)
        if not success:
            return "Rosdep install failed"
        return None
        

    def install_rosdep(self, rosdep_name, rdlp, default_yes):
        if "ROSDEP_DEBUG" in os.environ:
            print "Processing rosdep %s"%rosdep_name
        rosdep_dict = rdlp.lookup_rosdep(rosdep_name)
        if not rosdep_dict:
            return False
        mode = 'default'
        installer = None
        if type(rosdep_dict) != type({}):
            if "ROSDEP_DEBUG" in os.environ:
                print "OLD TYPE BACKWARDS COMPATABILITY MODE", rosdep_dict
                
            installer = self.osi.get_os().get_installer('default')
            packages = rosdep_dict.split()
            arg_map = {}
            arg_map['packages'] = packages
            rosdep_dict = {} #override old values
            rosdep_dict['default'] = arg_map 

        else:
            modes = rosdep_dict.keys()
            if len(modes) != 1:
                print "ERRROR: only one mode allowed, rosdep %s has mode %s"%(rosdep_name, modes)
                return False
            else:
                mode = modes[0]
                if "ROSDEP_DEBUG" in os.environ:
                    print "rosdep mode:", mode
                installer = self.osi.get_os().get_installer(mode)
        
        if not installer:
            raise RosdepException( "Rosdep failed to get an installer for mode %s"%mode)
            
        my_installer = installer(rosdep_dict[mode])


        # Check if it's already there
        print "Checking if rosdep %s is present"%rosdep_name
        if my_installer.check_presence():
            print "%s already installed"%rosdep_name
            return True
        else:
            print "%s not installed"%rosdep_name
        
        # Check for dependencies
        dependencies = my_installer.get_depends()
        for d in dependencies:
            print "Installing dependent rosdep %s"%d
            self.install_rosdep(d, rdlp, default_yes)
            


        result = my_installer.generate_package_install_command(default_yes)
        if result:
            print "successfully installed %s"%rosdep_name
        else:
            print "unsuccessfully installed %s"%rosdep_name
        return result

    def NEW_install(self, default_yes):
        failure = False
        for p in self.packages:
            rdlp = RosdepLookupPackage(self.osi.get_name(), self.osi.get_version(), p, self.yc)
            for r in self.rosdeps[p]:
                if not self.install_rosdep(r, rdlp, default_yes):
                    failure = True
                    if not self.robust:
                        return False
        return not failure
                    
    def depdb(self, packages):
        output = "Rosdep dependencies for operating system %s version %s "%(self.osi.get_name(), self.osi.get_version())
        for p in packages:
            output += "\nPACKAGE: %s\n"%p
            rdlp = RosdepLookupPackage(self.osi.get_name(), self.osi.get_version(), p, self.yc)
            rosdep_map = rdlp.rosdep_map
            for k,v in rosdep_map.iteritems():
                output = output + "<<<< %s -> %s >>>>\n"%(k, v)
        return output

    def where_defined(self, rosdeps):
        output = ""
        locations = {}

        for r in rosdeps:
            locations[r] = set()

        path = os.path.join(roslib.rosenv.get_ros_home(), "rosdep.yaml")
        rosdep_dict = self.yc.get_specific_rosdeps(path)
        for r in rosdeps:
            if r in rosdep_dict:
                locations[r].add("Override:"+path)
            

        for p in roslib.packages.list_pkgs():
            path = os.path.join(roslib.packages.get_pkg_dir(p), "rosdep.yaml")
            rosdep_dict = self.yc.get_specific_rosdeps(path)
            for r in rosdeps:
                if r in rosdep_dict:
                    addendum = ""
                    if roslib.stacks.stack_of(p):
                        addendum = "<<Unused due to package '%s' being in a stack.]]"%p
                    locations[r].add(">>" + path + addendum)
            

        for s in roslib.stacks.list_stacks():
            path = os.path.join(roslib.stacks.get_stack_dir(s), "rosdep.yaml")
            rosdep_dict = self.yc.get_specific_rosdeps(path)
            for r in rosdeps:
                if r in rosdep_dict:
                    locations[r].add(path)
            
        for rd in locations:
            output += "%s defined in %s"%(rd, locations[rd])
        return output

