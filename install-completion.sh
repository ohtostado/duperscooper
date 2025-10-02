#!/bin/bash
# Install bash/zsh tab completion for duperscooper

set -e

# Detect shell
SHELL_NAME="${1:-$(basename "$SHELL")}"

echo "Installing tab completion for $SHELL_NAME..."

# Determine which Python to use
# Priority: active venv > .venv in current dir > venv in current dir > system python
if [ -n "$VIRTUAL_ENV" ]; then
    PYTHON="python"
    echo "Using active virtual environment: $VIRTUAL_ENV"
elif [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
    echo "Using local .venv: $(pwd)/.venv"
elif [ -f "venv/bin/python" ]; then
    PYTHON="venv/bin/python"
    echo "Using local venv: $(pwd)/venv"
else
    PYTHON="python"
    echo "Using system Python"
fi

# Check if shtab is available (either via Python or as command)
if $PYTHON -c "import shtab" 2>/dev/null; then
    # shtab is installed in the Python environment - use it via python -m
    SHTAB="$PYTHON -m shtab"
    echo "Using shtab from Python environment"
elif command -v shtab &> /dev/null; then
    # shtab is available as a command (e.g., pipx install)
    # But we need to use it with the venv's Python to access duperscooper
    if [ "$PYTHON" != "python" ]; then
        # Use python -m if available, otherwise warn
        if $PYTHON -c "import shtab" 2>/dev/null; then
            SHTAB="$PYTHON -m shtab"
            echo "Using shtab via Python environment to access duperscooper"
        else
            echo "Error: shtab found in PATH but not in Python environment"
            echo "Install shtab in the same environment as duperscooper:"
            echo "  $PYTHON -m pip install shtab"
            exit 1
        fi
    else
        SHTAB="shtab"
        echo "Using shtab from PATH"
    fi
else
    echo "Error: shtab is not installed"
    echo ""
    echo "Install it with one of:"
    echo "  pip install shtab      # Install in active environment"
    echo "  pipx install shtab     # Install globally"
    echo ""
    exit 1
fi

# Check if duperscooper is installed (needed for shtab to import the parser)
if ! $PYTHON -c "import duperscooper" 2>/dev/null; then
    echo "Error: duperscooper is not installed or not importable"
    echo ""
    echo "Install it with one of:"
    echo "  pip install -e .           # Development install"
    echo "  pip install duperscooper   # Production install"
    echo ""
    echo "Or activate your virtual environment first:"
    echo "  source .venv/bin/activate"
    exit 1
fi

case "$SHELL_NAME" in
    bash)
        # Always prefer user directory (no sudo needed)
        COMPLETION_DIR="$HOME/.local/share/bash-completion/completions"

        # Create directory if it doesn't exist
        if [ ! -d "$COMPLETION_DIR" ]; then
            echo "Creating user completion directory: $COMPLETION_DIR"
            mkdir -p "$COMPLETION_DIR"
        fi

        echo "Generating bash completion script..."
        $SHTAB --shell=bash duperscooper.__main__.get_parser > \
            "$COMPLETION_DIR/duperscooper"

        echo "✓ Bash completion installed to $COMPLETION_DIR/duperscooper"
        echo ""
        echo "Completion will be loaded automatically in new bash sessions."
        echo "For the current session, run:"
        echo "  source $COMPLETION_DIR/duperscooper"
        ;;

    zsh)
        # Always prefer user directory (no sudo needed)
        COMPLETION_DIR="$HOME/.zsh/completions"

        # Create directory if it doesn't exist
        if [ ! -d "$COMPLETION_DIR" ]; then
            echo "Creating user completion directory: $COMPLETION_DIR"
            mkdir -p "$COMPLETION_DIR"
            echo ""
            echo "Note: Add this to your ~/.zshrc if not already present:"
            echo "  fpath=(~/.zsh/completions \$fpath)"
            echo "  autoload -Uz compinit && compinit"
            echo ""
        fi

        echo "Generating zsh completion script..."
        $SHTAB --shell=zsh duperscooper.__main__.get_parser > \
            "$COMPLETION_DIR/_duperscooper"

        echo "✓ Zsh completion installed to $COMPLETION_DIR/_duperscooper"
        echo ""
        echo "Restart your shell or run:"
        echo "  autoload -Uz compinit && compinit"
        ;;

    tcsh)
        COMPLETION_DIR="$HOME/.tcsh/completions"
        mkdir -p "$COMPLETION_DIR"

        echo "Generating tcsh completion script..."
        $SHTAB --shell=tcsh duperscooper.__main__.get_parser > \
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
