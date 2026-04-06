#!/usr/bin/env bash
set -euo pipefail

# Claude Code Cache Fix Installer (macOS)
# Patches cli.js to fix prompt caching bugs that drain Max plan usage.
# Safe to run multiple times. Stock 'claude' is never touched.
#
# Uses patches/apply-patches.py which has regex + semantic fallbacks
# for reliable patching across different minified code versions.

VERSION="2.1.90"
BASE="$HOME/cc-cache-fix"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PATCH_SCRIPT="$SCRIPT_DIR/patches/apply-patches.py"

get_cli_version() {
    local path="$1"
    if [ -f "$path" ]; then
        node "$path" --version 2>/dev/null || true
    fi
}

echo "========================================"
echo "  Claude Code Cache Fix Installer"
echo "  Target: v${VERSION}"
echo "========================================"
echo ""

# Check for Node.js
if ! command -v node &>/dev/null; then
    echo "[!] Node.js not found."
    if command -v brew &>/dev/null; then
        echo "[*] Installing via Homebrew..."
        brew install node
    else
        echo "    Install Node.js first: https://nodejs.org or 'brew install node'"
        exit 1
    fi
fi
echo "[*] Node.js: $(node --version)"

# Check for npm
if ! command -v npm &>/dev/null; then
    echo "[!] npm not found. Install Node.js properly."
    exit 1
fi

# Check for python3
if ! command -v python3 &>/dev/null; then
    echo "[!] python3 not found. Install Python 3 first."
    exit 1
fi

# Check for patch script
if [ ! -f "$PATCH_SCRIPT" ]; then
    echo "[!] Patch script not found at: $PATCH_SCRIPT"
    echo "    Run this script from the repo root."
    exit 1
fi

# Check for python3
if ! command -v python3 &>/dev/null; then
    echo "[!] python3 not found. Install Python 3 first."
    exit 1
fi

# Create project dir
mkdir -p "$BASE"
cd "$BASE"

# Install npm package
CLI="$BASE/node_modules/@anthropic-ai/claude-code/cli.js"
INSTALLED_VERSION="$(get_cli_version "$CLI")"
if [ "$INSTALLED_VERSION" != "$VERSION (Claude Code)" ]; then
    echo "[*] Installing @anthropic-ai/claude-code@${VERSION}..."
    npm install "@anthropic-ai/claude-code@${VERSION}"
else
    echo "[*] cli.js already installed at target version"
fi

# Backup
BACKUP_VERSION="$(get_cli_version "$CLI.orig")"
if [ "$BACKUP_VERSION" != "$VERSION (Claude Code)" ]; then
    echo "[*] Backing up cli.js"
    cp "$CLI" "$CLI.orig"
else
    echo "[*] Backup already matches target version"
fi

# Restore from backup (idempotent)
echo "[*] Restoring from backup..."
cp "$CLI.orig" "$CLI"

# Apply patches using apply-patches.py (has regex + semantic fallbacks)
echo "[*] Applying patches..."
python3 "$PATCH_SCRIPT" "$CLI"

# Verify it runs
PATCHED_VERSION=$(node "$CLI" --version 2>/dev/null || echo "FAILED")
echo "[*] Patched version: $PATCHED_VERSION"

if [[ "$PATCHED_VERSION" != *"$VERSION"* ]]; then
    echo "[!] Version check failed. Restoring backup."
    cp "$CLI.orig" "$CLI"
    exit 1
fi

# Create wrapper
mkdir -p "$HOME/.local/bin"
WRAPPER="$HOME/.local/bin/claude-patched"
if [ -L "$WRAPPER" ] || [ -f "$WRAPPER" ]; then
    rm -f "$WRAPPER"
fi
cat > "$WRAPPER" << WRAPPER_EOF
#!/usr/bin/env bash
exec node "$BASE/node_modules/@anthropic-ai/claude-code/cli.js" "\$@"
WRAPPER_EOF
chmod +x "$WRAPPER"
echo "[*] Created ~/.local/bin/claude-patched"

# Ensure PATH includes ~/.local/bin
SHELL_RC=""
if [ -f "$HOME/.zshrc" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ -f "$HOME/.bashrc" ]; then
    SHELL_RC="$HOME/.bashrc"
elif [ -f "$HOME/.bash_profile" ]; then
    SHELL_RC="$HOME/.bash_profile"
fi

if [ -n "$SHELL_RC" ]; then
    if ! grep -q '.local/bin' "$SHELL_RC" 2>/dev/null; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
        echo "[*] Added ~/.local/bin to PATH in $(basename "$SHELL_RC")"
    fi
fi

echo ""
echo "========================================"
echo "  Done!"
echo ""
echo "  Open a new terminal and run:"
echo "    claude-patched"
echo ""
echo "  All flags work as normal:"
echo "    claude-patched --dangerously-skip-permissions"
echo "    claude-patched --resume <session-id>"
echo ""
echo "  Stock 'claude' command is untouched."
echo "========================================"
