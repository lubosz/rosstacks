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

import roslib; roslib.load_manifest('roswtf')

import os
import socket
import sys
import traceback

import roslib.packages
import roslib.scriptutil
import rospy

def yaml_results(ctx):
    cd = ctx.as_dictionary()
    d = {}
    d['warnings'] = {}
    d['errors'] = {}
    wd = d['warnings']
    for warn in ctx.warnings:
        wd[warn.format_msg%cd] = warn.return_val
    ed = d['warnings']        
    for err in ctx.warnings:
        ed[err.format_msg%cd] = err.return_val
    import yaml
    print yaml.dump(d)

def print_results(ctx):
    if not ctx.warnings and not ctx.errors:
        print "No errors or warnings"
    else:
        if ctx.warnings:
            print "Found %s warning(s).\nWarnings are things that may be just fine, but are sometimes at fault\n"%len(ctx.warnings)
            for warn in ctx.warnings:
                print '\033[1mWARNING\033[0m', warn.msg
            print ''

        if ctx.errors:
            print "Found %s error(s).\n"%len(ctx.errors)        
            for e in ctx.errors:
                print '\033[31m\033[1mERROR\033[0m', e.msg
                #print "ERROR:", e.msg
    
def roswtf_main():
    from roswtf.context import WtfException
    try:
        _roswtf_main()
    except WtfException, e:
        print >> sys.stderr, e
        
def master_online():
    master = roslib.scriptutil.get_master()
    try:
        master.getPid('/roswtf')
        return master
    except socket.error:
        pass

def _roswtf_main():
    launch_files = names = None
    # performance optimization
    all_pkgs = roslib.packages.list_pkgs()

    import optparse
    parser = optparse.OptionParser(usage="usage: roswtf [launch file]")
    #TODO: --all-pkgs option
    options, args = parser.parse_args()
    if args:
        launch_files = args
        if 0:
            # disable names for now as don't have any rules yet
            launch_files = [a for a in args if os.path.isfile(a)]
            names = [a for a in args if not a in launch_files]
            names = [roslib.scriptutil.script_resolve_name('/roswtf', n) for n in names]
        
    from roswtf.context import WtfContext
    from roswtf.environment import wtf_check_environment, invalid_url
    from roswtf.graph import wtf_check_graph
    from roswtf.packages import wtf_check_packages
    from roswtf.roslaunchwtf import wtf_check_roslaunch_static, wtf_check_roslaunch_online
    
    import roswtf.plugins
    static_plugins, online_plugins = roswtf.plugins.load_plugins()

    all_warnings = []
    all_errors = []
    
    if launch_files:
        ctx = WtfContext.from_roslaunch(launch_files)
        #TODO: allow specifying multiple roslaunch files
    else:
        curr_package_dir, curr_package = roslib.packages.get_dir_pkg('.')
        if curr_package:
            print "Package:",curr_package
            ctx = WtfContext.from_package(curr_package)
            #TODO: load all .launch files in package
        else:
            print "No package in context"
            ctx = WtfContext.from_env()

    # static checks
    wtf_check_environment(ctx)
    wtf_check_packages(ctx)
    wtf_check_roslaunch_static(ctx)
    for p in static_plugins:
        p(ctx)

    print "="*80
    print "Static checks summary:\n"
    print_results(ctx)

    # Save static results and start afresh for online checks
    all_warnings.extend(ctx.warnings)
    all_errors.extend(ctx.errors)
    del ctx.warnings[:]
    del ctx.errors[:]    

    # test online
    print "="*80

    try:
        online_checks = False
        if not ctx.ros_master_uri or invalid_url(ctx.ros_master_uri):
            master = None
        else:
            master = roslib.scriptutil.get_master()
            master = master_online()
        if master is not None:
            online_checks = True
            print "Beginning tests of your ROS graph. These may take awhile..."
            
            # online checks
            wtf_check_graph(ctx, names=names)
        elif names:
            # TODO: need to rework this logic
            print "\nCannot communicate with master, unable to diagnose [%s]"%(', '.join(names))
            return
        else:
            print "\nCannot communicate with master, ignoring graph checks"
            return

        # spin up a roswtf node so we can subscribe to messages
        rospy.init_node('roswtf', anonymous=True)

        online_checks = True
        wtf_check_roslaunch_online(ctx)

        for p in online_plugins:
            online_checks = True
            p(ctx)

        if online_checks:
            # done
            print "\nOnline checks summary:\n"
            print_results(ctx)
            
    except Exception, e:
        traceback.print_exc()
        print >> sys.stderr, str(e)
        print "\nAborting checks, partial results summary:\n"
        print_results(ctx)

    #TODO: print results in YAML if run remotely
    #yaml_results(ctx)
