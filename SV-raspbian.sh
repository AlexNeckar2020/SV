#!/bin/bash

# 1. Get the absolute path of the directory where THIS script is located
# (whether it is clicked, run via terminal, or from a desktop link)
SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" &> /dev/null && pwd)

# 2. Run the main app from within its virtual environment
/home/pi/.SV_venv/bin/python3 "$SCRIPT_DIR/SV.py"

# Optional: give time to see terminal output before closing
sleep 30
