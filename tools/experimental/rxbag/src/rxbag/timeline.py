# Software License Agreement (BSD License)
#
# Copyright (c) 2009, Willow Garage, Inc.
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

from __future__ import with_statement

PKG = 'rxbag'
import roslib; roslib.load_manifest(PKG)
import rospy

import rosrecord

import bisect
import collections
import math
import os
import threading
import time

import wx

from util.base_frame import BaseFrame
from util.layer import Layer, LayerPanel
import playhead
import plugins
import status

from raw_view import RawView

from bag_index import BagIndex, BagIndexFactory, BagIndexPickler, BagIndexReader

class TimelinePanel(LayerPanel):
    def __init__(self, input_files, options, *args, **kwargs):
        LayerPanel.__init__(self, *args, **kwargs)
        
        self.bag_files = {}

        if not self._init_bag_files(input_files):
            raise Exception('No valid bag files')

        self._create_controls(options)
        self._create_toolbar()

    def _init_bag_files(self, input_files):
        unindexed = []

        for i, bag_path in enumerate(input_files):
            try:
                bag_file = rosrecord.BagReader(bag_path)
            except Exception, e:
                print 'Error loading %s: %s' % (bag_path, e)
                continue
            
            # Try to read the index directly from the bag file, or hit the index if not found
            idx = BagIndexReader(bag_path).load()
            if idx is None:
                idx = BagIndexPickler(bag_path + '.index').load()

            if idx is not None:
                bag_file.read_datatype_defs(idx)

                self.bag_files[bag_file] = idx
                
                print '%s\n%s\n%s' % (bag_path, '-' * len(bag_path), idx)
            else:
                unindexed.append(bag_path)
                
        if len(unindexed) + len(self.bag_files) == 0:
            return False

        for bag_path in unindexed:
            self._index_bag_file(bag_path, bag_path + '.index')
            
        return True

    def _index_bag_file(self, bag_path, index_path):
        rospy.loginfo('Index not found - indexing...')
        
        bag_index_factory = BagIndexFactory(bag_path)
        
        bag_index = bag_index_factory.index
        
        bag_file = rosrecord.BagReader(bag_path)
        self.bag_files[bag_file] = bag_index
        
        # Background thread to generate, then save the index
        class BagIndexFactoryThread(threading.Thread):
            def __init__(self, bag_index_factory):
                threading.Thread.__init__(self)
                self.bag_index_factory = bag_index_factory

            def run(self):
                if self.bag_index_factory.load():
                    BagIndexPickler(self.bag_index_factory.bag_path + '.index').save(self.bag_index_factory.index)
                    
                    print self.bag_index_factory.index

        self.bag_index_factory_thread = BagIndexFactoryThread(bag_index_factory)
        self.bag_index_factory_thread.start()

    def _create_controls(self, options):
        (width, height) = self.GetParent().GetClientSize()

        x, y = 5, 19

        self.timeline = Timeline(self, 'Timeline', x, y, width - x, height - y, max_repaint=1.0)
        self.timeline.set_bag_files(self.bag_files)

        self.status = status.StatusLayer(self, 'Status', self.timeline, self.timeline.x, 0, 300, 20)

        self.playhead = playhead.PlayheadLayer(self, 'Playhead', self.timeline, 0, 0, 12, self.timeline.height)

        self.layers = [self.timeline, self.status, self.playhead]

    def _create_toolbar(self):
        icons_dir = roslib.packages.get_pkg_dir(PKG) + '/icons/'

        tb = self.GetParent().CreateToolBar()

        start_tool       = tb.AddLabelTool(wx.ID_ANY, '', wx.Bitmap(icons_dir + 'control_start_blue.png'))
        rewind_tool      = tb.AddLabelTool(wx.ID_ANY, '', wx.Bitmap(icons_dir + 'control_rewind_blue.png'))
        play_tool        = tb.AddLabelTool(wx.ID_ANY, '', wx.Bitmap(icons_dir + 'control_play_blue.png'))
        fastforward_tool = tb.AddLabelTool(wx.ID_ANY, '', wx.Bitmap(icons_dir + 'control_fastforward_blue.png'))
        end_tool         = tb.AddLabelTool(wx.ID_ANY, '', wx.Bitmap(icons_dir + 'control_end_blue.png'))
        stop_tool        = tb.AddLabelTool(wx.ID_ANY, '', wx.Bitmap(icons_dir + 'control_stop_blue.png'))
        tb.AddSeparator()
        zoom_in_tool     = tb.AddLabelTool(wx.ID_ANY, '', wx.Bitmap(icons_dir + 'zoom_in.png'))
        zoom_out_tool    = tb.AddLabelTool(wx.ID_ANY, '', wx.Bitmap(icons_dir + 'zoom_out.png'))
        zoom_tool        = tb.AddLabelTool(wx.ID_ANY, '', wx.Bitmap(icons_dir + 'zoom.png'))
        tb.AddSeparator()
        thumbnails_tool  = tb.AddLabelTool(wx.ID_ANY, '', wx.Bitmap(icons_dir + 'pictures.png'))
        #tb.AddSeparator()
        #save_layout_tool = tb.AddLabelTool(wx.ID_ANY, '', wx.Bitmap(icons_dir + 'application_put.png'))
        #load_layout_tool = tb.AddLabelTool(wx.ID_ANY, '', wx.Bitmap(icons_dir + 'application_get.png'))

        tb.Bind(wx.EVT_TOOL, lambda e: self.timeline.navigate_start(),       start_tool)
        tb.Bind(wx.EVT_TOOL, lambda e: self.timeline.navigate_rewind(),      rewind_tool)
        tb.Bind(wx.EVT_TOOL, lambda e: self.timeline.navigate_play(),        play_tool)       
        tb.Bind(wx.EVT_TOOL, lambda e: self.timeline.navigate_fastforward(), fastforward_tool)       
        tb.Bind(wx.EVT_TOOL, lambda e: self.timeline.navigate_end(),         end_tool)
        tb.Bind(wx.EVT_TOOL, lambda e: self.timeline.navigate_stop(),        stop_tool)
        tb.Bind(wx.EVT_TOOL, lambda e: self.timeline.zoom_in(),              zoom_in_tool)
        tb.Bind(wx.EVT_TOOL, lambda e: self.timeline.zoom_out(),             zoom_out_tool)
        tb.Bind(wx.EVT_TOOL, lambda e: self.timeline.reset_zoom(),           zoom_tool)
        tb.Bind(wx.EVT_TOOL, lambda e: self.timeline.toggle_renderers(),     thumbnails_tool)
        #tb.Bind(wx.EVT_TOOL, lambda e: self.timeline.save_layout(),          save_layout_tool)
        #tb.Bind(wx.EVT_TOOL, lambda e: self.timeline.load_layout(),          load_layout_tool)

        tb.Realize()

class Timeline(Layer):
    name = 'Timeline'
    
    def __init__(self, parent, title, x, y, width, height, max_repaint=None):
        Layer.__init__(self, parent, title, x, y, width, height, max_repaint)

        self.bag_files = {}
        self.bag_file  = None
        self.bag_index = None

        ## Rendering parameters

        self.background_brush   = wx.Brush('white')
        self.topic_divider_pen  = wx.Pen('#dddddd', 1)
        self.topic_font_color   = wx.Colour(0, 0, 0)
        self.time_font_color    = wx.Colour(0, 0, 0)
        self.time_label_spacing = 6
        self.time_major_pen     = wx.Pen('#222222', 1, wx.SHORT_DASH)
        self.time_minor_pen     = wx.Pen('#aaaaaa', 1, wx.LONG_DASH)
        self.time_tick_pen      = wx.Pen('#888888', 1, wx.SHORT_DASH)
        self.time_tick_height   = 3

        self.sec_divisions = [0.001, 0.005, 0.01, 0.05, 0.1, 0.5,                                 # 1ms, 5ms, 10ms, 50ms, 100ms, 500ms
                              1, 5, 15, 30,                                                       # 1s, 5s, 15s, 30s
                              1 * 60, 2 * 60, 5 * 60, 10 * 60, 15 * 60, 30 * 60,                  # 1m, 2m, 5m, 10m, 15m, 30m
                              1 * 60 * 60, 2 * 60 * 60, 3 * 60 * 60, 6 * 60 * 60, 12 * 60 * 60,   # 1h, 2h, 3h, 6h, 12h
                              1 * 60 * 60 * 24, 7 * 60 * 60 * 24]                                 # 1d, 7d
        self.minor_spacing = 15
        self.major_spacing = 50

        self.topic_font        = wx.Font(9, wx.FONTFAMILY_SCRIPT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        self.topic_font_height = None
        self.topic_name_sizes  = None
        self.margin_left       = 0
        self.margin_right      = 20

        self.time_font        = wx.Font(9, wx.FONTFAMILY_SCRIPT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        self.time_font_height = None
        
        self.history_top        = 26
        self.history_border_pen = wx.Pen('black', 1)

        self.bag_end_width = 4
        self.bag_end_pen   = wx.Pen('black', 1)
        
        self.default_datatype_color = wx.Colour(0, 0, 0)
        self.datatype_colors = {
            'sensor_msgs/CameraInfo':            wx.Colour(  0,   0, 150),
            'sensor_msgs/Image':                 wx.Colour(  0,  80,  80),
            'sensor_msgs/LaserScan':             wx.Colour(150,   0,   0),
            'pr2_msgs/LaserScannerSignal':       wx.Colour(150,   0,   0),
            'pr2_mechanism_msgs/MechanismState': wx.Colour(  0, 150,   0),
            'tf/tfMessage':                      wx.Colour(  0, 150,   0),
        }
        self.default_msg_combine_px = 1.5

        self.zoom_sensitivity = 0.005
        self.min_zoom_speed   = 0.5
        self.max_zoom_speed   = 2.0
        self.min_zoom         = 0.0001      # max zoom out (in px/s)
        self.max_zoom         = 50000.0     # max zoom in  (in px/s)

        self.max_play_speed =  1024.0
        self.min_play_speed = -1024.0

        self.viewer_types       = {}
        self.timeline_renderers = {}
        self.rendered_topics    = set()

        self.load_plugins()

        ##

        self.clicked_pos = None

        self.history_left   = 0
        self.history_height = 0
        self.history_width  = 0
        self.history_bounds = {}

        self.stamp_left    = None
        self.stamp_right   = None
        self.playhead      = None
        self.playhead_lock = threading.Lock()
        
        self.views = []

        self.listeners = {}

        self.playhead_indices = None

        class PlayThread(threading.Thread):
            def __init__(self, timeline):
                threading.Thread.__init__(self)

                self.setDaemon(True)

                self.timeline  = timeline
                self.stop_flag = False

            def run(self):
                self.last_frame, self.last_playhead = None, None
                
                while not self.stop_flag:
                    wx.CallAfter(self.step)
                    time.sleep(0.05)

            def step(self):
                if self.timeline.play_speed == 0.0:
                    self.last_frame    = None
                    self.last_playhead = None
                else:
                    now = time.time()
                    if self.last_frame and self.timeline.playhead == self.last_playhead:
                        new_playhead = self.timeline.playhead + (now - self.last_frame) * self.timeline.play_speed
    
                        start_stamp, end_stamp = self.timeline.bag_index.start_stamp, self.timeline.bag_index.end_stamp
                        if new_playhead > end_stamp:
                            new_playhead = start_stamp
                        elif new_playhead < start_stamp:
                            new_playhead = end_stamp
    
                        self.timeline.set_playhead(new_playhead)

                    self.last_frame    = now
                    self.last_playhead = self.timeline.playhead

            def stop(self):
                self.stop_flag = True

        self.play_speed = 0.0

        self.play_thread = PlayThread(self)
        self.play_thread.start()

    def on_close(self, event):
        self.play_thread.stop()

    def save_layout(self):
        user_config_dir = wx.StandardPaths.Get().GetUserConfigDir()
        config_dir = os.path.join(user_config_dir, '.rxbag')
        if not os.path.exists(config_dir):
            os.mkdir(config_dir)
        layout_file = os.path.join(config_dir, 'layout')
        config = wx.Config(localFilename=layout_file)
        
        # TODO

        #for i, view in enumerate(self.views):
        #    config.Write('/Views/View%d' % (i + 1), view.__class__.__name__)
        #config.Flush()

    def load_layout(self):
        user_config_dir = wx.StandardPaths.Get().GetUserConfigDir()
        config_dir = os.path.join(user_config_dir, '.rxbag')
        if not os.path.exists(config_dir):
            return
        layout_file = os.path.join(config_dir, 'layout')
        config = wx.Config(localFilename=layout_file)
        
        # TODO

    def add_view(self, topic, view):
        self.views.append(view)
        self.add_listener(topic, view)

    def remove_view(self, topic, view):
        self.remove_listener(topic, view)
        self.views.remove(view)

    def get_viewer_types(self, datatype):
        return [RawView] + self.viewer_types.get('*', []) + self.viewer_types.get(datatype, [])
    
    def get_renderers(self):
        renderers = []

        for topic in self.topics:
            datatype = self.bag_index.get_datatype(topic)
            renderer = self.timeline_renderers.get(datatype)
            if renderer is not None:
                renderers.append((topic, renderer))
                
        return renderers

    def load_plugins(self):
        for msg_view, timeline_renderer, msg_types in plugins.load_plugins():
            for msg_type in msg_types:
                self.viewer_types.setdefault(msg_type, []).append(msg_view)
            if timeline_renderer is not None:
                self.timeline_renderers[msg_type] = timeline_renderer(self)

    def set_bag_files(self, bag_files):
        self.bag_files = bag_files
        
        # HACK
        self.bag_file  = list(self.bag_files)[0]
        self.bag_index = self.bag_files[self.bag_file]

    def is_renderer_active(self, topic):
        return topic in self.rendered_topics

    def toggle_renderers(self):
        idle_renderers = len(self.rendered_topics) < len(self.topics)
        
        self.set_renderers_active(idle_renderers)

    def set_renderers_active(self, active):
        if active:
            for topic in self.topics:
                self.rendered_topics.add(topic)
        else:
            self.rendered_topics.clear()

        self.force_repaint()
        self.parent.playhead.force_repaint()

    def set_renderer_active(self, topic, active):
        if active:
            if topic in self.rendered_topics:
                return
            self.rendered_topics.add(topic)
        else:
            if not topic in self.rendered_topics:
                return
            self.rendered_topics.remove(topic)
        
        self.force_repaint()
        self.parent.playhead.force_repaint()

    def add_listener(self, topic, listener):
        self.listeners.setdefault(topic, []).append(listener)

        self.update_message_view()

    def remove_listener(self, topic, listener):
        topic_listeners = self.listeners.get(topic)
        if not topic_listeners is None and listener in topic_listeners:
            topic_listeners.remove(listener)

    @property
    def topics(self):
        return sorted(self.bag_index.topics)

    @property
    def history_bottom(self):
        return self.history_top + self.history_height
    
    @property
    def history_right(self):
        return self.history_left + self.history_width

    def _set_status(self, status):
        self.parent.GetParent().SetStatusText(str(status))

    ## Navigation

    def navigate_play(self): self.play_speed = 1.0
    def navigate_stop(self): self.play_speed = 0.0

    def navigate_rewind(self):
        if self.play_speed <= -1.0:
            self.play_speed *= 2.0
        elif self.play_speed < 0.001:
            self.play_speed = -1.0
        else:
            self.play_speed *= 0.5
            
        self.play_speed = max(self.min_play_speed, self.play_speed)
        
    def navigate_fastforward(self):
        if self.play_speed >= 1.0:
            self.play_speed *= 2.0
        elif self.play_speed > -0.001:
            self.play_speed = 1.0
        else:
            self.play_speed *= 0.5

        self.play_speed = min(self.max_play_speed, self.play_speed)

    def navigate_start(self): self.set_playhead(self.bag_index.start_stamp)
    def navigate_end(self):   self.set_playhead(self.bag_index.end_stamp)

    ## View port

    def reset_timeline(self):
        self.reset_zoom() 
        self.set_playhead(self.stamp_left)
        
    def set_timeline_view(self, stamp_left, stamp_right):
        self.stamp_left  = stamp_left
        self.stamp_right = stamp_right

        self.force_repaint()

    def translate_timeline(self, dx):
        dstamp = self.map_dx_to_dstamp(dx)

        self.stamp_left  -= dstamp
        self.stamp_right -= dstamp

        self.force_repaint()

    def reset_zoom(self):
        self.set_timeline_view(self.bag_index.start_stamp, self.bag_index.end_stamp)

    def zoom_in(self):  self.zoom_timeline(0.5)
    def zoom_out(self): self.zoom_timeline(2.0)

    def zoom_timeline(self, zoom):
        new_stamp_interval = zoom * (self.stamp_right - self.stamp_left)
        
        # Enforce zoom limits
        px_per_sec = self.history_width / new_stamp_interval
        if px_per_sec < self.min_zoom:
            new_stamp_interval = self.history_width / self.min_zoom
        elif px_per_sec > self.max_zoom:
            new_stamp_interval = self.history_width / self.max_zoom
        
        playhead_fraction = (self.playhead - self.stamp_left) / (self.stamp_right - self.stamp_left)
        self.stamp_left   = self.playhead - playhead_fraction * new_stamp_interval
        self.stamp_right  = self.stamp_left + new_stamp_interval

        self._layout()

        self.force_repaint()
    
    def set_playhead(self, playhead):
        with self.playhead_lock:
            self.playhead = playhead
            
            if self.playhead > self.stamp_right:
                dstamp = self.playhead - self.stamp_right + (self.stamp_right - self.stamp_left) * 0.75
                dstamp = min(dstamp, self.bag_index.end_stamp - self.stamp_right)
                
                self.stamp_left  += dstamp
                self.stamp_right += dstamp
                
                self.invalidate()
            elif self.playhead < self.stamp_left:
                dstamp = self.stamp_left - self.playhead + (self.stamp_right - self.stamp_left) * 0.75
                dstamp = min(dstamp, self.stamp_left - self.bag_index.start_stamp)

                self.stamp_left  -= dstamp
                self.stamp_right -= dstamp
                self.invalidate()
    
            # Get the indices in each topic msg_positions corresponding to the timestamp
            self.playhead_indices = dict([(topic, self.bag_index._data.find_stamp_index(topic, self.playhead)) for topic in self.topics])
    
            self.update_message_view()
            
            self.parent.status.invalidate()
            self.parent.playhead.update_position()

    ### Rendering

    def on_size(self, event):
        (w, h) = self.parent.GetClientSize()
        
        self.resize(w - self.x, h - self.y)   # resize layer to fill client area

    def check_dirty(self):
        if self.bag_index is not None and not self.bag_index.loaded:
            self.invalidate()

    def paint(self, dc):
        dc.SetBackground(self.background_brush)
        dc.Clear()

        if self.bag_index is None or len(self.topics) == 0:
            return

        if not self.stamp_left:
            if self.bag_index.loaded:
                self.reset_timeline()
            else:
                start_stamp = self.bag_index.start_stamp
                
                self.set_timeline_view(start_stamp, start_stamp + (30 * 60))  # default to showing 30 mins if index not created yet
                self.set_playhead(self.stamp_left)

        if not self.stamp_left or not self.stamp_right:
            return

        self._calc_font_sizes(dc)
        self._layout()

        self._draw_topic_dividers(dc)
        self._draw_time_indicators(dc)
        self._draw_message_history(dc)
        self._draw_bag_ends(dc)
        self._draw_topic_names(dc)
        self._draw_history_border(dc)

    def _calc_font_sizes(self, dc):
        dc.SetFont(self.topic_font)
        self.topic_name_sizes = dict([(topic, dc.GetTextExtent(topic)) for topic in self.topics])

        dc.SetFont(self.time_font)
        self.time_font_height = dc.GetTextExtent('12:34')[1]

    def _layout(self):
        max_topic_name_width   = max([w for (w, h) in self.topic_name_sizes.values()])
        self.topic_font_height = max([h for (w, h) in self.topic_name_sizes.values()])

        self.history_left  = self.margin_left + max_topic_name_width + 6
        self.history_width = self.width - self.history_left - self.margin_right

        self.history_bounds = {}
        y = self.history_top
        for topic in self.topics:
            datatype = self.bag_index.get_datatype(topic)
            
            topic_height = None
            if topic in self.rendered_topics:
                renderer = self.timeline_renderers.get(datatype)
                if renderer:
                    topic_height = renderer.get_segment_height(topic)
            if not topic_height:
                topic_height = self.topic_font_height
            
            self.history_bounds[topic] = (self.history_left, y, self.history_width, topic_height)

            y += topic_height - 2

        self.history_bottom = max([y + h for (x, y, w, h) in self.history_bounds.values()])

    def _draw_topic_dividers(self, dc):
        clip_left  = self.history_left
        clip_right = self.history_left + self.history_width

        dc.SetPen(self.topic_divider_pen)
        dc.DrawLineList([(max(clip_left, x), y, min(clip_right, x + w), y) for (x, y, w, h) in self.history_bounds.values()])

    ## Draws time indicators on the timeline 
    def _draw_time_indicators(self, dc):
        x_per_sec = self.map_dstamp_to_dx(1.0)

        major_divisions = [s for s in self.sec_divisions if x_per_sec * s >= self.major_spacing]
        if len(major_divisions) == 0:
            major_division = max(self.sec_divisions)
        else:
            major_division = min(major_divisions)

        minor_divisions = [s for s in self.sec_divisions if x_per_sec * s >= self.minor_spacing and major_division % s == 0]
        if len(minor_divisions) > 0:
            minor_division = min(minor_divisions)
        else:
            minor_division = None

        start_stamp = self.bag_index.start_stamp

        major_stamps = list(self._get_stamps(start_stamp, major_division))
        self._draw_major_divisions(dc, major_stamps, start_stamp, major_division)
        if minor_division:
            minor_stamps = [s for s in self._get_stamps(start_stamp, minor_division) if s not in major_stamps]
            self._draw_minor_divisions(dc, minor_stamps, start_stamp, minor_division)

    def _draw_major_divisions(self, dc, stamps, start_stamp, division):
        dc.SetPen(self.time_major_pen)
        dc.SetFont(self.time_font)
        dc.SetTextForeground(self.time_font_color)

        for stamp in stamps:
            x            = self.map_stamp_to_x(stamp, False)

            label        = self._get_label(division, stamp - start_stamp)
            label_x      = x + 3
            label_y      = self.history_top - self.time_font_height - self.time_label_spacing
            label_extent = dc.GetTextExtent(label)
            if label_x + label_extent[0] < self.width:
                dc.DrawText(label, label_x, label_y)
            
            dc.DrawLine(x, label_y + 1, x, self.history_bottom)

    def _draw_minor_divisions(self, dc, stamps, start_stamp, division):
        xs = [self.map_stamp_to_x(stamp) for stamp in stamps]

        dc.SetPen(self.time_tick_pen)
        dc.DrawLineList([(x, self.history_top - self.time_tick_height, x, self.history_top) for x in xs])

        dc.SetPen(self.time_minor_pen)
        dc.DrawLineList([(x, self.history_top, x, self.history_bottom) for x in xs])

    ## Returns visible stamps every stamp_step 
    def _get_stamps(self, start_stamp, stamp_step):
        if start_stamp >= self.stamp_left:
            stamp = start_stamp
        else:
            stamp = start_stamp + int((self.stamp_left - start_stamp) / stamp_step) * stamp_step + stamp_step

        while stamp < self.stamp_right:
            yield stamp
            stamp += stamp_step

    def _get_label(self, division, elapsed):
        secs  = int(elapsed) % 60

        mins  = int(elapsed) / 60
        hrs   = mins / 60
        days  = hrs / 24
        weeks = days / 7
        
        if division >= 7 * 24 * 60 * 60:    # >1wk divisions: show weeks
            return '%dw' % weeks
        elif division >= 24 * 60 * 60:      # >24h divisions: show days
            return '%dd' % days
        elif division >= 60 * 60:           # >1h divisions: show hours 
            return '%dh' % hrs
        elif division >= 5 * 60:            # >5m divisions: show minutes
            return '%dm' % mins
        elif division >= 1:                 # >1s divisions: show minutes:seconds
            return '%d:%02d' % (mins, secs)
        elif division >= 0.1:               # >0.1s divisions: show seconds.0
            return '%d.%s' % (secs, str(int(10.0 * (elapsed - int(elapsed)))))
        elif division >= 0.01:              # >0.1s divisions: show seconds.0
            return '%d.%02d' % (secs, int(100.0 * (elapsed - int(elapsed))))
        else:                               # show seconds.00
            return '%d.%03d' % (secs, int(1000.0 * (elapsed - int(elapsed))))

    ## Draw boxes to show messages regions in timelines
    def _draw_message_history(self, dc):
        for topic, (x, y, w, h) in self.history_bounds.items():
            msg_y      = y + 1
            msg_height = h - 3
            
            datatype       = self.bag_index.get_datatype(topic)
            datatype_color = self.datatype_colors.get(datatype, self.default_datatype_color)

            renderer = None
            msg_combine_interval = None
            if topic in self.rendered_topics:
                renderer = self.timeline_renderers.get(datatype)
                if not renderer is None:
                    msg_combine_interval = self.map_dx_to_dstamp(renderer.msg_combine_px)
            
            if msg_combine_interval is None:
                msg_combine_interval = self.map_dx_to_dstamp(self.default_msg_combine_px)

            # Set pen based on datatype
            dc.SetPen(wx.Pen(datatype_color))
            dc.SetBrush(wx.Brush(datatype_color))
           
            # Find the index of the earliest visible stamp
            stamp_left_index  = self.bag_index._data.find_stamp_index(topic, self.stamp_left)
            stamp_right_index = self.bag_index._data.find_stamp_index(topic, self.stamp_right)

            # Iterate through regions of connected messages
            for (stamp_start, stamp_end) in self._find_regions((stamp for (stamp, pos) in self.bag_index._data.msg_positions[topic][stamp_left_index:stamp_right_index]), msg_combine_interval):
                # Calculate region rectangle bounds 
                region_x_start = self.map_stamp_to_x(stamp_start)
                region_x_end   = self.map_stamp_to_x(stamp_end)
                region_width   = max(1, region_x_end - region_x_start) 
                region_rect    = (region_x_start, msg_y, region_width, msg_height)

                # Use custom datatype renderer
                if renderer and renderer.draw_timeline_segment(dc, topic, stamp_start, stamp_end, *region_rect):
                    continue

                # Use default renderer
                dc.DrawRectangle(*region_rect)

    ## Groups timestamps into regions connected by timestamps less than max_interval secs apart
    def _find_regions(self, stamps, max_interval):
        region_start, prev_stamp = None, None
        for stamp in stamps:
            if prev_stamp:
                if stamp - prev_stamp > max_interval:
                    region_end = prev_stamp
                    yield (region_start, region_end)
                    region_start = stamp
            else:
                region_start = stamp

            prev_stamp = stamp

        if region_start and prev_stamp:
            yield (region_start, prev_stamp)

    ## Draws topic names
    def _draw_topic_names(self, dc):
        topics = self.history_bounds.keys()
        coords = [(self.margin_left, y + (h / 2) - (self.topic_font_height / 2)) for (x, y, w, h) in self.history_bounds.values()]

        dc.SetFont(self.topic_font)
        dc.SetTextForeground(self.topic_font_color)
        dc.DrawTextList([t.lstrip('/') for t in topics], coords)

    ## Draw markers to indicate the extent of the bag file
    def _draw_bag_ends(self, dc):
        dc.SetPen(self.bag_end_pen)

        marker_top, marker_bottom = self.history_top - 2, self.history_bottom + 2

        # Draw start marker
        start_stamp = self.bag_index.start_stamp
        if start_stamp > self.stamp_left and start_stamp < self.stamp_right:
            x = self.map_stamp_to_x(start_stamp)
            dc.DrawLineList([(x - i, marker_top, x - i, marker_bottom) for i in range(1, self.bag_end_width)])

        # Draw end marker
        end_stamp = self.bag_index.end_stamp
        if end_stamp > self.stamp_left and end_stamp < self.stamp_right:
            x = self.map_stamp_to_x(end_stamp)
            dc.DrawLineList([(x + i, marker_top, x + i, marker_bottom) for i in range(1, self.bag_end_width)])

    def _draw_history_border(self, dc):
        dc.SetPen(self.history_border_pen)
        dc.SetBrush(wx.Brush('white', wx.TRANSPARENT))
        bounds_width = min(self.history_width, self.parent.width - self.x)
        dc.DrawRectangle(self.history_left, self.history_top, bounds_width, self.history_bottom - self.history_top)

    def map_dx_to_dstamp(self, dx):
        return float(dx) * (self.stamp_right - self.stamp_left) / self.history_width

    def map_x_to_stamp(self, x, clamp_to_visible=True):
        fraction = float(x - self.history_left) / self.history_width

        if clamp_to_visible:
            if fraction <= 0.0:
                return self.stamp_left
            elif fraction >= 1.0:
                return self.stamp_right

        return self.stamp_left + fraction * (self.stamp_right - self.stamp_left)

    def map_dstamp_to_dx(self, dstamp):
        return (float(dstamp) * self.history_width) / (self.stamp_right - self.stamp_left)

    def map_stamp_to_x(self, stamp, clamp_to_visible=True):
        fraction = (stamp - self.stamp_left) / (self.stamp_right - self.stamp_left)

        if clamp_to_visible:
            fraction = min(1.0, max(0.0, fraction))

        return self.history_left + fraction * self.history_width

    ### Control

    # Mouse events

    def on_left_down(self, event):
        self.clicked_pos = event.GetPosition()
        if not self.contains(*self.clicked_pos):
            return

        if event.ShiftDown():
            return

        x, y = self.clicked_pos[0] - self.x, self.clicked_pos[1] - self.y
        if x < self.history_left or x > self.history_left + self.history_width:
            return

        self.set_playhead(self.map_x_to_stamp(x))  

    def on_middle_down(self, event):
        self.clicked_pos = event.GetPosition()

    def on_right_down(self, event):
        self.clicked_pos = event.GetPosition()
        if not self.contains(*self.clicked_pos):
            return

        self.parent.PopupMenu(TimelinePopupMenu(self.parent, self), self.clicked_pos)

    def on_mousewheel(self, event):
        dz = event.GetWheelRotation() / event.GetWheelDelta()
        self.zoom_timeline(1.0 - dz * 0.2)
        
    def on_mouse_move(self, event):
        mouse_pos = event.GetPosition()

        if not event.Dragging():
            return

        left, middle, right = event.LeftIsDown(), event.MiddleIsDown(), event.RightIsDown()

        if middle or event.ShiftDown():
            x, y = mouse_pos

            dx, dy = x - self.clicked_pos[0], y - self.clicked_pos[1]

            if dx != 0:
                self.translate_timeline(dx)
            if dy != 0:
                zoom = min(self.max_zoom_speed, max(self.min_zoom_speed, 1.0 + self.zoom_sensitivity * dy))
                self.zoom_timeline(zoom)

            self.clicked_pos = mouse_pos

            self.parent.playhead.update_position()

        elif left:
            x, y = mouse_pos[0] - self.x, mouse_pos[1] - self.y
            
            self.set_playhead(self.map_x_to_stamp(x))

            self.clicked_pos = mouse_pos
            
    ##
    
    def load_msg_by_stamp(self, topic, stamp):
        index = topic.find_stamp_index(stamp)
        if not index:
            return None

        pos = topic.msg_positions[index][1]

    def update_message_view(self):
        if not self.playhead_indices:
            return

        msgs = {}
        for topic in self.playhead_indices:
            if topic in self.listeners:
                playhead_index = self.playhead_indices[topic]
                if playhead_index is not None:
                    # Load the message
                    pos = self.bag_index.msg_positions[topic][playhead_index][1]
                    (datatype, msg, stamp) = self.bag_file.load_message(pos, self.bag_index)

                    msgs[topic] = (stamp, datatype, playhead_index, msg)
                    continue

            msgs[topic] = None

        # Inform the listeners
        for topic, msg_data in msgs.items():
            topic_listeners = self.listeners.get(topic)
            if not topic_listeners:
                continue
            
            if msg_data:
                for listener in topic_listeners:
                    listener.message_viewed(self.bag_file, self.bag_index, topic, *msg_data)
            else:
                for listener in topic_listeners:
                    listener.message_cleared()

## Timeline popup menu.  Allows user to manipulate the timeline view, and open new message views.
class TimelinePopupMenu(wx.Menu):
    def __init__(self, parent, timeline):
        wx.Menu.__init__(self)

        self.parent   = parent
        self.timeline = timeline

        # Reset Timeline
        self.reset_timeline_menu = wx.MenuItem(self, wx.NewId(), 'Reset Timeline')
        self.AppendItem(self.reset_timeline_menu)
        self.Bind(wx.EVT_MENU, lambda e: self.timeline.reset_timeline(), id=self.reset_timeline_menu.GetId())

        # Get the renderers
        renderers = self.timeline.get_renderers()

        # Thumbnails...
        if len(renderers) > 0:
            self.thumbnail_menu = wx.Menu()
            self.AppendSubMenu(self.thumbnail_menu, 'Thumbnails...', 'View message thumbnails')

            # Thumbnails... / Show All
            self.show_thumbnails_menu = wx.MenuItem(self.thumbnail_menu, wx.NewId(), 'Show All')
            self.thumbnail_menu.AppendItem(self.show_thumbnails_menu)
            self.thumbnail_menu.Bind(wx.EVT_MENU, lambda e: self.timeline.set_renderers_active(True), id=self.show_thumbnails_menu.GetId())
            
            # Thumbnails... / Hide All
            self.hide_thumbnails_menu = wx.MenuItem(self.thumbnail_menu, wx.NewId(), 'Hide All')
            self.thumbnail_menu.AppendItem(self.hide_thumbnails_menu)
            self.thumbnail_menu.Bind(wx.EVT_MENU, lambda e: self.timeline.set_renderers_active(False), id=self.hide_thumbnails_menu.GetId())
            
            # ---
            self.thumbnail_menu.AppendSeparator()
            
            # Thumbnails... / topic/subtopic/subsubtopic
            for topic, renderer in renderers:
                renderer_item = self.TimelineRendererMenuItem(self.thumbnail_menu, wx.NewId(), topic.lstrip('/'), topic, renderer, self.timeline)
                self.thumbnail_menu.AppendItem(renderer_item)
    
                renderer_item.Check(topic in self.timeline.rendered_topics)

        # View (by topic)...
        self.view_topic_menu = wx.Menu()
        self.AppendSubMenu(self.view_topic_menu, 'View (by topic)...', 'View message detail')
        
        for topic in self.timeline.topics:
            datatype = self.timeline.bag_index.get_datatype(topic)

            # View... / topic/subtopic/subsubtopic
            topic_menu = wx.Menu()
            self.view_topic_menu.AppendSubMenu(topic_menu, topic.lstrip('/'), topic)

            viewer_types = self.timeline.get_viewer_types(datatype)

            # View... / topic/subtopic/subsubtopic / Viewer
            for viewer_type in viewer_types:
                topic_menu.AppendItem(self.TopicViewMenuItem(topic_menu, wx.NewId(), viewer_type.name, topic, viewer_type, self.timeline))

        # View (by datatype)...
        self.view_datatype_menu = wx.Menu()
        self.AppendSubMenu(self.view_datatype_menu, 'View (by datatype)...', 'View message detail')
        
        topics_by_datatype = self.timeline.bag_index.get_topics_by_datatype()
        
        for datatype in sorted(topics_by_datatype):
            # View... / datatype
            datatype_menu = wx.Menu()
            self.view_datatype_menu.AppendSubMenu(datatype_menu, datatype, datatype)
            
            topics = topics_by_datatype[datatype]
            
            viewer_types = self.timeline.get_viewer_types(datatype)
            
            for topic in [t for t in self.timeline.topics if t in topics]:   # use timeline ordering
                topic_menu = wx.Menu()
                datatype_menu.AppendSubMenu(topic_menu, topic.lstrip('/'), topic)
    
                # View... / datatype / topic/subtopic/subsubtopic / Viewer
                for viewer_type in viewer_types:
                    topic_menu.AppendItem(self.TopicViewMenuItem(topic_menu, wx.NewId(), viewer_type.name, topic, viewer_type, self.timeline))

    class TimelineRendererMenuItem(wx.MenuItem):
        def __init__(self, parent, id, label, topic, renderer, timeline):
            wx.MenuItem.__init__(self, parent, id, label, kind=wx.ITEM_CHECK)
            
            self.topic    = topic
            self.renderer = renderer
            self.timeline = timeline

            parent.Bind(wx.EVT_MENU, self.on_menu, id=self.GetId())

        def on_menu(self, event):
            self.timeline.set_renderer_active(self.topic, not self.timeline.is_renderer_active(self.topic))

    class TopicViewMenuItem(wx.MenuItem):
        def __init__(self, parent, id, label, topic, viewer_type, timeline):
            wx.MenuItem.__init__(self, parent, id, label)
            
            self.topic       = topic
            self.viewer_type = viewer_type
            self.timeline    = timeline
    
            parent.Bind(wx.EVT_MENU, self.on_menu, id=self.GetId())

        def on_menu(self, event):
            frame = BaseFrame(None, 'rxbag', self.topic, title='rxbag - %s [%s]' % (self.topic.lstrip('/'), self.viewer_type.name), pos=(4, 4), size=(640, 480))
            panel = LayerPanel(frame, -1)
            view  = self.viewer_type(self.timeline, panel, self.topic, 0, 0, *frame.GetClientSize())
            panel.layers = [view]
            frame.Show()
            
            self.timeline.add_view(self.topic, view)
