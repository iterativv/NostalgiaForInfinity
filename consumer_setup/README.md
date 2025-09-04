# NFI CONSUMER SETUP (proof-of-concept)

Better docs coming soon! (probably...)

This is an attempt to parallelize NFI X6 heavy pair population between multiple dry-run producer bots in order for the bot to react to the market changes faster.

## Usage (docker)

1. Open `consumer_setup/.env` file and edit the variables to your need, **very carefully** following the instruction comments inside the file.
2. Inside consumer_setup catalog, in the terminal type `docker compose up -d` to start the bots.

### Cheatsheet

Reload the bots: `docker compose up -d --force-recreate`

Stop the bots: `docker compose down`

Watch logs: `docker compose logs -f`