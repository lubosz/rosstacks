/*
 * Copyright (c) 2008, Willow Garage, Inc.
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 *     * Redistributions of source code must retain the above copyright
 *       notice, this list of conditions and the following disclaimer.
 *     * Redistributions in binary form must reproduce the above copyright
 *       notice, this list of conditions and the following disclaimer in the
 *       documentation and/or other materials provided with the distribution.
 *     * Neither the name of Willow Garage, Inc. nor the names of its
 *       contributors may be used to endorse or promote products derived from
 *       this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
 * ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
 * LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
 * CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 * SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 * CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 */

/* Author: Josh Faust */

/*
 * Test handles
 */

#include <string>
#include <sstream>
#include <fstream>

#include <gtest/gtest.h>

#include <time.h>
#include <stdlib.h>

#include "ros/ros.h"
#include "ros/node.h"
#include "ros/callback_queue.h"
#include <test_roscpp/TestArray.h>
#include <test_roscpp/TestStringString.h>

using namespace ros;
using namespace test_roscpp;

TEST(RoscppHandles, nodeHandleConstructionDestruction)
{
  {
    ASSERT_FALSE(ros::Node::instance());

    ros::NodeHandle n1;
    ASSERT_TRUE(ros::Node::instance());

    {
      ros::NodeHandle n2;
      ASSERT_TRUE(ros::Node::instance());

      {
        ros::NodeHandle n3(n2);
        ASSERT_TRUE(ros::Node::instance());

        {
          ros::NodeHandle n4 = n3;
          ASSERT_TRUE(ros::Node::instance());
        }
      }
    }

    ASSERT_TRUE(ros::Node::instance());
  }

  ASSERT_FALSE(ros::Node::instance());

  {
    ros::NodeHandle n;
    ASSERT_TRUE(ros::Node::instance());
  }

  ASSERT_FALSE(ros::Node::instance());
}

int32_t g_recv_count = 0;
void subscriberCallback(const test_roscpp::TestArray::ConstPtr& msg)
{
  ++g_recv_count;
}

class SubscribeHelper
{
public:
  SubscribeHelper()
  : recv_count_(0)
  {}

  void callback(const test_roscpp::TestArray::ConstPtr& msg)
  {
    ++recv_count_;
  }

  int32_t recv_count_;
};

TEST(RoscppHandles, subscriberValidity)
{
  ros::NodeHandle n;

  ros::Subscriber sub;
  ASSERT_FALSE(sub);

  sub = n.subscribe("test", 0, subscriberCallback);
  ASSERT_TRUE(sub);
}

TEST(RoscppHandles, subscriberDestructionMultipleCallbacks)
{
  ros::NodeHandle n;
  ros::Publisher pub = n.advertise<test_roscpp::TestArray>("test", 0);
  test_roscpp::TestArray msg;

  {
    SubscribeHelper helper;
    ros::Subscriber sub_class = n.subscribe("test", 0, &SubscribeHelper::callback, &helper);

    ros::Duration d(0.05);
    int32_t last_class_count = helper.recv_count_;
    while (last_class_count == helper.recv_count_)
    {
      pub.publish(msg);
      ros::spinOnce();
      d.sleep();
    }

    int32_t last_fn_count = g_recv_count;
    {
      ros::Subscriber sub_fn = n.subscribe("test", 0, subscriberCallback);

      ASSERT_TRUE(sub_fn != sub_class);

      last_fn_count = g_recv_count;
      while (last_fn_count == g_recv_count)
      {
        pub.publish(msg);
        ros::spinOnce();
        d.sleep();
      }
    }

    last_fn_count = g_recv_count;
    last_class_count = helper.recv_count_;
    while (last_class_count == helper.recv_count_)
    {
      pub.publish(msg);
      ros::spinOnce();
      d.sleep();
    }
    d.sleep();

    ASSERT_EQ(last_fn_count, g_recv_count);
  }
}

TEST(RoscppHandles, subscriberCopy)
{
  ros::NodeHandle n;

  g_recv_count = 0;

  {
    ros::Subscriber sub1 = n.subscribe("/test", 0, subscriberCallback);

    {
      ros::Subscriber sub2 = sub1;

      {
        ros::Subscriber sub3(sub2);

        ASSERT_TRUE(sub3 == sub2);

        V_string topics;
        n.getSubscribedTopics(topics);
        ASSERT_TRUE(std::find(topics.begin(), topics.end(), "/test") != topics.end());
      }

      ASSERT_TRUE(sub2 == sub1);

      V_string topics;
      n.getSubscribedTopics(topics);
      ASSERT_TRUE(std::find(topics.begin(), topics.end(), "/test") != topics.end());
    }

    V_string topics;
    n.getSubscribedTopics(topics);
    ASSERT_TRUE(std::find(topics.begin(), topics.end(), "/test") != topics.end());
  }

  V_string topics;
  n.getSubscribedTopics(topics);
  ASSERT_TRUE(std::find(topics.begin(), topics.end(), "/test") == topics.end());
}

TEST(RoscppHandles, publisherCopy)
{
  ros::NodeHandle n;

  g_recv_count = 0;

  {
    ros::Publisher pub1 = n.advertise<test_roscpp::TestArray>("/test", 0);

    {
      ros::Publisher pub2 = pub1;

      {
        ros::Publisher pub3(pub2);

        ASSERT_TRUE(pub3 == pub2);

        V_string topics;
        n.getAdvertisedTopics(topics);
        ASSERT_TRUE(std::find(topics.begin(), topics.end(), "/test") != topics.end());
      }

      ASSERT_TRUE(pub2 == pub1);

      V_string topics;
      n.getAdvertisedTopics(topics);
      ASSERT_TRUE(std::find(topics.begin(), topics.end(), "/test") != topics.end());
    }

    V_string topics;
    n.getAdvertisedTopics(topics);
    ASSERT_TRUE(std::find(topics.begin(), topics.end(), "/test") != topics.end());
  }

  V_string topics;
  n.getAdvertisedTopics(topics);
  ASSERT_TRUE(std::find(topics.begin(), topics.end(), "/test") == topics.end());
}

TEST(RoscppHandles, publisherMultiple)
{
  ros::NodeHandle n;

  g_recv_count = 0;

  {
    ros::Publisher pub1 = n.advertise<test_roscpp::TestArray>("/test", 0);

    {
      ros::Publisher pub2 = n.advertise<test_roscpp::TestArray>("/test", 0);

      ASSERT_TRUE(pub1 != pub2);

      V_string topics;
      n.getAdvertisedTopics(topics);
      ASSERT_TRUE(std::find(topics.begin(), topics.end(), "/test") != topics.end());
    }

    V_string topics;
    n.getAdvertisedTopics(topics);
    ASSERT_TRUE(std::find(topics.begin(), topics.end(), "/test") != topics.end());
  }

  V_string topics;
  n.getAdvertisedTopics(topics);
  ASSERT_TRUE(std::find(topics.begin(), topics.end(), "/test") == topics.end());
}

bool serviceCallback(TestStringString::Request& req, TestStringString::Response& res)
{
  return true;
}

void pump(ros::CallbackQueue* queue)
{
  while (queue->isEnabled())
  {
    queue->callAvailable();
  }
}

TEST(RoscppHandles, serviceAdv)
{
  ros::NodeHandle n;
  TestStringString t;

  ros::CallbackQueue queue;
  n.setCallbackQueue(&queue);
  boost::thread th(boost::bind(pump, &queue));
  {
    ros::ServiceServer srv = n.advertiseService("/test_srv", serviceCallback);

    ASSERT_TRUE(ros::service::call("/test_srv", t));
  }

  queue.disable();
  th.join();

  ASSERT_FALSE(ros::service::call("/test_srv", t));
}

TEST(RoscppHandles, serviceAdvCopy)
{
  ros::NodeHandle n;
  TestStringString t;

  ros::CallbackQueue queue;
  n.setCallbackQueue(&queue);
  boost::thread th(boost::bind(pump, &queue));

  {
    ros::ServiceServer srv1 = n.advertiseService("/test_srv", serviceCallback);

    {
      ros::ServiceServer srv2 = srv1;

      {
        ros::ServiceServer srv3(srv2);

        ASSERT_TRUE(srv3 == srv2);

        ASSERT_TRUE(ros::service::call("/test_srv", t));
      }

      ASSERT_TRUE(srv2 == srv1);

      ASSERT_TRUE(ros::service::call("/test_srv", t));
    }

    ASSERT_TRUE(ros::service::call("/test_srv", t));
  }

  ASSERT_FALSE(ros::service::call("/test_srv", t));

  queue.disable();
  th.join();
}

TEST(RoscppHandles, serviceAdvMultiple)
{
  ros::NodeHandle n;

  ros::ServiceServer srv = n.advertiseService("/test_srv", serviceCallback);
  ros::ServiceServer srv2 = n.advertiseService("/test_srv", serviceCallback);
  ASSERT_TRUE(srv);
  ASSERT_FALSE(srv2);

  ASSERT_TRUE(srv != srv2);
}

int32_t g_sub_count = 0;
void connectedCallback(const ros::SingleSubscriberPublisher& pub)
{
  ++g_sub_count;
}

TEST(RoscppHandles, trackedObjectWithAdvertiseSubscriberCallback)
{
  ros::NodeHandle n;

  boost::shared_ptr<char> tracked(new char);

  ros::Publisher pub = n.advertise<test_roscpp::TestArray>("/test", 0, connectedCallback, SubscriberStatusCallback(), tracked);

  g_recv_count = 0;
  ros::Subscriber sub = n.subscribe("/test", 0, subscriberCallback);

  Duration d(0.01);
  while (g_sub_count == 0)
  {
    d.sleep();
    ros::spinOnce();
  }
  ASSERT_EQ(g_sub_count, 1);

  sub.shutdown();

  tracked.reset();
  sub = n.subscribe("/test", 0, subscriberCallback);

  Duration d2(0.01);
  for (int i = 0; i < 10; ++i)
  {
    d2.sleep();
    ros::spinOnce();
  }

  ASSERT_EQ(g_sub_count, 1);
}

class ServiceClass
{
public:
  bool serviceCallback(TestStringString::Request& req, TestStringString::Response& res)
  {
    return true;
  }
};

TEST(RoscppHandles, trackedObjectWithServiceCallback)
{
  ros::NodeHandle n;

  ros::CallbackQueue queue;
  n.setCallbackQueue(&queue);
  boost::thread th(boost::bind(pump, &queue));

  boost::shared_ptr<ServiceClass> tracked(new ServiceClass);
  ros::ServiceServer srv = n.advertiseService("/test_srv", &ServiceClass::serviceCallback, tracked);

  TestStringString t;
  ASSERT_TRUE(ros::service::call("/test_srv", t));

  tracked.reset();

  ASSERT_FALSE(ros::service::call("/test_srv", t));

  queue.disable();
  th.join();
}

TEST(RoscppHandles, trackedObjectWithSubscriptionCallback)
{
  ros::NodeHandle n;

  boost::shared_ptr<SubscribeHelper> tracked(new SubscribeHelper);

  g_recv_count = 0;
  ros::Subscriber sub = n.subscribe("/test", 0, &SubscribeHelper::callback, tracked);

  ros::Publisher pub = n.advertise<test_roscpp::TestArray>("/test", 0);

  test_roscpp::TestArray msg;
  Duration d(0.01);
  while (tracked->recv_count_ == 0)
  {
    pub.publish(msg);
    d.sleep();
    ros::spinOnce();
  }
  ASSERT_GE(tracked->recv_count_, 1);

  tracked.reset();

  pub.publish(msg);
  Duration d2(0.01);
  for (int i = 0; i < 10; ++i)
  {
    d2.sleep();
    ros::spinOnce();
  }
}

TEST(RoscppHandles, nodeHandleNames)
{
  ros::NodeHandle n1;
  EXPECT_STREQ(n1.resolveName("blah").c_str(), "/blah");
  EXPECT_STREQ(n1.resolveName("~blah").c_str(), (ros::this_node::getName() + "/blah").c_str());

  ros::NodeHandle n2("internal_ns");
  EXPECT_STREQ(n2.resolveName("blah").c_str(), "/internal_ns/blah");
  EXPECT_STREQ(n2.resolveName("~blah").c_str(), (ros::this_node::getName() + "/internal_ns/blah").c_str());

  ros::NodeHandle n3(n2, "2");
  EXPECT_STREQ(n3.resolveName("blah").c_str(), "/internal_ns/2/blah");
  EXPECT_STREQ(n3.resolveName("~blah").c_str(), (ros::this_node::getName() + "/internal_ns/2/blah").c_str());
}

TEST(RoscppHandles, nodeHandleNameRemapping)
{
  M_string remap;
  remap["a"] = "b";
  remap["/a/a"] = "/a/b";
  remap["c"] = "/a/c";
  remap["d/d"] = "/c/e";
  remap["d/e"] = "c/f";
  remap["e"] = "~e";
  ros::NodeHandle n("", remap);

  EXPECT_STREQ(n.resolveName("a").c_str(), "/b");
  EXPECT_STREQ(n.resolveName("/a/a").c_str(), "/a/b");
  EXPECT_STREQ(n.resolveName("c").c_str(), "/a/c");
  EXPECT_STREQ(n.resolveName("d/d").c_str(), "/c/e");
  EXPECT_STREQ(n.resolveName("e").c_str(), (ros::this_node::getName() + "/e").c_str());

  ros::NodeHandle n2("z", remap);
  EXPECT_STREQ(n2.resolveName("a").c_str(), "/z/b");
  EXPECT_STREQ(n2.resolveName("/a/a").c_str(), "/a/b");
  EXPECT_STREQ(n2.resolveName("c").c_str(), "/a/c");
  EXPECT_STREQ(n2.resolveName("d/d").c_str(), "/c/e");
  EXPECT_STREQ(n2.resolveName("d/e").c_str(), "/z/c/f");
  EXPECT_STREQ(n2.resolveName("e").c_str(), (ros::this_node::getName() + "/z/e").c_str());
}

TEST(RoscppHandles, nodeHandleShutdown)
{
  ros::NodeHandle n;

  ros::Subscriber sub = n.subscribe("/test", 0, subscriberCallback);
  ros::Publisher pub = n.advertise<test_roscpp::TestArray>("/test", 0);
  ros::ServiceServer srv = n.advertiseService("/test_srv", serviceCallback);

  n.shutdown();

  ASSERT_FALSE(pub);
  ASSERT_FALSE(sub);
  ASSERT_FALSE(srv);
}

TEST(RoscppHandles, deprecatedAPIAutoSpin)
{
  new ros::Node("test");

  {
    ros::NodeHandle n;
    ros::Subscriber sub = n.subscribe("/test", 0, subscriberCallback);
    ros::Publisher pub = n.advertise<test_roscpp::TestArray>("/test", 0);

    g_recv_count = 0;
    test_roscpp::TestArray msg;
    while (g_recv_count == 0)
    {
      pub.publish(msg);
      ros::Duration d(0.01);
      d.sleep();
    }
  }

  delete ros::Node::instance();
}

int main(int argc, char** argv)
{
  testing::InitGoogleTest(&argc, argv);
  ros::init(argc, argv, "test_handles");

  return RUN_ALL_TESTS();
}

