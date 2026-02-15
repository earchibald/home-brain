#!/bin/bash
if ! docker ps | grep -q homepage; then
  curl -d "Homepage is down!" ntfy.sh/omnibus-brain-notifications-v3
fi
