#!/bin/bash
# Uninstall bash/zsh tab completion for duperscooper

SHELL_NAME="${1:-$(basename "$SHELL")}"

echo "Uninstalling tab completion for $SHELL_NAME..."

case "$SHELL_NAME" in
    bash)
        REMOVED=false
        if [ -f "$HOME/.local/share/bash-completion/completions/duperscooper" ]; then
            rm "$HOME/.local/share/bash-completion/completions/duperscooper"
            echo "✓ Removed user completion: $HOME/.local/share/bash-completion/completions/duperscooper"
            REMOVED=true
        fi
        if [ -f "/usr/share/bash-completion/completions/duperscooper" ]; then
            sudo rm "/usr/share/bash-completion/completions/duperscooper"
            echo "✓ Removed system completion: /usr/share/bash-completion/completions/duperscooper"
            REMOVED=true
        fi
        if [ "$REMOVED" = false ]; then
            echo "No bash completion found"
            exit 1
        fi
        ;;

    zsh)
        REMOVED=false
        if [ -f "$HOME/.zsh/completions/_duperscooper" ]; then
            rm "$HOME/.zsh/completions/_duperscooper"
            echo "✓ Removed user completion: $HOME/.zsh/completions/_duperscooper"
            REMOVED=true
        fi
        if [ -f "/usr/local/share/zsh/site-functions/_duperscooper" ]; then
            sudo rm "/usr/local/share/zsh/site-functions/_duperscooper"
            echo "✓ Removed system completion: /usr/local/share/zsh/site-functions/_duperscooper"
            REMOVED=true
        fi
        if [ "$REMOVED" = false ]; then
            echo "No zsh completion found"
            exit 1
        fi
        ;;

    tcsh)
        if [ -f "$HOME/.tcsh/completions/duperscooper.completion.csh" ]; then
            rm "$HOME/.tcsh/completions/duperscooper.completion.csh"
            echo "✓ Removed tcsh completion: $HOME/.tcsh/completions/duperscooper.completion.csh"
        else
            echo "No tcsh completion found"
            exit 1
        fi
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
echo "Tab completion uninstalled successfully!"
echo "Restart your shell for changes to take effect."
