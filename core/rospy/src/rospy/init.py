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
"""
ROSPY initialization 

This is mainly routines for initializing the master or slave based on
the OS environment.
"""

import os
import logging
import time

import roslib.rosenv

import rospy.core 
import rospy.masterslave 
import rospy.msnode 
import rospy.msproxy 
import rospy.names
import rospy.tcpros 

DEFAULT_NODE_PORT = 0 #bind to any open port
DEFAULT_MASTER_PORT=11311 #default port for master's to bind to

_node = None #global var for ros init and easy interpreter access 
## Retrieve NodeProxy for slave node running on this machine
##
## @return rospy.msproxy.NodeProxy: slave node API handle
def get_node_proxy():
    return _node

###################################################
# rospy module lower-level initialization

_local_master_uri = None
## @return str: URI of master instance if a master is running within this Python interpreter
def get_local_master_uri():
    return _local_master_uri

## Start a local master instance
def start_master(environ, port=DEFAULT_MASTER_PORT):
    global _local_master_uri
    master = rospy.msnode.ROSNode(rospy.core.MASTER_NAME, port, rospy.masterslave.ROSMasterHandler())
    master.start()
    while not master.uri and not rospy.core.is_shutdown():
        time.sleep(0.0001) #poll for init
    _local_master_uri = master.uri
    return master

## URI of master that will be used if master is not otherwise configured.
def default_master_uri():
    return 'http://localhost:%s/'%DEFAULT_MASTER_PORT

## Subroutine for start_node()
def _sub_start_node(environ, name, master_uri=None, port=DEFAULT_NODE_PORT):
    if not master_uri:
        master_uri = roslib.rosenv.get_master_uri()
    if not master_uri:
        master_uri = default_master_uri()

    name = rospy.names.resolve_name(name) #remapping occurs here
    handler = rospy.masterslave.ROSHandler(name, master_uri)
    node = rospy.msnode.ROSNode(name, port, handler)
    node.start()
    while not node.uri and not rospy.core.is_shutdown():
        time.sleep(0.00001) #poll for XMLRPC init
    logging.getLogger("rospy.init").info("ROS Slave URI: [%s]", node.uri)

    while not handler._is_registered() and not rospy.core.is_shutdown():
        time.sleep(0.1) #poll for master registration
    logging.getLogger("rospy.init").info("registered with master")

    return rospy.msproxy.NodeProxy(node.uri)

## Load ROS slave node, initialize from environment variables
## @param environ dict: environment variables
## @param name str: override ROS_NODE: name of slave node
## @param master_uri str: override ROS_MASTER_URI: XMlRPC URI of central ROS server
## @param port int: override ROS_PORT: port of slave xml-rpc node
## @return rospy.msproxy.NodeProxy: node proxy instance
def start_node(environ, name, master_uri=None, port=None):
    global _node
    rospy.tcpros.init_tcpros()
    if _node is not None:
        raise Exception("Only one master/slave can be run per instance (multiple calls to start_master/start_node)")
    _node = _sub_start_node(environ, name, master_uri, port)
    return _node
    
