#!/bin/bash

# This script launches two separate terminal windows for the backend and frontend services.
# It assumes you are running the script from the parent directory of 'Elysia' and 'frontend'.

# Determine the terminal emulator to use. lxterminal is common on Raspberry Pi OS.
# The script will fall back to gnome-terminal or xterm if lxterminal is not found.
if command -v lxterminal &> /dev/null; then
    TERMINAL_CMD="lxterminal"
elif command -v gnome-terminal &> /dev/null; then
    TERMINAL_CMD="gnome-terminal"
elif command -v xterm &> /dev/null; then
    TERMINAL_CMD="xterm"
else
    echo "Error: No supported terminal emulator found (lxterminal, gnome-terminal, or xterm)."
    exit 1
fi

echo "Using $TERMINAL_CMD to launch services in new windows..."

# Launch the backend service in a new terminal window
echo "Starting backend..."
$TERMINAL_CMD --command "bash -c 'cd Elysia && source .venv/bin/activate && python backend/main.py; exec bash'" &

# Launch the frontend service in a separate terminal window
echo "Starting frontend..."
$TERMINAL_CMD --command "bash -c 'source .venv/bin/activate && cd frontend && npm start; exec bash'" &

echo "Services launched. Check the new terminal windows for output."
