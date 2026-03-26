#!/usr/bin/env bash
# GitHub App Installation Token - Shell Helper
#
# Source this to set GITHUB_TOKEN from a GitHub App's installation token.
# Tokens are cached and auto-refreshed when expired.
#
# Required env vars:
#   GITHUB_APP_ID                  - The App ID
#   GITHUB_APP_PRIVATE_KEY_PATH    - Path to the .pem private key
#   GITHUB_APP_INSTALLATION_ID     - Installation ID (optional if single installation)
#
# Usage:
#   source scripts/gh-app-token.sh
#   # GITHUB_TOKEN is now set and exported

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -z "$GITHUB_APP_ID" ]; then
    echo "⚠ GITHUB_APP_ID not set — skipping GitHub App auth"
    return 1 2>/dev/null || exit 1
fi

if [ -z "$GITHUB_APP_PRIVATE_KEY_PATH" ]; then
    echo "⚠ GITHUB_APP_PRIVATE_KEY_PATH not set — skipping GitHub App auth"
    return 1 2>/dev/null || exit 1
fi

_APP_TOKEN=$(python3 "$_SCRIPT_DIR/gh-app-token.py" 2>/dev/null)

if [ -n "$_APP_TOKEN" ] && [ ${#_APP_TOKEN} -gt 10 ]; then
    export GITHUB_TOKEN="$_APP_TOKEN"
    export GH_AUTH_METHOD="github-app"
    echo "✓ GitHub App token set (expires in ~1 hour)"
else
    echo "⚠ Failed to get GitHub App installation token"
    echo "  Run: python3 $_SCRIPT_DIR/gh-app-token.py 2>&1  to debug"
    return 1 2>/dev/null || exit 1
fi

unset _APP_TOKEN _SCRIPT_DIR
