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

## Python utility for iterating over messages in a ROS .bag file
## See http://pr.willowgarage.com/wiki/ROS/LogFormat
# authors: jamesb, kwc

import roslib; roslib.load_manifest('rosrecord')

import os
import sys
import time
import optparse
from cStringIO import StringIO

import rospy
import roslib.genpy
import roslib.gentools
import roslib.msgs
import roslib.message
import roslib.rostime
import struct

class ROSRecordException(Exception): pass

HEADER_V1_1 = "#ROSRECORD V1.1"
HEADER_V1_2 = "#ROSRECORD V1.2"

g_message_defs = {}

## @return stream: file stream, ready to call next_msg on
## @raise ROSRecordException if file format is unrecognized    
def open_log_file(filename):
  if isinstance(filename, file):
    f = filename
  else:
    f = open(filename,'r')
  try:
    l = f.readline().rstrip() #ROSRECORD V1.1
    HEADERS = [ HEADER_V1_1, HEADER_V1_2 ]
    if not l in HEADERS:
      raise ROSRecordException("rosrecord.py only supports %s. File version is %s" % (",".join(HEADERS), l))
    return f, l
  except:
    f.close()
    raise

## get the next message. also calls any registered handlers
## @param f open log stream object to read from
## @param raw bool See return
## @return (str, data, rospy.Time): (topic, data, time). If not \a
## raw, data will be the deserialized Message. If \a raw, data will be
## a sequence (datatype, data, md5sum, bag_position). More elements
## may be added to this sequence in the future. Message next message
## in bag for which there is a matching handler
def next_msg_v1_1(f, raw=False):
  bag_pos = f.tell()
  # read topic/md5/type string headers
  topic = f.readline().rstrip()
  if not topic:
    return None, None, None
  md5sum = f.readline().rstrip()
  datatype = f.readline().rstrip()
  # migration for rostools->roslib rename
  if datatype in ['rostools/Header', 'rostools/Log', 'rostools/Time']:
    datatype = datatype.replace('rostools', 'roslib')

  # read time stamp
  data = f.read(12)
  if len(data) != 12:
    print >> sys.stderr, "WARNING: bag file appears to be corrupt (1)"
    return None, None, None
  ( time_sec, time_nsec, length ) = struct.unpack("<LLL", data)

  # read msg
  data = f.read(length)
  if len(data) != length:
    print >> sys.stderr, "WARNING: bag file appears to be corrupt (2)"
    return None, None, None

  try:
    pytype = g_message_defs[md5sum]
  except KeyError:
    try:
      pytype = roslib.message.get_message_class(datatype)
    except Exception:
      pytype = None

    if pytype is None:
      raise ROSRecordException("Cannot deserialize messages of type [%s]: cannot locate message class"%datatype)
    else:
      if (pytype._md5sum != md5sum):
        (package, type) = datatype.split('/')
        if (roslib.gentools.compute_md5_v1(roslib.gentools.get_file_dependencies(roslib.msgs.msg_file(package,type))) == md5sum):
          print "In V1.1 Logfile, found old md5sum for type [%s].  Allowing implicit migration to new md5sum."%datatype
        else:
          raise ROSRecordException("Cannot deserialize messages of type [%s]: md5sum is outdated in V1.1 bagfile"%datatype)
      g_message_defs[md5sum] = pytype

  if raw:
    return topic, (datatype, data, pytype._md5sum, bag_pos, pytype), rospy.Time(time_sec, time_nsec)
  else:
    msg = pytype()
    msg.deserialize(data)
    return topic, msg, rospy.Time(time_sec, time_nsec)

## get the next message. also calls any registered handlers
## @param f open log stream object to read from
## @param raw bool See return
## @return (str, data, rospy.Time): (topic, data, time). If not \a
## raw, data will be the deserialized Message. If \a raw, data will be
## a sequence (datatype, data, md5sum, bag_position). More elements
## may be added to this sequence in the future. Message next message
## in bag for which there is a matching handler
def next_msg_v1_2(f, raw=False):

  def read_sized(f):
    data = f.read(4)
    if len(data) != 4:
      return None
    (size,) = struct.unpack("<L", data)
    r = f.read(size)
    if len(r) != size:
      return None
    return r

  bag_pos = f.tell()

  # read header
  message_header = read_sized(f)
  if message_header == None:
    return None, None, None
  # read msg
  message_data = read_sized(f)
  if message_data == None:
    print >> sys.stderr, "WARNING: bag file appears to be corrupt (5)"
    return None, None, None

  # parse header into a dict hdr
  hdr = {}
  while message_header != "":
    if len(message_header) < 4:
      print >> sys.stderr, "WARNING: bag file appears to be corrupt (2)"
      return None, None, None
    (size,) = struct.unpack("<L", message_header[:4])
    message_header = message_header[4:]

    if len(message_header) < size:
      print >> sys.stderr, "WARNING: bag file appears to be corrupt (3)"
      return None, None, None
    (name, sep, value) = message_header[:size].partition('=')
    if sep == "":
      print >> sys.stderr, "WARNING: bag file appears to be corrupt (4)"
      return None, None, None
    hdr[name] = value
    message_header = message_header[size:]
  
  try:
    op = hdr['op']
  except KeyError:

    cur = f.tell()
    f.seek(0, os.SEEK_END)
    end = f.tell()
    f.seek(cur)

    print >> sys.stderr, "WARNING: Found incomplete message header. %d bytes left."%(end - cur,)
    return None,None,None

## The following hack sometimes recovers a corrupt file, but is by no means robust/correct

#    skipped = 4
#
#    tmp = f.read(4)
#    while (tmp != "md5="):
#      n = f.read(1)
#      skipped = skipped + 1
#      if (n == ""):
#        print >> sys.stderr, "WARNING: No candidate md5sum found before end of file."
#        return None,None,None
#      else:
#        tmp = tmp[1:]+n
#
#    print >> sys.stderr, "WARNING: Skipped %d bytes."%(skipped,)
#
#    f.seek(-12,os.SEEK_CUR)
#
#    return next_msg_v1_2(f, raw)
  
  if op == chr(1): # is a message definition
    required = set([ 'topic', 'md5', 'type', 'def'])
    assert required.issubset(set(hdr.keys()))
    topic = hdr['topic']
    md5sum = hdr['md5']
    datatype = hdr['type']
    msg_def = hdr['def']
    try:
      g_message_defs[md5sum] = roslib.genpy.generate_dynamic(datatype, msg_def)[datatype]
    except roslib.genpy.MsgGenerationException, e:
      raise ROSRecordException(str(e))
    if (g_message_defs[md5sum]._md5sum != md5sum):
      print "In V1.2 logfile, md5sum for type [%s] does not match definition.  Updating to new md5sum."%datatype
    return next_msg_v1_2(f, raw)

  required = set([ 'topic', 'md5', 'type', 'sec', 'nsec' ])
  assert required.issubset(set(hdr.keys()))
  topic = hdr['topic']
  md5sum = hdr['md5']
  datatype = hdr['type']
  (time_sec,) = struct.unpack("<L", hdr['sec'])
  (time_nsec,) = struct.unpack("<L", hdr['nsec'])

  try:
    pytype = g_message_defs[md5sum]
  except KeyError:
    raise ROSRecordException("Cannot deserialize messages of type [%s].  Message was not preceeded in bagfile by definition"%datatype)

  if raw:
    return topic, (datatype, message_data, pytype._md5sum, bag_pos, pytype), rospy.Time(time_sec, time_nsec)
  else:
    msg = pytype()
    msg.deserialize(message_data)
    return topic, msg, rospy.Time(time_sec, time_nsec)

## iterator for (topic, msg) in filename
## @param filename str: name of file to playback from
## @raise ROSRecordException if file format is unrecognized
def logplayer(filename, raw=False, seek=None):
  f,version = open_log_file(filename)
  next_msg = {
    HEADER_V1_1 : next_msg_v1_1,
    HEADER_V1_2 : next_msg_v1_2
  }[version]
  if seek is not None:
    f.seek(seek)
  try:
    try:
      while True:
        topic, msg, t = next_msg(f, raw)
        if msg == None or rospy.is_shutdown():
          break
        yield topic, msg, t
    except KeyboardInterrupt:
      pass # break iterator
  finally:
    f.close()

## Utility class for writing Message instances to a ROS .bag file
class Rebagger_v1_1(object):
  def __init__(self, filename):
    self.buff = StringIO()
    self.f = open(filename, 'w')
    self.f.write(HEADER_V1_1+'\n')
    
  ## Add a message to the bag
  ## @param msg Message: message to add to bag
  ## @param raw bool: if True, \a msg is in raw format (msg_type, serialized_bytes)
  ## @param t Time: ROS time of message publication
  def add(self, topic, msg, t=None, raw=False):
    # note: timestamp does not respect sim time as Rebagger is not required to be running in a rospy node
    if raw:
      f = self.f
      msg_type = msg[0]
      serialized_bytes = msg[1]
      md5sum = msg[2]
      f.write(topic+'\n'+md5sum+'\n'+msg_type+'\n')
      if not t:
        t = roslib.rostime.Time.from_seconds(time.time())
      f.write(struct.pack("<LLL", t.secs, t.nsecs, len(serialized_bytes)))
      f.write(serialized_bytes)
    else:
      f = self.f
      buff = self.buff
      md5sum = msg.__class__._md5sum
      msg_type = msg.__class__._type
      f.write(topic+'\n'+md5sum+'\n'+msg_type+'\n')    
      msg.serialize(buff)
      if not t:
        t = roslib.rostime.Time.from_seconds(time.time())
      f.write(struct.pack("<LLL", t.secs, t.nsecs, buff.tell()))
      f.write(buff.getvalue())

      buff.seek(0)
      buff.truncate(0)
    
  def close(self):
    if self.f:
      self.f.close()
    self.buff = None

## Utility class for writing Message instances to a ROS .bag file
class Rebagger(object):
  def __init__(self, filename):
    self.buff = StringIO()
    self.f = open(filename, 'w')
    self.f.write(HEADER_V1_2+'\n')

    self.defined = set()

  def add_hdr_data(self, hdr, data):
    s = ""
    for k,v in hdr.items():
      s += struct.pack("<L", len(k) + 1 + len(v))
      s += k
      s += '='
      s += v
    self.f.write(struct.pack("<L", len(s)))
    self.f.write(s)
    self.f.write(struct.pack("<L", len(data)))
    self.f.write(data)
    
  ## Add a message to the bag
  ## @param msg Message: message to add to bag
  ## @param raw bool: if True, \a msg is in raw format (msg_type, serialized_bytes, md5sum, pytype)
  ## @param t Time: ROS time of message publication
  def add(self, topic, msg, t=None, raw=False):
    if raw:
      f = self.f
      msg_type = msg[0]
      serialized_bytes = msg[1]

      if (len(msg) == 5):
        md5sum = msg[4]._md5sum
      else:
        md5sum = msg[2]

      if not msg_type in self.defined:
        if (len(msg) == 5):
          pytype = msg[4]
        else:
          try:
            pytype = roslib.message.get_message_class(msg_type)
          except Exception:
            pytype = None
          if pytype is None:
            raise ROSRecordException("cannot locate message class and no message class provided for [%s]"%msg_type)

        if (pytype._md5sum != md5sum):
          print >> sys.stderr, "WARNING: md5sum of loaded type [%s] does not match that specified in Rebagger.add"%msg_type
          #raise ROSRecordException("md5sum of loaded type does not match that of data being recorded")

        self.defined.add(msg_type)
        self.add_hdr_data({ 'op' : chr(1), 'topic' : topic, 'md5' : md5sum, 'type' : msg_type, 'def' : pytype._full_text }, '')

      # note: timestamp does not respect sim time as Rebagger is not required to be running in a rospy node
      if not t:
        t = roslib.rostime.Time.from_seconds(time.time())
      self.add_hdr_data({ 'op' : chr(2),
                          'topic' : topic,
                          'md5' : md5sum,
                          'type' : msg_type,
                          'sec' : struct.pack("<L", t.secs),
                          'nsec' : struct.pack("<L", t.nsecs)}, serialized_bytes)
    else:
      f = self.f
      buff = self.buff
      md5sum = msg.__class__._md5sum
      msg_type = msg.__class__._type

      if not msg_type in self.defined:
        self.defined.add(msg_type)
        self.add_hdr_data({ 'op' : chr(1), 'topic' : topic, 'md5' : md5sum, 'type' : msg_type, 'def' : msg._full_text }, '')
      msg.serialize(buff)
      # note: timestamp does not respect sim time as Rebagger is not required to be running in a rospy node
      if not t:
        t = roslib.rostime.Time.from_seconds(time.time())
      self.add_hdr_data({ 'op' : chr(2),
                          'topic' : topic,
                          'md5' : md5sum,
                          'type' : msg_type,
                          'sec' : struct.pack("<L", t.secs),
                          'nsec' : struct.pack("<L", t.nsecs)}, buff.getvalue())
      buff.seek(0)
      buff.truncate(0)
    
  def close(self):
    if self.f:
      self.f.close()
    self.buff = None


## Filter the contents of \a inbag to \a outbag using \a filter_fn
## @param inbag str: filename of input bag file.
## @param outbag str: filename of output bag file. Existing bag file will be overwritten
## @param filter_fn fn(topic, msg, time): Python function that returns True if msg is to be kept
## @param raw bool: if True, \a msg will be kept deserialized. This is
## useful if you are removing messages that no longer exist.
## @param verbose_pattern fn(topic, msg, time): Python function that
## returns string to print for verbose debugging
def rebag(inbag, outbag, filter_fn, verbose_pattern=None, raw=False):
  if verbose_pattern:
    rebag = Rebagger(outbag)
    for topic, msg, t in logplayer(inbag, raw=raw):
      if filter_fn(topic, msg, t):
        print "MATCH", verbose_pattern(topic, msg, t)
        rebag.add(topic, msg, t, raw=raw)          
        if rospy.is_shutdown():
          break
      else:
        print "NO MATCH", verbose_pattern(topic, msg, t)          
  else: #streamlined
    rebag = Rebagger(outbag)
    for topic, msg, t in logplayer(inbag, raw=raw):
      if filter_fn(topic, msg, t):
        rebag.add(topic, msg, t, raw=raw)
        if rospy.is_shutdown():
          break
    

## main routine for rosrebag
def rebag_main():
  ## filter function that uses command line expression to test topic/message/time
  def expr_eval(expr):
    def eval_fn(topic, m, t):
      return eval(expr)
    return eval_fn
    
  parser = optparse.OptionParser(usage="""usage: %prog in.bag out.bag filter-expression

filter-expression can be any Python-legal expression.
The following variables are available:
 * topic: name of topic
 * m: message
 * t: time of message (t.secs, t.nsecs)
""", prog='rosrebag')  
  parser.add_option('--print', dest="verbose_pattern", default=None,
                    metavar="PRINT-EXPRESSION", help="Python expression to print for verbose debugging. Uses same variables as filter-expression.")

  options, args = parser.parse_args()
  if len(args) == 0:
    parser.print_usage()
    sys.exit(0)
  elif len(args) != 3:
    parser.error("invalid arguments")
  inbag = args[0]
  outbag = args[1]
  expr = args[2]
  if options.verbose_pattern:
    verbose_pattern = expr_eval(options.verbose_pattern)
  else:
    verbose_pattern = None    
  if not os.path.isfile(inbag):
    print >> sys.stderr, "cannot locate input bag file [%s]"%inbag
    sys.exit(1)
  rebag(inbag, outbag, expr_eval(expr), verbose_pattern=verbose_pattern)
    
def demo():
  filename = "/u/kwc/bags/chatter.bag"
  for topic, msg, t in logplayer(filename):
    print topic, msg, t

def rebag_demo():
  inbag = '/u/kwc/bags/chatter.bag'
  outbag = '/u/kwc/bags/rechatter.bag'
  rebag(inbag, outbag, lambda msg, topic, t: True)

if __name__ == '__main__':
  demo()
