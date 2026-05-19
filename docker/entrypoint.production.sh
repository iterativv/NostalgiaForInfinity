#!/bin/bash
set -e

mkdir -p /freqtrade/user_data/logs
chown ftuser:ftuser /freqtrade/user_data/logs

exec gosu ftuser freqtrade "$@"
