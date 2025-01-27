#!/bin/sh

### Prereqs:
## 1. A directory with the NFIX repo setup on the main branch to run via docker compose

### Simple script that does the following:
## 1. Pull NFIX repo
## 2. Stop, Pull, and Start freqtrader via docker compose
## 3. Add this script to a cron job to run at a specific interval: */60 * * * * /path/to/update_nfx_docker_compose.sh

NFI_LOCAL_REPO=/home/user/NostalgiaForInfinity

# pull from NFIX repo
echo "updating local NFIX repo"
cd $NFI_LOCAL_REPO
latest_local_commit=$(git rev-parse HEAD)
git pull
latest_remote_commit=$(git rev-parse HEAD)

if [ "$latest_local_commit" != "$latest_remote_commit" ]; then
    echo "restarting freqtrade with NFIX"
    docker compose pull
    docker compose stop
    docker compose up -d
fi
