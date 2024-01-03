#!/bin/bash

# Define the mount point of the SD card and log file location
MOUNT_POINT="/media/nas"
LOG_FILE="[PATH TO LOGS]/copysdlogs.log"

# Log the start of the process
echo "Executing user: $(whoami)" >> "$LOG_FILE"
echo "Script started at $(date)" >> "$LOG_FILE"
env >> "$LOG_FILE"
echo "Script execution initiated. The copy operation will run in the background." >> "$LOG_FILE"

# Path to the background script
BACKGROUND_SCRIPT="[PATH TO BACKGROUND SCRIPT]/background_copy_sd.sh"

# Run the background process asynchronously
nohup "$BACKGROUND_SCRIPT" "$MOUNT_POINT" "$LOG_FILE" >> "$LOG_FILE" 2>&1 &

echo "Script completed at $(date)" >> "$LOG_FILE"
