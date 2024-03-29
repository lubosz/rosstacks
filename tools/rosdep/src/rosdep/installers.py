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

import subprocess
import roslib.os_detect
import os 
import shutil
import urllib
import urllib2
import tarfile
import tempfile
import yaml
import hashlib

import rosdep.base_rosdep
import rosdep.core


class InstallerAPI():
    def __init__(self, arg_dict):
        """
        Set all required fields here 
        """
        raise NotImplementedError("Base class __init__")
    
    def check_presence(self):
        """
        This script will return true if the rosdep is found on the
        system, otherwise false.
        """
        raise NotImplementedError("Base class check_presence")

    def generate_package_install_command(self, default_yes, execute = True, display = True):
        """
        If execute is True, install the rosdep, else if display = True
        print the script it would have run to install.
        @param default_yes  Pass through -y or equivilant to package manager
        """
        raise NotImplementedError("Base class generate_package_install_command")

    def get_depends(self): 
        """ 
        Return the dependencies, only necessary if the package manager
        doesn't handle the dependencies.
        """
        return [] # Default return empty list


def fetch_file(url, md5sum=None):
    contents = ''
    try:
        fh= urllib2.urlopen(url)
        contents = fh.read()
        filehash =  hashlib.md5(contents).hexdigest()
        if md5sum and filehash != md5sum:
            raise rosdep.core.RosdepException( "md5sum didn't match for %s.  Expected %s got %s"%(url, md5sum, filehash))
    except urllib2.URLError as ex:
        raise rosdep.core.RosdepException(str(ex))

    return contents    

def assert_file_hash(filename, md5sum):
    md5 = hashlib.md5()
    with open(filename,'rb') as f: 
        for chunk in iter(lambda: f.read(8192), ''): 
            md5.update(chunk)
    if md5sum != md5.hexdigest():
        raise rosdep.core.RosdepException("md5sum check on %s failed.  Expected %s got %s"%(filename, md5sum, md5.hexdigest()))

def get_file_hash(filename):
    md5 = hashlib.md5()
    with open(filename,'rb') as f: 
        for chunk in iter(lambda: f.read(8192), ''): 
            md5.update(chunk)
    return md5.hexdigest()

class SourceInstaller(InstallerAPI):
    def __init__(self, arg_dict):
        self.url = arg_dict.get("uri")
        if not self.url:
            raise rosdep.core.RosdepException("uri required for source rosdeps") 
        self.alt_url = arg_dict.get("alternate-uri")
        self.md5sum = arg_dict.get("md5sum")

        self.manifest = None

        #TODO add md5sum verification
        if "ROSDEP_DEBUG" in os.environ:
            print "Downloading manifest %s"%self.url

        error = ''

        contents = ''
        # fetch the manifest
        try:
            contents = fetch_file(self.url, self.md5sum)
        except rosdep.core.RosdepException as ex:
            if "ROSDEP_DEBUG" in os.environ:
                print "Failed to fetch file %s for reason %s"%(self.url, ex)

        if not contents: # try the backup url
            if not self.alt_url:
                raise rosdep.core.RosdepException("Failed to load a rdmanifest from %s, and no alternate URI given"%(self.url))
            try:
                contents = fetch_file(self.alt_url, self.md5sum)
            except rosdep.core.RosdepException as ex:
                if "ROSDEP_DEBUG" in os.environ:
                    print "Failed to fetch file %s for reason %s"%(self.alt_url, ex)

        if not contents:
            raise rosdep.core.RosdepException("Failed to load a rdmanifest from either %s or %s"%(self.url, self.alt_url))
                
        try:
            self.manifest = yaml.load(contents)
        except yaml.scanner.ScannerError as ex:
            raise rosdep.core.RosdepException("Failed to parse yaml in %s:  Error: %s"%(contents, ex))
                
        if "ROSDEP_DEBUG" in os.environ:
            print "Downloaded manifest:\n{{{%s\n}}}\n"%self.manifest
        
        self.install_command = self.manifest.get("install-script", "#!/bin/bash\n#no install-script specificd")
        self.check_presence_command = self.manifest.get("check-presence-script", "#!/bin/bash\n#no check-presence-script\nfalse")

        self.exec_path = self.manifest.get("exec-path", ".")

        self.depends = self.manifest.get("depends", [])

        self.tarball = self.manifest.get("uri")
        if not self.tarball:
            raise rosdep.core.RosdepException("uri required for source rosdeps") 
        self.alternate_tarball = self.manifest.get("alternate-uri")
        self.tarball_md5sum = self.manifest.get("md5sum")
        

    def check_presence(self):

        return rosdep.core.create_tempfile_from_string_and_execute(self.check_presence_command)

    def generate_package_install_command(self, default_yes = False, execute = True, display =True):
        tempdir = tempfile.mkdtemp()
        success = False

        if "ROSDEP_DEBUG" in os.environ:
            print "Fetching %s"%self.tarball
        f = urllib.urlretrieve(self.tarball)
        filename = f[0]
        if self.tarball_md5sum:
            hash1 = get_file_hash(filename)
            if self.tarball_md5sum != hash1:
                #try backup tarball if it is defined
                if self.alternate_tarball:
                    f = urllib.urlretrieve(self.alternate_tarball)
                    filename = f[0]
                    hash2 = get_file_hash(filename)
                    if self.tarball_md5sum != hash2:
                        raise rosdep.core.RosdepException("md5sum check on %s and %s failed.  Expected %s got %s and %s"%(self.tarball, self.alternate_tarball, self.tarball_md5sum, hash1, hash2))
                else:
                    raise rosdep.core.RosdepException("md5sum check on %s failed.  Expected %s got %s "%(self.tarball, self.tarball_md5sum, hash1))
            
        else:
            if "ROSDEP_DEBUG" in os.environ:
                print "No md5sum defined for tarball, not checking."
            
        try:
            tarf = tarfile.open(filename)
            tarf.extractall(tempdir)

            if execute:
                if "ROSDEP_DEBUG" in os.environ:
                    print "Running installation script"
                success = rosdep.core.create_tempfile_from_string_and_execute(self.install_command, os.path.join(tempdir, self.exec_path))
            elif display:
                print "Would have executed\n{{{%s\n}}}"%self.install_command
            
        finally:
            shutil.rmtree(tempdir)
            os.remove(f[0])

        if success:
            if "ROSDEP_DEBUG" in os.environ:
                print "successfully executed script"
            return True
        return False

    def get_depends(self): 
        #todo verify type before returning
        return self.depends
        

        

class AptInstaller(InstallerAPI):
    """ 
    An implementation of the InstallerAPI for use on debian style
    systems.
    """
    def __init__(self, arg_dict):
        packages = arg_dict.get("packages", "")
        if type(packages) == type("string"):
            packages = packages.split()

        self.packages = packages


    def get_packages_to_install(self):
         return list(set(self.packages) - set(self.dpkg_detect(self.packages)))


    def check_presence(self):
        return len(self.get_packages_to_install()) == 0


    def generate_package_install_command(self, default_yes = False, execute = True, display = True):
        script = '!#/bin/bash\n#no script'
        packages_to_install = self.get_packages_to_install()
        if not packages_to_install:
            script =  "#!/bin/bash\n#No Packages to install"
        if default_yes:
            script = "#!/bin/bash\n#Packages %s\nsudo apt-get install -y "%packages_to_install + ' '.join(packages_to_install)        
        else:
            script =  "#!/bin/bash\n#Packages %s\nsudo apt-get install "%packages_to_install + ' '.join(packages_to_install)

        if execute:
            return rosdep.core.create_tempfile_from_string_and_execute(script)
        elif display:
            print "To install packages: %s would have executed script\n{{{\n%s\n}}}"%(packages_to_install, script)
        return False


    def dpkg_detect(self, pkgs):
        """ 
        Given a list of package, return the list of installed packages.
        """
        ret_list = []
        # this is mainly a hack to support version locking for eigen.
        # we strip version-locking syntax, e.g. libeigen3-dev=3.0.1-*.
        # our query does not do the validation on the version itself.
        version_lock_map = {}
        for p in pkgs:
            if '=' in p:
                version_lock_map[p.split('=')[0]] = p
            else:
                version_lock_map[p] = p
        cmd = ['dpkg-query', '-W', '-f=\'${Package} ${Status}\n\'']
        cmd.extend(version_lock_map.keys())

        pop = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (std_out, std_err) = pop.communicate()
        std_out = std_out.replace('\'','')
        pkg_list = std_out.split('\n')
        for pkg in pkg_list:
            pkg_row = pkg.split()
            if len(pkg_row) == 4 and (pkg_row[3] =='installed'):
                ret_list.append( pkg_row[0])
        return [version_lock_map[r] for r in ret_list]
        

class YumInstaller(InstallerAPI):
    """ 
    An implementation of the InstallerAPI for use on yum/fedora style
    systems.
    """
    def __init__(self, arg_dict):
        packages = arg_dict.get("packages", "")
        if type(packages) == type("string"):
            packages = packages.split()

        self.packages = packages


    def get_packages_to_install(self):
         return list(set(self.packages) - set(self.dpkg_detect(self.packages)))


    def check_presence(self):
       return len(self.get_packages_to_install()) == 0


    def generate_package_install_command(self, default_yes = False, execute = True, display = True):
        script = '!#/bin/bash\n#no script'
        packages_to_install = self.get_packages_to_install()
        if not packages_to_install:
            script = "#!/bin/bash\n#No Packages to install"
        elif default_yes:
            script = "#!/bin/bash\n#Packages %s\nsudo yum install -y "%packages_to_install + ' '.join(packages_to_install)        
        else:
            script = "#!/bin/bash\n#Packages %s\nsudo yum install "%packages_to_install + ' '.join(packages_to_install)

        if execute:
            return rosdep.core.create_tempfile_from_string_and_execute(script)
        elif display:
            print "To install packages: %s would have executed script\n{{{\n%s\n}}}"%(packages_to_install, script)
        return False


    def dpkg_detect(self, pkgs):
        """ 
        Given a list of packages, return the list of installed packages.
        """
        ret_list = []
        #cmd = ['rpm', '-q', '--qf ""']  # suppress output for installed packages
        cmd = ['rpm', '-q', '--qf', '%{NAME}\n']  # output: "pkg_name" for installed, error text for not installed packages
        cmd.extend(pkgs)
        
        pop = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (std_out, std_err) = pop.communicate()
        out_lines = std_out.split('\n')
        for line in out_lines:
            # if there is no space, it's not an error text -> it's installed
            if line and ' ' not in line:
                ret_list.append(line)
        return ret_list
        

class PipInstaller(InstallerAPI):
    """ 
    An implementation of the InstallerAPI for use on debian style
    systems.
    """
    def __init__(self, arg_dict):
        packages = arg_dict.get("packages", "")
        if type(packages) == type("string"):
            packages = packages.split()

        self.depends = arg_dict.get("depends", [])
        self.packages = packages

    def get_packages_to_install(self):
         return list(set(self.packages) - set(self.pip_detect(self.packages)))

    def check_presence(self):
        return len(self.get_packages_to_install()) == 0

    def get_depends(self):
        #todo verify type before returning
        return self.depends

    def generate_package_install_command(self, default_yes = False, execute = True, display = True):
        packages_to_install = self.get_packages_to_install()
        script = '!#/bin/bash\n#no script'
        if not packages_to_install:
            script =  "#!/bin/bash\n#No PIP Packages to install"
        #if default_yes:
        #    script = "#!/bin/bash\n#Packages %s\nsudo apt-get install -U "%packages_to_install + ' '.join(packages_to_install)        
        #else:
        script =  "#!/bin/bash\n#Packages %s\nsudo pip install -U "%packages_to_install + ' '.join(packages_to_install)

        if execute:
            return rosdep.core.create_tempfile_from_string_and_execute(script)
        elif display:
            print "To install packages: %s would have executed script\n{{{\n%s\n}}}"%(packages_to_install, script)
        return False

    def pip_detect(self, pkgs):
        """ 
        Given a list of package, return the list of installed packages.
        """
        ret_list = []
        cmd = ['pip', 'freeze']
        pop = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (std_out, std_err) = pop.communicate()
        pkg_list = std_out.split('\n')
        for pkg in pkg_list:
            pkg_row = pkg.split("==")
            print pkg_row
            if pkg_row[0] in pkgs:
                ret_list.append( pkg_row[0])
        return ret_list

class PacmanInstaller(InstallerAPI):
    """
    An implementation of the InstallerAPI for use on pacman systems
    """
    def __init__(self,arg_dict):
        packages = arg_dict.get("packages","")
        if type(packages) == type("string"):
            packages = packages.split()

        self.packages = packages

    def get_packages_to_install(self):
         return list(set(self.packages) - set(self.pacman_detect(self.packages)))

    def check_presence(self):
        return len(self.get_packages_to_install()) == 0

    def generate_package_install_command(self, default_yes = False, execute = True, display = True):
        script = '!#/bin/bash\n#no script'
        packages_to_install = self.get_packages_to_install()
        if not packages_to_install:
            script =  "#!/bin/bash\n#No Packages to install"
        script = "#!/bin/bash\n#Packages %s\nsudo pacman -S "%packages_to_install + ' '.join(packages_to_install)

        if execute:
            return rosdep.core.create_tempfile_from_string_and_execute(script)
        elif display:
            print ("To install packages: %s would have executed script\n{{{\n%s\n}}}"%(packages_to_install, script))
        return False

    def pacman_detect(self, pkgs):
        """
        Given a list of package, return the list of installed packages.
        """
        ret_list = []
        cmd = ['pacman','-Q']
        cmd.extend(pkgs)
        pop = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (std_out, std_err) = pop.communicate()
        pkg_list = std_out.split('\n')
        for pkg in pkg_list:
            pkg_row = pkg.split()
            if len(pkg_row) == 2 and pkg_row[0] in pkgs:
                ret_list.append( pkg_row[0])
        return ret_list

class MacportsInstaller(InstallerAPI):
    """ 
    An implementation of the InstallerAPI for use on macports systems.
    """
    def __init__(self, arg_dict):
        packages = arg_dict.get("packages", "")
        if type(packages) == type("string"):
            packages = packages.split()

        self.packages = packages

    def get_packages_to_install(self):
         return list(set(self.packages) - set(self.port_detect(self.packages)))

    def check_presence(self):
        return len(self.get_packages_to_install()) == 0

    def generate_package_install_command(self, default_yes = False, execute = True, display = True):
        script = '!#/bin/bash\n#no script'
        packages_to_install = self.get_packages_to_install()
        if not packages_to_install:
            script =  "#!/bin/bash\n#No Packages to install"
        script = "#!/bin/bash\n#Packages %s\nsudo port install "%packages_to_install + ' '.join(packages_to_install)        

        if execute:
            return rosdep.core.create_tempfile_from_string_and_execute(script)
        elif display:
            print "To install packages: %s would have executed script\n{{{\n%s\n}}}"%(packages_to_install, script)
        return False

    def port_detect(self, pkgs):
        """ 
        Given a list of package, return the list of installed packages.
        """
        ret_list = []
        cmd = ['port', 'installed']
        cmd.extend(pkgs)
        pop = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (std_out, std_err) = pop.communicate()
        pkg_list = std_out.split('\n')
        for pkg in pkg_list:
            pkg_row = pkg.split()
            if len(pkg_row) == 3 and pkg_row[0] in pkgs and pkg_row[2] =='(active)':
                ret_list.append( pkg_row[0])
        return ret_list
