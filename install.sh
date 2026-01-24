#!/bin/bash

# Neovolt Integration Installation Script for Home Assistant
# This script will copy the integration files to your Home Assistant custom_components directory

set -e

echo "========================================="
echo "Neovolt Integration Installer"
echo "========================================="
echo ""

# Check if running in Home Assistant environment
if [ ! -d "/config" ]; then
    echo "Error: /config directory not found."
    echo "This script should be run from within Home Assistant (e.g., using Terminal addon)"
    echo ""
    echo "Alternative: Manually copy files to your config/custom_components/neovolt/ directory"
    exit 1
fi

# Create custom_components directory if it doesn't exist
echo "Creating custom_components directory..."
mkdir -p /config/custom_components/neovolt

# Check if integration already exists
if [ -d "/config/custom_components/neovolt" ] && [ "$(ls -A /config/custom_components/neovolt)" ]; then
    echo ""
    echo "Warning: Neovolt integration directory already exists and contains files."
    read -p "Do you want to overwrite? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 1
    fi
fi

# Copy files
echo ""
echo "Installing Neovolt integration files..."

# Assuming files are in the same directory as this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# List of required files
FILES=(
    "__init__.py"
    "manifest.json"
    "const.py"
    "config_flow.py"
    "modbus_client.py"
    "sensor.py"
    "number.py"
    "select.py"
    "switch.py"
    "button.py"
    "strings.json"
)

# Copy each file
for file in "${FILES[@]}"; do
    if [ -f "$SCRIPT_DIR/$file" ]; then
        cp "$SCRIPT_DIR/$file" /config/custom_components/neovolt/
        echo "  ✓ Copied $file"
    else
        echo "  ✗ Warning: $file not found in script directory"
    fi
done

echo ""
echo "========================================="
echo "Installation Complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Restart Home Assistant"
echo "2. Go to Settings → Devices & Services"
echo "3. Click '+ Add Integration'"
echo "4. Search for 'Neovolt Solar Inverter'"
echo "5. Enter your Modbus TCP connection details"
echo ""
echo "For detailed instructions, see README.md"
echo ""
