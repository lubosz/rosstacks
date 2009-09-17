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
Master/Slave XML-RPC Wrappers

Simplifies usage of master/slave APIs by automatically inserting caller ID
and also adding python dictionary accessors on the parameter server.
"""
    
import rospy.core
import rospy.exceptions
import rospy.masterslave
import rospy.names
import rospy.paramserver

class NodeProxy(object):
    """
    Convenience wrapper for ROSNode API and XML-RPC implementation.
    Eliminates the need to pass in callerId as the first argument.
    """

    def __init__(self, uri):
        super(NodeProxy, self).__init__()
        self.target = rospy.core.xmlrpcapi(uri)
        
    def __getattr__(self, key): #forward api calls to target
        f = getattr(self.target, key)
        remappings = rospy.masterslave.ROSHandler.remappings(key)
        def wrappedF(*args, **kwds):
            args = [rospy.names.get_caller_id(),]+list(args)
            #print "Remap indicies", remappings
            for i in remappings:
                i = i + 1 #callerId does not count
                #print "Remap %s => %s"%(args[i], rospy.names.resolve_name(args[i]))
                args[i] = rospy.names.resolve_name(args[i])
            return f(*args, **kwds)
        return wrappedF
    
class MasterProxy(NodeProxy):
    """
    Convenience wrapper for ROS master API and XML-RPC implementation.
    Shares same methods as ROSMasterHandler due to method-forwarding.
    Also remaps parameter server for python dictionary-like access, e.g.::
    
      master[key] = value

    """

    def __init__(self, uri):
        """
        Constructor for wrapping a remote master instance.
        @param uri: XML-RPC URI of master
        @type uri: str
        """
        super(MasterProxy, self).__init__(uri)

    def __getattr__(self, key): #forward api calls to target
        #Same as NodeProxy, but asks ROSMasterHandler instead
        f = getattr(self.target, key)
        remappings = rospy.masterslave.ROSMasterHandler.remappings(key)
        def wrappedF(*args, **kwds):
            args = [rospy.names.get_caller_id(),]+list(args)
            #print "Remap indicies", remappings
            for i in remappings:
                i = i + 1 #callerId does not count
                #print "Remap %s => %s"%(args[i], rospy.names.resolve_name(args[i]))
                args[i] = rospy.names.resolve_name(args[i])
            return f(*args, **kwds)
        return wrappedF

    def __getitem__(self, key):
        """
        Fetch item from parameter server and subscribe to future updates so that
        values can be cached.
        @param key: parameter key
        @type key: str
        """
        #NOTE: remapping occurs here!
        resolved_key = rospy.names.resolve_name(key)
        if 1: # disable param cache
            code, msg, value = self.target.getParam(rospy.names.get_caller_id(), resolved_key)
            if code != 1: #unwrap value with Python semantics
                raise KeyError(key)
            return value

        try:
            # check for value in the parameter server cache
            return rospy.paramserver.get_param_server_cache().get(resolved_key)
        except KeyError:
            # first access, make call to parameter server
            code, msg, value = self.target.subscribeParam(rospy.names.get_caller_id(), rospy.core.get_node_uri(), resolved_key)
            if code != 1: #unwrap value with Python semantics
                raise KeyError(key)
            # set the value in the cache so that it's marked as subscribed
            rospy.paramserver.get_param_server_cache().set(resolved_key, value)
            return value
        
    def __setitem__(self, key, val):
        """
        Set parameter value on Parameter Server
        @param key: parameter key
        @type key: str
        @param val: parameter value
        @type val: XMLRPC legal value
        """
        self.target.setParam(rospy.names.get_caller_id(), rospy.names.resolve_name(key), val)
        
    def search_param(self, key):
        """
        Search for a parameter matching key on the parameter server
        @return: found key or None if search did not succeed
        @rtype: str
        @raise ROSException: if parameter server reports an error
        """
        code, msg, val = self.target.searchParam(rospy.names.get_caller_id(), rospy.names.remap_name(key))
        if code == 1:
            return val
        elif code == -1:
            return None
        else:
            raise rospy.exceptions.ROSException("cannot search for parameter parameter: %s"%msg)
        
    def __delitem__(self, key):
        """
        Delete parameter key from the parameter server.
        @raise ROSException: if parameter server reports an error
        """
        resolved_key = rospy.names.resolve_name(key)
        code, msg, _ = self.target.deleteParam(rospy.names.get_caller_id(), resolved_key)
        if code != 1:
            raise rospy.exceptions.ROSException("cannot delete parameter: %s"%msg)
        elif 0: #disable parameter cache
            # set the value in the cache so that it's marked as subscribed
            rospy.paramserver.get_param_server_cache().delete(resolved_key)

    def __contains__(self, key):
        """
        Check if parameter is set on Parameter Server
        @param key: parameter key
        @type key: str
        @raise ROSException: if parameter server reports an error
        """        
        code, msg, value = self.target.hasParam(rospy.names.get_caller_id(), rospy.names.resolve_name(key))
        if code != 1:
            raise rospy.exceptions.ROSException("cannot check parameter on server: %s"%msg)
        return value
        
    def __iter__(self):
        """
        @raise ROSException: if parameter server reports an error
        """
        code, msg, value = self.target.getParamNames(rospy.names.get_caller_id())
        if code == 1:
            return value.__iter__()
        else:
            raise rospy.exceptions.ROSException("cannot retrieve parameter names: %s"%msg)
