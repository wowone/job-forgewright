#!/usr/bin/env bash
# Cross-platform runner for latent-cli
# Auto-detects OS and architecture, then runs the appropriate binary

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="${SCRIPT_DIR}/bin"

# Detect OS
detect_os() {
    case "$(uname -s)" in
        Darwin*)
            echo "darwin"
            ;;
        Linux*)
            echo "linux"
            ;;
        CYGWIN*|MINGW*|MSYS*)
            echo "windows"
            ;;
        *)
            echo "unknown"
            ;;
    esac
}

# Detect architecture
detect_arch() {
    case "$(uname -m)" in
        x86_64|amd64)
            echo "amd64"
            ;;
        arm64|aarch64)
            echo "arm64"
            ;;
        armv7l)
            echo "arm64"
            ;;
        *)
            echo "unknown"
            ;;
    esac
}

OS=$(detect_os)
ARCH=$(detect_arch)

if [ "$OS" = "unknown" ] || [ "$ARCH" = "unknown" ]; then
    echo "Error: Unable to detect platform ($(uname -s) $(uname -m))" >&2
    echo "Please manually run the appropriate binary from ${BIN_DIR}/" >&2
    ls -1 "${BIN_DIR}/" 2>/dev/null || echo "No binaries found in ${BIN_DIR}/" >&2
    exit 1
fi

# Windows uses .exe extension
EXT=""
if [ "$OS" = "windows" ]; then
    EXT=".exe"
fi

BINARY="${BIN_DIR}/latent-cli-${OS}-${ARCH}${EXT}"

if [ ! -f "$BINARY" ]; then
    echo "Error: Binary not found: $BINARY" >&2
    echo "" >&2
    echo "Available binaries:" >&2
    ls -1 "${BIN_DIR}/" 2>/dev/null || echo "No binaries found in ${BIN_DIR}/" >&2
    echo "" >&2
    echo "Your platform: ${OS} ${ARCH}" >&2
    exit 1
fi

# Make binary executable if needed
if [ ! -x "$BINARY" ] && [ "$OS" != "windows" ]; then
    chmod +x "$BINARY" 2>/dev/null || true
fi

# Run the binary with all passed arguments
exec "$BINARY" "$@"
