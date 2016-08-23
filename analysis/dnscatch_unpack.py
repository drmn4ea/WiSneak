import base64

##############################
# DNS catcher script logfile
input_fname = './dns_logs/dnscatch.log'

# Output file name (.csv)
output_fname = "dnscatch.csv"

###############

# Log contains lines which look like:
# Request: [68.87.71.227:52994] (udp) / 'GAXDAQZ2...rest of base32-encoded payload here...000000.your.tunnel.server.' (A)
# These decode to e.g.: 2.C0:FF:EE:D0:0D:00.ssid
# (that is check_attempts, MAC address, then the ssid separated by periods)

with open(input_fname, 'r') as f:
    with open(output_fname, 'wt') as outf:
        for line in f.readlines():
            #print line
            if ".t.cexx.org" in line:
                (junk1, payload) = line.split("'", 1)
                (payload, junk2) = payload.split(".", 1)

                #print "Raw payload: %s" % payload
                # The '=' characters at the end of the Base64 strings are replaced by 0s in the payload
                # to comply with valid domain naming characters; change them back here.
                payload = payload.replace("0", "=")
                try:
                    decoded_payload = base64.b32decode(payload)
                    print "Decoded payload is: %s" % decoded_payload
                    #print decoded_payload.split('.', 2)
                    #outf.write("%s, %s, %s" % decoded_payload.split('.', 2))
                    outf.write(decoded_payload.replace('.', ', ', 3) + '\n')
                except TypeError:
                    print "(invalid payload: %s)" % payload
