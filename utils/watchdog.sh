#!/bin/bash

while true; do
  if ! pgrep -f "python backend/main.py" > /dev/null; then
    echo "Restarting Elysia..."
    python backend/main.py &
  fi
  sleep 10
done
