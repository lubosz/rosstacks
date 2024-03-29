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
# $Author$

"""
Common ros script utilities, such as methods convenience methods for
creating master xmlrpc proxies and executing rospack. This library
is relatively immature and much of the functionality here will
likely be moved elsewhere as the API solidifies.
"""

import itertools
import os
import re
import string
import subprocess
import sys

import roslib.names 
import roslib.network

## caller ID for master calls where caller ID is not vital
_GLOBAL_CALLER_ID = '/script'

_is_interactive = False
def set_interactive(interactive):
    """
    General API for a script specifying that it is being run in an
    interactive environment. Many libraries may wish to change their
    behavior based on being interactive (e.g. disabling signal
    handlers on Ctrl-C).

    @param interactive: True if current script is being run in an interactive shell
    @type  interactive: bool
    """
    global _is_interactive
    _is_interactive = interactive

def is_interactive():
    """
    General API for a script specifying that it is being run in an
    interactive environment. Many libraries may wish to change their
    behavior based on being interactive (e.g. disabling signal
    handlers on Ctrl-C).

    @return: True if interactive flag has been set
    @rtype: bool
    """
    return _is_interactive

def myargv(argv=None):
    """
    Remove ROS remapping arguments from sys.argv arguments.
    @return: copy of sys.argv with ROS remapping arguments removed
    @rtype: [str]
    """
    if argv is None:
        argv = sys.argv
    return [a for a in argv if not roslib.names.REMAP in a]

def script_resolve_name(script_name, name):
    """
    Name resolver for scripts. Supports ROS_NAMESPACE.  Does not
    support remapping arguments.
    @param name: name to resolve
    @type  name: str
    @param script_name: name of script. script_name must not
    contain a namespace.
    @type  script_name: str
    @return: resolved name
    @rtype: str
    """
    if not name: #empty string resolves to namespace
        return roslib.names.get_ros_namespace()
    #Check for global name: /foo/name resolves to /foo/name
    if roslib.names.is_global(name):
        return name
    #Check for private name: ~name resolves to /caller_id/name
    elif roslib.names.is_private(name):
        return ns_join(roslib.names.make_caller_id(script_name), name[1:])
    return roslib.names.get_ros_namespace() + name

import warnings
def deprecated(func):
    """This is a decorator which can be used to mark functions
    as deprecated. It will result in a warning being emmitted
    when the function is used."""
    def newFunc(*args, **kwargs):
        warnings.warn("Call to deprecated function %s." % func.__name__,
                      category=DeprecationWarning, stacklevel=2)
        return func(*args, **kwargs)
    newFunc.__name__ = func.__name__
    newFunc.__doc__ = func.__doc__
    newFunc.__dict__.update(func.__dict__)
    return newFunc

@deprecated
def get_master():
    """
    Get an XMLRPC handle to the Master. It is recommended to use the
    `rosgraph.masterapi` library instead, as it provides many
    conveniences.
    
    @return: XML-RPC proxy to ROS master
    @rtype: xmlrpclib.ServerProxy
    @raises ValueError if master URI is invalid
    """
    try:
        import xmlrpc.client as xmlrpcclient  #Python 3.x
    except ImportError:
        import xmlrpclib as xmlrpcclient #Python 2.x
    
    # changed this to not look as sys args and remove dependency on roslib.rosenv for cleaner cleanup
    uri = os.environ['ROS_MASTER_URI']
    # #1730 validate URL for better error messages
    try:
        roslib.network.parse_http_host_and_port(uri)
    except ValueError:
        raise ValueError("invalid master URI: %s"%uri)
    return xmlrpcclient.ServerProxy(uri)

@deprecated
def get_param_server():
    """
    @return: ServerProxy XML-RPC proxy to ROS parameter server
    @rtype: xmlrpclib.ServerProxy
    """
    return get_master()
