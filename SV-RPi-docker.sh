#!/bin/bash

# 1. Grant Docker access to the local X11 display (for GUI)
xhost +local:docker > /dev/null

# 2. Safety check for the hardware rules on the host
if [ ! -f /etc/udev/rules.d/10-oceanoptics.rules ]; then
    echo "Warning: USB rules (10-oceanoptics.rules) not found on host. Spectrometer may be inaccessible."
fi

# 3. Run the container
# --privileged: Access to GPIO/PWM
# -v /dev:/dev: Maps USB/Serial hardware
# --rm: Deletes container instance on exit (saves SD space)
docker run -it --rm \
    --privileged \
    --net=host \
    -e DISPLAY=$DISPLAY \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -v /dev:/dev \
    sv_app:v1
