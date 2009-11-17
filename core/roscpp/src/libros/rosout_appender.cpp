/*
 * Software License Agreement (BSD License)
 *
 *  Copyright (c) 2008, Willow Garage, Inc.
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

#include "ros/rosout_appender.h"
#include "ros/this_node.h"
#include "ros/node_handle.h"
#include "ros/topic_manager.h"
#include "ros/advertise_options.h"
#include "ros/names.h"

#include <log4cxx/spi/loggingevent.h>

namespace ros
{

ROSOutAppender::ROSOutAppender()
: shutting_down_(false)
, publish_thread_(boost::bind(&ROSOutAppender::logThread, this))
{
  AdvertiseOptions ops;
  ops.init<roslib::Log>(names::resolve("/rosout"), 0);
  ops.latch = true;
  SubscriberCallbacksPtr cbs(new SubscriberCallbacks);
  TopicManager::instance()->advertise(ops, cbs);
}

ROSOutAppender::~ROSOutAppender()
{
  shutting_down_ = true;
  queue_condition_.notify_all();

  publish_thread_.join();
}

const std::string&  ROSOutAppender::getLastError()
{
  return last_error_;
}

void ROSOutAppender::append(const log4cxx::spi::LoggingEventPtr& event, log4cxx::helpers::Pool& pool)
{
  roslib::LogPtr msg(new roslib::Log);

  msg->header.stamp = ros::Time::now();

  if (event->getLevel() == log4cxx::Level::getFatal())
  {
    msg->level = roslib::Log::FATAL;
    last_error_ = event->getMessage();
  }
  else if (event->getLevel() == log4cxx::Level::getError())
  {
    msg->level = roslib::Log::ERROR;
    last_error_ = event->getMessage();
  }
  else if (event->getLevel() == log4cxx::Level::getWarn())
  {
    msg->level = roslib::Log::WARN;
  }
  else if (event->getLevel() == log4cxx::Level::getInfo())
  {
    msg->level = roslib::Log::INFO;
  }
  else if (event->getLevel() == log4cxx::Level::getDebug())
  {
    msg->level = roslib::Log::DEBUG;
  }

  msg->name = this_node::getName();
  msg->msg = event->getMessage();

  const log4cxx::spi::LocationInfo& info = event->getLocationInformation();
  msg->file = info.getFileName();
  msg->function = info.getMethodName();
  msg->line = info.getLineNumber();

  this_node::getAdvertisedTopics(msg->topics);

  boost::mutex::scoped_lock lock(queue_mutex_);
  log_queue_.push_back(msg);
  queue_condition_.notify_all();
}

void ROSOutAppender::logThread()
{
  while (!shutting_down_)
  {
    V_Log local_queue;

    {
      boost::mutex::scoped_lock lock(queue_mutex_);

      queue_condition_.wait(lock);

      if (shutting_down_)
      {
        return;
      }

      local_queue.swap(log_queue_);
    }

    V_Log::iterator it = local_queue.begin();
    V_Log::iterator end = local_queue.end();
    for (; it != end; ++it)
    {
      TopicManager::instance()->publish(names::resolve("/rosout"), *(*it));
    }
  }
}

} // namespace ros
