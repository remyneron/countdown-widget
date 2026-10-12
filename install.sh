#!/usr/bin/env bash
set -e

INSTALL_DIR="$HOME/.local/share/countdown-widget"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"

echo "=== Installing Countdown Widget ==="

mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"
mkdir -p "$APP_DIR"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$SCRIPT_DIR" != "$INSTALL_DIR" ]; then
    echo "Copying files to $INSTALL_DIR..."
    cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR"/
fi

cd "$INSTALL_DIR"

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Installing Python dependencies..."
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r requirements.txt

# Create launcher wrapper
cat << 'EOF' > "$BIN_DIR/countdown"
#!/usr/bin/env bash
export QT_QPA_PLATFORM=xcb
exec "$HOME/.local/share/countdown-widget/venv/bin/python3" "$HOME/.local/share/countdown-widget/countdown_widget.py" "$@"
EOF
chmod +x "$BIN_DIR/countdown"

# Create .desktop entry
cat << EOF > "$APP_DIR/countdown.desktop"
[Desktop Entry]
Type=Application
Name=countdown
Comment=Minimalist Always-on-Top Countdown Widget
Exec=$BIN_DIR/countdown
Icon=$INSTALL_DIR/icon.jpg
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=false
EOF
chmod +x "$APP_DIR/countdown.desktop"

echo "=== Installation complete! ==="
echo "You can launch the widget via:"
echo "  - Terminal: countdown"
echo "  - Application Menu: countdown"
