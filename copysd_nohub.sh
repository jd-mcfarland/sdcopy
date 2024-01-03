#!/bin/bash
set -x

# Define the base destination directory
DESTINATION="/mnt/7c2456dd-dbd7-4c0a-ac11-192eb0c1f2af/nas_backup/PhotoLandingZone"

# Create a unique subdirectory for each copy job
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
SUBDIR="$DESTINATION/$TIMESTAMP"
mkdir -p "$SUBDIR"

# Define the mount point of the SD card and log file location
MOUNT_POINT="/media/nas"
LOG_FILE="/home/nas/Documents/copysdlogs/copysdlogs.log"
echo "Executing user: $(whoami)" >> "$LOG_FILE"
echo "Script started at $(date)" >> "$LOG_FILE"
env >> "$LOG_FILE"

# Notify user of script execution
echo "Script execution initiated. The copy operation is running in the background." >> "$LOG_FILE"

# Run the wait-for-mount and copy operations in the background
nohup bash -c "
    echo 'Begin Background Process at $(date)' >> '$LOG_FILE'
    MAX_WAIT=10  # Maximum number of seconds to wait
    for ((i=1; i<=MAX_WAIT; i++)); do
        if [ -d '$MOUNT_POINT' ] && [ \"\$(ls -A '$MOUNT_POINT')\" ]; then
            echo 'SD card mounted, proceeding with copy' >> '$LOG_FILE'
            break
        fi
        echo 'Waiting for SD card to mount (\$i/\$MAX_WAIT)' >> '$LOG_FILE'
        sleep 1
    done

    if [ -d '$MOUNT_POINT' ] && [ \"\$(ls -A '$MOUNT_POINT')\" ]; then
        cp -R '$MOUNT_POINT'/* '$SUBDIR/'
        # Email notification commented out
        # SUBJECT='Copy Job Completed'
        # BODY='Copy job to $SUBDIR completed successfully'
        # echo -e \"Subject: \$SUBJECT\r\n\r\n\$BODY\" | msmtp parabellum2000@gmail.com
        echo 'Copy job completed successfully at $(date)' >> '$LOG_FILE'
    else
        echo 'SD card not mounted, aborting copy' >> '$LOG_FILE'
        # Email notification commented out
        # SUBJECT='Copy Job Failed'
        # BODY='Copy job failed - SD card not mounted'
        # echo -e \"Subject: \$SUBJECT\r\n\r\n\$BODY\" | msmtp parabellum2000@gmail.com
    fi
" >> "$LOG_FILE" 2>&1 &
wait $!

echo "Script completed at $(date)" >> "$LOG_FILE"
