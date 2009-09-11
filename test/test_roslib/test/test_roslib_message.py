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
import time
import unittest

import roslib.message
import rostest

# Not much to test, just tripwires

class MessageTest(unittest.TestCase):
    def test_Message(self):
        import cStringIO
        from roslib.message import Message, SerializationError
        self.assert_(isinstance(Message(), Message))
        m = Message()
        b = cStringIO.StringIO()
        m.serialize(b)
        m.deserialize('')

        # test args/keywords constructor
        try:
            Message(1, 2, 3, one=1, two=2, three=3)
            self.fail("Message should not allow *args and **kwds")
        except TypeError: pass
        try:
            Message()._get_types()
            self.fail("_get_types() should not be callable on abstract Message instance")
        except: pass

        # test Empty message
        class M1(Message):
            __slots__ = []
            def __init__(self, *args, **kwds):
                super(M1, self).__init__(*args, **kwds)
            def _get_types(self): return []
            
        # - test __str__ on empty
        self.assertEquals('', str(M1()))
        # - should not fail on default constructor
        M1()._check_types()
        # - must fail if provided an exception
        try:
            M1()._check_types(Exception("test"))
            self.fail("_check_types must fail if explicitly provided an exception")
        except SerializationError: pass

        # Test simple message with two fields
        class M2(Message):
            __slots__ = ['a', 'b']
            def _get_types(self): return ['int32', 'int32']
            def __init__(self, *args, **kwds):
                super(M2, self).__init__(*args, **kwds)
        self.assertEquals('a: 1\nb: 2', str(M2(1, 2)))
        # - test check types with two int type
        M2(1, 2)._check_types()
        M2(a=1, b=2)._check_types()
        invalid = [M2(a=1), M2('1', '2'), M2(1, '2'), M2(1., 2.), M2(None, 2)]
        for m in invalid:
            try:
                m._check_types()
                self.fail("check_types for %s should have failed"%m)
            except SerializationError: pass
        
        
        valid = [
            ((), {}, M1),
            ((), {}, M2),
            ((1, 2), {}, M2),
            ((), {'a': 1, 'b': 2}, M2),
            ((), {'a': 1}, M2),((), {'b': 2}, M2),
            ]
        invalid = [
            ((1,), {}, M1),
            ((), {'one': 1}, M1),
            ((1), {}, M2),((1, 2, 3), {}, M2),
            ((), {'c': 1}, M2),((), {'a': 1, 'b': 2, 'c': 1}, M2),
            ]
        for args, kwds, cls in valid:
            cls(*args, **kwds)
        val = time.time()
        val2 = time.time()
        self.assertEquals(val, M2(val, 2).a)
        self.assertEquals(val, M2(1, val).b)
        self.assertEquals(val, M2(a=val).a)
        self.assertEquals(None, M2(a=val).b)
        self.assertEquals(None, M2(b=val).a)
        self.assertEquals(val, M2(b=val).b)
        self.assertEquals(val, M2(a=val, b=val2).a)
        self.assertEquals(val2, M2(a=val, b=val2).b)
        for args, kwds, cls in invalid:
            try:
                cls(*args, **kwds)
                self.fail("Message should have failed for cls[%s] *args[%s] and **kwds[%s]"%(cls, args, kwds))
            except: pass
        
    def test_strify_message(self):
        # this is a bit overtuned, but it will catch regressions
        from roslib.message import Message, strify_message
        class M1(Message):
            __slots__ = []
            def __init__(self): pass
        self.assertEquals('', strify_message(M1()))
        class M2(Message):
            __slots__ = ['str', 'int', 'float', 'bool', 'list']
            def __init__(self, str_, int_, float_, bool_, list_):
                self.str = str_
                self.int = int_       
                self.float = float_
                self.bool = bool_
                self.list = list_
                
        self.assertEquals("""str: string
int: 123456789101112
float: 5678.0
bool: True
list: [1, 2, 3]""", strify_message(M2('string', 123456789101112, 5678., True, [1,2,3])))
        self.assertEquals("""str: string
int: -1
float: 0.0
bool: False
list: []""", strify_message(M2('string', -1, 0., False, [])))
        class M3(Message):
            __slots__ = ['m2']
            def __init__(self, m2):
                self.m2 = m2
        self.assertEquals("""m2: 
  str: string
  int: -1
  float: 0.0
  bool: False
  list: []""", strify_message(M3(M2('string', -1, 0., False, []))))

        # test array of Messages field
        class M4(Message):
            __slots__ = ['m2s']
            def __init__(self, m2s):
                self.m2s = m2s
                
        self.assertEquals("""m2s: [
    str: string
    int: 1234
    float: 5678.0
    bool: True
    list: [1, 2, 3],
    str: string
    int: -1
    float: 0.0
    bool: False
    list: []]""", strify_message(M4([
                        M2('string', 1234, 5678., True, [1,2,3]),
                        M2('string', -1, 0., False, []),
                        ])))
        # test Time and Duration
        from roslib.rostime import Time, Duration
        class M5(Message):
            __slots__ = ['t', 'd']
            def __init__(self, t, d):
                self.t = t
                self.d = d        
        self.assertEquals("""t: 987000000654
d: 123000000456""", strify_message(M5(Time(987, 654), Duration(123, 456))))
        
        # test final clause of strify -- str anything that isn't recognized
        self.assertEquals("set([1])", strify_message(set([1])))

    def test_ServiceDefinition(self):
        from roslib.message import ServiceDefinition
        self.assert_(isinstance(ServiceDefinition(), ServiceDefinition))

    def test_check_type(self):
        # check_type() currently does not do harder checks like
        # type-checking class types.  as soon as it does, it will need
        # test to validate this.
        from roslib.message import check_type, SerializationError
        from roslib.rostime import Time, Duration
        valids = [
            ('byte', 1), ('byte', -1),
            ('string', ''), ('string', 'a string of text'),
            ('int32[]', []),
            ('int32[]', [1, 2, 3, 4]),
            ('time', Time()), ('time', Time.from_seconds(1.0)),
            ('time', Time(10000)), ('time', Time(1000, -100)),
            ('duration', Duration()),('duration', Duration()), 
            ('duration', Duration(100)), ('duration', Duration(-100, -100)),
                  ]

        for t, v in valids:
            try:
                check_type('n', t, v)
            except Exception, e:
                import traceback
                traceback.print_exc()
                raise Exception("failure type[%s] value[%s]: %s"%(t, v, str(e)))

        invalids = [
            ('byte', 129), ('byte', -129), ('byte', 'byte'), ('byte', 1.0),
            ('string', 1),
            ('uint32', -1),
            ('int8', 112312), ('int8', -112312),
            ('uint8', -1), ('uint8', 112312),
            ('int32', '1'), ('int32', 1.),
            ('int32[]', 1), ('int32[]', [1., 2.]), ('int32[]', [1, 2.]), 
            ('duration', 1), ('time', 1),            
            ]
        for t, v in invalids:
            try:
                check_type('n', t, v)
                self.fail("check_type[%s, %s] should have failed"%(t, v))
            except SerializationError: pass
    
    def test_get_message_class(self):
        from roslib.message import get_message_class
      
        try:
            self.assertEquals(None, get_message_class('String'))
            self.fail("should have thrown ValueError")
        except ValueError: pass
        # non-existent package
        self.assertEquals(None, get_message_class('fake/Fake'))
        # non-existent message
        self.assertEquals(None, get_message_class('roslib/Fake'))
        # package with no messages
        self.assertEquals(None, get_message_class('genmsg_cpp/Fake'))
    
        import roslib.msg
        self.assertEquals(roslib.msg.Header, get_message_class('Header'))
        self.assertEquals(roslib.msg.Header, get_message_class('roslib/Header'))
        self.assertEquals(roslib.msg.Log, get_message_class('roslib/Log'))    

    def test_get_service_class(self):
        from roslib.message import get_service_class

        # non-existent package
        self.assertEquals(None, get_service_class('fake/Fake'))
        # non-existent message
        self.assertEquals(None, get_service_class('roslib/Fake'))
        # package with no messages
        self.assertEquals(None, get_service_class('genmsg_cpp/Fake'))
    
        import std_srvs.srv 
        self.assertEquals(std_srvs.srv.Empty, get_service_class('std_srvs/Empty'))    

if __name__ == '__main__':
  rostest.unitrun('test_roslib', 'test_message', MessageTest, coverage_packages=['roslib.message'])

