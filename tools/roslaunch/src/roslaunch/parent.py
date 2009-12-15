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
roslaunch.parent providees the L{ROSLaunchParent} implementation,
which represents the main 'parent' roslaunch process. 

ROSLaunch has a client/server architecture for running remote
processes. When a user runs roslaunch, this creates a "parent"
roslaunch process, which is responsible for managing local
processes. This parent process will also start "child" processes on
remote machines. The parent can then invoke methods on this child
process to launch remote processes, and the child can invoke methods
on the parent to provide feedback.
"""

import logging
import sys

import roslaunch.config
from roslaunch.core import printlog_bold, printerrlog, RLException
import roslaunch.launch
import roslaunch.pmon
import roslaunch.server
import roslaunch.xmlloader 

#TODOXXX: probably move process listener infrastructure into here

# TODO: remove after wg_hardware_roslaunch has been updated
# qualification accesses this API, which has been relocated
load_config_default = roslaunch.config.load_config_default

class ROSLaunchParent(object):
    """
    ROSLaunchParent represents the main 'parent' roslaunch process. It
    is responsible for loading the launch files, assigning machines,
    and then starting up any remote processes. The __main__ method
    delegates most of runtime to ROSLaunchParent.
    """

    def __init__(self, run_id, roslaunch_files, is_core=False, port=None, local_only=False, process_listeners=None):
        """
        @param run_id: UUID of roslaunch session
        @type  run_id: str
        @param roslaunch_files: list of launch configuration
            files to load
        @type  roslaunch_files: [str]
        @param is_core bool: if True, this launch is a roscore
            instance. This affects the error behavior if a master is
            already running (i.e. it fails).
        @type  is_core: bool
        @param process_listeners: (optional) list of process listeners
            to register with process monitor once launch is running
        @type  process_listeners: [L{roslaunch.pmon.ProcessListener}]
        @throws RLException
        """
        
        self.logger = logging.getLogger('roslaunch.parent')
        self.run_id = run_id
        self.process_listeners = process_listeners
        
        self.roslaunch_files = roslaunch_files
        self.is_core = is_core
        self.port = port
        self.local_only = local_only

        # flag to prevent multiple shutdown attempts
        self._shutting_down = False
        
        self.config = self.runner = self.server = self.pm = self.remote_runner = None

    def _load_config(self):
        self.config = roslaunch.config.load_config_default(self.roslaunch_files, self.port)

    def _start_pm(self):
        """
        Start the process monitor
        """
        self.pm = roslaunch.pmon.start_process_monitor()
        
    def _init_runner(self):
        """
        Initialize the roslaunch runner
        """
        if self.config is None:
            raise RLException("config is not initialized")
        if self.pm is None:
            raise RLException("pm is not initialized")
        if self.server is None:
            raise RLException("server is not initialized")
        self.runner = roslaunch.launch.ROSLaunchRunner(self.run_id, self.config, server_uri=self.server.uri, pmon=self.pm, is_core=self.is_core, remote_runner=self.remote_runner)

        # print runner info to user, put errors last to make the more visible
        print self.config.summary(local=self.remote_runner is None)
        if self.config:
            for err in self.config.config_errors:
                printerrlog("WARNING: %s"%err)

    def _start_server(self):
        """
        Initialize the roslaunch parent XML-RPC server        
        """
        if self.config is None:
            raise RLException("config is not initialized")
        if self.pm is None:
            raise RLException("pm is not initialized")

        self.logger.info("starting parent XML-RPC server")
        self.server = roslaunch.server.ROSLaunchParentNode(self.config, self.pm)
        self.server.start()
        if not self.server.uri:
            raise RLException("server URI did not initialize")
        self.logger.info("... parent XML-RPC server started")        
        
    def _init_remote(self):
        """
        Initialize the remote process runner, if required. Subroutine
        of _start_remote, separated out for easier testing
        """
        if self.config is None:
            raise RLException("config is not initialized")
        if self.pm is None:
            raise RLException("pm is not initialized")
        if self.server is None:
            raise RLException("server is not initialized")

        if not self.local_only and self.config.has_remote_nodes():
            # keep the remote package lazy-imported
            import roslaunch.remote
            self.remote_runner = roslaunch.remote.ROSRemoteRunner(self.run_id, self.config, self.pm, self.server)
        elif self.local_only:
            printlog_bold("LOCAL\nlocal only launch specified, will not launch remote nodes\nLOCAL\n")

    def _start_remote(self):
        """
        Initializes and runs the remote process runner, if required
        """
        self._init_remote()
        if self.remote_runner is not None:
            # start_servers() runs the roslaunch children
            self.remote_runner.start_children()
    
    def _start_infrastructure(self):
        """
        load config, start XMLRPC servers and process monitor
        """        
        self._load_config()

        # Start the process monitor
        self._start_pm()

        # Startup the roslaunch runner and XMLRPC server.
        # Requires pm
        self._start_server()

        # Startup the remote infrastructure.
        # Requires config, pm, and server
        self._start_remote()

    def _stop_infrastructure(self):
        """
        Tear down server and process monitor. Not multithread safe.
        """
        #TODO more explicit teardown of remote infrastructure

        # test and set flag so we don't shutdown multiple times
        if self._shutting_down:
            return
        self._shutting_down = True
        
        if self.server:
            self.server.shutdown("roslaunch parent complete")
        if self.pm:
            self.pm.shutdown()
            self.pm.join()
        
    def start(self):
        """
        Run the parent roslaunch
        """
        self.logger.info("starting roslaunch parent run")
        
        # load config, start XMLRPC servers and process monitor
        self._start_infrastructure()
            
        # Initialize the actual runner. 
        # Requires config, pm, server and remote_runner
        self._init_runner()

        # Start the launch
        self.runner.launch()
        self.logger.info("... roslaunch parent running, waiting for process exit")
        if self.process_listeners:
            for l in self.process_listeners:
                self.runner.pm.add_process_listener(l)
        
    def spin_once(self):
        """
        Run the parent roslaunch event loop once
        """
        if self.runner:
            self.runner.spin_once()

    def spin(self):
        """
        Run the parent roslaunch until exit
        """
        if not self.runner:
            raise RLException("parent not started yet")
        try:
            # Blocks until all processes dead/shutdown
            self.runner.spin()
        finally:
            self._stop_infrastructure()

    def shutdown(self):
        """
        Stop the parent roslaunch.
        """
        self._stop_infrastructure()        
