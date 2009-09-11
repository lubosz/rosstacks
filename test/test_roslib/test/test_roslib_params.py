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
import sys
import unittest

import roslib.names
import rostest

class ParamsTest(unittest.TestCase):
  
  def test_load_param_mappings(self):
    from roslib.params import load_command_line_node_params
    self.assertEquals({}, load_command_line_node_params([]))
    self.assertEquals({}, load_command_line_node_params(['foo']))
    self.assertEquals({}, load_command_line_node_params(['_foo']))
    self.assertEquals({}, load_command_line_node_params([':=']))
    self.assertEquals({}, load_command_line_node_params([':=:=']))
    self.assertEquals({}, load_command_line_node_params(['_f:=']))
    self.assertEquals({}, load_command_line_node_params([':=b']))
    self.assertEquals({}, load_command_line_node_params(['_foo:=_bar:=baz']))    
    
    self.assertEquals({'foo': 'bar'}, load_command_line_node_params(['_foo:=bar']))
    self.assertEquals({'foo': 'bar'}, load_command_line_node_params(['./f', '-x', '--blah', '_foo:=bar']))
    self.assertEquals({'a': 'one', 'b': 2, 'c': 3.0, 'd':[1,2,3,4]}, load_command_line_node_params(['_c:=3.0', '_c:=', ':=3', '_a:=one', '_b:=2', '_d:=[1,2,3,4]']))
    

if __name__ == '__main__':
  rostest.unitrun('test_roslib', 'test_params', ParamsTest, coverage_packages=['roslib.params'])

