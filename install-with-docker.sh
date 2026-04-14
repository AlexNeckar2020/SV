#!/bin/bash

# Get the absolute path for this script folder
APP_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# --- Color table for ANSI escape codes ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}--- Stern-Volmer app installation (with Docker) ---${NC}\n"

# 1. Host Dependencies
echo -e "${YELLOW}Step 1/6:${GREEN} Installing host system dependencies...${NC}"
sudo apt update
sudo apt install -y libusb-dev libudev-dev

# 2. Enable UART interfaces in config.txt
echo -e "\n${YELLOW}Step 2/6:${GREEN} Configuring Raspberry Pi Hardware UARTs...${NC}"
if [ -f "/boot/firmware/config.txt" ]; then
    CONFIG_FILE="/boot/firmware/config.txt"
else
    CONFIG_FILE="/boot/config.txt"
fi
# Array of UART overlays needed
UARTS=("uart3" "uart4" "uart5")
for uart in "${UARTS[@]}"; do
    if grep -q "dtoverlay=$uart" "$CONFIG_FILE"; then
        echo -e "${GREEN}UART overlay $uart seems already enabled.${NC}"
    else
        echo -e "${GREEN}Enabling $uart...${NC}"
        # Append to the end of the file
        sudo bash -c "echo 'dtoverlay=$uart' >> $CONFIG_FILE"
    fi
done

# 3. Permissions
echo -e "${YELLOW}Step 3/6:${GREEN} Configuring user groups (Docker & Serial)...${NC}"
sudo usermod -aG docker $USER
sudo usermod -aG dialout $USER

# 4. Build Logic with Space Management
echo -e "${YELLOW}Step 4/6:${GREEN} Preparing Docker image...${NC}"
if docker image inspect sv_app:v1 >/dev/null 2>&1; then
    echo -e "${RED}Warning: ${YELLOW}Image 'sv_app:v1' already exists.${NC}"
    read -p "Do you want to REBUILD the image (slow)? (y/N): " confirm
    if [[ ! $confirm =~ ^[Yy]$ ]]; then
        SKIP_BUILD=true
    fi
fi

if [ "$SKIP_BUILD" != true ]; then
    # Clean up old "dangling" layers before building to save SD card space
    echo -e "${GREEN}Cleaning old cache to free space...${NC}"
    docker image prune -f
    echo -e "${GREEN}Building image (slow, please wait until complete)...${NC}"
    docker build -t sv_app:v1 "$APP_DIR"
else
    echo -e "${GREEN}Using existing image.${NC}"
fi

# 5. USB Rules (Sourcing from /Rsc/10-oceanoptics.rules)
echo -e "${YELLOW}Step 5/6:${GREEN} Applying OceanOptics USB rules...${NC}"
RULES_SRC="$APP_DIR/Rsc/10-oceanoptics.rules"
RULES_DEST="/etc/udev/rules.d/10-oceanoptics.rules"

if [ -f "$RULES_SRC" ]; then
    sudo cp "$RULES_SRC" "$RULES_DEST"
    sudo udevadm control --reload-rules && sudo udevadm trigger
    echo -e "${GREEN}Rules applied.${NC}"
else
    echo -e "${RED}Warning: {YELLOW}$RULES_SRC not found, USB spectrometer permissions need to be added manually or device access will fail.${NC}"
fi

# 6. Desktop Shortcut
echo -e "${YELLOW}Step 6/6:${GREEN} Creating desktop shortcut...${NC}"
DESKTOP_FILE="/home/pi/Desktop/Stern-Volmer.desktop"
cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Name=Stern-Volmer (Docker)
Comment=Launch Stern-Volmer controller app from the Docker container
Icon=$APP_DIR/Rsc/SV.png
Exec=$APP_DIR/SV-RPi-docker.sh
Terminal=true
Type=Application
X-KeepTerminal=true
EOF

chmod +x "$DESKTOP_FILE"
chmod +x "$APP_DIR/SV-RPi-docker.sh"
gio set "$DESKTOP_FILE" metadata::trusted true

# End of installation message
printf "${CYAN}"
cat <<EOF

 ***********************************************************************
 * Installation complete!                                              *
 * IMPORTANT: Please $(printf "${RED}REBOOT${CYAN}") your Pi for config changes to take effect. *
 ***********************************************************************
EOF
printf "${NC}\n"
sleep 30
