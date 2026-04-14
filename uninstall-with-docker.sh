#!/bin/bash

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}--- Stern-Volmer Docker Uninstaller ---${NC}\n"

# 1. Remove the Docker Image (The heavy part)
if docker image inspect sv_app:v1 >/dev/null 2>&1; then
    echo -e "${YELLOW}Step 1/2:${GREEN} Removing Docker image (sv_app:v1)...${NC}"
    docker rmi -f sv_app:v1
    # Final cleanup of any orphaned layers
    docker builder prune -f
else
    echo -e "${YELLOW}Step 1/2:${RED} No Docker image found.${NC}"
fi

# 2. Remove the Desktop Shortcut
DESKTOP_FILE="/home/pi/Desktop/Stern-Volmer.desktop"
if [ -f "$DESKTOP_FILE" ]; then
    echo -e "${YELLOW}Step 2/2:${GREEN} Removing desktop shortcut...${NC}"
    rm "$DESKTOP_FILE"
else
    echo -e "${YELLOW}Step 2/2:${RED} Shortcut not found.${NC}"
fi

# Optional: We usually leave the udev rules as they don't take space
# but you can add: sudo rm /etc/udev/rules.d/10-oceanoptics.rules here.

echo -e "\n${CYAN}Uninstallation complete!${NC}"
sleep 30
