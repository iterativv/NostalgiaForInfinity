#Fork of https://github.com/lobap/NostalgiaForInfinity_Update/blob/master/NostalgiaForInfinity_Update.sh
#Changed a little bit by Yogabba (becouse for some reason didnt want to restart docker after update)
#Update to latest tag
#need to add to crontab by typing "crontab -e" in terminal "
#   */60 * * * * /bin/bash -c "ft_userdata/user_data/tools/simple_update.sh
#


#!/bin/bash

ROOT_PATH="Your root path f.e. (/home/user"
NFI_PATH="${ROOT_PATH}/NFI/NostalgiaForInfinityX.py"
FT_PATH="${ROOT_PATH}/ft_userdata/user_data/strategies/NostalgiaForInfinityX.py"
TG_TOKEN=""
TG_CHAT_ID=""
GIT_URL="https://github.com/iterativv/NostalgiaForInfinity"

# Go to NFI directory
cd $(dirname ${NFI_PATH})

# Fetch latest tags
git fetch --tags

# Get tags names
latest_tag=$(git describe --tags `git rev-list --tags --max-count=1`)
current_tag=$(git describe --tags)

# Create a new branch with the latest tag name and copy the new version of the strategy
if [ "$latest_tag" != "$current_tag" ]; then

    # Checkout to latest tag and update the NFI in Freqtrade folder
    git checkout tags/$latest_tag -b $latest_tag || git checkout $latest_tag
    cp $NFI_PATH $FT_PATH

    # Get tag to which the latest tag is pointing
    latest_tag_commit=$(git rev-list -n 1 tags/${latest_tag})

	# Compose the main message send by the bot
    curl -s --data "text=NFI is updated to tag: *${latest_tag}* . Please wait for reload..." \
         --data "parse_mode=markdown" \
         --data "chat_id=$TG_CHAT_ID" \
         "https://api.telegram.org/bot${TG_TOKEN}/sendMessage"

    sleep 120

    docker restart freqtrade

    curl -s --data "text=NFI reload has been completed!" \
         --data "parse_mode=markdown" \
         --data "chat_id=$TG_CHAT_ID" \
         "https://api.telegram.org/bot${TG_TOKEN}/sendMessage"
fi
