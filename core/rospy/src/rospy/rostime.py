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
ROS time and duration representations, as well as internal routines
for managing wallclock versus a simulated clock.  The important data
classes are L{Time} and L{Duration}, which represent the ROS 'time'
and 'duration' primitives, respectively.
"""

import threading
import time
import traceback

import rospy.exceptions

import roslib.msg
import roslib.rosenv
import roslib.rostime

## /time support. This hooks into the rospy Time representation and
## allows it to be overriden with data from the /time topic.

_rostime_initialized = False
_rostime_current = None
_rostime_cond = threading.Condition()

# subclass roslib to provide abstraction layer
class Duration(roslib.rostime.Duration):
    """
    Duration represents the ROS 'duration' primitive type, which
    consists of two integers: seconds and nanoseconds. The Duration
    class allows you to add and subtract Duration instances, including
    adding and subtracting from L{Time} instances.
    """
    __slots__ = []

    def __init__(self, secs=0, nsecs=0):
        """
        Create new Duration instance. secs and nsecs are integers and
        correspond to the ROS 'duration' primitive type.

        @param secs: seconds
        @type  secs: int
        @param nsecs: nanoseconds
        @type  nsecs: int
        """
        super(Duration, self).__init__(secs, nsecs)

class Time(roslib.rostime.Time):
    """
    Time represents the ROS 'time' primitive type, which consists of two
    integers: seconds since epoch and nanoseconds since seconds. Time
    instances are mutable.

    The L{Time.now()} factory method can initialize Time to the
    current ROS time and L{from_seconds()} can be used to create a
    Time instance from the Python's time.time() float seconds
    representation.

    The Time class allows you to subtract Time instances to compute
    Durations, as well as add Durations to Time to create new Time
    instances.

    Usage::
      now = rospy.Time.now()
      zero_time = rospy.Time()

      # NOTE: in general, you will want to avoid using time.time() in ROS code
      import time
      py_time = rospy.Time.from_seconds(time.time())
    """
    __slots__ = []    

    def __init__(self, secs=0, nsecs=0):
        """
        Constructor: secs and nsecs are integers and correspond to the
        ROS 'time' primitive type. You may prefer to use the static
        L{from_seconds()} and L{now()} factory methods instead.
        
        @param secs: seconds since epoch
        @type  secs: int
        @param nsecs: nanoseconds since seconds (since epoch)
        @type  nsecs: int
        """
        super(Time, self).__init__(secs, nsecs)
        
    def now():
        """
        Create new L{Time} instance representing current time. This
        can either be wall-clock time or a simulated clock. It is
        strongly recommended that you use the now() factory to create
        current time representations instead of reading wall-clock
        time and create Time instances from it.
        
        @return: L{Time} instance for current time
        @rtype: L{Time}
        """
        if not _rostime_initialized:
            raise rospy.exceptions.ROSInitException("time is not initialized. Have you called init_node()?")
        if _rostime_current is not None:
            # initialize with sim time
            return _rostime_current
        else:
            # initialize with wallclock
            float_secs = time.time()
            secs = int(float_secs)
            nsecs = int((float_secs - secs) * 1000000000)
            return Time(secs, nsecs)

    now = staticmethod(now)

    # have to reproduce super class implementation to return correct typing
    
    def from_seconds(float_secs):
        """
        Create new Time instance from a float seconds representation
        (e.g. time.time()).
        
        @param float_secs: time value in time.time() format
        @type  float_secs: float
        @return: Time instance for specified time
        @rtype: L{Time}
        """
        secs = int(float_secs)
        nsecs = int((float_secs - secs) * 1000000000)
        return Time(secs, nsecs)
    
    from_seconds = staticmethod(from_seconds)
    
def _set_rostime(t):
    """Callback to update ROS time from a ROS Topic"""
    if isinstance(t, roslib.rostime.Time):
        t = Time(t.secs, t.nsecs)
    elif not isinstance(t, Time):
        raise ValueError("must be Time instance")
    global _rostime_current
    _rostime_current = t
    try:
        _rostime_cond.acquire()
        _rostime_cond.notifyAll()
    finally:
        _rostime_cond.release()
    
def get_rostime():
    """
    Get the current time as a L{Time} object    
    @return: current time as a L{rospy.Time} object
    @rtype: L{Time}
    """
    return Time.now()

def get_time():
    """
    Get the current time as float secs (time.time() format)
    @return: time in secs (time.time() format)    
    @rtype: float
    """
    return Time.now().to_seconds()

def set_rostime_initialized(val):
    """
    Internal use.
    Mark rostime as initialized. This flag enables other routines to
    throw exceptions if rostime is being used before the underlying
    system is initialized.
    @param val: value for initialization state
    @type  val: bool
    """
    global _rostime_initialized
    _rostime_initialized = val

def is_rostime_initialized():
    """
    Internal use.
    @return: True if rostime has been initialized
    @rtype: bool
    """
    return _rostime_initialized    

def get_rostime_cond():
    """
    internal API for helper routines that need to wait on time updates
    @return: rostime conditional var
    @rtype: threading.Cond
    """
    return _rostime_cond

def is_wallclock():
    """
    Internal use for ROS-time routines.
    @return: True if ROS is currently using wallclock time
    @rtype: bool
    """
    return _rostime_current == None
    
def switch_to_wallclock():
    """
    Internal use.
    Switch ROS to wallclock time. This is mainly for testing purposes.
    """
    global _rostime_current
    _rostime_current = None
    try:
        _rostime_cond.acquire()
        _rostime_cond.notifyAll()
    finally:
        _rostime_cond.release()

