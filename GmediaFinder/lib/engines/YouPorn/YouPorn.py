#-*- coding: UTF-8 -*-

import mechanize
import re
import urllib, urllib2
from gi.repository import Gtk
import time
from gi.repository import GObject

try:
    from lib.functions import *
    from lib.get_stream import Browser
except:
    from GmediaFinder.lib.functions import *
    from GmediaFinder.lib.get_stream import Browser


URL = "http://youporn.com/"
ENTER_URL = "%s?user_choice=Enter" % URL
BROWSE_URL = "%sbrowse/%s?page=%s" % (URL, "%s", "%d")
TOP_RATED_URL = "%stop_rated/%s?page=%s" % (URL, "%s", "%d")
MOST_VIEWED_URL = "%smost_viewed/%s?page=%s" % (URL, "%s", "%d")
SEARCH_URL = "%ssearch/%s?query=%s&type=straight&page=%s" % (URL, "%s", "%s", "%s")

class YouPorn(object):
    def __init__(self,gui):
        self.gui = gui
        self.name ="YouPorn"
        self.engine_type = "video"
        self.current_page = 1
        self.main_start_page = 1
        self.thread_stop=False
        self.adult_content=True
        self.search_url = "http://www.youporn.com/search/%s?query=%s&type=%s&page=%s"
        self.initialized=False
        self.has_browser_mode = False
        ## options labels
        self.order_label = _("Order by: ")
        self.browser = mechanize.Browser()
        self.browser.addheaders = []
        self.scrapper=Browser(gui)
        self.start_engine()
    
    
    def start_engine(self):
        self.gui.engine_list[self.name] = ''
    
    def load_gui(self):
        ## create orderby combobox
        self.orderbyOpt = {self.order_label:{_("Most recent"):"time",_("Most viewed"):"views",
                           _("Most rated"):"rating",_("Duration"):"duration",
                           _("Most relevant"):"relevance",
            },
        }
        self.orderby = create_comboBox(self.gui, self.orderbyOpt)
        self.orderby.setIndexFromString(_("Most relevant"))
    
    def filter(self, data, query):
        flag_found = False
        title=""
        markup=""
        link=""
        for line in data.readlines():
            if self.thread_stop == True:
                break
            ## search link
            if 'href="/watch' in line:
                flag_found = True
                l = re.search('href=\"(.*?)\"',line).group(1)
                link = "http://www.youporn.com%s" % l
            elif 'class="flipbook' in line:
                title = re.search('alt=\"(.*?)\"',line).group(1)
                img_link = re.search('src=\"(.*?)\"',line).group(1)
                img = download_photo(img_link)
                GObject.idle_add(self.gui.add_sound, title, link, img, None, self.name)
            ## check for next page
            #elif 'id="navNext"' in line:
                #end_flag=False
            continue
            
        if not flag_found:
            self.print_info(_("%s: No results for %s...") % (self.name,query))
            time.sleep(5)
        self.thread_stop=True
    
    def get_search_url(self,query,page):
        if not self.initialized:
            self.browser.open(ENTER_URL)
            self.initialized = True
        choice = self.orderby.getSelected()
        orderby = self.orderbyOpt[self.order_label][choice]
        return SEARCH_URL % (orderby,query,page)
    
    def search(self, data, query, page):
        try:
            print data
            self.filter(data, query)
        except:
            self.print_info(_("%s: Connexion failed...") % self.name)
            time.sleep(5)
            self.thread_stop=True
            
    def play(self,link):
        self.scrapper.load_uri(link)
            
    def print_info(self,msg):
        GObject.idle_add(self.gui.info_label.set_text,msg)
    
