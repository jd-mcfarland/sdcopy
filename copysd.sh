#!/bin/bash
set -x

# Define the base destination directory
DESTINATION="/mnt/7c2456dd-dbd7-4c0a-ac11-192eb0c1f2af/nas_backup/PhotoLandingZone"

# # Define the group name
# GROUP_NAME="sdcopy"

# Create a unique subdirectory for each copy job
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
SUBDIR="$DESTINATION/$TIMESTAMP"
mkdir -p "$SUBDIR"

# # Set group ownership and permissions for the new subdirectory
# chgrp -R "$GROUP_NAME" "$SUBDIR"
# chmod -R 775 "$SUBDIR"

# Define the mount point of the SD card and log file location
MOUNT_POINT="/media/nas"
LOG_FILE="/home/nas/Documents/copysdlogs/copysdlogs.log"
echo "Executing user: $(whoami)" >> $LOG_FILE
echo "!!!!!!!!!!!!!!!!!!Script started!!!!!!!!!!!! at $(date)" >> "$LOG_FILE"
env > "$LOG_FILE"
echo "!!!!!!!!!!!!!!!!!!End Foreground Process!!!!!!!!!!!! at $(date)" >> "$LOG_FILE"

# Run the wait-for-mount and copy operations in the background
(
    
    nohup sh -c 'echo "Background process test" >> /home/nas/Documents/copysdlogs/copysdlogs.log' 

    echo "!!!!!!!!!!!!!!!!!!Begin Background Process!!!!!!!!!!!! at $(date)" >> "/home/nas/Documents/copysdlogs/copysdlogs.log"
    MOUNT_POINT="/media/nas"
    echo "Executing Background user: $(whoami)" >> "/home/nas/Documents/copysdlogs/copysdlogs.log"
    echo "Background process running at $(date)" >>"/home/nas/Documents/copysdlogs/copysdlogs.log"
    env > "$LOG_FILE"
    # Wait for the SD card to be mounted
    MAX_WAIT=10  # Maximum number of seconds to wait
    for ((i=1; i<=MAX_WAIT; i++)); do
        if [ -d "$MOUNT_POINT" ] && [ "$(ls -A "$MOUNT_POINT")" ]; then
            echo "SD card mounted, proceeding with copy" >> "/home/nas/Documents/copysdlogs/copysdlogs.log"
            break
        fi
        echo "Waiting for SD card to mount ($i/$MAX_WAIT)" >> "/home/nas/Documents/copysdlogs/copysdlogs.log"
        sleep 1
    done

    # Proceed with copying if the SD card is mounted
    if [ -d "$MOUNT_POINT" ] && [ "$(ls -A "$MOUNT_POINT")" ]; then
        cp -R "$MOUNT_POINT"/* "$SUBDIR/"
        
        # Prepare email notification
        SUBJECT="Copy Job Completed"
        BODY="Copy job to $SUBDIR completed successfully"
        echo -e "Subject: $SUBJECT\r\n\r\n$BODY" | msmtp parabellum2000@gmail.com

        echo "Copy job completed successfully at $(date)" >> "/home/nas/Documents/copysdlogs/copysdlogs.log"
    else
        echo "SD card not mounted, aborting copy" >> "/home/nas/Documents/copysdlogs/copysdlogs.log"
        
        # Prepare email notification for failure
        SUBJECT="Copy Job Failed"
        BODY="Copy job failed - SD card not mounted"
        echo -e "Subject: $SUBJECT\r\n\r\n$BODY" | msmtp parabellum2000@gmail.com
    fi
) &

# Notify user of script execution
echo "Script execution initiated. The copy operation is running in the background."
echo "Script completed" >> "$LOG_FILE"