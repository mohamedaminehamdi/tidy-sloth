#!/bin/sh
# Tidy Sloth installer:  curl -fsSL https://mohamedaminehamdi.github.io/tidy-sloth/install.sh | sh
#
# Everything goes in your home folder; no admin password. It installs:
#   uv (runs the app's Python), Tidy Sloth, Ollama + Gemma 4 (names files), the TabPFN weights (learns your folders),
#   and a Tidy Sloth app in ~/Applications. Nothing on your disk moves until you press Approve in the app.
# Undo it all: tidy-sloth --uninstall && uv tool uninstall tidy-sloth
set -eu

SITE="https://mohamedaminehamdi.github.io/tidy-sloth"
WHEEL="${SLOTH_SOURCE:-$SITE/tidy_sloth-0.1.0-py3-none-any.whl}"

say() { printf '\n\033[1m🦥 %s\033[0m\n' "$1"; }
fail() { printf '\n%s\n' "$1" >&2; exit 1; }

main() {
  [ "$(uname -s)" = Darwin ] || fail "Tidy Sloth is for macOS."
  [ "$(uname -m)" = arm64 ] || fail "Tidy Sloth needs a Mac with Apple silicon (M1 or newer)."
  [ "$(sw_vers -productVersion | cut -d. -f1)" -ge 14 ] || fail "Tidy Sloth needs macOS 14 (Sonoma) or newer."

  export PATH="$HOME/.local/bin:$PATH"
  if ! command -v uv >/dev/null 2>&1; then
    say "Installing uv, which runs Tidy Sloth's Python without touching your system"
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi

  say "Installing Tidy Sloth"
  uv tool install --force --refresh --python 3.12 "$WHEEL" </dev/null
  bin="$(uv tool dir --bin)"

  flags=""
  if [ -n "${SLOTH_SKIP_MODELS:-}" ]; then
    flags="--skip-models"
  elif ! curl -sf http://localhost:11434/api/version >/dev/null 2>&1; then
    if [ -d /Applications/Ollama.app ] || [ -d "$HOME/Applications/Ollama.app" ]; then
      say "Starting Ollama"
      open -g -a Ollama </dev/null || true
    else
      say "Installing Ollama, which runs Gemma 4 on this Mac"
      tmp="$(mktemp -d)"
      curl -fL --progress-bar https://ollama.com/download/Ollama-darwin.zip -o "$tmp/Ollama.zip"
      mkdir -p "$HOME/Applications"
      ditto -xk "$tmp/Ollama.zip" "$HOME/Applications"
      rm -rf "$tmp"
      open -g "$HOME/Applications/Ollama.app" </dev/null || true
    fi
  fi

  answer=n
  if [ -z "${SLOTH_SKIP_MODELS:-}" ] && (: </dev/tty) 2>/dev/null; then
    printf '\nBuild a fresh plan every night at 3 am, ready when you wake up? It never moves anything on its own. [y/N] '
    read -r answer </dev/tty || answer=n
  fi
  case "$answer" in [yY]*) flags="$flags --overnight-on" ;; esac

  say "Downloading the models and making the app"
  # shellcheck disable=SC2086  # $flags is a list of words
  "$bin/tidy-sloth" --setup $flags </dev/null

  say "All set. Tidy Sloth is in your Applications folder."
  if [ -z "${SLOTH_SKIP_MODELS:-}" ]; then
    echo "Opening it now. macOS will ask if it may look in your folders; nothing moves until you approve."
    open "$HOME/Applications/Tidy Sloth.app"
  fi
}

main "$@"
