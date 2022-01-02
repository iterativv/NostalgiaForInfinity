#!/bin/sh

### Prereqs:
##  1. Freqtrade setup to run via docker-compose
##  2. A directory with the NFI repo with the NFI master branch

### Simple script that does the following:
## 1. Pulls latest NFI Repo
## 2. Copies updated NFIX sxtrategy file to Freqtrade
## 3. Optionally Commits the update strategy to a local repo
## 4. Stops, Build, and Start freqtrader via docker-compose

NFI_REPO_HOME=/root/freqtrade/NostalgiaForInfinity
FREQTRADE_HOME=/root/freqtrade/freqtrade-docker/ft_userdata
COMMIT_TO_LOCAL_REPO=true

#pull latest NFIX strategy and copy to freqtrade
echo "updating NFO Strategy"
cd $NFI_REPO_HOME
git pull
cp NostalgiaForInfinityX.py $FREQTRADE_HOME/user_data/strategies
echo "copied NFI Strategy to freqtrader"

#optionally add the update strategy file to your own repo
if [ "$COMMIT_TO_LOCAL_REPO" = true ] ; then
    echo 'Commiting updates to local repo'

    #ensure local repo to up to date
    echo "added updates strategy to git"
    cd $FREQTRADE_HOME
    git pull

    #commit update strategy file to local repo
    cd $FREQTRADE_HOME/user_data/strategies
    git add NostalgiaForInfinityX.py
    git commit -m "updated nfix strategy"
    git push

fi

#build and start via docker compose
echo "Starting freqtrade with NFIX"
docker-compose stop
docker-compose build
docker-compose up -d
