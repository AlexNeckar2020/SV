#!/bin/bash

# --- Color table for ANSI escape codes ---
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}Uninstalling Stern-Volmer controller app...${NC}\n"

# 1. Remove the virtual environment
echo -e "${YELLOW}Step 1/2:${GREEN} Removing virtual environment...${NC}"
if [ -d "/home/pi/.SV_venv" ]; then
    rm -rf /home/pi/.SV_venv
else
    echo -e "${YELLOW} Virtual environment not found, did nothing.${NC}"
fi

# 2. Remove the desktop shortcut
DESKTOP_FILE="/home/pi/Desktop/Stern-Volmer.desktop"
echo -e "${YELLOW}Step 2/2:${GREEN} Removing desktop shortcut...${NC}"
if [ -f "$DESKTOP_FILE" ]; then
    rm "$DESKTOP_FILE"
else
    echo -e "${YELLOW} Desktop shortcut not found, did nothing.${NC}"
fi

# Summary
printf "${CYAN}"
cat <<EOF

 *********************************************************
 * Uninstallation complete!                              *
 * The system dependencies (libusb, etc.), if installed, *
 * were left intact to ensure system stability.          *
 *********************************************************
EOF
printf "${NC}\n"

sleep 30
