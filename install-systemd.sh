#!/bin/bash
set -euo pipefail

# Install SMTP server and workers as systemd services
# Supports both SQS (AWS) and Redis (non-AWS) architectures

# Create user and group
sudo useradd -r -s /bin/false smtp || true

# Create installation directory
sudo mkdir -p /opt/py-smtp-server

# Copy files
sudo cp -r . /opt/py-smtp-server/
sudo chown -R smtp:smtp /opt/py-smtp-server

# Create environment file from example if it doesn't exist
if [ ! -f /opt/py-smtp-server/.env ]; then
    sudo cp /opt/py-smtp-server/.env.example /opt/py-smtp-server/.env
    sudo chown smtp:smtp /opt/py-smtp-server/.env
    echo "Created .env file from template - please edit /opt/py-smtp-server/.env"
fi

# Install dependencies
cd /opt/py-smtp-server
sudo -u smtp uv sync

# Install systemd services
sudo cp py-smtp-server.service /etc/systemd/system/
sudo cp py-smtp-worker.service /etc/systemd/system/
sudo cp py-smtp-redis-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable py-smtp-server

echo "Installation complete. Edit /opt/py-smtp-server/.env for configuration"
echo ""
echo "Choose your architecture:"
echo ""
echo "=== SQS Architecture (AWS) ==="
echo "Enable SQS worker:"
echo "  sudo systemctl enable py-smtp-worker"
echo "  sudo systemctl start py-smtp-server py-smtp-worker"
echo ""
echo "Commands:"
echo "  Status: sudo systemctl status py-smtp-server py-smtp-worker"
echo "  Logs: sudo journalctl -u py-smtp-server -u py-smtp-worker -f"
echo ""
echo "=== Redis Architecture (Non-AWS) ==="
echo "Install Redis first: sudo apt install redis-server"
echo "Enable Redis worker:"
echo "  sudo systemctl enable py-smtp-redis-worker"
echo "  sudo systemctl start py-smtp-server py-smtp-redis-worker"
echo ""
echo "Commands:"
echo "  Status: sudo systemctl status py-smtp-server py-smtp-redis-worker"
echo "  Logs: sudo journalctl -u py-smtp-server -u py-smtp-redis-worker -f"
