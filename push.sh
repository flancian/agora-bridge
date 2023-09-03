#!/bin/bash
#
# This simple script tries to autopush (uploads/updates) repositories that this bridge is responsible for updating.
# As of 2023-09-03, this means /stream -- meaning social media activity as dumped by the mastodon and matrix agora bots (twitter is broken due to elon).
#
# As with everything in this directory, if you're running an Agora in bare metal (without using containers/coop cloud) you probably want to run it as a systemd user service.
#
# Based on the equally humble https://gitlab.com/flancia/hedgedoc-export :)
#
# Keep it simple? Or maybe I'm just lazy.
# If this broke you: sorry :)
cd ~/agora/stream

# YOLO :)
while true; do 
	git add .
	git commit -a -m "stream update"
	git push
	sleep 60
done
