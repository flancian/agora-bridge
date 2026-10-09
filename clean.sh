#!/bin/bash
find ~/agora -type f -path '*/.git/*' -name '*.lock' -mmin +5 -delete 2>/dev/null || true
