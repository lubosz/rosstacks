/*********************************************************************
*
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
*********************************************************************/

#include "rosrecord/time_publisher.h"
#include <ros/time.h>  


TimePublisher::TimePublisher():
  freeze_time_(true), 
  is_started_(false),
  publish_thread_(NULL),
  time_scale_factor_(1.0)
{}


TimePublisher::~TimePublisher()
{
  if (publish_thread_){
    publish_thread_->join(); // Wait for the thread to die before I kill the TimePublisher.
    delete publish_thread_;
  }
}

void TimePublisher::initialize(double publish_frequency, double time_scale_factor)
{

  // set frequency to publish
  publish_freq_ = publish_frequency;
  
  // We can't publish any time yet
  horizon_.fromSec(0.0);

  // advertise time topic
  time_pub = node_handle.advertise<roslib::Time>("time",1);
  publish_thread_ = new boost::thread(boost::bind(&TimePublisher::publishTime, this));


  time_scale_factor_ = time_scale_factor;
}

// Freeze time by repeatedly publishing the same time.
void TimePublisher::freezeTime()
{
  // lock
  boost::mutex::scoped_lock offset_lock(offset_mutex_);
  
  freeze_time_ = true;

  horizon_.fromSec(0.0);
}
  

// start time at bag timepoint bag_time
void TimePublisher::startTime(ros::Time bag_time) 
{
  // lock
  boost::mutex::scoped_lock offset_lock(offset_mutex_);
  
  // time is not frozen any more
  freeze_time_ = false;
  
  // get time we should publish
  last_pub_time_ = bag_time;

  // get system time when started
  last_sys_time_ = getSysTime();
  
  is_started_ = true;
}



void TimePublisher::stepTime(ros::Time bag_time) 
{
  assert(freeze_time_);
  
  // lock
  boost::mutex::scoped_lock offset_lock(offset_mutex_);
  
  // get time we should publish; 
  last_pub_time_ = bag_time;

  // get system time when started
  last_sys_time_ = getSysTime();

  // Reset horizon, to allow for publication of a time message while
  // stepping.
  horizon_ = last_sys_time_;
  
  is_started_ = true;
}

// Update the time up to which the publisher is allowed to run
void TimePublisher::setHorizon(ros::Time& horizon) 
{
  boost::mutex::scoped_lock offset_lock(offset_mutex_);
  horizon_ = horizon;
}

// Accessor, with lock
const ros::Time& TimePublisher::getHorizon()
{
  boost::mutex::scoped_lock offset_lock(offset_mutex_);
  return horizon_;
}
  

// get the system time
ros::Time TimePublisher::getSysTime()
{
  struct timeval timeofday;
  gettimeofday(&timeofday,NULL);
  return ros::Time().fromNSec(1e9*timeofday.tv_sec + 1e3*timeofday.tv_usec);
}



// publish time
void TimePublisher::publishTime()
{
  roslib::Time pub_msg; 
  while(node_handle.ok()) {  
    if (is_started_){
      ros::Time now = getSysTime();
      // Are we allowed to publish this time yet?
      while(((now - getHorizon()) > ros::Duration(0,100000)) && node_handle.ok())
      {
        usleep(1000);
        now = getSysTime();
      }

      {
        boost::mutex::scoped_lock offset_lock(offset_mutex_);
        pub_msg.rostime = last_pub_time_ + 
                ((now - last_sys_time_) * time_scale_factor_);
        last_sys_time_ = now;
        last_pub_time_ = pub_msg.rostime;
      }
      time_pub.publish(pub_msg);
    }
    usleep(1e6 / (publish_freq_ * time_scale_factor_));
  }
}
