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

import os

import rosdep.base_rosdep
from rosdep.linux_helpers import *
import roslib.os_detect

###### Macports SPECIALIZATION #########################
def port_detect(p):
    cmd = ['port', 'installed', p]
    pop = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (std_out, std_err) = pop.communicate()
    
    return (std_out.count("(active)") > 0)

class Osx(roslib.os_detect.Osx, rosdep.base_rosdep.RosdepBaseOS):
    def __init__(self):
        self.installers = {}
        self.installers['pip'] = rosdep.installers.PipInstaller
        self.installers['macports'] = rosdep.installers.MacportsInstaller
        self.installers['default'] = rosdep.installers.MacportsInstaller
        self.installers['source'] = rosdep.installers.SourceInstaller

    def strip_detected_packages(self, packages):
        return [p for p in packages if not port_detect(p)] 

    def generate_package_install_command(self, packages, default_yes):        
        if len(packages) < 1:
            return "#No packages to install"
        return "#Packages\nsudo port install " + ' '.join(packages)

###### END Osx SPECIALIZATION ########################
