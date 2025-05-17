#!/bin/bash
# UK Streaming Service Downloader - Firefox Setup Script for macOS
# This script will set up the necessary Firefox configuration for the UK Streaming Service Downloader

# Create directories
mkdir -p ~/Downloads/UKStreamDownloads/temp

# Check if Firefox is installed on macOS
if [ ! -d "/Applications/Firefox.app" ]; then
    echo "❌ Firefox is not detected in the Applications folder."
    echo "Please ensure Firefox is installed in /Applications/Firefox.app"
    exit 1
fi

# Create Firefox profile for streaming
echo "Creating Firefox profile for streaming..."
PROFILE_DIR="$HOME/Downloads/UKStreamDownloads/firefox_profile"
/Applications/Firefox.app/Contents/MacOS/firefox -CreateProfile "ukstreamer $PROFILE_DIR"

# Open Firefox with the new profile to install extensions
echo "Opening Firefox with the new profile..."
echo "Please install the following extensions:"
echo "1. Stream Detector: https://addons.mozilla.org/en-US/firefox/addon/hls-stream-detector/"
echo "2. Widevine Content Decryption Module (from your WidevineProxy_v0.8.2.xpi file)"
echo
echo "After installing the extensions, close Firefox and run the main downloader script."

/Applications/Firefox.app/Contents/MacOS/firefox -P ukstreamer -url "https://addons.mozilla.org/en-US/firefox/addon/hls-stream-detector/"

echo "✅ Firefox setup complete!"
echo "Now you can run the main script to download content from UK streaming services."#!/bin/bash
# UK Streaming Service Downloader - Firefox Setup Script for macOS
# This script will set up the necessary Firefox configuration for the UK Streaming Service Downloader

# Create directories
mkdir -p ~/Downloads/UKStreamDownloads/temp

# Check if Firefox is installed on macOS
if [ ! -d "/Applications/Firefox.app" ]; then
    echo "❌ Firefox is not detected in the Applications folder."
    echo "Please ensure Firefox is installed in /Applications/Firefox.app"
    exit 1
fi

# Create Firefox profile for streaming
echo "Creating Firefox profile for streaming..."
PROFILE_DIR="$HOME/Downloads/UKStreamDownloads/firefox_profile"
/Applications/Firefox.app/Contents/MacOS/firefox -CreateProfile "ukstreamer $PROFILE_DIR"

# Open Firefox with the new profile to install extensions
echo "Opening Firefox with the new profile..."
echo "Please install the following extensions:"
echo "1. Stream Detector: https://addons.mozilla.org/en-US/firefox/addon/hls-stream-detector/"
echo "2. Widevine Content Decryption Module (from your WidevineProxy_v0.8.2.xpi file)"
echo
echo "After installing the extensions, close Firefox and run the main downloader script."

/Applications/Firefox.app/Contents/MacOS/firefox -P ukstreamer -url "https://addons.mozilla.org/en-US/firefox/addon/hls-stream-detector/"

echo "✅ Firefox setup complete!"
echo "Now you can run the main script to download content from UK streaming services."#!/bin/bash
# UK Streaming Service Downloader - Firefox Setup Script
# This script will set up the necessary Firefox configuration for the UK Streaming Service Downloader

# Create directories
mkdir -p ~/Downloads/UKStreamDownloads/temp

# Check if Firefox is installed
if ! command -v firefox &> /dev/null; then
    echo "❌ Firefox is not installed. Please install Firefox first."
    exit 1
fi

# Create Firefox profile for streaming
echo "Creating Firefox profile for streaming..."
PROFILE_DIR="$HOME/Downloads/UKStreamDownloads/firefox_profile"
firefox -CreateProfile "ukstreamer $PROFILE_DIR"

# Open Firefox with the new profile to install extensions
echo "Opening Firefox with the new profile..."
echo "Please install the following extensions:"
echo "1. Stream Detector: https://addons.mozilla.org/en-US/firefox/addon/hls-stream-detector/"
echo "2. Widevine Content Decryption Module: https://github.com/T-vK/Widevine-L3-Proxy"
echo
echo "After installing the extensions, close Firefox and run the main downloader script."

firefox -P ukstreamer -url "https://addons.mozilla.org/en-US/firefox/addon/hls-stream-detector/"

echo "✅ Firefox setup complete!"
echo "Now you can run the main script to download content from UK streaming services."
