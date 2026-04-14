#!/bin/bash

# Get the absolute path for this script folder
APP_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# --- Color table for ANSI escape codes ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # reset to no color

echo -e "${CYAN}--- Stern-Volmer app installation ---${NC}\n"

# 1. Install system dependencies for USB (libusb) and Serial access
echo -e "\n${YELLOW}Step 1/8:${GREEN} Installing system dependencies...${NC}"
sudo apt update
sudo apt install -y python3-dev libusb-dev libudev-dev

# 2. Enable UART interfaces in config.txt
echo -e "\n${YELLOW}Step 2/8:${GREEN} Configuring Raspberry Pi Hardware UARTs...${NC}"
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

# 3. Create virtual environment in ~/.SV_venv
echo -e "\n${YELLOW}Step 3/8:${GREEN} Creating virtual environment...${NC}"
python3 -m venv /home/pi/.SV_venv

# 4. Activate environment and upgrade core tools
echo -e "\n${YELLOW}Step 4/8:${GREEN} Activating virtual environment...${NC}"
source /home/pi/.SV_venv/bin/activate
pip install --upgrade pip setuptools wheel cython

# 5. Install Python packages
echo -e "\n${YELLOW}Step 5/8:${GREEN} Installing Python requirements...${NC}"
# Point the Python builder to the location of package config (.pc) files
# export PKG_CONFIG_PATH=/usr/lib/aarch64-linux-gnu/pkgconfig:/usr/share/pkgconfig
# Find dynamically the correct paths for libusb headers and libraries
# export CFLAGS=$(pkg-config --cflags libusb-1.0)
# export LDFLAGS=$(pkg-config --libs libusb-1.0)
pip install -r requirements/linux.txt

# 6. Set up USB permissions for SeaBreeze (spectrometer)
echo -e "\n${YELLOW}Step 6/8:${GREEN} Configuring SeaBreeze USB rules...${NC}"
if [ -f "/home/pi/.SV_venv/bin/seabreeze_os_setup" ]; then
    sudo /home/pi/.SV_venv/bin/seabreeze_os_setup
else
    echo -e "${RED}Warning: ${YELLOW}seabreeze_os_setup not found. USB use may require sudo.${NC}"
fi

# 7. Add user to dialout group for UART/Serial access
echo -e "\n${YELLOW}Step 7/8:${GREEN} Granting Serial port permissions...${NC}"
sudo usermod -a -G dialout $USER

# 8. Create desktop shortcut for the app
echo -e "\n${YELLOW}Step 8/8:${GREEN} Creating desktop shortcut...${NC}"
cp $APP_DIR/Rsc/SV.png /home/pi/.SV_venv/SV.png
DESKTOP_FILE="/home/pi/Desktop/Stern-Volmer.desktop"
# Use a Heredoc to write the desktop shortcut file
cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Name=Stern-Volmer
Comment=Launch Stern-Volmer controller app from the virtual environment
Icon=/home/pi/.SV_venv/SV.png
Exec=$APP_DIR/SV-raspbian.sh
Terminal=true
Type=Application
X-KeepTerminal=true
EOF
# Make the shortcut executable
chmod +x "$DESKTOP_FILE"
# Trust the new desktop shortcut
gio set "$DESKTOP_FILE" metadata::trusted true
# Force updating the desktop
# update-desktop-database /home/pi/Desktop/ > /dev/null 2>&1 || true

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
