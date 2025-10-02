#!/bin/bash
# Install bash/zsh tab completion for duperscooper

set -e

# Detect shell
SHELL_NAME="${1:-$(basename "$SHELL")}"

echo "Installing tab completion for $SHELL_NAME..."

# Check if shtab command is available
if ! command -v shtab &> /dev/null; then
    echo "Error: shtab command not found in PATH"
    echo "Install it with: pip install shtab  OR  pipx install shtab"
    exit 1
fi

# Check if duperscooper is installed (needed for shtab to import the parser)
if ! python -c "import duperscooper" 2>/dev/null; then
    echo "Error: duperscooper is not installed or not importable"
    echo "Install it with: pip install -e .  OR  pip install duperscooper"
    exit 1
fi

case "$SHELL_NAME" in
    bash)
        # Try user directory first, fall back to system
        if [ -d "$HOME/.local/share/bash-completion/completions" ]; then
            COMPLETION_DIR="$HOME/.local/share/bash-completion/completions"
            SUDO=""
        elif [ -d "/usr/share/bash-completion/completions" ]; then
            COMPLETION_DIR="/usr/share/bash-completion/completions"
            SUDO="sudo"
        else
            echo "Error: Could not find bash completion directory"
            echo "Creating user completion directory..."
            mkdir -p "$HOME/.local/share/bash-completion/completions"
            COMPLETION_DIR="$HOME/.local/share/bash-completion/completions"
            SUDO=""
        fi

        echo "Generating bash completion script..."
        shtab --shell=bash duperscooper.__main__.get_parser | \
            $SUDO tee "$COMPLETION_DIR/duperscooper" > /dev/null

        echo "✓ Bash completion installed to $COMPLETION_DIR/duperscooper"
        echo ""
        echo "Restart your shell or run:"
        echo "  source $COMPLETION_DIR/duperscooper"
        ;;

    zsh)
        # Try user directory first, fall back to system
        if [ -d "$HOME/.zsh/completions" ]; then
            COMPLETION_DIR="$HOME/.zsh/completions"
            SUDO=""
        elif [ -d "/usr/local/share/zsh/site-functions" ]; then
            COMPLETION_DIR="/usr/local/share/zsh/site-functions"
            SUDO="sudo"
        else
            echo "Creating user completion directory..."
            mkdir -p "$HOME/.zsh/completions"
            COMPLETION_DIR="$HOME/.zsh/completions"
            SUDO=""
            echo ""
            echo "Note: Add this to your ~/.zshrc if not already present:"
            echo "  fpath=(~/.zsh/completions \$fpath)"
            echo "  autoload -Uz compinit && compinit"
            echo ""
        fi

        echo "Generating zsh completion script..."
        shtab --shell=zsh duperscooper.__main__.get_parser | \
            $SUDO tee "$COMPLETION_DIR/_duperscooper" > /dev/null

        echo "✓ Zsh completion installed to $COMPLETION_DIR/_duperscooper"
        echo ""
        echo "Restart your shell or run:"
        echo "  autoload -Uz compinit && compinit"
        ;;

    tcsh)
        COMPLETION_DIR="$HOME/.tcsh/completions"
        mkdir -p "$COMPLETION_DIR"

        echo "Generating tcsh completion script..."
        shtab --shell=tcsh duperscooper.__main__.get_parser > \
            "$COMPLETION_DIR/duperscooper.completion.csh"

        echo "✓ Tcsh completion installed to $COMPLETION_DIR/duperscooper.completion.csh"
        echo ""
        echo "Add to ~/.tcshrc:"
        echo "  source $COMPLETION_DIR/duperscooper.completion.csh"
        ;;

    *)
        echo "Error: Unsupported shell '$SHELL_NAME'"
        echo "Supported shells: bash, zsh, tcsh"
        echo ""
        echo "Usage: $0 [bash|zsh|tcsh]"
        exit 1
        ;;
esac

echo ""
echo "Tab completion installed successfully!"
