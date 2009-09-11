/*
 * Software License Agreement (BSD License)
 *
 *  Copyright (c) 2009, Willow Garage, Inc.
 *  All rights reserved.
 *
 *  Redistribution and use in source and binary forms, with or without
 *  modification, are permitted provided that the following conditions
 *  are met:
 *
 *   * Redistributions of source code must retain the above copyright
 *     notice, this list of conditions and the following disclaimer.
 *   * Redistributions in binary form must reproduce the above
 *     copyright notice, this list of conditions and the following
 *     disclaimer in the documentation and/or other materials provided
 *     with the distribution.
 *   * Neither the name of Willow Garage, Inc. nor the names of its
 *     contributors may be used to endorse or promote products derived
 *     from this software without specific prior written permission.
 *
 *  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 *  "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 *  LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
 *  FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
 *  COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
 *  INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
 *  BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
 *  LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
 *  CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
 *  LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
 *  ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 *  POSSIBILITY OF SUCH DAMAGE.
 */

// TEMP to remove warnings during build while things internally still use deprecated APIs
#include "ros/macros.h"
#undef ROSCPP_DEPRECATED
#define ROSCPP_DEPRECATED
// END TEMP

#include "ros/init.h"
#include "ros/names.h"
#include "ros/node.h"
#include "ros/xmlrpc_manager.h"
#include "ros/poll_manager.h"
#include "ros/connection_manager.h"
#include "ros/topic_manager.h"
#include "ros/service_manager.h"
#include "ros/this_node.h"
#include "ros/network.h"
#include "ros/file_log.h"
#include "ros/callback_queue.h"
#include "ros/param.h"
#include "ros/rosout_appender.h"

#include "roscpp/GetLoggers.h"
#include "roscpp/SetLoggerLevel.h"

#include <ros/console.h>
#include <ros/time.h>

namespace ros
{

namespace master
{
void init(const M_string& remappings);
}

namespace names
{
void init(const M_string& remappings);
}

namespace this_node
{
void init(const std::string& names, const M_string& remappings, uint32_t options);
}

namespace network
{
void init(const M_string& remappings);
}

namespace param
{
void init(const M_string& remappings);
}

namespace file_log
{
void init(const M_string& remappings);
}

CallbackQueue g_global_queue;
bool g_initialized = false;
bool g_started = false;
boost::mutex g_start_mutex;
bool g_ok = false;
uint32_t g_init_options = 0;
bool g_shutdown_requested = false;
volatile bool g_shutting_down = false;
boost::mutex g_shutting_down_mutex;
boost::thread g_internal_queue_thread;
extern CallbackQueue g_global_queue;
ROSOutAppenderPtr g_rosout_appender;

bool isInitialized()
{
  return g_initialized;
}

bool isShuttingDown()
{
  return g_shutting_down;
}

void checkForShutdown()
{
  if (g_shutdown_requested)
  {
    shutdown();
  }
}

void requestShutdown()
{
  g_shutdown_requested = true;
}

void shutdownCallback(XmlRpc::XmlRpcValue& params, XmlRpc::XmlRpcValue& result)
{
  int num_params = 0;
  if (params.getType() == XmlRpc::XmlRpcValue::TypeArray)
    num_params = params.size();
  if (num_params > 1)
  {
    std::string reason = params[1];
    ROS_WARN("Shutdown request received.");
    ROS_WARN("Reason given for shutdown: [%s]", reason.c_str());
    requestShutdown();
  }

  result = xmlrpc::responseInt(1, "", 0);
}

bool getLoggers(roscpp::GetLoggers::Request&, roscpp::GetLoggers::Response& resp)
{
  log4cxx::spi::LoggerRepositoryPtr repo = log4cxx::Logger::getLogger(ROSCONSOLE_ROOT_LOGGER_NAME)->getLoggerRepository();

  log4cxx::LoggerList loggers = repo->getCurrentLoggers();
  log4cxx::LoggerList::iterator it = loggers.begin();
  log4cxx::LoggerList::iterator end = loggers.end();
  for (; it != end; ++it)
  {
    resp.loggers.push_back((*it)->getName());
  }

  return true;
}

bool setLoggerLevel(roscpp::SetLoggerLevel::Request& req, roscpp::SetLoggerLevel::Response&)
{
  log4cxx::LoggerPtr logger = log4cxx::Logger::getLogger(req.logger);
  log4cxx::LevelPtr level;

  if (req.level == "DEBUG" || req.level == "debug" || req.level == "Debug")
  {
    level = log4cxx::Level::getDebug();
  }
  else if (req.level == "INFO" || req.level == "info" || req.level == "Info")
  {
    level = log4cxx::Level::getInfo();
  }
  else if (req.level == "WARN" || req.level == "warn" || req.level == "Warn")
  {
    level = log4cxx::Level::getWarn();
  }
  else if (req.level == "ERROR" || req.level == "error" || req.level == "Error")
  {
    level = log4cxx::Level::getError();
  }
  else if (req.level == "FATAL" || req.level == "fatal" || req.level == "Fatal")
  {
    level = log4cxx::Level::getFatal();
  }

  if (level)
  {
    logger->setLevel(level);
    console::notifyLoggerLevelsChanged();
    return true;
  }

  return false;
}

void timeCallback(const roslib::Time::ConstPtr& msg)
{
  Time::setNow(msg->rostime);
}

CallbackQueuePtr getInternalCallbackQueue()
{
  static CallbackQueuePtr queue;
  if (!queue)
  {
    queue.reset(new CallbackQueue);
  }

  return queue;
}

void basicSigintHandler(int sig)
{
  ros::requestShutdown();
}

void internalCallbackQueueThreadFunc()
{
  disableAllSignalsInThisThread();

  CallbackQueuePtr queue = getInternalCallbackQueue();

  while (!g_shutting_down)
  {
    queue->callAvailable(WallDuration(0.05));
  }
}

void start()
{
  boost::mutex::scoped_lock lock(g_start_mutex);
  if (g_started)
  {
    return;
  }

  g_shutdown_requested = false;
  g_shutting_down = false;
  g_started = true;
  g_ok = true;

  PollManager::instance()->addPollThreadListener(checkForShutdown);
  XMLRPCManager::instance()->bind("shutdown", shutdownCallback);

  TopicManager::instance()->start();
  ServiceManager::instance()->start();
  ConnectionManager::instance()->start();
  PollManager::instance()->start();
  XMLRPCManager::instance()->start();

  if (!(g_init_options & init_options::NoSigintHandler))
  {
    signal(SIGINT, basicSigintHandler);
  }

  if (!(g_init_options & init_options::NoRosout))
  {
    g_rosout_appender = new ROSOutAppender;
    const log4cxx::LoggerPtr& logger = log4cxx::Logger::getLogger(ROSCONSOLE_ROOT_LOGGER_NAME);
    logger->addAppender(g_rosout_appender);
  }

  if (!g_shutting_down)
  {
    {
      ros::AdvertiseServiceOptions ops;
      ops.init<roscpp::GetLoggers>(names::resolve("~get_loggers"), getLoggers);
      ops.callback_queue = getInternalCallbackQueue().get();
      ServiceManager::instance()->advertiseService(ops, 0);
    }

    if (!g_shutting_down)
    {
      {
        ros::AdvertiseServiceOptions ops;
        ops.init<roscpp::SetLoggerLevel>(names::resolve("~set_logger_level"), setLoggerLevel);
        ops.callback_queue = getInternalCallbackQueue().get();
        ServiceManager::instance()->advertiseService(ops, 0);
      }

      if (!g_shutting_down)
      {
        bool use_sim_time = false;
        param::param("/use_sim_time", use_sim_time, use_sim_time);
        if (use_sim_time)
        {
          Time::setNow(ros::Time());
        }

        if (!g_shutting_down)
        {
          {
            ros::SubscribeOptions ops;
            ops.init<roslib::Time>("/time", 1, timeCallback);
            ops.callback_queue = getInternalCallbackQueue().get();
            TopicManager::instance()->subscribe(ops, 0, 0);
          }

          g_internal_queue_thread = boost::thread(internalCallbackQueueThreadFunc);
          g_global_queue.enable();
          getGlobalCallbackQueue()->enable();

          ROS_INFO("Started node [%s], pid [%d], bound on [%s], xmlrpc port [%d], tcpros port [%d], logging to [%s], using [%s] time", this_node::getName().c_str(), getpid(), network::getHost().c_str(), XMLRPCManager::instance()->getServerPort(), ConnectionManager::instance()->getTCPPort(), file_log::getLogFilename().c_str(), Time::useSystemTime() ? "real" : "sim");
        }
      }
    }
  }
}

void init(const M_string& remappings, const std::string& name, uint32_t options)
{
  if (!g_initialized)
  {
    g_init_options = options;
    g_ok = true;

    ROSCONSOLE_AUTOINIT;
    ros::Time::init();
    network::init(remappings);
    master::init(remappings);
    names::init(remappings);
    this_node::init(name, remappings, options);
    param::init(remappings);
    file_log::init(remappings);

    g_initialized = true;
    Node::s_initialized_ = true;
  }
}

void init(int& argc, char** argv, const std::string& name, uint32_t options)
{
  M_string remappings;

  int full_argc = argc;
  // now, move the remapping argv's to the end, and decrement argc as needed
  for (int i = 0; i < argc; )
  {
    std::string arg = argv[i];
    size_t pos = arg.find(":=");
    if (pos != std::string::npos)
    {
      std::string local_name = arg.substr(0, pos);
      std::string external_name = arg.substr(pos + 2);

      remappings[local_name] = external_name;

      // shuffle everybody down and stuff this guy at the end of argv
      char *tmp = argv[i];
      for (int j = i; j < full_argc - 1; j++)
        argv[j] = argv[j+1];
      argv[argc-1] = tmp;
      argc--;
    }
    else
    {
      i++; // move on, since we didn't shuffle anybody here to replace it
    }
  }

  init(remappings, name, options);
}

void init(const VP_string& remappings, const std::string& name, uint32_t options)
{
  M_string remappings_map;
  VP_string::const_iterator it = remappings.begin();
  VP_string::const_iterator end = remappings.end();
  for (; it != end; ++it)
  {
    remappings_map[it->first] = it->second;
  }

  init(remappings_map, name, options);
}

void spin()
{
  SingleThreadedSpinner s;
  spin(s);
}

void spin(Spinner& s)
{
  s.spin();
}

void spinOnce()
{
  g_global_queue.callAvailable(ros::WallDuration());
}

CallbackQueue* getGlobalCallbackQueue()
{
  return &g_global_queue;
}

bool ok()
{
  return g_ok;
}

void shutdown()
{
  boost::mutex::scoped_lock lock(g_shutting_down_mutex);
  if (g_shutting_down)
  {
    return;
  }

  g_shutting_down = true;

  g_global_queue.disable();
  g_global_queue.clear();

  getGlobalCallbackQueue()->disable();
  getGlobalCallbackQueue()->clear();

  if (g_internal_queue_thread.get_id() != boost::this_thread::get_id())
  {
    g_internal_queue_thread.join();
    ROS_DEBUG("internal callback queue thread shut down");
  }

  const log4cxx::LoggerPtr& logger = log4cxx::Logger::getLogger(ROSCONSOLE_ROOT_LOGGER_NAME);
  logger->removeAppender(g_rosout_appender);
  g_rosout_appender = 0;

  XMLRPCManager::instance()->shutdown();
  TopicManager::instance()->shutdown();
  ServiceManager::instance()->shutdown();
  ConnectionManager::instance()->shutdown();
  PollManager::instance()->shutdown();

  g_started = false;
  g_ok = false;
  Time::shutdown();
}

/////////////////////////////////////////////////////////////////////////////////////////////////
// Deprecated init functions
/////////////////////////////////////////////////////////////////////////////////////////////////

void init(int& _argc, char** _argv)
{
  Node::s_args_.clear();

  int full_argc = _argc;
  // now, move the remapping argv's to the end, and decrement argc as needed
  for (int i = 0; i < _argc; )
  {
    std::string arg = _argv[i];
    size_t pos = arg.find(":=");
    if (pos != std::string::npos)
    {
      std::string local_name = arg.substr(0, pos);
      std::string external_name = arg.substr(pos + 2);

      Node::s_remappings_.push_back(std::make_pair(local_name, external_name));
      Node::s_args_.push_back(_argv[i]);

      // shuffle everybody down and stuff this guy at the end of argv
      char *tmp = _argv[i];
      for (int j = i; j < full_argc - 1; j++)
        _argv[j] = _argv[j+1];
      _argv[_argc-1] = tmp;
      _argc--;
    }
    else
    {
      i++; // move on, since we didn't shuffle anybody here to replace it
    }
  }

  init(Node::s_remappings_);
  Node::s_initialized_ = true;
}

void init(const VP_string& remappings)
{
  Node::s_remappings_ = remappings;
  Node::s_initialized_ = true;
}

}
