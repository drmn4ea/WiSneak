#! /bin/sh
# /etc/init.d/dnscatch_at_satartup 

### BEGIN INIT INFO
# Provides:          dnscatch
# Required-Start:    $remote_fs $syslog $all
# Required-Stop:     $remote_fs $syslog
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: Simple script to start a program at boot
# Description:       A simple script from www.stuffaboutcode.com which will start / stop a program a boot / shutdown.
### END INIT INFO

# If you want a command to always run, put it here

# Carry out specific functions when asked to by the system
case "$1" in
  start)
    echo "Starting dnscatch"
    # run application you want to start
    # ensure we start with a clean interfaces file
    cd /home/pi/Desktop/shared
    sudo cp dnscatch.log dnscatch.log.old
    sudo stdbuf -i0 -o0 -e0 python ./dnscatch.py >> dnscatch.log &
    ;;
  stop)
    echo "Stopping dnscatch"
    # kill application you want to stop
    killall python
    ;;
  *)
    echo "Usage: /etc/init.d/dnscatch {start|stop}"
    exit 1
    ;;
esac

exit 0
