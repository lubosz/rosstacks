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

#ifndef ROSBAG_TIME_PUBLISHER_H
#define ROSBAG_TIME_PUBLISHER_H

#include <ros/ros.h>
#include <ros/time.h>

#include <iostream>
#include <sys/time.h>

#include <boost/bind.hpp>
#include <boost/thread/condition.hpp>
#include <boost/thread/mutex.hpp>
#include <boost/thread/thread.hpp>

namespace rosbag
{

class TimePublisher
{
public:
    TimePublisher();
    ~TimePublisher();

    //! Initialize publisher
    void initialize(double publish_frequency, double time_scale_factor = 1.0);

    //! Freeze time by publishing the repeatedly publishing the same time
    void freezeTime();

    //! Start time at bag timepoint bag_time
    void startTime(ros::Time bag_time);

    //! Step the timepoint bag_time
    void stepTime(ros::Time bag_time);

    //! Update the time up to which the publisher is allowed to run
    void setHorizon(ros::Time& horizon);

private:
    ros::Time        getSysTime();       //!< get the system time
    void             publishTime();      //!< publish time
    const ros::Time& getHorizon();       //!< accessor, with lock

private:
    double          publish_freq_;
    ros::NodeHandle node_handle;
    ros::Publisher  time_pub_;
    ros::Time       horizon_;            //!< time that we're allowed to publish until
    ros::Time       last_pub_time_;      //!< a time in the bag's time
    ros::Time       last_sys_time_;      //!< start/restart time at playback
    bool            freeze_time_;        //!< stop time
    bool            is_started_;
    boost::mutex    offset_mutex_;
    boost::thread*  publish_thread_;
    double          time_scale_factor_;

    volatile bool continue_;
};

}

#endif
