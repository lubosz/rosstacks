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

import os
import sys

import roslib.manifest
import roslib.packages
import roslib.rosenv
import roslib.scriptutil
import roslib.substitution_args

import roslaunch.depends

from roswtf.model import WtfWarning

class WtfException(Exception): pass

## Context object for storing information about the state of the ROS
## system we are attempting to debug
class WtfContext(object):
    __slots__ = ['pkg', 'pkg_dir', 'pkgs',
                 'manifest_file', 'manifest',
                 'env', 'ros_root', 'ros_package_path', 'pythonpath',
                 'ros_master_uri',
                 'roslaunch_uris',
                 'ros_bindeps_path',
                 'ros_boost_root',
                 'launch_files',
                 'launch_file_deps',
                 'launch_file_missing_deps',
                 'system_state',
                 'service_providers',
                 'topics', 'services',
                 'nodes', 'uri_node_map',
                 'expected_edges',
                 'actual_edges',
                 'unconnected_subscriptions',
                 'use_sim_time',
                 'warnings', 'errors']
    
    def __init__(self):
        # main package we are running 
        self.pkg = None
        self.pkg_dir = None
        # - list of all packages involved in this check
        self.pkgs = []

        # manifest location of package that we are running 
        self.manifest_file = None
        # manifest of package that we are running 
        self.manifest = None

        # environment variables 
        self.env = {}

        # provide these for convenience
        self.ros_root = None
        self.ros_package_path = None
        self.pythonpath = None
        self.ros_bindeps_path = None        
        self.ros_boost_root = None        
        
        # launch file that is being run
        self.launch_files = None
        self.launch_file_deps = None
        self.launch_file_missing_deps = None        
        
        # online state
        self.roslaunch_uris = None 
        self.system_state = None #master.getSystemState
        self.topics = None
        self.services = None
        self.service_providers = None #names of nodes with services
        self.nodes = None
        self.uri_node_map = {}
        self.expected_edges = None
        self.actual_edges = None
        self.unconnected_subscriptions = None
        self.use_sim_time = None
        
        # warnings that we have collected so far
        self.warnings = []
        # errors that we have collected so far
        self.errors = []

    ## @return dict: dictionary representation of context, which is
    ## useful for producing error messages
    def as_dictionary(self):
        return dict((s, getattr(self, s)) for s in self.__slots__)

    @staticmethod
    ## @param roslaunch_file str: roslaunch_file to check
    def from_roslaunch(roslaunch_files, env=os.environ):
        ctx = WtfContext()
        ctx.launch_files = roslaunch_files
        _load_roslaunch(ctx, roslaunch_files)
        # ctx.pkg initialized by _load_roslaunch
        _load_pkg(ctx, ctx.pkg)
        _load_env(ctx, env)
        return ctx
        
    @staticmethod
    ## @throws WtfException: if context state cannot be initialized
    def from_package(pkg, env=os.environ):
        ctx = WtfContext()
        _load_pkg(ctx, pkg)
        _load_env(ctx, env)
        return ctx

    @staticmethod
    ## @throws WtfException: if context state cannot be initialized
    def from_env(env=os.environ):
        ctx = WtfContext()
        _load_env(ctx, env)
        return ctx
    
## utility for initializing WtfContext state from roslaunch file
def _load_roslaunch(ctx, roslaunch_files):
    try:
        base_pkg, file_deps, missing = roslaunch.depends.roslaunch_deps(roslaunch_files)
        ctx.pkg = base_pkg
        ctx.launch_file_deps = file_deps
        ctx.launch_file_missing_deps = missing
    except roslib.substitution_args.SubstitutionException, se:
        raise WtfException("Cannot load roslaunch file(s): "+str(se))
    except roslaunch.depends.RoslaunchDepsException, e:
        raise WtfException(str(e))

## utility for initializing WtfContext state
## @throws WtfException: if context state cannot be initialized
def _load_pkg(ctx, pkg):
    ctx.pkg = pkg
    ctx.pkgs = [pkg] + roslib.scriptutil.rospack_depends(pkg)
    try:
        ctx.pkg_dir = roslib.packages.get_pkg_dir(pkg)
        ctx.manifest_file = roslib.manifest.manifest_file(pkg)
        ctx.manifest_file = roslib.manifest.parse_file(ctx.manifest_file)        
    except roslib.packages.InvalidROSPkgException:
        raise WtfException("Cannot locate manifest file for package [%s]"%pkg)

## utility for initializing WtfContext state
## @throws WtfException: if context state cannot be initialized
def _load_env(ctx,env):
    ctx.env = env
    try:
        ctx.ros_root = env[roslib.rosenv.ROS_ROOT]
    except KeyError:
        raise WtfException("ROS_ROOT is not set")
    ctx.ros_package_path = env.get(roslib.rosenv.ROS_PACKAGE_PATH, None)
    ctx.pythonpath = env.get('PYTHONPATH', None)
    ctx.ros_master_uri = env.get(roslib.rosenv.ROS_MASTER_URI, None)
    ctx.ros_bindeps_path = env.get(roslib.rosenv.ROS_BINDEPS_PATH, None)
    ctx.ros_boost_root = env.get(roslib.rosenv.ROS_BOOST_ROOT, None)    
    
