#!/bin/bash
set -e

# Default to sibling directory
BULL_SRC_DIR="../../bull"
BULL_REPO="https://github.com/gokrazy/bull.git"

echo "🐂 Setting up Bull..."

# 0. Check for Go
if ! command -v go &> /dev/null; then
    echo "❌ Go is not installed or not in PATH."
    echo "Please install Go (https://go.dev/doc/install) and try again."
    echo "On Debian/Ubuntu: sudo apt install golang-go"
    exit 1
fi

# 1. Check if source exists
if [ ! -d "$BULL_SRC_DIR" ]; then
    echo "Directory $BULL_SRC_DIR not found."
    read -p "Clone bull from $BULL_REPO? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git clone "$BULL_REPO" "$BULL_SRC_DIR"
    else
        echo "Aborting."
        exit 1
    fi
fi

# 2. Build and Install
echo "Building and installing bull..."
cd "$BULL_SRC_DIR"

if ! go install ./cmd/...; then
    echo
    echo "❌ Build failed."
    echo "This might be due to an outdated Go version or syntax errors in the source."
    echo "Current 'go version': $(go version)"
    echo
    echo "If your Go is too old, you can install a newer version easily:"
    echo "  go install golang.org/dl/go1.24@latest"
    echo "  ~/go/bin/go1.24 download"
    echo "  ~/go/bin/go1.24 install ./cmd/..."
    exit 1
fi

# 3. Verify
if [ -f "$HOME/go/bin/bull" ]; then
    echo "✅ Bull installed successfully to $HOME/go/bin/bull"
    $HOME/go/bin/bull -version || true
else
    echo "❌ Build seemed to succeed, but binary not found in $HOME/go/bin/"
    exit 1
fi