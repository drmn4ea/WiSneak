#! /bin/sh
# /etc/init.d/WifindAtStartup.sh 

### BEGIN INIT INFO
# Provides:          wifind
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
    echo "Starting wifind"
    # run application you want to start
    # ensure we start with a clean interfaces file
    sudo cp /etc/network/interfaces.good /etc/network/interfaces
    cd /home/pi/Desktop/shared
    sudo python ./wifind.py >> wifind.log &
    ;;
  stop)
    echo "Stopping wifind"
    # kill application you want to stop
    killall python
    ;;
  *)
    echo "Usage: /etc/init.d/wifind {start|stop}"
    exit 1
    ;;
esac

exit 0
