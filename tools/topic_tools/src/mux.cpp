///////////////////////////////////////////////////////////////////////////////
// demux is a generic ROS topic demultiplexer: one input topic is fanned out
// to 1 of N output topics. A service is provided to select between the outputs
//
// Copyright (C) 2009, Morgan Quigley
//
// Redistribution and use in source and binary forms, with or without
// modification, are permitted provided that the following conditions are met:
//   * Redistributions of source code must retain the above copyright notice,
//     this list of conditions and the following disclaimer.
//   * Redistributions in binary form must reproduce the above copyright
//     notice, this list of conditions and the following disclaimer in the
//     documentation and/or other materials provided with the distribution.
//   * Neither the name of Stanford University nor the names of its
//     contributors may be used to endorse or promote products derived from
//     this software without specific prior written permission.
//
// THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
// AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
// IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
// ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
// LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
// CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
// SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
// INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
// CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
// ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
// POSSIBILITY OF SUCH DAMAGE.
/////////////////////////////////////////////////////////////////////////////


#include <cstdio>
#include <vector>
#include <list>
#include "ros/console.h"
#include "std_msgs/String.h"
#include "topic_tools/MuxSelect.h"
#include "topic_tools/MuxAdd.h"
#include "topic_tools/MuxList.h"
#include "topic_tools/MuxDelete.h"
#include "topic_tools/shape_shifter.h"
#include "topic_tools/parse.h"

using std::string;
using std::vector;
using std::list;
using namespace topic_tools;

const static string g_none_topic = "__none";
static ShapeShifter *g_selected = NULL;
static ros::NodeHandle *g_node = NULL;
static bool g_advertised = false;
static string g_output_topic;
static ros::Publisher g_pub;
static ros::Publisher g_pub_selected;

struct sub_info_t
{
  ros::Subscriber sub;
  ShapeShifter* msg;
};
static list<struct sub_info_t> g_subs;


bool sel_srv_cb( topic_tools::MuxSelect::Request  &req,
                 topic_tools::MuxSelect::Response &res )
{
  bool ret = false;
  if (g_selected)
    res.prev_topic = g_selected->topic;
  else
    res.prev_topic = string("");
  // see if it's the magical '__none' topic, in which case we open the circuit
  if (req.topic == g_none_topic)
  {
    ROS_INFO("mux selected to no input.");
    g_selected = NULL;
    ret = true;
  }
  else
  {
    ROS_INFO("trying to switch mux to %s", req.topic.c_str());
    // spin through our vector of inputs and find this guy
    for (list<struct sub_info_t>::iterator it = g_subs.begin();
	 it != g_subs.end();
	 ++it)
    {
      if (it->msg->topic == req.topic)
      {
	g_selected = it->msg;
	ROS_INFO("mux selected input: [%s]", it->msg->topic.c_str());
	ret = true;
      }
    }
  }

  if(ret)
  {
    std_msgs::String t;
    t.data = req.topic;
    g_pub_selected.publish(t);
  }

  return ret;
}

bool sel_srv_cb_dep( topic_tools::MuxSelect::Request  &req,
		     topic_tools::MuxSelect::Response &res )
{
  ROS_WARN("the <topic>_select service is deprecated; use mux/select instead");
  return sel_srv_cb(req,res);
}


void in_cb(const boost::shared_ptr<ShapeShifter const>& msg,
           ShapeShifter* s)
{
  if (!g_advertised)
  {
    ROS_INFO("advertising");
    g_pub = msg->advertise(*g_node, g_output_topic, 10);
    g_advertised = true;
  }
  if (s == g_selected)
    g_pub.publish(msg);
}

bool list_topic_cb(topic_tools::MuxList::Request& req,
	 	   topic_tools::MuxList::Response& res)
{
  for (list<struct sub_info_t>::iterator it = g_subs.begin();
       it != g_subs.end();
       ++it)
  {
    res.topics.push_back(it->msg->topic);
  }

  return true;
}

bool add_topic_cb(topic_tools::MuxAdd::Request& req,
		  topic_tools::MuxAdd::Response& res)
{
  // Check that it's not already in our list
  ROS_INFO("trying to add %s to mux", req.topic.c_str());
  
  // Can't add the __none topic
  if(req.topic == g_none_topic)
  {
    ROS_WARN("failed to add topic %s to mux, because it's reserved for special use",
	     req.topic.c_str());
    return false;
  }

  // spin through our vector of inputs and find this guy
  for (list<struct sub_info_t>::iterator it = g_subs.begin();
       it != g_subs.end();
       ++it)
  {
    if (it->msg->topic == req.topic)
    {
      ROS_WARN("tried to add a topic that mux was already listening to: [%s]", 
	       it->msg->topic.c_str());
      return false;
    }
  }

  struct sub_info_t sub_info;
  try
  {
    sub_info.sub = g_node->subscribe<ShapeShifter>(req.topic, 10, boost::bind(in_cb, _1, sub_info.msg));
  }
  catch(ros::InvalidNameException& e)
  {
    ROS_WARN("failed to add topic %s to mux, because it's an invalid name: %s",
	     req.topic.c_str(), e.what());
    return false;
  }

  sub_info.msg = new ShapeShifter;
  sub_info.msg->topic = req.topic;
  g_subs.push_back(sub_info);

  ROS_INFO("added %s to mux", req.topic.c_str());

  return true;
}

bool del_topic_cb(topic_tools::MuxDelete::Request& req,
		  topic_tools::MuxDelete::Response& res)
{
  // Check that it's in our list
  ROS_INFO("trying to delete %s from mux", req.topic.c_str());
  // spin through our vector of inputs and find this guy
  for (list<struct sub_info_t>::iterator it = g_subs.begin();
       it != g_subs.end();
       ++it)
  {
    if (it->msg->topic == req.topic)
    {
      it->sub.shutdown();
      delete it->msg;
      g_subs.erase(it);
      ROS_INFO("deleted topic %s from mux", req.topic.c_str());
      return true;
    }
  }

  ROS_WARN("tried to delete non-subscribed topic %s from mux", req.topic.c_str());
  return false;
}

int main(int argc, char **argv)
{
  vector<string> args;
  ros::removeROSArgs(argc, (const char**)argv, args);

  if (args.size() < 3)
  {
    printf("\nusage: mux OUT_TOPIC IN_TOPIC1 [IN_TOPIC2 [...]]\n\n");
    return 1;
  }
  std::string topic_name;
  if(!getBaseName(args[1], topic_name))
    return 1;
  ros::init(argc, argv, topic_name + string("_mux"),
            ros::init_options::AnonymousName);
  vector<string> topics;
  for (unsigned int i = 2; i < args.size(); i++)
    topics.push_back(args[i]);
  ros::NodeHandle n;
  g_node = &n;
  g_output_topic = args[1];
  // Put our API into the "mux" namespace, which the user should usually remap
  ros::NodeHandle mux_nh("mux");
  // Latched publisher for selected input topic name
  g_pub_selected = mux_nh.advertise<std_msgs::String>(string("selected"), 1, true);
  // Backward compatibility
  ros::ServiceServer ss = n.advertiseService(g_output_topic + string("_select"), sel_srv_cb_dep);
  // New service
  ros::ServiceServer ss_select = mux_nh.advertiseService(string("select"), sel_srv_cb);
  ros::ServiceServer ss_add = mux_nh.advertiseService(string("add"), add_topic_cb);
  ros::ServiceServer ss_list = mux_nh.advertiseService(string("list"), list_topic_cb);
  ros::ServiceServer ss_del = mux_nh.advertiseService(string("delete"), del_topic_cb);
  for (size_t i = 0; i < topics.size(); i++)
  {
    struct sub_info_t sub_info;
    sub_info.msg = new ShapeShifter;
    sub_info.msg->topic = topics[i];
    sub_info.sub = n.subscribe<ShapeShifter>(topics[i], 10, boost::bind(in_cb, _1, sub_info.msg));
    g_subs.push_back(sub_info);
  }
  g_selected = g_subs.front().msg; // select first topic to start
  std_msgs::String t;
  t.data = g_selected->topic;
  g_pub_selected.publish(t);
  ros::spin();
  for (list<struct sub_info_t>::iterator it = g_subs.begin();
       it != g_subs.end();
       ++it)
  {
    it->sub.shutdown();
    delete it->msg;
  }

  g_subs.clear();
  return 0;
}

