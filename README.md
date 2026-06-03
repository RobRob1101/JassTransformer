# Python Random Jass Bot

A simple random Jass bot written in Python that connects to the `jass-server` using WebSockets. It participates in the Jass Challenge tournament sessions alongside JVM bots like JassTheRipper.

## Setup

1. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Bot

Run the bot script, passing the websocket URL of the `jass-server` and specifying the bot's name and team index:

```bash
python3 -m randombot.bot --url ws://localhost:3000 --name "PythonRandomBot" --team 1

python3 -m rulebasedbot.bot --url ws://localhost:3000 --name "PythonRuleBasedBot" --team 1

```

- `--url`: The WebSocket URL of the `jass-server` (default: `ws://localhost:3000`).
- `--name`: The player name displayed in the tournament (default: `PythonRandomBot`).
- `--team`: The team index, either `0` or `1` (default: `1`).
