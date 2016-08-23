# -*- coding: utf-8 -*-


from StringIO import StringIO
import sqlite3
import zlib
import socket
import fcntl
import struct
import random
from operator import itemgetter, attrgetter
import base64
import json
import time
import threading


# Non-standard libraries (install them)
import wifi
import pycurl
from gps import *


########################

# Sqlite database file to log to
dbfile = "wifis.db"

# Name of your wireless interface. For most users this is probably wlan0, but for testing you might want to have one connected stably to your own wifi
# while connecting to others on a second interface.
iface = "wlan0"

# For best results, select *either* location logging *or* tunnel probing, not both
# (tunnel probing will tie up the WiFi interface for many seconds at a time and block receiving scan results for location)

####
# If True, will log WiFi scan results (APs in view and signal strength) and GPS coordinates to the db.
log_location = True

# If True, will probe discovered APs for tunneling capability.
probe_for_tunneling = True
####

# The following options are for tunnel probing only. For probing to work, the companion 'dnscatch.py' must be running
# at the IP address delegated to by the tunnel domain and able to receive and respond to requests from the Internet.

# Maxumum number of tries to evaluate an open Wifi before writing it off. This number should be high-ish (or at least >1)
# if the survey device is moving quickly, sweeping an antenna, etc.
max_attempts = 10

# Domain to use for DNS tunneling check. It should be able to return a record that unambiguously indicates it received our data payload.
dns_tunnel_domain = "t.example.com"

# Expected IP address response from DNS tunnel server if not being meddled with.
# It does not have to be a valid IP, and will not be used for anything other than confirming the response matches the expected value.
dns_tunnel_pass_response = '123.45.67.89'

# URL to use for HTTP response test. It should be a plain HTTP (not HTTPS) webpage with known, and ideally short, contents, ideally on a server you own.
# In most cases we expect the AP to intercept the response and return a captive portal/login page (which is still useful),
#   but we might get truly lucky once in a while and get the real contents.
http_resp_url = "http://www.google.com"

# Expected string to be contained in a 'passing' HTTP response, indicating the AP served the actually requested page and not
# its own captive portal login page. This should ideally be something fairly unique (not found on portal pages) and served up by a server you own.
http_resp_pass_string = "I'm Feeling Lucky"

########################


gpsd = None #setting a global variable for the gpsd instance


# Cheesy way to get the assigned IP address of an arbitrary interface.
# Ref: http://stackoverflow.com/questions/24196932/how-can-i-get-the-ip-address-of-eth0-in-python

def get_ip_address(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8915,  # SIOCGIFADDR
        struct.pack('256s', ifname[:15])
    )[20:24])



def Search(interface='wlan0'):
    wifilist = []

    cells = wifi.Cell.all(interface)

    for cell in cells:
        wifilist.append(cell)

    return wifilist


def FindFromSearchList(ssid):
    wifilist = Search()

    for cell in wifilist:
        if cell.ssid == ssid:
            return cell

    return False

def FindFromSearchListByAddress(address):
    wifilist = Search()

    for cell in wifilist:
        if cell.address == address:
            return cell

    return False



def FindFromSavedList(ssid, interface='wlan0'):
    cell = wifi.Scheme.find(interface, ssid)
    if cell:
        return cell

    return False


def Connect(ssid, password=None):
    cell = FindFromSearchList(ssid)

    if cell:
        savedcell = FindFromSavedList(cell.ssid)

        # Already Saved from Setting
        if savedcell:
	    try:
            	savedcell.activate()
	    except wifi.exceptions.ConnectionError:
		Delete(ssid)
		return False
            return cell

        # First time to conenct
        else:
            if cell.encrypted:
                if password:
                    scheme = Add(cell, password)

                    try:
                        scheme.activate()

                    # Wrong Password
                    except wifi.exceptions.ConnectionError:
                        Delete(ssid)
                        return False

                    return cell
                else:
                    return False
            else:
                scheme = Add(cell)

                try:
                    scheme.activate()
                except wifi.exceptions.ConnectionError:
                    Delete(ssid)
                    return False

                return cell
    
    return False


def Add(cell, password=None, interface='wlan0'):
    if not cell:
        return False

    scheme = wifi.Scheme.for_cell(interface, cell.ssid, cell, password)
    scheme.save()
    return scheme


def Delete(ssid):
    if not ssid:
        return False

    cell = FindFromSavedList(ssid)

    if cell:
        cell.delete()
        return True

    return False


class GpsPoller(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        global gpsd #bring it in scope
        gpsd = gps(mode=WATCH_ENABLE) #starting the stream of info
        self.current_value = None
        self.running = True #setting the thread running to true
 
    def run(self):
        global gpsd
        while gpsp.running:
            gpsd.next() #this will continue to loop and grab EACH set of gpsd info to clear the buffer
 

if __name__ == '__main__':

    gpsp = GpsPoller() # create the thread
    try:
        gpsp.start() # start it up
    except:
        pass

    # connect to 'database' (or file)
    conn = sqlite3.connect(dbfile)
    c = conn.cursor()

    # CREATE TABLE IF NOT EXISTS foo (id INTEGER, ...);
    # create the table
    c.execute('''CREATE TABLE IF NOT EXISTS wifis (
        bssid TEXT PRIMARY KEY NOT NULL,
        ssid TEXT,
        check_level INT NOT NULL,
        check_attempts INT NOT NULL,
        encrypted INT NOT NULL,
        maxSigSeen INT NOT NULL,
        tunnel_supported INT NOT NULL,
        http_response BLOB);
                ''')

    # check_level:
    #   0 - Completely unchecked
    #   1 - Connected and got IP address (DHCP response)
    #   2 - Got DNS response
    #   3 - Got HTTP response

    # Create a table for SSID geolocation too
    c.execute('''CREATE TABLE IF NOT EXISTS wifilocation (
        rowid INTEGER PRIMARY KEY,
        runkey INTEGER,
        localtime REAL,
        wifi_json TEXT,
        gps_lat REAL,
        gps_lon REAL,
        gps_time TEXT);
                ''')

    conn.commit() # ensure the changes stick

    # Create a random 'unique' value for this run, used to associate wifi-location data from the same run together
    # since the RasPi's clock will start from 0 each time it is powered on.
    # Hopefully it will actually be random given that the startup conditions for each run will be very similar.
    runkey = random.randint(0, 999999999)

    # First-time setup complete, now start fishing!...
    while True:
        
        # Search WiFi and return WiFi list
        wifilist = Search(interface=iface)

        print "Searched for access points"
        # Sort the list by signal strength; this is beneficial for the location mode and (probably) the tunnel probing mode.
        wifilist = sorted(wifilist, key=attrgetter('signal'), reverse=True)

        #print "Wifilist:"
        #print wifilist

        if log_location:
            # Location phase: Grab the top 'n' APs by signal strength. Dump their info to a database entry tied to the current local time
            # (resets everytime the Pi is powercycled, but should monotonically increase during a single run)
            # and the randomly generated 'runkey' used as a session identifier.

            # JSON format expected by MLS:
            ##{
            ##    "wifiAccessPoints": [
            ##        {
            ##            "macAddress": "xx:xx:xx:xx:xx:xx",
            ##            "signalStrength": -46
            ##        },
            ##        {
            ##            "macAddress": "xx:xx:xx:xx:xx:xx",
            ##            "signalStrength": -51
            ##        },
            ##        {
            ##            "macAddress": "xx:xx:xx:xx:xx:xx",
            ##            "signalStrength": -72
            ##        }
            ##    ]
            ##}

            geoaps = [] # empty dict to populate with AP data. May as well just store it in the same format as the location service will need...
            for i in range(0, min([len(wifilist), 12])): # Put a practical limit on the number of APs stored per iteration, e.g. if in a very dense area. More are unlikely to improve location results.
                geoaps.append({'macAddress':wifilist[i].address, 'signalStrength':wifilist[i].signal, 'ssid':wifilist[i].ssid})
            #print geoaps
            # Wrap that in a parent 'wifiAccessPoints' key so we directly output the correct JSON text
            mls_geoaps = []
            mls_geoaps.append({'wifiAccessPoints':geoaps})
            #print json.dumps(mls_geoaps[0], ensure_ascii=False, indent=4)
            #print "GPS UTC, fix.time:"
            #print gpsd.utc
            #print gpsd.fix.time
            #print "7 values..."
            #print runkey
            #print time.time()
            #print json.dumps(mls_geoaps[0], ensure_ascii=False, indent=4)
            #print gpsd.fix.latitude
            #print gpsd.fix.longitude
            #print gpsd.utc

            c.execute('''INSERT INTO wifilocation (runkey, localtime, wifi_json, gps_lat, gps_lon, gps_time)
                        VALUES (?,?,?,?,?,?);
                        ''', (runkey, time.time(), json.dumps(mls_geoaps[0], ensure_ascii=False, indent=4), gpsd.fix.latitude, gpsd.fix.longitude, gpsd.utc,))
            conn.commit()
        
        # State variable to tell if we've already evaluated an open AP in this search phase.
        # Connecting to and poking at one takes a while, so any others from the scan are likely out of range by now if driving.
        # This ensures we only do tunnel probing on one per scan (but will still add all unknown ones to DB).
        already_evaluated_one = False

        for i in wifilist:
        #    print "SSID: %s, address=%s, enc=%s" % (i.ssid, i.address, i.encrypted)

            # First, see if we recognize this AP. If it's new, add it to the db.
            c.execute('SELECT * FROM wifis WHERE bssid=?', (i.address,))
            #print "Query response for %s:" % i.address
            resp = c.fetchone()
            #print resp
            if resp is None:
                print "New WiFi found: %s (%s)" % (i.ssid, i.address)
                c.execute('''INSERT INTO wifis (bssid, ssid, check_level, check_attempts, encrypted, maxSigSeen, tunnel_supported, http_response)
                    VALUES (?,?,0,0,?,?,0,'');
                    ''', (i.address, i.ssid, i.encrypted, i.quality,))
            else:
                print "Known WiFi found: %s (%s)" % (i.ssid, i.address)
            
            # Decide what to do with this AP. If it was encrypted, just move on after adding it to the db (if it didn't exist).
            # Otherwise, investigate further...
            if probe_for_tunneling and (not i.encrypted) and (not already_evaluated_one) and len(i.ssid):
                # HACK: ifdown chokes on /etc/network/interfaces entries generated by 'wifi' with empty SSIDs,
                # so don't even try to connect to them.
                # We are probably throwing away a bunch of tunnelable APs this way, but I really can't be arsed to work around this.

                # It's either newly added to the database, or already known. Check if it is fully evaluated - if not, proceed to the relevant evaluation step
                c.execute('SELECT check_level, check_attempts, maxSigSeen, tunnel_supported, http_response FROM wifis WHERE bssid=?', (i.address,))
                resp = c.fetchone() # shouldn't fail
                if resp:
                    check_level, check_attempts, maxSigSeen, tunnel_supported, http_response = resp # unpack result to friendly variables
                    if (check_level < 3) and (check_attempts < max_attempts):
                        check_attempts = check_attempts + 1
                        already_evaluated_one = True # Ensure we only evaluate this one AP this search cycle so we don't test stale ones we've already driven past
                        
                        # Not fully checked yet; start (or continue) by connecting to it.
                        # If check_level 0 (uncharted), bump it if we get a connection and non-bogus IP.
                        print "  * Attempting connection to %s" % i.ssid
                        # Ugly: The underlying guts of the 'wifi' module (actually, the /etc/network/interfaces file it's a thin wrapper around)
                        # does not support selecting/connecting to an AP by MAC address, only name (SSID). There is a fair chance that any location has
                        # multiple APs with the same common SSID in-sight at once (linksys, xfinitywifi...) and/or APs with an ampty SSID. Someday if I (or someone) really feels like fixing enough
                        # plumbing to deal with this, please do!
                        if(Connect(i.ssid)):
                            # sez it worked
                            print "     *** It worked! (probably). Got address:"
                            print get_ip_address(iface)  # '192.168.0.110' # requires sudo
                            # TODO: Can we really tell programmatically if IP we got is bogus or not, apart from testing against well-known internal address ranges (192.168...)
                            # or well-known probably-bogus address ranges (169.xxx)? I think the latter are Microsoft-specific anyway...
                            if check_level == 0:
                                    check_level = check_level + 1
                            if check_level == 1: # not 'elif'; we want to fall through on the same connection and perform the next check.
                                # confirm we are connected and try a DNS lookup for response.
                                # FIXME: I'm not sure how to easily check we're still connected / in range except via data request (and associated timeout),
                                # so lets just do that for now...
                                
                                dns_tunnel_payload = base64.b32encode(str(check_attempts) + '.' + i.address + '.' + i.ssid)
                                dns_tunnel_payload = dns_tunnel_payload.replace("=","0") # comcast doesn't seem to like queries with = signs as padding; they go through but we don't get the response
                                try:
                                    print "Doing DNS query...",
                                    tunnel_resp = socket.gethostbyname(dns_tunnel_payload + '.' + dns_tunnel_domain)
                                    #tunnel_resp = socket.gethostbyname(dns_tunnel_domain)
                                    if tunnel_resp:
                                            check_level = check_level + 1
                                            print "Got response: %s" % tunnel_resp
                                            if tunnel_resp == dns_tunnel_pass_response:
                                                    tunnel_supported = 1
                                            else:
                                                    tunnel_supported = 0

                                except:
                                    print "DNS lookup failed!"
                                    pass
                            if (check_level == 2) and (i.ssid != 'xfinitywifi'):
                                # confirm we are connected and fetch the contents of a known website (implies another DNS lookup, but...).
                                # We can later compare these to see if any standard/popular portal landing pages stand out.
                                # Now skipping 'xfinitywifi' since we already have plenty of results from them
                                http_response = ''
                                buffer = StringIO()
                                h = pycurl.Curl()
                                h.setopt(h.URL, http_resp_url)
                                h.setopt(h.INTERFACE, iface)
                                h.setopt(h.WRITEDATA, buffer)
                                h.setopt(h.FOLLOWLOCATION, 1)
                                h.setopt(h.MAXREDIRS, 3)
                                h.setopt(h.TIMEOUT, 16)

                                try:
                                    h.perform()
                                except:
                                    pass
                                
                                h.close()

                                http_response = buffer.getvalue()
                                if len(http_response):
                                    print "Got HTTP response!"
                                    if http_resp_pass_string in http_response:
                                            print "Got authentic HTTP result!"
                                            # FIXME: Do something useful with this data
                                    check_level = check_level + 1

                        else:
                            print "Connection attempt failed"

                    
                    if i.quality > maxSigSeen:
                        maxSigSeen = i.quality

                    # Done with any checking (for now); update the db record.
                    c.execute(u'UPDATE wifis SET check_level=?, check_attempts=?, maxSigSeen=?, tunnel_supported=?, http_response=? WHERE bssid=?;', (check_level, check_attempts, maxSigSeen, tunnel_supported, sqlite3.Binary(zlib.compress(http_response)), i.address) )
                    conn.commit()
                    Delete(i.ssid)

