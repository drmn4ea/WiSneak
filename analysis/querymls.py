
from __future__ import division
from datetime import datetime, timedelta
import json
import sqlite3

# external stuff
import requests


###########################

# UTC offset in hours
tzoffset = "-4"

# Select whether to export the GPS track (relies only on local data)
export_gps_track = True

# Select whether to export the WiFi-derived track (makes a request to Mozilla per point; disable for testing or when not needed)
export_wifi_track = True

# Select whether to export a list of points with a tunnelable AP in range. Requires CSV output from dnscatch_unpack.py.
export_tunnel_aps = True

# Filename of tunnelable AP list
tunnel_aps_fname = 'dnscatch.csv'

# URL for Mozilla Location Services queries
query_url = 'https://location.services.mozilla.com/v1/geolocate?key=YOUR_API_KEY'

# Database file for location tracks
loc_dbfile = 'wifis.db'


###########################


def list_runkeys(c):
    ''' Given a sqlite cursor, extract the list of unique runkeys from the db.'''
    c.execute('SELECT DISTINCT runkey FROM wifilocation;')
    ret = c.fetchall()
    #print ret
    # E.g: [(129325110,), (208731282,), (399435108,), (617262454,), (807860553,)]
    # Extract the results into a proper list
    ret2 = []
    ret2.extend([i[0] for i in ret])
    #print ret2
    # E.g. [129325110, 208731282, 399435108, 617262454, 807860553]

    # While we're at it, get some basic stats about each runkey.
    # Basically, want to know the approximate start/end times of the run and
    # how many valid points it contains
    results = []
    for i in ret2:
        #print i
        c.execute('SELECT gps_time FROM wifilocation WHERE runkey=? AND gps_lat IS NOT NULL AND gps_time IS NOT "";', (i,))
        one_run_result = c.fetchall()
        if len(one_run_result):
            min_time = 99999999999999
            max_time = 0
            for j in one_run_result:
                if len(j[0]): # catch empty strings
                    t = gpstime_to_epoch(j[0])
                    if min_time > t:
                        min_time = t
                    if max_time < t:
                        max_time = t
            results.append([i, len(one_run_result), min_time, max_time])
    return results




def gpstime_to_epoch(s):
    ''' Given a raw GPSD UTC time string, convert to epoch seconds'''
    # s is e.g.: "2016-08-13T20:48:31.000Z"
    # Parsing these is a bit ugly; steal cookbook code from the internet
    # Ref: http://stackoverflow.com/questions/969285/how-do-i-translate-a-iso-8601-datetime-string-into-a-python-datetime-object
    # http://stackoverflow.com/questions/8777753/converting-datetime-date-to-utc-timestamp-in-python
    #print s
    t = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%fZ")
    #print t
    td = t - datetime(1970,1,1)
    return (td.microseconds + (td.seconds + td.days * 86400) * 10**6) / 10**6

    #return datetime.datetime.fromtimestamp(t + 0.0) # floatify
    #return t.total_seconds()



def get_gps_trackpoints_for_runkey(c, runkey, include_macs = False):
    ''' Given a database cursor and runkey, output the list of GPS lat/lon points in time order.
        NB: Time order uses the system clock, not the GPS clock in case it matters.
    '''

    # Build the query string based on the input options
    q1 = 'SELECT gps_lat, gps_lon'
    q2 = ', wifi_json'
    q3 = ' FROM wifilocation WHERE runkey=? AND gps_lat IS NOT NULL AND gps_time IS NOT "" ORDER BY localtime;'

    if include_macs:
        query = q1 + q2 + q3
    else:
        query = q1 + q3
    
    c.execute(query, (runkey,))
    trackpoints = c.fetchall()
    if len(trackpoints):
        return trackpoints

def get_wifi_trackpoints_for_runkey(c, runkey, match_gps = False, include_macs=False, include_accuracy = False, min_accuracy=None):
    ''' Given a database cursor and runkey, output the list of WiFi lat/lon points in time order by querying Mozilla Location Service or compatible service.
        If 'match_gps' is True, exclude points that don't have a corresponding GPS coordinate.
        NB: Time order uses the system clock, not the GPS clock in case it matters.
    '''
    
    # The WiFi AP data is stored in the DB as a JSON text blob pre-formatted in the MLS (v1) query format ('cause why not?),
    # so just pass it along to the server.
    # On success, the result should also be a JSON string, similar to:
    # {"location": {"lat": 42.1234567, "lng": -71.7654321}, "accuracy": 114.1786328}
    
    if match_gps:
        c.execute('SELECT wifi_json FROM wifilocation WHERE runkey=? AND gps_lat IS NOT NULL AND gps_time IS NOT "" ORDER BY localtime;', (runkey,))
    else:
        c.execute('SELECT wifi_json FROM wifilocation WHERE runkey=? ORDER BY localtime;', (runkey,))
    trackpoints = c.fetchall()
    trackpoints_out = []
    if len(trackpoints):
        for i in xrange(len(trackpoints)):
            r = requests.post(query_url, data=trackpoints[i][0])
            if 'lng' in r.text: # cheesy validation that we have a non-error result
                point_dict = json.loads(r.text)
                point = [point_dict['location']['lat'], point_dict['location']['lng']]
                if include_macs:
                    point.append(trackpoints[i][0]) # wifi_json
                if include_accuracy:
                    point.append(point_dict['accuracy'])
                if min_accuracy is None:
                    trackpoints_out.append(point)
                elif point_dict['accuracy'] < min_accuracy:
                    trackpoints_out.append(point)
                else:
                    print "Accuracy too low; dropping the following point:"
                print "%u/%u : %s (accuracy: %.2f)" % (i, len(trackpoints), str(point[0:2]), point_dict['accuracy'])

            else:
                # Failed; dump the contents to the screen
                print "Unexpected response from server:"
                print r.text
    #print trackpoints_out
    return trackpoints_out


def get_tunnelable(points, tunnel_aps_fname):
    ''' Given a list of points in [lat, lon, wifi_json] form and a CSV file containing a list of tunnelable AP MAC addresses
        in [x, mac, x] format, return only those points which have a tunnelable AP in view
    '''
    with open(tunnel_aps_fname, 'rt') as f:
        # Extract the 2nd column of each line of the CSV file into a new list, with whitespace trimmed
        tunnel_macs = [x.split(',', 2)[1].replace(' ','') for x in f.readlines()]
        #print tunnel_macs
        #print pts[0][2]
        tunnel_pts = []
        for j in pts:
            #print j[0:2]
            tunnel = False
            for k in tunnel_macs:
                if k in j[2]:
                    tunnel = True
            if tunnel:
                tunnel_pts.append(j)
                
        print "Total %u of %u points had a tunneling AP in range" % (len(tunnel_pts), len(pts))
        return tunnel_pts


def dump_trackpoints_to_gpx(trackpoints, waypoints=[], starttimestring=None, fname='default.gpx', title='Default Track'):
    ''' Given a list of (lat,lon) tuples, create a valid-looking .GPX file.'''
    # Extremely cheesy GPX file generation ahead. Headers cribbed from:
    # http://www.gpsvisualizer.com/convert_input
    # https://en.wikipedia.org/wiki/GPS_Exchange_Format
    # http://cycleseven.org/gps-waypoints-routes-and-tracks-the-difference

    #if(len(trackpoints)):
    with open(fname, 'wt') as f:
        f.write('<?xml version="1.0"?>\n\t<gpx creator="IoToiletTracker http://tim.cexx.org/" version="1.1" xmlns="http://www.topografix.com/GPX/1/1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd">\n')
        f.write('\t<trk>\n')
        f.write('\t\t<name>%s</name>\n' % title)
        if len(trackpoints):
            f.write('\t\t<trkseg>\n')
            for i in trackpoints:
                f.write('\t\t\t<trkpt lat="%f" lon="%f"></trkpt>\n' % (i[0], i[1]))
            f.write('\t\t</trkseg>\n')
        f.write('\t</trk>\n')
        if len(waypoints):
            for i in waypoints:
                f.write('\t<wpt lat="%f" lon="%f"></wpt>\n' % (i[0], i[1]))
        f.write('</gpx>')

def dump_trackpoints_to_csv(trackpoints, starttimestring=None, fname='default.csv', title='Default Track'):
    ''' Given a list of (lat,lon) tuples, create a CSV file.'''

    if(len(trackpoints)):
        with open(fname, 'wt') as f:
            for i in trackpoints:
                f.write('%f,%f\n' % (i[0], i[1]))
    




if __name__ == "__main__":

    # Open the location file
    loc_conn = sqlite3.connect(loc_dbfile)
    loc_c = loc_conn.cursor()

    # Get the unique 'runkeys' in the dataset. Each runkey is a unique random number identifying a single run (trip / power cycle)
    # So far, my RPI manages to generate unique runkeys for each ride despite identical startup conditions and headless operation,
    # but I can't guarantee this for all cases...
    runkeys = list_runkeys(loc_c)
    # output is runkey, nPts, startTime, endTime
    #print runkeys
    # display info about the runkeys and let the user select one (or all)
    print "\r\nPlease select a trip, or enter 'a' for all trips."
    for i in xrange(len(runkeys)):
        print "%u) %u (%u points, %s ~ %s)" % (i, runkeys[i][0], runkeys[i][1], datetime.fromtimestamp(runkeys[i][2]).strftime('%c'), datetime.fromtimestamp(runkeys[i][3]).strftime('%c'))
    resp = raw_input()
    if not 'a' in resp and not 'A' in resp:
        # Pass on only the selected entry
        runkeys = [runkeys[int(resp)]]

    #print runkeys

    for i in runkeys:
        # Do the actual work of generating GPX from the given data.
        if export_gps_track:
            # This part is easy; just dump the list of valid lat/lon coordinates
            #print i[0]
            print "Exporting GPS track..."
            pts = get_gps_trackpoints_for_runkey(loc_c, i[0], include_macs = True) # so we can match tunnel-able APs later
            title = 'gps-%u-%s' % (i[0], datetime.fromtimestamp(i[2]).strftime('%Y%m%d__%H_%M_%S'))
            dump_trackpoints_to_gpx(pts, fname=title + '.gpx', title=title)
            dump_trackpoints_to_csv(pts, fname=title + '.csv', title=title)

            if export_tunnel_aps:
                print "Exporting tunnelable APs as waypoints..."
                # Laziness: Match the in-view APs for each *gps* point against the dnscatch output, then dump only those points to a new GPX.
                # This has the benefit of slightly cleaner-looking output (the GPS tracks tend to be better), with the downside of making GPS a hard requirement.

                tunnel_pts = get_tunnelable(pts, tunnel_aps_fname)
                
                title = 'gps-%u-%s-tunnelable' % (i[0], datetime.fromtimestamp(i[2]).strftime('%Y%m%d__%H_%M_%S'))
                # want to dump these as waypoints only, not trackpoints, so just pass an empty list for trackpoints
                dump_trackpoints_to_gpx([], waypoints = tunnel_pts, fname=title + '.gpx', title=title)


        if export_wifi_track:
            print "Exporting WiFi track..."
            pts = get_wifi_trackpoints_for_runkey(loc_c, i[0], match_gps = False, include_macs = True, min_accuracy=1000.0)
            title = 'wifi-%u-%s' % (i[0], datetime.fromtimestamp(i[2]).strftime('%Y%m%d__%H_%M_%S'))
            dump_trackpoints_to_gpx(pts, fname=title + '.gpx', title=title)
            # also dump as POIs to make the actual location points easier to see
            dump_trackpoints_to_gpx([], waypoints=pts, fname=title + '-points.gpx', title=title)
            dump_trackpoints_to_csv(pts, fname=title + '.csv', title=title)

            if export_tunnel_aps:
                #print pts
                tunnel_pts = get_tunnelable(pts, tunnel_aps_fname)
                title = 'wifi-%u-%s-tunnelable' % (i[0], datetime.fromtimestamp(i[2]).strftime('%Y%m%d__%H_%M_%S'))
                # want to dump these as waypoints only, not trackpoints, so just pass an empty list for trackpoints
                dump_trackpoints_to_gpx([], waypoints = tunnel_pts, fname=title + '.gpx', title=title)
