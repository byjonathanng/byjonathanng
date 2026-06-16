#!/bin/bash
# Double-click this file (on a Mac) to set up and start syncing.
# It opens a Terminal window, installs what it needs the first time,
# then keeps your Jira, Trello and Reminders in sync.

cd "$(dirname "$0")" || exit 1

echo "================================================"
echo "   tasksync — keeping your tasks in sync"
echo "================================================"
echo ""

# 1. Make sure Python 3 is available.
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 isn't installed yet."
  echo "Please install it from https://www.python.org/downloads/ ,"
  echo "then double-click this file again."
  echo ""
  read -r -p "Press Enter to close this window."
  exit 1
fi

# 2. First-time setup: a private folder for the bits this needs.
if [ ! -d .venv ]; then
  echo "First-time setup (this takes a minute)..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --upgrade pip >/dev/null 2>&1
pip install -q -r requirements.txt

# 3. Check the settings file exists.
if [ ! -f config.yaml ]; then
  echo ""
  echo "I can't find your settings file (config.yaml) yet."
  echo "Open GETTING_STARTED.md and follow Steps 1-4 to create it,"
  echo "then double-click this file again."
  echo ""
  read -r -p "Press Enter to close this window."
  exit 1
fi

# 4. Test the connections before doing anything.
echo ""
echo "Checking your connections..."
if ! python -m tasksync doctor; then
  echo ""
  echo "One or more connections didn't work (see above)."
  echo "Double-check the matching section in config.yaml and try again."
  echo "GETTING_STARTED.md has a troubleshooting section."
  echo ""
  read -r -p "Press Enter to close this window."
  exit 1
fi

# 5. All good — start syncing on a loop.
echo ""
echo "Everything connected. Syncing now!"
echo "Keep this window open. To stop, press Ctrl-C or just close it."
echo ""
python -m tasksync sync --loop
