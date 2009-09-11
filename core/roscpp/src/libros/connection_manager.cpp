/*
 * Copyright (C) 2009, Willow Garage, Inc.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *   * Redistributions of source code must retain the above copyright notice,
 *     this list of conditions and the following disclaimer.
 *   * Redistributions in binary form must reproduce the above copyright
 *     notice, this list of conditions and the following disclaimer in the
 *     documentation and/or other materials provided with the distribution.
 *   * Neither the names of Willow Garage, Inc. nor the names of its
 *     contributors may be used to endorse or promote products derived from
 *     this software without specific prior written permission.
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

#include "ros/connection_manager.h"
#include "ros/poll_manager.h"
#include "ros/connection.h"
#include "ros/subscriber_link.h"
#include "ros/service_client_link.h"
#include "ros/transport/transport_tcp.h"
#include "ros/transport/transport_udp.h"

#include <ros/assert.h>

namespace ros
{

ConnectionManagerPtr g_connection_manager;
boost::mutex g_connection_manager_mutex;
const ConnectionManagerPtr& ConnectionManager::instance()
{
  if (!g_connection_manager)
  {
    boost::mutex::scoped_lock lock(g_connection_manager_mutex);
    if (!g_connection_manager)
    {
      g_connection_manager.reset(new ConnectionManager);
    }
  }

  return g_connection_manager;
}

ConnectionManager::ConnectionManager()
: connection_id_counter_(0)
{
  ROS_DEBUG("ConnectionManager constructor");

}

ConnectionManager::~ConnectionManager()
{
  ROS_DEBUG("ConnectionManager destructor");
  shutdown();
}

void ConnectionManager::start()
{
  poll_manager_ = PollManager::instance();
  poll_conn_ = poll_manager_->addPollThreadListener(boost::bind(&ConnectionManager::removeDroppedConnections, this));

  // Bring up the TCP listener socket
  tcpserver_transport_ = TransportTCPPtr(new TransportTCP(&poll_manager_->getPollSet()));
  if (!tcpserver_transport_->listen(0, MAX_TCPROS_CONN_QUEUE, boost::bind(&ConnectionManager::tcprosAcceptConnection, this, _1)))
  {
    ROS_FATAL("Listen failed");
    ROS_BREAK();
  }

  // Bring up the UDP listener socket
  udpserver_transport_ = TransportUDPPtr(new TransportUDP(&poll_manager_->getPollSet()));
  if (!udpserver_transport_->createIncoming(0, true))
  {
    ROS_FATAL("Listen failed");
    ROS_BREAK();
  }
}

void ConnectionManager::shutdown()
{
  if (udpserver_transport_)
  {
    udpserver_transport_->close();
    udpserver_transport_.reset();
  }

  if (tcpserver_transport_)
  {
    tcpserver_transport_->close();
    tcpserver_transport_.reset();
  }

  poll_manager_->removePollThreadListener(poll_conn_);

  clear();
}

void ConnectionManager::clear()
{
  boost::mutex::scoped_lock conn_lock(connections_mutex_);
  for(S_Connection::iterator itr = connections_.begin();
      itr != connections_.end();
      itr++)
  {
    const ConnectionPtr& conn = *itr;
    conn->drop();
  }

  boost::mutex::scoped_lock dropped_lock(dropped_connections_mutex_);
  dropped_connections_.clear();
}

uint32_t ConnectionManager::getTCPPort()
{
  return tcpserver_transport_->getServerPort();
}

uint32_t ConnectionManager::getUDPPort()
{
  return udpserver_transport_->getServerPort();
}

uint32_t ConnectionManager::getNewConnectionID()
{
  boost::mutex::scoped_lock lock(connection_id_counter_mutex_);
  uint32_t ret = connection_id_counter_++;
  return ret;
}

void ConnectionManager::addConnection(const ConnectionPtr& conn)
{
  boost::mutex::scoped_lock lock(connections_mutex_);

  connections_.insert(conn);
  conn->addDropListener(boost::bind(&ConnectionManager::onConnectionDropped, this, _1));
}

void ConnectionManager::onConnectionDropped(const ConnectionPtr& conn)
{
  boost::mutex::scoped_lock lock(dropped_connections_mutex_);
  dropped_connections_.push_back(conn);
}

void ConnectionManager::removeDroppedConnections()
{
  V_Connection local_dropped;
  {
    boost::mutex::scoped_lock dropped_lock(dropped_connections_mutex_);
    dropped_connections_.swap(local_dropped);
  }

  boost::mutex::scoped_lock conn_lock(connections_mutex_);

  V_Connection::iterator conn_it = local_dropped.begin();
  V_Connection::iterator conn_end = local_dropped.end();
  for (;conn_it != conn_end; ++conn_it)
  {
    const ConnectionPtr& conn = *conn_it;

    size_t prev_size = connections_.size();
    connections_.erase(conn);
    ROS_ASSERT(connections_.size() == (prev_size - 1));
  }
}

void ConnectionManager::udprosIncomingConnection(const TransportUDPPtr& transport, Header& header)
{
  std::string client_uri = ""; // TODO: transport->getClientURI();
  ROS_DEBUG("UDPROS received a connection from [%s]", client_uri.c_str());

  ConnectionPtr conn(new Connection());
  addConnection(conn);

  conn->initialize(transport, true, NULL);
  onConnectionHeaderReceived(conn, header);
}

void ConnectionManager::tcprosAcceptConnection(const TransportTCPPtr& transport)
{
  std::string client_uri = transport->getClientURI();
  ROS_DEBUG("TCPROS received a connection from [%s]", client_uri.c_str());

  ConnectionPtr conn(new Connection());
  addConnection(conn);

  conn->initialize(transport, true, boost::bind(&ConnectionManager::onConnectionHeaderReceived, this, _1, _2));
}

bool ConnectionManager::onConnectionHeaderReceived(const ConnectionPtr& conn, const Header& header)
{
  bool ret = false;
  std::string val;
  if (header.getValue("topic", val))
  {
    ROS_DEBUG("Connection: Creating SubscriberLink for topic [%s] connected to [%s]", val.c_str(), conn->getTransport()->getTransportInfo().c_str());

    SubscriberLinkPtr sub_link(new SubscriberLink());
    sub_link->initialize(conn);
    ret = sub_link->handleHeader(header);
  }
  else if (header.getValue("service", val))
  {
    ROS_DEBUG("Connection: Creating ServiceClientLink for service [%s] connected to [%s]", val.c_str(), conn->getTransport()->getTransportInfo().c_str());

    ServiceClientLinkPtr link(new ServiceClientLink());
    link->initialize(conn);
    ret = link->handleHeader(header);
  }
  else
  {
    ROS_ERROR("Got a connection for a type other than 'topic' or 'service'.  Fail.");
    return false;
  }

  return ret;
}

}
