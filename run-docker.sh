#!/bin/sh
# This assumes... many things :) See README.md, Dockerfile and ./run-*.sh for more.
# This runs an Agora in an interactive container, mounting 'agora' in your home directory as the Agora root.

docker run -it -p 5018:5018 -v ${HOME}/agora:/home/agora/agora -u agora git.coopcloud.tech/flancian/agora-bridge
