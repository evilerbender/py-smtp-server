#!/usr/bin/env bash
set -euo pipefail

# Package and deploy SMTP server project to S3
# Usage: ./package-deploy.sh [options] [s3-bucket] [version] [s3-key-path]
# Options:
#   --bucket=BUCKET     S3 bucket name
#   --version=VERSION   Version string
#   --key-path=PATH     S3 key path prefix
#   --help              Show this help
# Or use environment variables: S3_BUCKET, VERSION, S3_KEY_PATH

# Parse named arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --bucket=*)
            ARG_BUCKET="${1#*=}"
            shift
            ;;
        --bucket)
            ARG_BUCKET="$2"
            shift 2
            ;;
        --version=*)
            ARG_VERSION="${1#*=}"
            shift
            ;;
        --version)
            ARG_VERSION="$2"
            shift 2
            ;;
        --key-path=*)
            ARG_KEY_PATH="${1#*=}"
            shift
            ;;
        --key-path)
            ARG_KEY_PATH="$2"
            shift 2
            ;;
        --force)
            FORCE_OVERWRITE=true
            shift
            ;;
        --check)
            CHECK_EXISTS=true
            shift
            ;;
        --help)
            echo "Usage: $0 [options] [s3-bucket] [version] [s3-key-path]"
            echo ""
            echo "Options:"
            echo "  --bucket BUCKET     S3 bucket name"
            echo "  --bucket=BUCKET     S3 bucket name"
            echo "  --version VERSION   Version string"
            echo "  --version=VERSION   Version string"
            echo "  --key-path PATH     S3 key path prefix"
            echo "  --key-path=PATH     S3 key path prefix"
            echo "  --force             Overwrite existing files without prompting"
            echo "  --check             Check if file exists and prompt before overwriting"
            echo "  --help              Show this help"
            echo ""
            echo "Environment variables:"
            echo "  S3_BUCKET           S3 bucket name"
            echo "  VERSION             Version string"
            echo "  S3_KEY_PATH         S3 key path prefix"
            echo ""
            echo "Examples:"
            echo "  $0 --bucket my-bucket --key-path releases"
            echo "  $0 --bucket=my-bucket --key-path=releases"
            echo "  $0 --version v1.2.3"
            echo "  S3_KEY_PATH=apps/email $0"
            exit 0
            ;;
        -*)
            echo "Unknown option $1"
            exit 1
            ;;
        *)
            # Positional arguments
            if [[ -z "${POSITIONAL_BUCKET:-}" ]]; then
                POSITIONAL_BUCKET="$1"
            elif [[ -z "${POSITIONAL_VERSION:-}" ]]; then
                POSITIONAL_VERSION="$1"
            elif [[ -z "${POSITIONAL_KEY_PATH:-}" ]]; then
                POSITIONAL_KEY_PATH="$1"
            fi
            shift
            ;;
    esac
done

# Configuration with priority: named args > env vars > positional args > pyproject.toml > defaults
PROJECT_NAME="py-smtp-server"
DEFAULT_BUCKET="deployment-artifacts"

# Get version from pyproject.toml if no version specified
PYPROJECT_VERSION=""
if [[ -f "pyproject.toml" ]] && [[ -z "${ARG_VERSION:-}" ]] && [[ -z "${VERSION:-}" ]] && [[ -z "${POSITIONAL_VERSION:-}" ]]; then
    PYPROJECT_VERSION=$(uv version --short 2>/dev/null || echo "")
fi

VERSION="${ARG_VERSION:-${VERSION:-${POSITIONAL_VERSION:-${PYPROJECT_VERSION:-$(date +%Y%m%d-%H%M%S)}}}}"
S3_BUCKET="${ARG_BUCKET:-${S3_BUCKET:-${POSITIONAL_BUCKET:-$DEFAULT_BUCKET}}}"
S3_KEY_PATH="${ARG_KEY_PATH:-${S3_KEY_PATH:-${POSITIONAL_KEY_PATH:-}}}"
FORCE_OVERWRITE="${FORCE_OVERWRITE:-false}"
CHECK_EXISTS="${CHECK_EXISTS:-false}"
ARTIFACT_NAME="${PROJECT_NAME}-${VERSION}.tar.gz"

# Build S3 paths
if [[ -n "$S3_KEY_PATH" ]]; then
    # Remove leading and trailing slashes from key path
    S3_KEY_PATH="${S3_KEY_PATH#/}"  # Remove leading slash
    S3_KEY_PATH="${S3_KEY_PATH%/}"  # Remove trailing slash
    S3_ARTIFACT_PATH="${S3_KEY_PATH}/${ARTIFACT_NAME}"
    S3_LATEST_PATH="${S3_KEY_PATH}/${PROJECT_NAME}-latest.tar.gz"
else
    S3_ARTIFACT_PATH="${ARTIFACT_NAME}"
    S3_LATEST_PATH="${PROJECT_NAME}-latest.tar.gz"
fi

# Check if file exists (unless --force is used)
if [[ "$FORCE_OVERWRITE" != "true" ]]; then
    if aws s3 ls "s3://${S3_BUCKET}/${S3_ARTIFACT_PATH}" >/dev/null 2>&1; then
        if [[ "$CHECK_EXISTS" == "true" ]]; then
            echo "⚠️  File already exists: s3://${S3_BUCKET}/${S3_ARTIFACT_PATH}"
            read -p "Overwrite? (y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                echo "❌ Deployment cancelled"
                exit 1
            fi
        else
            echo "⚠️  File already exists: s3://${S3_BUCKET}/${S3_ARTIFACT_PATH}"
            echo "💡 Use --force to overwrite or --check to prompt"
            exit 1
        fi
    fi
fi

echo "📦 Packaging ${PROJECT_NAME} v${VERSION}..."

# Clean project first
echo "🧹 Cleaning project..."
./clean.sh

# Create temporary directory for packaging
TEMP_DIR=$(mktemp -d)
PACKAGE_DIR="${TEMP_DIR}/${PROJECT_NAME}"

echo "📁 Copying files to ${PACKAGE_DIR}..."

# Copy project files using archive mode
mkdir -p "${PACKAGE_DIR}"
cp -a . "${PACKAGE_DIR}/"

# Clean the package using our existing clean script
cd "${PACKAGE_DIR}"
./clean.sh

# Remove additional packaging-specific files
rm -f package-deploy.sh  # Don't include this script in the package
rm -rf .git/ .gitignore 2>/dev/null || true
rm -rf .amazonq/ 2>/dev/null || true
rm -f .env 2>/dev/null || true

# Create the tarball
cd "${TEMP_DIR}"
echo "🗜️  Creating tarball ${ARTIFACT_NAME}..."

# Check if we're on macOS or using bsdtar to avoid AppleDouble files
TAR_OPTS="-czf"
if [[ "$(uname)" == "Darwin" ]] || tar --version 2>/dev/null | grep -q "bsdtar"; then
    TAR_OPTS="--disable-copyfile --no-xattrs --no-acls --no-fflags -czf"
fi

tar ${TAR_OPTS} "${ARTIFACT_NAME}" "${PROJECT_NAME}/"

# Upload to S3
echo "☁️  Uploading to s3://${S3_BUCKET}/${S3_ARTIFACT_PATH}..."
aws s3 cp "${ARTIFACT_NAME}" "s3://${S3_BUCKET}/${S3_ARTIFACT_PATH}"

# Create latest symlink
echo "🔗 Creating latest version link..."
aws s3 cp "s3://${S3_BUCKET}/${S3_ARTIFACT_PATH}" "s3://${S3_BUCKET}/${S3_LATEST_PATH}"

# Change back to original directory before cleanup
cd - > /dev/null

# Cleanup
rm -rf "${TEMP_DIR}"

echo "✅ Deployment complete!"
echo "📍 Artifact: s3://${S3_BUCKET}/${S3_ARTIFACT_PATH}"
echo "📍 Latest:   s3://${S3_BUCKET}/${S3_LATEST_PATH}"
echo ""
echo "📥 To download and deploy:"
echo "   aws s3 cp s3://${S3_BUCKET}/${S3_ARTIFACT_PATH} ."
echo "   tar -xzf ${ARTIFACT_NAME}"
echo "   cd ${PROJECT_NAME}"
echo "   sudo ./install-systemd.sh"
