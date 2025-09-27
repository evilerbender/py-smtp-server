#!/bin/bash
set -euo pipefail

# Install SMTP server and SQS worker as systemd services

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
sudo systemctl daemon-reload
sudo systemctl enable py-smtp-server
sudo systemctl enable py-smtp-worker

echo "Installation complete. Edit /opt/py-smtp-server/.env for configuration"
echo ""
echo "SMTP Server commands:"
echo "  Start: sudo systemctl start py-smtp-server"
echo "  Status: sudo systemctl status py-smtp-server"
echo "  Logs: sudo journalctl -u py-smtp-server -f"
echo ""
echo "SQS Worker commands:"
echo "  Start: sudo systemctl start py-smtp-worker"
echo "  Status: sudo systemctl status py-smtp-worker"
echo "  Logs: sudo journalctl -u py-smtp-worker -f"
echo ""
echo "Start both services:"
echo "  sudo systemctl start py-smtp-server py-smtp-worker"
