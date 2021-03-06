WiSneak - A WiFi hotspot DNS tunneling survey tool
--------------------------------------------------

WiSneak is a collection of ugly Python scripts for surveying (wardriving) the landscape of WiFi hotspots for susceptibility to DNS tunneling, and for use by WiFi geolocation. Data gathered from such surveys can be used to determine if, or where, various IoT telemetry projects are feasible using public WiFi hotspots. These scripts are tested on a Raspberry Pi running Raspbian Jessie, but should run in almost any Linux environment.

DNS tunneling is a technique for sneaking small amounts of data through public WiFi hotspots that normally require a valid login or payments (captive portals) before they will let you reach the open Internet. WiFi geolocation, of course, is the use of a giant database of collected WiFi access point location data to estimate your location based on the existence and signal strength of nearby access points.

Overview
--------

WiSneak consists of two main parts: 

1) A survey script (wifind.py), which scans and surveys the access points. This is typically run from a portable computer on a moving vehicle.

2) A fake DNS server script (dnscatch.py) for the survey script to phone home to. 

A couple other scripts (analysis folder) are used to process the logged data and perform geolocation queries using the Mozilla Location Service.

This is extremely hacky and done basically in the most expedient manner possible. It's ugly, but it works.

Requirements
------------

### Services (only needed for tunnel probing mode) ###
* Domain name
* Web hosting account that will let you create custom DNS records for your domain (e.g. Dreamhost shared hosting). This is required only for the DNS tunneling portion of the survey; you can still collect WiFi geolocation results without a domain or web hosting.

### Hardware ###

* One portable Linux computer with WiFi capabilities (USB dongle is fine)
* USB GPS dongle
* For tunnel probing only: A second Linux computer capable of receiving and responding to data from the Internet (i.e. port forwarding set up correctly on your firewall or wireless access point)

### Software ###
Python 2.x

#### On DNS catcher server (if tunnel probing) ####
[dnslib](https://pypi.python.org/pypi/dnslib)

#### On survey computer ####
[wifi](https://wifi.readthedocs.io/en/latest/)  
[pycurl](http://pycurl.io/)  
[gpsd](http://catb.org/gpsd/)  
gpsd-clients  

#### On analysis computer (may be the same machine as one of the above) ####
[requests](http://docs.python-requests.org/en/master/)

Most of these prerequisites can be installed using 'pip' on recent versions of Python2 (sudo pip install packagename)

Setup
-----

### Web Hosting DNS and Home Router ###
To use DNS tunneling surveying, you need to add a DNS record for your domain that defines a subdomain and delegates to (points to) a fake nameserver (dnscatch.py) under your control. To set this up:

1) Create a NS record whose name is the name of your desired tunneling subdomain, and whose value is a more descriptive subdomain. The name doesn't really matter for this script, but if you want to do any serious use of DNS tunneling (e.g. ozymandns, iodine) on your own, keep it short to maximize the possible payload. For example, if you own example.com and want to use "t.example.com" as your tunneling subdomain, create a NS record with name "t" and value e.g. "tunnel.example.com." (note the period at the end).

2) Create an A record that points the NS record you created above to the IP address of your fake DNS server (dnscatch.py). This can be a PC sitting in your apartment, as long as it has unimpeded internet access. Mine runs on a Raspberry Pi attached to my WiFi access point attached to residential cable internet. For example, if you used "tunnel.example.com" as your descriptive name, create an A record with name "tunnel" and value "198.51.100.42" (or whatever the external IP address of your cablemodem is).

3) If running the server on a home internet connection, you probably have to tweak your router/firewall/Wireless Access Point's configuration to forward port 53 (DNS) to your server. If you are given the option to forward TCP or UDP, select both (really, UDP should be enough). This won't affect your ability to resolve domain names or surf the web; it only applies to *incoming* DNS requests, which will be generated by the survey script.

### Fake DNS server ###

The following instructions worked for me on a Raspberry Pi.

Make sure dnslib is installed. Copy dnscatch.py to somewhere convenient on the server. This is basically just the dnslib "fixed DNS resolver" example with the response hardcoded to 123.45.67.89 (feel free to pick your own descriptive value). Optionally, test everything is working by starting the script, then accessing your tunnel domain name in a web browser. You should get one or more entries onscreen referring to that name. If so, congratulations, your DNS records and any port forwarding are set up correctly! Finally, run the script "for real" with the console output redirected to a file, e.g. "sudo dnscatch.py >> dnscatch.log", or set it to run at startup if you prefer (see example init.d script in the "support_files" subfolder).

### Survey Device ###

1) Install the required libraries listed above, and ensure your network adapter is configured and working properly. Open your /etc/network/interfaces file and ensure the section pertaining to your network card is configured similar to:

	allow-hotplug wlan0
	iface wlan0 inet manual
		wpa-conf /etc/wpa_supplicant/wpa_supplicant.conf

Make a backup copy of this file, e.g. "interfaces.good" so that a known-good copy can be restored at startup.

2) Edit your /etc/dhcp/dhclient.conf file to reduce the timeouts and maximize the chance of success when traveling at speed. Find the "timeout" line and set it to the desired value; around 10 seconds works for me. Too short delay will cause false rejections of potentially receptive tunneling APs that are just sluggish or at the edge or radio range; too long a delay and you'll miss a lot of other APs while waiting on a single connection attempt. Then, find the "initial-interval" line and set it to a low value, e.g. 1 second. This tells the DHCP client to retry more aggressively.

3) Plug in your GPS dongle and ensure that it appears as a USB-serial port (e.g. /dev/ttyUSB0). Optional: verify it is putting out data. Assuming it is on /dev/ttyUSB0, you can use:

	stty -F /dev/ttyUSB0 ispeed 4800 && cat </dev/ttyUSB0

You should begin to see NMEA text strings on the console. If you get a "Permisison denied" / "unable to perform all the requested actions", try running this as superuser ("sudo stty...").

NB: On a Raspberry Pi 2 (Raspbian Jessie, 8/2016), I had to muck about in the udev rules (/lib/udev/rules.d/60-gpsd.rules) so that gpsd could successfully connect to the device (permissions crap). In particular, this file included a rule for my device (using the very common PL2023 USB-serial chip), but it was commented out with a note, "rule disabled in Debian as it matches too many other devices". Uncommenting this line and rebooting fixed it.

Optionally, try running 'cgps' at the console to ensure gpsd can connect to your device.

4) Copy 'wifind.py' to the desired location and adjust the configuration near the top of the file as desired.

5) Optional but recommended: Set the script to run at startup. I strongly recommend reviewing the "WifindAtStartup" init.d script in the wifind support_files folder. In particular, make sure that the known-good copy of /etc/network/interfaces is restored before the script starts, as the WiFi surveying process requires rapidly adding and removing AP info from this file, and it can occasionally wind up in an unhappy state.


Operation
---------

Wifind.py has two main modes of operation, location logging and tunnel probing. Both can be run at the same time, but for best location logging results, the location logging mode should be run on its own as the probing process ties up the WiFi interface quite a bit.

In the location logging mode, it scans for nearby access points and dumps the list to a database record along with the local time, GPS lat/lon and GPS time. The number of points per second is determined (probably) by your GPS's update rate. 

In the tunnel probing mode, it scans for nearby access points and attempts to connect to any unsecured access point whose tunneling status is not yet known. If it successfully connects (DHCP address assignment), it sends a DNS tunneling probe (will be caught and responded to by 'dnscatch') containing basic information about the AP (BSSID and SSID), waits for a response, then tries to fetch a known HTTP web page and check for a known string in the response. This determines whether the AP is truly open (returns desired page) or a captive portal (asks for login or money). The HTTP response is logged to the database file for later review. An access point is 'known' if it proceeds all the way to the HTTP check or the maximum number of attempts is reached. Summary details of both encrypted and unencrypted APs (BSSID, SSID, etc.) are logged as well.

NOTE: Due to a limitation in the Wireless Tools for Linux, probing access points with an empty SSID ('') is unsupported and these are ignored.

Analysis
--------

First, run 'dnscatch_unpack.py' on the dnscatch log to extract the local list of successful tunneling APs.

Next, set up the options at the beginning of 'querymls.py' and run it. This will list each survey trip (run) taken and prompt for which one(s) to dump data for. Location track data is exported as .GPX waypoint files, and .GPX POI (points of interest) files to optionally mark individual track points. Depending on the options selected, the GPS track, WiFi geolocation track and/or points with a tunnelable AP in view are exported.

NOTE: The WiFi geolocation option uses Mozilla Location Service, which nominally requires an API key (free of charge). You can use the key 'test' for small-volume hobby use, but please don't abuse it. MLS reserves the right to limit the number of requests per day or per user / API key. GPS location tracks are generated from local data only and don't hit any external servers.