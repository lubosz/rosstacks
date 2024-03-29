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
Library for configuring python logging to standard ROS locations (e.g. ROS_LOG_DIR).
"""

import os
import sys
import logging
import logging.config

from rospkg import get_ros_root, get_log_dir
from rospkg.environment import ROS_LOG_DIR

import roslib.exceptions
    
def configure_logging(logname, level=logging.INFO, filename=None, env=None):
    """
    Configure Python logging package to send log files to ROS-specific log directory
    @param logname str: name of logger
    @type  logname: str
    @param filename: filename to log to. If not set, a log filename
        will be generated using logname
    @type filename: str
    @param env: override os.environ dictionary
    @type  env: dict
    @return: log file name
    @rtype: str
    @raise roslib.exceptions.ROSLibException: if logging cannot be configured as specified
    """
    if env is None:
        env = os.environ

    logname = logname or 'unknown'
    log_dir = get_log_dir(env=env)
    
    # if filename is not explicitly provided, generate one using logname
    if not filename:
        log_filename = os.path.join(log_dir, '%s-%s.log'%(logname, os.getpid()))
    else:
        log_filename = os.path.join(log_dir, filename)

    logfile_dir = os.path.dirname(log_filename)
    if not os.path.exists(logfile_dir):
        try:
            makedirs_with_parent_perms(logfile_dir)
        except OSError:
            # cannot print to screen because command-line tools with output use this
            sys.stderr.write("WARNING: cannot create log directory [%s]. Please set %s to a writable location.\n"%(logfile_dir, ROS_LOG_DIR))
            return None
    elif os.path.isfile(logfile_dir):
        raise roslib.exceptions.ROSLibException("Cannot save log files: file [%s] is in the way"%logfile_dir)

    if 'ROS_PYTHON_LOG_CONFIG_FILE' in os.environ:
        config_file = os.environ['ROS_PYTHON_LOG_CONFIG_FILE']
    else:
        config_file = os.path.join(get_ros_root(env=env), 'config', 'python_logging.conf')

    if not os.path.isfile(config_file):
        # logging is considered soft-fail
        sys.stderr.write("WARNING: cannot load logging configuration file, logging is disabled\n")
        return log_filename
    
    # pass in log_filename as argument to pylogging.conf
    os.environ['ROS_LOG_FILENAME'] = log_filename
    # #3625: disabling_existing_loggers=False
    logging.config.fileConfig(config_file, disable_existing_loggers=False)
    return log_filename

def makedirs_with_parent_perms(p):
    """
    Create the directory using the permissions of the nearest
    (existing) parent directory. This is useful for logging, where a
    root process sometimes has to log in the user's space.
    @param p: directory to create
    @type  p: str
    """    
    p = os.path.abspath(p)
    parent = os.path.dirname(p)
    # recurse upwards, checking to make sure we haven't reached the
    # top
    if not os.path.exists(p) and p and parent != p:
        makedirs_with_parent_perms(parent)
        s = os.stat(parent)
        os.mkdir(p)

        # if perms of new dir don't match, set anew
        s2 = os.stat(p)
        if s.st_uid != s2.st_uid or s.st_gid != s2.st_gid:
            os.chown(p, s.st_uid, s.st_gid)
        if s.st_mode != s2.st_mode:
            os.chmod(p, s.st_mode)    
