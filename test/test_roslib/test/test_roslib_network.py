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
import roslib; roslib.load_manifest('test_roslib')

import os
import struct
import sys
import unittest

import roslib.network
import rosunit

class MockSock(object):
  def __init__(self, data=''):
    self.data = data
  def recv(self):
    d = self.data
    self.data = ''
    return d
  def sendall(self, d):
    self.data = self.data + d
  def send(self, d):
    self.data = self.data + d
    return len(d)
    
    
class NetworkTest(unittest.TestCase):
  
  def test_encode_ros_handshake_header(self):
    from roslib.network import encode_ros_handshake_header
    d = {}
    self.assertEquals(struct.pack('<I', 0), encode_ros_handshake_header(d))
    s = "a=b"
    d['a'] = 'b'
    encoded = struct.pack('<I', len(s))+s
    self.assertEquals(struct.pack('<I', len(encoded))+encoded,
                      encode_ros_handshake_header({'a': 'b'}))
    d['c'] = 'd' 
    s = "c=d"
    encoded = encoded+struct.pack('<I', len(s))+s    
    self.assertEquals(struct.pack('<I', len(encoded))+encoded,
                      encode_ros_handshake_header(d))
    d['rawtype'] = '#line 1\nline 2\nline 3\nline\t4\r\r\n'
    s = "rawtype=#line 1\nline 2\nline 3\nline\t4\r\r\n"
    encoded = encoded+struct.pack('<I', len(s))+s        
    self.assertEquals(struct.pack('<I', len(encoded))+encoded,
                      encode_ros_handshake_header(d))
  
  def test_decode_ros_handshake_header(self):
    from roslib.network import decode_ros_handshake_header, ROSHandshakeException

    invalids = ["field1","",]
    # prepend field length
    invalids = [(struct.pack('<I', len(s)) + s) for s in invalids]
    # prepend message length
    invalids = [(struct.pack('<I', len(s)) + s) for s in invalids]
    
    # invalid message length prefix
    valid = "a=b"
    valid = struct.pack('<I', len(valid)) + valid
    invalids.append(struct.pack('<I', 123)+valid)
    # invalid field length prefix
    invalid = struct.pack('<I', 123)+'a=b'
    invalids.append(struct.pack("<I", len(invalid)) + invalid)
    
    for i in invalids:
      try:
        decode_ros_handshake_header(i)
        self.fail("should have failed: %s"%i)
      except ROSHandshakeException: pass
    
    self.assertEquals({}, decode_ros_handshake_header(struct.pack('<I', 0)))
    # single-field tests
    tests = [
      ("a=b", {'a': 'b'}),
      # whitespace in keys is ignored
      (" a =b", {'a': 'b'}),
      ('newlines=\n\n\n\n', {'newlines': '\n\n\n\n'}),
      ('equals=foo=bar=car', {'equals': 'foo=bar=car'}),
      ("spaces=one two three four",{'spaces': 'one two three four'}),
      ]
    for s, d in tests:
      # add in length fields
      s = struct.pack('<I', len(s)+4) + struct.pack('<I', len(s)) + s      
      self.assertEquals(d, decode_ros_handshake_header(s))
    
    # multi-field tests
    tests = [ {'a': 'b', 'c': 'd'},
              {'spaces': '    ', 'tabs': '\t\t\t\t', 'equals': '====='},
              ]
    for t in tests:
      s = ''
      for k, v in t.iteritems():
        f = "%s=%s"%(k, v)
        s += struct.pack('<I', len(f)) + f
      s = struct.pack('<I', len(s)) + s
      self.assertEquals(t, decode_ros_handshake_header(s))
      # make sure that decode ignores extra past header len
      self.assertEquals(t, decode_ros_handshake_header(s+s))      

  def test_parse_http_host_and_port(self):
    from roslib.network import parse_http_host_and_port
    invalid = ['', 'http://', 'http://localhost:bar', None]
    for t in invalid:
      try:
        parse_http_host_and_port(t)
        self.fail("should have failed: %s"%t)
      except ValueError:
        pass

    self.assertEquals(('localhost', 80), parse_http_host_and_port('http://localhost'))
    self.assertEquals(('localhost', 1234), parse_http_host_and_port('http://localhost:1234'))
    self.assertEquals(('localhost', 1), parse_http_host_and_port('http://localhost:1'))
    self.assertEquals(('willowgarage.com', 1), parse_http_host_and_port('http://willowgarage.com:1'))        

  def test_get_local_address(self):
    # mostly a tripwire test
    from roslib.network import get_local_address
    a = get_local_address()
    self.assert_(type(a) == str)
    self.assert_(a)

    # now test address override
    os.environ['ROS_IP'] = 'bar'
    self.assertEquals('bar', get_local_address())
    os.environ['ROS_HOSTNAME'] = 'foo'
    self.assertEquals('foo', get_local_address())

    try:
      real_argv = sys.argv[:]
      sys.argv = real_argv[:] + ['__ip:=1.2.3.4']
      self.assertEquals('1.2.3.4', get_local_address())
      sys.argv = real_argv[:] + ['__hostname:=bar']      
      self.assertEquals('bar', get_local_address())
    finally:
      sys.argv = real_argv
    
  def test_get_local_addresses(self):
    # mostly a tripwire test
    from roslib.network import get_local_addresses
    addrs = get_local_addresses()
    self.assert_(type(addrs) == list)
    self.assert_(len(addrs))
    for a in addrs:
      self.assert_(type(a) == str)

    # should be unaffected
    os.environ['ROS_IP'] = 'bar'
    self.assertEquals(addrs, get_local_addresses())    
    os.environ['ROS_HOSTNAME'] = 'foo'
    self.assertEquals(addrs, get_local_addresses())

  def test_get_bind_address(self):
    from roslib.network import get_bind_address
    self.assertEquals('0.0.0.0', get_bind_address('foo'))
    self.assertEquals('127.0.0.1', get_bind_address('localhost'))
    self.assertEquals('127.0.0.1', get_bind_address('127.0.1.1'))        

    # now test address override
    os.environ['ROS_IP'] = 'bar'
    self.assertEquals('0.0.0.0', get_bind_address())        
    self.assertEquals('0.0.0.0', get_bind_address('foo'))
    os.environ['ROS_IP'] = 'localhost'
    self.assertEquals('127.0.0.1', get_bind_address())    
    self.assertEquals('0.0.0.0', get_bind_address('foo')) 
    os.environ['ROS_HOSTNAME'] = 'bar'
    self.assertEquals('0.0.0.0', get_bind_address())    
    self.assertEquals('0.0.0.0', get_bind_address('foo'))    
    os.environ['ROS_HOSTNAME'] = 'localhost'
    self.assertEquals('127.0.0.1', get_bind_address())    
    self.assertEquals('0.0.0.0', get_bind_address('foo'))    

  def test_get_host_name(self):
    from roslib.network import get_host_name
    self.assertEquals(type(get_host_name()), str)
    
    os.environ['ROS_IP'] = 'foo'
    self.assertEquals('foo', get_host_name())
    os.environ['ROS_HOSTNAME'] = 'bar'
    self.assertEquals('bar', get_host_name())

    try:
      real_argv = sys.argv[:]
      sys.argv = real_argv[:] + ['__ip:=1.2.3.4']
      self.assertEquals('1.2.3.4', get_host_name())
      sys.argv = real_argv[:] + ['__hostname:=baz']      
      self.assertEquals('baz', get_host_name())
    finally:
      sys.argv = real_argv
    
  def test_create_local_xmlrpc_uri(self):
    from roslib.network import parse_http_host_and_port, create_local_xmlrpc_uri
    self.assertEquals(type(create_local_xmlrpc_uri(1234)), str)
    os.environ['ROS_HOSTNAME'] = 'localhost'    
    self.assertEquals(('localhost', 1234), parse_http_host_and_port(create_local_xmlrpc_uri(1234)))
    
  def setUp(self):
    self._ros_hostname = self._ros_ip = None
    if 'ROS_HOSTNAME' in os.environ:
      self._ros_hostname = os.environ['ROS_HOSTNAME']
      del os.environ['ROS_HOSTNAME']
    if 'ROS_IP' in os.environ:
      self._ros_ip = os.environ['ROS_IP']
      del os.environ['ROS_IP']
    
  def tearDown(self):
    if 'ROS_HOSTNAME' in os.environ:
      del os.environ['ROS_HOSTNAME']
    if 'ROS_IP' in os.environ:
      del os.environ['ROS_IP']
    if self._ros_hostname:
      os.environ['ROS_HOSTNAME'] = self._ros_hostname 
    if self._ros_ip:
      os.environ['ROS_IP'] = self._ros_ip
    
if __name__ == '__main__':
  rosunit.unitrun('test_roslib', 'test_network', NetworkTest, coverage_packages=['roslib.network'])

