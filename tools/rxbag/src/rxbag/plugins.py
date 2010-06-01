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

"""
Loads plugins.
"""

PKG = 'rxbag'
import roslib; roslib.load_manifest(PKG)

import sys
import traceback

import roslib.rospack

def load_plugins():
    """
    Finds all rxbag plugins.
    
    @return: a list of plugins
    @rtype:  list of functions which return tuples of (MessageView, TimelineRenderer, list of: message type or '*')
    """
    plugins = []

    to_check = roslib.rospack.rospack_depends_on_1('rxbag')

    for pkg in to_check:
        manifest_file = roslib.manifest.manifest_file(pkg, True)
        manifest      = roslib.manifest.parse_file(manifest_file)

        plugin_module_names = manifest.get_export('rxbag', 'plugin')

        if not plugin_module_names:
            continue
        elif len(plugin_module_names) != 1:
            print >> sys.stderr, "Cannot load plugin [%s]: invalid 'plugin' attribute" % (pkg)
            continue
        plugin_module_name = plugin_module_names[0]

        try:
            # Load that package's namespace
            roslib.load_manifest(pkg)
    
            # Import specified plugin module
            plugin_module = __import__(plugin_module_name)
            for sub_module in plugin_module_name.split('.')[1:]:
                plugin_module = getattr(plugin_module, sub_module)
    
            # Retrieve the function
            plugins_func = None
            try:
                plugins_func = getattr(plugin_module, 'get_rxbag_plugins')
            except AttributeError: pass
    
            if plugins_func:
                plugins.extend(plugins_func())
            else:
                print >> sys.stderr, "Cannot load plugin [%s]: no 'get_rxbag_plugins' attribute" % (plugin_module_name)

        except Exception, ex:
            print >> sys.stderr, "Unable to load plugin [%s] from package [%s]:\n%s" % (plugin_module_name, pkg, traceback.format_exc())

    return plugins
