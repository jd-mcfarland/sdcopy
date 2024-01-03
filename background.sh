#!/bin/bash

# Assign passed arguments to variables
MOUNT_POINT="$1"
LOG_FILE="$2"

echo 'Begin Background Process' >> "$LOG_FILE"
MAX_WAIT=10

# Wait for the SD card to mount
for ((i=1; i<=MAX_WAIT; i++)); do
    # Find the specific mount point for the SD card within /media/nas
    SDCARD_MOUNT_POINT=$(find "$MOUNT_POINT" -mindepth 1 -maxdepth 1 -type d -print -quit)
    if [ -d "$SDCARD_MOUNT_POINT" ]; then
        echo "SD card mounted at $SDCARD_MOUNT_POINT" >> "$LOG_FILE"
        break
    fi
    echo "Waiting for SD card to mount ($i/$MAX_WAIT)" >> "$LOG_FILE"
    sleep 1
done

if [ -z "$SDCARD_MOUNT_POINT" ]; then
    echo 'SD card not mounted, aborting copy' >> "$LOG_FILE"
    SUBJECT="Copy Job Failed"
    BODY="Copy job failed - SD card not mounted"
    echo -e "Subject: $SUBJECT\r\n\r\n$BODY" | msmtp parabellum2000+sdcopy@gmail.com
    exit 1
fi

# Extract the name of the SD card from its mount point
SDCARD_NAME=$(basename "$SDCARD_MOUNT_POINT")
SDCARD_NAME=${SDCARD_NAME// /_}  # Replace spaces with underscores

# Create a unique subdirectory for each copy job using the SD card name, date, and time in 12-hour format (without seconds)
TIMESTAMP=$(date +"%Y%m%d_%I%M_%p") # 12-hour format with AM/PM, without seconds
DESTINATION="/mnt/7c2456dd-dbd7-4c0a-ac11-192eb0c1f2af/nas_backup/PhotoLandingZone/${SDCARD_NAME}_$TIMESTAMP"
mkdir -p "$DESTINATION"

# File for Rsync job summary
RSYNC_SUMMARY_FILE="$DESTINATION/transfer_summary.txt"

echo "Starting rsync to $DESTINATION..." >> "$LOG_FILE"
# Run Rsync and capture its output in the summary file
rsync -av --progress "$SDCARD_MOUNT_POINT"/ "$DESTINATION/" > "$RSYNC_SUMMARY_FILE" 2>&1

# Set ownership to root:sdcopy and permissions
chown -R nas:sdcopy "$DESTINATION"
chmod -R 2775 "$DESTINATION"
find "$DESTINATION" -type d -exec chmod 2775 {} \;
find "$DESTINATION" -type f -exec chmod 0664 {} \;

echo 'Rsync job completed' >> "$LOG_FILE"

# Email notification for success
SUBJECT="Copy Job Completed"
BODY="Copy job to $DESTINATION completed successfully"
echo -e "Subject: $SUBJECT\r\n\r\n$BODY" | msmtp parabellum2000+sdcopy@gmail.com

# Safely unmount the specific SD card mount point
echo "Unmounting $SDCARD_MOUNT_POINT..." >> "$LOG_FILE"
umount "$SDCARD_MOUNT_POINT"
if [ $? -eq 0 ]; then
    echo "SD card successfully unmounted from $SDCARD_MOUNT_POINT" >> "$LOG_FILE"
else
    echo "Failed to unmount SD card from $SDCARD_MOUNT_POINT" >> "$LOG_FILE"
fi
