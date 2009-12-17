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

import roslib.rosenv
import roslib.os_detect
import rostest

class RoslibOsDetectTest(unittest.TestCase):
  
  def test_tripwire_ubuntu(self):
      ubuntu = roslib.os_detect.Ubuntu()
      self.assertEqual("ubuntu", ubuntu.get_name())

  def test_tripwire_debian(self):
      debian = roslib.os_detect.Debian()
      self.assertEqual("debian", debian.get_name())

  def test_tripwire_macports(self):
      macports = roslib.os_detect.Macports()
      self.assertEqual("macports", macports.get_name())
    
  def test_tripwire_arch(self):
      arch = roslib.os_detect.Arch()
      self.assertEqual("arch", arch.get_name())

  def test_tripwire_fedora(self):
      fedora = roslib.os_detect.Fedora()
      self.assertEqual("fedora", fedora.get_name())

  def test_tripwire_rhel(self):
      rhel = roslib.os_detect.Rhel()
      self.assertEqual("rhel", rhel.get_name())


  def test_tripwire_OSAbstraction(self):
    osa = roslib.os_detect.OSAbstraction()

if __name__ == '__main__':
  rostest.unitrun('test_roslib', 'test_os_detect', RoslibOsDetectTest, coverage_packages=['roslib.os_detect'])
