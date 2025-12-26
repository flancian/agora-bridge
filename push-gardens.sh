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

sync_gardens() {
    # Iterate through all directories in garden/
    # We use find to safely handle potential spaces in filenames, though unlikely for usernames
    for d in "$GARDEN_ROOT"/*; do
        if [ -d "$d/.git" ]; then
            cd "$d" || continue
            
            # Check if remote is our hosted forge.
            # This is critical to avoid trying to push to external repos (GitHub/GitLab)
            # where we definitely don't have write access.
            REMOTE_URL=$(git remote get-url origin 2>/dev/null)
            if echo "$REMOTE_URL" | grep -q "git.anagora.org"; then
                
                # Construct SSH URL for write access (Port 2222)
                # We do NOT touch 'origin' so that pull.py can continue to use HTTPS/public access.
                # We use a separate 'deploy' remote for pushing.
                
                # Strip protocol and domain to get the path (e.g., "user/repo.git")
                REPO_PATH=$(echo "$REMOTE_URL" | sed -E 's|https://git.anagora.org/||; s|git@git.anagora.org:||; s|ssh://git@git.anagora.org:2222/||')
                SSH_URL="ssh://git@git.anagora.org:2222/${REPO_PATH}"
                
                # Ensure 'deploy' remote exists and is correct
                CURRENT_DEPLOY=$(git remote get-url deploy 2>/dev/null)
                if [ "$CURRENT_DEPLOY" != "$SSH_URL" ]; then
                    if git remote | grep -q "^deploy$"; then
                        git remote set-url deploy "$SSH_URL"
                    else
                        git remote add deploy "$SSH_URL"
                    fi
                    echo "  🔗 Set 'deploy' remote to: $SSH_URL"
                fi

                # Check for uncommitted changes (modified, added, deleted)
                # OR if local main is ahead of origin/main (committed but not pushed)
                # Note: We check against origin for status, but push to deploy.
                CHANGES=$(git status --porcelain)
                
                # Check if we are ahead of the DEPLOY remote (if it exists/fetched)
                # For simplicity, we just try to push if there are local commits or changes.
                
                if [[ -n "$CHANGES" ]]; then
                    echo "[$(date)] Syncing $d..."
                    git add .
                    git commit -m "Agora Edit (Bullpen)"
                    
                    if git push deploy HEAD; then
                        echo "  ✅ Pushed to deploy successfully."
                    else
                         echo "  ❌ Push to deploy failed."
                    fi
                elif [ "$(git rev-list --count HEAD ^deploy/main 2>/dev/null || echo 1)" -gt 0 ]; then
                     # If we have commits not on deploy (or deploy/main unknown), try pushing
                     # This covers the "Ahead" case
                     echo "[$(date)] Syncing commits to $d..."
                     if git push deploy HEAD; then
                        echo "  ✅ Pushed to deploy successfully."
                     else
                        echo "  ❌ Push to deploy failed."
                     fi
                fi
            fi
        fi
    done
}

# Run immediately on start
echo "Running initial sync..."
sync_gardens

# If not running once, enter the loop
if [ "$ONCE" = false ]; then
    echo "Initial sync complete. Entering watch loop..."
    while true; do
        sleep 60
        sync_gardens
    done
fi
