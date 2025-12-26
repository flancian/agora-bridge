#!/bin/bash
# Pushes changes in hosted gardens back to git.anagora.org
# This script is meant to be run as a service (agora-pusher.service).

# Default to standard garden path if not set
GARDEN_ROOT="${AGORA_ROOT:-$HOME/agora/garden}"

echo "Starting Garden Pusher loop..."
echo "Watching: $GARDEN_ROOT"

ONCE=false
if [[ "$1" == "--once" || "$1" == "-1" ]]; then
    ONCE=true
    echo "Running once..."
fi

while true; do
    # Iterate through all directories in garden/
    # We use find to safely handle potential spaces in filenames, though unlikely for usernames
    for d in "$GARDEN_ROOT"/*; do
        if [ -d "$d/.git" ]; then
            cd "$d" || continue
            
            # Check if remote is our hosted forge.
            # This is critical to avoid trying to push to external repos (GitHub/GitLab)
            # where we definitely don't have write access.
            if git remote get-url origin 2>/dev/null | grep -q "git.anagora.org"; then
                
                # Check for uncommitted changes (modified, added, deleted)
                # OR if local main is ahead of origin/main (committed but not pushed)
                CHANGES=$(git status --porcelain)
                AHEAD=$(git rev-list --count origin/main..main 2>/dev/null)
                
                if [[ -n "$CHANGES" || "$AHEAD" -gt 0 ]]; then
                    echo "[$(date)] Syncing $d..."
                    
                    if [[ -n "$CHANGES" ]]; then
                        git add .
                        git commit -m "Agora Edit (Bullpen)"
                    fi
                    
                    # Try to push. If it fails (e.g. auth), log it but don't crash.
                    if git push; then
                        echo "  ✅ Pushed successfully."
                    else
                        echo "  ❌ Push failed. Check permissions/keys."
                    fi
                fi
            fi
        fi
    done
    
    if [ "$ONCE" = true ]; then
        break
    fi
    
    # Wait before next cycle
    sleep 60
done
