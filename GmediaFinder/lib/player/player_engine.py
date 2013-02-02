#-*- coding: UTF-8 -*-
#
# gmediafinder's player engine

import sys
import os, math
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GstVideo
from gi.repository import Gtk,Gdk
# Needed for window.get_xid(), xvimagesink.set_window_handle(), respectively:
from gi.repository import GdkX11
from gi.repository import GObject


Gst_STATE_VOID_PENDING        = 0
Gst_STATE_NULL                = 1
Gst_STATE_READY               = 2
Gst_STATE_PAUSED              = 3
Gst_STATE_PLAYING             = 4
Gst_STATE_BUFFERING           = 5

class GstPlayer(GObject.GObject):
    __gsignals__ = { 'fill-status-changed': (GObject.SignalFlags.RUN_FIRST,
                                             None,
                                             (float,)) }

    def __init__(self, mainGui,playerGui):
	GObject.GObject.__init__(self)
	Gst.init(None)
	self.mainGui = mainGui
	self.playerGui = playerGui
        self.playing = False
	self.status=Gst_STATE_READY
	self.file_tags = {}
        self.player = Gst.ElementFactory.make("playbin", "player")
        self.videowidget = self.playerGui.movie_window
        self.on_eos = False
	self._cbuffering = -1
	audiosink = Gst.ElementFactory.make("autoaudiosink",None)
        audiosink.set_property('async-handling', True)
        if sys.platform == "win32":
            self.player.videosink = Gst.ElementFactory.make('dshowvideosink',None)
        else:
            self.player.videosink = Gst.ElementFactory.make('xvimagesink',None)

        self.player.set_property("audio-sink", audiosink)
        self.player.set_property("video-sink", self.player.videosink)
	#self.player.set_property('buffer-size', 1024000)

        bus = self.player.get_bus()
        bus.enable_sync_message_emission()
        bus.add_signal_watch()
        bus.connect('message', self.on_message)
	bus.connect('sync-message::element', self.on_sync_message)
	bus.connect("message::tag", self.bus_message_tag)
	bus.connect('message::buffering', self.on_message_buffering)

        # activate media download
        self._temp_location = None
        self.started_buffering = False
        self.fill_timeout_id = 0
        #self.player.props.flags |= 0x80
        self.player.connect("deep-notify::temp-location", self.on_temp_location)

    @GObject.property
    def download_filename(self):
        return self._temp_location

    def on_sync_message(self, bus, message):
        if message.structure is None:
            return
        if message.structure.get_name() == 'prepare-xwindow-id':
            # Sync with the X server before giving the X-id to the sink
            if sys.platform == "win32":
                win_id = self.videowidget.window.handle
            else:
                win_id = self.videowidget.window.get_xid()
            self.attach_drawingarea(win_id)
            self.player.videosink.set_property('force-aspect-ratio', True)
	    
            
    def on_message(self, bus, message):
        t = message.type
        if t == Gst.MESSAGE_ERROR:
            err, debug = message.parse_error()
            print "Error: %s" % err, debug
            if self.on_eos:
                self.on_eos()
            self.playing = False
	    GObject.idle_add(self.emit, 'finished')
        elif t == Gst.MESSAGE_EOS:
            if self.on_eos:
                self.on_eos()
            self.playing = False
	    GObject.idle_add(self.emit, 'finished')
        elif t == Gst.MESSAGE_BUFFERING:
            self.process_buffering_stats(message)

    def process_buffering_stats(self, message):
        if not self.started_buffering:
            self.started_buffering = True
            if self.fill_timeout_id:
                GObject.source_remove(self.fill_timeout_id)
            self.fill_timeout_id = GObject.timeout_add(200,
                                                       self.buffering_timeout)

    def buffering_timeout(self):
        query = Gst.query_new_buffering(Gst.FORMAT_PERCENT)
        if self.player.query(query):
            fmt, start, stop, total = query.parse_buffering_range()
            if stop != -1:
                fill_status = stop / 10000.
            else:
                fill_status = 100.

            self.emit("fill-status-changed", fill_status)

            if fill_status == 100.:
                # notify::download_filename value
                self.notify("download_filename")
                return False
        return True

    
    def on_message_buffering(self, bus, message):
	percent = 0
	percent = message.parse_buffering()
	if math.floor(percent/5) > self._cbuffering:
	    self._cbuffering = math.floor(percent/5)
	    buffering = _('Buffering :')
	    self.status = Gst_STATE_BUFFERING
	    GObject.idle_add(self.playerGui.media_name_label.set_markup,'<small><b>%s</b> %s%s</small>' % (buffering,percent,'%'))

	if percent == 100:
	    self._cbuffering = -1
	    if self.get_state() == Gst_STATE_PAUSED:
		GObject.idle_add(self.mainGui.info_label.set_text,'')
		self.playerGui.pause_resume()
	elif self.status == Gst_STATE_BUFFERING:
	    if not self.get_state() == Gst_STATE_PAUSED:
		self.playerGui.pause_resume()
    
    def on_temp_location(self, playbin, queue, prop):
        self._temp_location = queue.props.temp_location

    def set_location(self, location):
	self.started_buffering = False
        self.player.set_property('uri', location)

    def attach_drawingarea(self,window_id):
	self.player.videosink.set_xwindow_id(window_id)
    
    def query_position(self):
        "Returns a (position, duration) tuple"
        try:
            position, format = self.player.query_position(Gst.FORMAT_TIME)
        except:
            position = Gst.CLOCK_TIME_NONE

        try:
            duration, format = self.player.query_duration(Gst.FORMAT_TIME)
        except:
            duration = Gst.CLOCK_TIME_NONE

        return (position, duration)

    def seek(self, location):
        """
        @param location: time to seek to, in nanoseconds
        """
        Gst.debug("seeking to %r" % location)
        event = Gst.event_new_seek(1.0, Gst.FORMAT_TIME,
            Gst.SEEK_FLAG_FLUSH | Gst.SEEK_FLAG_ACCURATE,
            Gst.SEEK_TYPE_SET, location,
            Gst.SEEK_TYPE_NONE, 0)

        res = self.player.send_event(event)
        if res:
            Gst.info("setting new stream time to 0")
            self.player.set_new_stream_time(0L)
        else:
            Gst.error("seek to %r failed" % location)
	    
    def bus_message_tag(self, bus, message):
	codec = None
	self.audio_codec = None
	self.media_bitrate = None
	self.mode = None
	self.media_codec = None
	#we received a tag message
	taglist = message.parse_tag()
	self.old_name = self.mainGui.media_name
	#put the keys in the dictionary
	for key in taglist.keys():
		#print key, taglist[key]
		if key == "preview-image" or key == "image":
			ipath="/tmp/temp.png"
			img = open(ipath, 'w')
			img.write(taglist[key])
			img.close()
			self.media_thumb = GdkPixbuf.Pixbuf.new_from_file_at_scale(ipath, 64,64, 1)
			try:
			    self.mainGui.model.set_value(self.mainGui.selected_iter, 0, self.media_thumb)
			except:
			    thumb = None
		elif key == "bitrate":
			r = int(taglist[key]) / 1000
			self.file_tags[key] = "%sk" % r
		elif key == "channel-mode":
			self.file_tags[key] = taglist[key]
		elif key == "audio-codec":
			k = str(taglist[key])
			if not self.file_tags.has_key(key) or self.file_tags[key] == '':
				self.file_tags[key] = k
		elif key == "video-codec":
			k = str(taglist[key])
			if not self.file_tags.has_key(key) or self.file_tags[key] == '':
				self.file_tags[key] = k
		elif key == "container-format":
			k = str(taglist[key])
			if not self.file_tags.has_key(key) or self.file_tags[key] == '':
				self.file_tags[key] = k
		#print self.file_tags
	try:
		if self.file_tags.has_key('video-codec') and self.file_tags['video-codec'] != "":
			codec = self.file_tags['video-codec']
		else:
			codec = self.file_tags['audio-codec']
		if codec == "" and self.file_tags['container-format'] != "":
			codec = self.file_tags['container-format']
		if ('MP3' in codec or 'ID3' in codec):
				self.media_codec = 'mp3'
		elif ('XVID' in codec):
				self.media_codec = 'avi'
		elif ('MPEG-4' in codec or 'H.264' in codec or 'MP4' in codec):
				self.media_codec = 'mp4'
		elif ('WMA' in codec or 'ASF' in codec or 'Microsoft Windows Media 9' in codec):
				self.media_codec = 'wma'
		elif ('Quicktime' in codec):
				self.media_codec = 'mov'
		elif ('Vorbis' in codec or 'Ogg' in codec):
				self.media_codec = 'ogg'
		elif ('Sorenson Spark Video' in codec or 'On2 VP6/Flash' in codec):
				self.media_codec = 'flv'
		elif ('VP8' in codec):
			self.media_codec = 'webm'
		self.media_bitrate = self.file_tags['bitrate']
		self.mode = self.file_tags['channel-mode']
		#self.model.set_value(self.selected_iter, 1, self.media_markup)
		self.file_tags = tags
		self.playerGui.media_codec = self.media_codec
	except:
		return

    def pause(self):
        Gst.info("pausing player")
        self.player.set_state(Gst.STATE_PAUSED)
        self.playing = False

    def play(self):
        Gst.info("playing player")
        self.player.set_state(Gst.STATE_PLAYING)
        self.playing = True
        
    def stop(self):
        self.player.set_state(Gst.STATE_NULL)
        Gst.info("stopped player")
	self.playing = False
        if self._temp_location:
            try:
                os.unlink(self._temp_location)
            except OSError:
                pass
            self._temp_location = ''

    def get_state(self, timeout=1,full=False):
	if full:
	    return self.player.get_state(timeout=timeout)
	else:
	    success, state, pending = self.player.get_state(1)
	    return state.real

    def is_playing(self):
        return self.playing

GObject.type_register(GstPlayer)
GObject.signal_new('finished',
                   GstPlayer,
                   GObject.SignalFlags.RUN_LAST,
                   GObject.TYPE_BOOLEAN,
                   ())
