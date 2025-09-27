#!/bin/bash
set -euo pipefail

# Simple test script for local SMTP server
# Usage: ./test-email.sh

SMTP_HOST=${SMTP_HOST:-localhost}
SMTP_PORT=${SMTP_PORT:-8025}

echo "Testing SMTP server at ${SMTP_HOST}:${SMTP_PORT}..."

# Send test email via telnet
{
    echo "HELO test-client"
    echo "MAIL FROM: test-sender@example.com"
    echo "RCPT TO: test-recipient@example.com"
    echo "DATA"
    echo "From: test-sender@example.com"
    echo "To: test-recipient@example.com"
    echo "Subject: Test Email $(date)"
    echo "Date: $(date -R)"
    echo ""
    echo "This is a test email sent at $(date)"
    echo "Server: ${SMTP_HOST}:${SMTP_PORT}"
    echo "."
    echo "QUIT"
} | telnet ${SMTP_HOST} ${SMTP_PORT}

echo ""
echo "Email sent! Check ./emails/ directory for saved message:"
ls -la ./emails/*.eml 2>/dev/null || echo "No emails found in ./emails/"
