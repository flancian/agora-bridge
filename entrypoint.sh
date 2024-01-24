#!/bin/bash
#
# Caveats in run.sh apply :)
#
# For a supported way to run an Agora on containers, please refer to [[agora recipe]] for [[coop cloud]] in the Agora of Flancia: https://anagora.org/agora-recipe

git pull
poetry install
(cd ~/agora && git pull)
(cd ~/agora && find . -iname 'index.lock' -exec rm {} \;)
./run-dev.sh 
