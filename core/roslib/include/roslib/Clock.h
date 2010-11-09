#warning("This header has been deprecated in favor of rosgraph_msgs/Clock.h")

/* Auto-generated by genmsg_cpp for file /Users/kwc/ros/core/roslib/msg/Clock.msg */
#ifndef ROSLIB_MESSAGE_CLOCK_H
#define ROSLIB_MESSAGE_CLOCK_H
#include <string>
#include <vector>
#include <ostream>
#include "ros/serialization.h"
#include "ros/builtin_message_traits.h"
#include "ros/message_operations.h"
#include "ros/message.h"
#include "ros/time.h"


namespace roslib
{
template <class ContainerAllocator>
struct Clock_ : public ros::Message
{
  typedef Clock_<ContainerAllocator> Type;

  Clock_()
  : clock()
  {
  }

  Clock_(const ContainerAllocator& _alloc)
  : clock()
  {
  }

  typedef ros::Time _clock_type;
  ros::Time clock;


private:
  static const char* __s_getDataType_() { return "roslib/Clock"; }
public:
  ROSCPP_DEPRECATED static const std::string __s_getDataType() { return __s_getDataType_(); }

  ROSCPP_DEPRECATED const std::string __getDataType() const { return __s_getDataType_(); }

private:
  static const char* __s_getMD5Sum_() { return "a9c97c1d230cfc112e270351a944ee47"; }
public:
  ROSCPP_DEPRECATED static const std::string __s_getMD5Sum() { return __s_getMD5Sum_(); }

  ROSCPP_DEPRECATED const std::string __getMD5Sum() const { return __s_getMD5Sum_(); }

private:
  static const char* __s_getMessageDefinition_() { return "# roslib/Clock is used for publishing simulated time in ROS. \n\
# This message simply communicates the current time.\n\
# For more information, see http://www.ros.org/wiki/Clock\n\
time clock\n\
\n\
"; }
public:
  ROSCPP_DEPRECATED static const std::string __s_getMessageDefinition() { return __s_getMessageDefinition_(); }

  ROSCPP_DEPRECATED const std::string __getMessageDefinition() const { return __s_getMessageDefinition_(); }

  ROSCPP_DEPRECATED virtual uint8_t *serialize(uint8_t *write_ptr, uint32_t seq) const
  {
    ros::serialization::OStream stream(write_ptr, 1000000000);
    ros::serialization::serialize(stream, clock);
    return stream.getData();
  }

  ROSCPP_DEPRECATED virtual uint8_t *deserialize(uint8_t *read_ptr)
  {
    ros::serialization::IStream stream(read_ptr, 1000000000);
    ros::serialization::deserialize(stream, clock);
    return stream.getData();
  }

  ROSCPP_DEPRECATED virtual uint32_t serializationLength() const
  {
    uint32_t size = 0;
    size += ros::serialization::serializationLength(clock);
    return size;
  }

  typedef boost::shared_ptr< ::roslib::Clock_<ContainerAllocator> > Ptr;
  typedef boost::shared_ptr< ::roslib::Clock_<ContainerAllocator>  const> ConstPtr;
}; // struct Clock
typedef  ::roslib::Clock_<std::allocator<void> > Clock;

typedef boost::shared_ptr< ::roslib::Clock> ClockPtr;
typedef boost::shared_ptr< ::roslib::Clock const> ClockConstPtr;


template<typename ContainerAllocator>
std::ostream& operator<<(std::ostream& s, const  ::roslib::Clock_<ContainerAllocator> & v)
{
  ros::message_operations::Printer< ::roslib::Clock_<ContainerAllocator> >::stream(s, "", v);
  return s;}

} // namespace roslib

namespace ros
{
namespace message_traits
{
template<class ContainerAllocator>
struct MD5Sum< ::roslib::Clock_<ContainerAllocator> > {
  static const char* value() 
  {
    return "a9c97c1d230cfc112e270351a944ee47";
  }

  static const char* value(const  ::roslib::Clock_<ContainerAllocator> &) { return value(); } 
  static const uint64_t static_value1 = 0xa9c97c1d230cfc11ULL;
  static const uint64_t static_value2 = 0x2e270351a944ee47ULL;
};

template<class ContainerAllocator>
struct DataType< ::roslib::Clock_<ContainerAllocator> > {
  static const char* value() 
  {
    return "roslib/Clock";
  }

  static const char* value(const  ::roslib::Clock_<ContainerAllocator> &) { return value(); } 
};

template<class ContainerAllocator>
struct Definition< ::roslib::Clock_<ContainerAllocator> > {
  static const char* value() 
  {
    return "# roslib/Clock is used for publishing simulated time in ROS. \n\
# This message simply communicates the current time.\n\
# For more information, see http://www.ros.org/wiki/Clock\n\
time clock\n\
\n\
";
  }

  static const char* value(const  ::roslib::Clock_<ContainerAllocator> &) { return value(); } 
};

template<class ContainerAllocator> struct IsFixedSize< ::roslib::Clock_<ContainerAllocator> > : public TrueType {};
} // namespace message_traits
} // namespace ros

namespace ros
{
namespace serialization
{

template<class ContainerAllocator> struct Serializer< ::roslib::Clock_<ContainerAllocator> >
{
  template<typename Stream, typename T> inline static void allInOne(Stream& stream, T m)
  {
    stream.next(m.clock);
  }

  ROS_DECLARE_ALLINONE_SERIALIZER;
}; // struct Clock_
} // namespace serialization
} // namespace ros

namespace ros
{
namespace message_operations
{

template<class ContainerAllocator>
struct Printer< ::roslib::Clock_<ContainerAllocator> >
{
  template<typename Stream> static void stream(Stream& s, const std::string& indent, const  ::roslib::Clock_<ContainerAllocator> & v) 
  {
    s << indent << "clock: ";
    Printer<ros::Time>::stream(s, indent + "  ", v.clock);
  }
};


} // namespace message_operations
} // namespace ros

#endif // ROSLIB_MESSAGE_CLOCK_H

