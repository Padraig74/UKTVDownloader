#!/bin/bash
# UK Streaming Service Downloader
# A tool to download and decrypt content from Channel 4, ITV, and Channel 5
# Requirements: curl, xmlstarlet, jq, dotnet, N_m3u8DL-RE, ffmpeg

# Configuration
DOWNLOAD_DIR="$HOME/Downloads/UKStreamDownloads"
TEMP_DIR="$DOWNLOAD_DIR/temp"
N_M3U8DL_RE_PATH="$HOME/tools/N_m3u8DL-RE/N_m3u8DL-RE.dll"
KEYS_FILE="$HOME/.uk_stream_keys.json"
USER_AGENT="Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:138.0) Gecko/20100101 Firefox/138.0"

# Create directories
mkdir -p "$DOWNLOAD_DIR" "$TEMP_DIR"

# Check for required tools
for cmd in curl xmlstarlet jq dotnet ffmpeg; do
  if ! command -v $cmd &> /dev/null; then
    echo "❌ $cmd is required but not installed. Please install it using brew."
    exit 1
  fi
done

# Check for N_m3u8DL-RE
if [ ! -f "$N_M3U8DL_RE_PATH" ]; then
  echo "❌ N_m3u8DL-RE not found at $N_M3U8DL_RE_PATH"
  echo "Please download it from https://github.com/nilaoda/N_m3u8DL-RE/releases"
  echo "and place it in ~/tools/N_m3u8DL-RE/"
  exit 1
fi

# Initialize keys file if it doesn't exist
if [ ! -f "$KEYS_FILE" ]; then
  echo "{}" > "$KEYS_FILE"
fi

# Display banner
clear
echo "🎬 UK STREAMING SERVICE DOWNLOADER"
echo "===================================="
echo "Supports Channel 4, ITV, and Channel 5"
echo "Created by Claude - Anthropic"
echo

# Get URL from user
read -p "📎 Paste the show URL: " SHOW_URL

if [ -z "$SHOW_URL" ]; then
  echo "❌ No URL provided."
  exit 1
fi

# Determine the service
if [[ "$SHOW_URL" == *"channel4.com"* ]] || [[ "$SHOW_URL" == *"all4.com"* ]]; then
  SERVICE="Channel4"
elif [[ "$SHOW_URL" == *"itv.com"* ]] || [[ "$SHOW_URL" == *"itvx.com"* ]]; then
  SERVICE="ITV"
elif [[ "$SHOW_URL" == *"channel5.com"* ]] || [[ "$SHOW_URL" == *"my5.tv"* ]]; then
  SERVICE="Channel5"
else
  echo "❌ Unsupported URL. This script only works with Channel 4, ITV, and Channel 5."
  exit 1
fi

echo "✅ Detected service: $SERVICE"

# Create a timestamp for the output files
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Extract program ID from URL
if [[ "$SERVICE" == "Channel4" ]]; then
  PROGRAM_ID=$(echo "$SHOW_URL" | grep -o '[0-9]\+\-[0-9]\+' | head -1)
  if [ -z "$PROGRAM_ID" ]; then
    PROGRAM_ID=$(echo "$SHOW_URL" | grep -o '[0-9]\+' | head -1)
  fi
elif [[ "$SERVICE" == "ITV" ]]; then
  PROGRAM_ID=$(echo "$SHOW_URL" | grep -o '[0-9a-zA-Z]\+/[0-9a-zA-Z]\+$' | head -1 | tr '/' '_')
  if [ -z "$PROGRAM_ID" ]; then
    PROGRAM_ID=$(date +"%Y%m%d")
  fi
else
  # Channel5
  PROGRAM_ID=$(echo "$SHOW_URL" | grep -o '[0-9a-zA-Z\-]\+$' | head -1)
  if [ -z "$PROGRAM_ID" ]; then
    PROGRAM_ID=$(date +"%Y%m%d")
  fi
fi

OUTPUT_NAME="${SERVICE}_${PROGRAM_ID}_${TIMESTAMP}"
echo "📁 Output name: $OUTPUT_NAME"

# Function to extract MPD URL and PSSH using Firefox
extract_mpd_and_pssh() {
  echo "🔍 Extracting MPD URL and PSSH..."
  echo "Opening Firefox to analyze the stream. Please wait..."
  
  # We'll use a temporary Firefox profile to avoid conflicts
  PROFILE_DIR="$TEMP_DIR/firefox_profile"
  mkdir -p "$PROFILE_DIR"
  
  # Start Firefox with the Stream Detector addon and the URL
  firefox -CreateProfile "ukstreamer $PROFILE_DIR" > /dev/null 2>&1
  firefox -P ukstreamer -url "$SHOW_URL" &
  FIREFOX_PID=$!
  
  echo "Firefox is running. Please:"
  echo "1. Wait for the video player to load"
  echo "2. Press play on the video to trigger the stream"
  echo "3. Use the 'Stream Detector' extension to find the MPD URL"
  echo "4. Use 'Widevine Content Decryption Module' to capture license requests"
  echo
  echo "When you have the MPD URL and PSSH, press Ctrl+C to continue..."
  
  # Wait for user to manually extract info
  trap "kill $FIREFOX_PID 2>/dev/null; echo -e '\nContinuing...';" INT
  wait $FIREFOX_PID
  trap - INT
  
  # Ask for the MPD URL
  read -p "📎 Paste the MPD URL: " MPD_URL
  
  if [ -z "$MPD_URL" ]; then
    echo "❌ No MPD URL provided."
    exit 1
  fi
  
  # Try to extract PSSH from MPD
  echo "🔍 Fetching MPD content to extract PSSH..."
  TMPFILE="$TEMP_DIR/mpd_content.xml"
  curl -s -H "User-Agent: $USER_AGENT" "$MPD_URL" -o "$TMPFILE"
  
  # Try different extraction methods
  PSSH=$(xmlstarlet sel -t -v "//*[local-name()='ContentProtection'][@schemeIdUri='urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed']/*[local-name()='pssh']" "$TMPFILE" 2>/dev/null)
  
  if [ -z "$PSSH" ]; then
    # Try alternate extraction if the first method fails
    PSSH=$(grep -o '<pssh>[^<]*</pssh>' "$TMPFILE" | head -1 | sed 's/<pssh>\(.*\)<\/pssh>/\1/')
  fi
  
  if [ -z "$PSSH" ]; then
    echo "❌ Could not extract PSSH automatically."
    read -p "📎 Please paste the PSSH manually: " PSSH
    
    if [ -z "$PSSH" ]; then
      echo "❌ No PSSH provided."
      exit 1
    fi
  else
    echo "✅ Successfully extracted PSSH: ${PSSH:0:20}..."
  fi
  
  # Look for subtitle URL
  echo "🔍 Looking for subtitle URL..."
  
  if [[ "$SERVICE" == "Channel4" ]]; then
    # Try to construct Channel4 subtitle URL pattern
    SUBTITLE_URL="https://subs.channel4.com/${PROGRAM_ID}/${PROGRAM_ID}.vtt"
    if curl --output /dev/null --silent --head --fail "$SUBTITLE_URL"; then
      echo "✅ Found subtitle URL: $SUBTITLE_URL"
    else
      SUBTITLE_URL=""
    fi
  elif [[ "$SERVICE" == "ITV" ]]; then
    # For ITV, we might need to check network traffic
    echo "⚠️ For ITV subtitles, please check network traffic for .vtt files"
    SUBTITLE_URL=""
  else
    # For Channel5, also check network traffic
    echo "⚠️ For Channel5 subtitles, please check network traffic for .vtt files"
    SUBTITLE_URL=""
  fi
  
  if [ -z "$SUBTITLE_URL" ]; then
    read -p "📎 Paste subtitle URL if available (or press Enter to skip): " SUBTITLE_URL
  fi
}

# Function to get DRM key
get_drm_key() {
  # Check if we already have a key for this PSSH
  if [ -f "$KEYS_FILE" ]; then
    EXISTING_KEY=$(jq -r --arg pssh "$PSSH" '.[$pssh]' "$KEYS_FILE")
    if [ "$EXISTING_KEY" != "null" ]; then
      echo "✅ Found cached key for PSSH: $EXISTING_KEY"
      DRM_KEY="$EXISTING_KEY"
      return
    fi
  fi
  
  # Extract KID from PSSH
  echo "🔍 Extracting KID from PSSH..."
  
  # Base64 decode PSSH and extract KID (bytes 32-48 in most Widevine PSSH boxes)
  PSSH_DECODED=$(echo "$PSSH" | base64 --decode 2>/dev/null | xxd -p | tr -d '\n')
  KID=$(echo "$PSSH_DECODED" | grep -o '................................................' | tail -n +3 | head -1)
  
  if [ -n "$KID" ]; then
    echo "✅ Extracted KID: $KID"
  else
    echo "❓ Could not extract KID automatically from PSSH."
  fi
  
  # Guide user through manual key extraction
  echo
  echo "🔑 DRM KEY EXTRACTION 🔑"
  echo "To get the decryption key, you need to use the Widevine Proxy extension in Firefox"
  echo "1. Go to the video page and play the video"
  echo "2. Check the Widevine Proxy extension for license requests"
  echo "3. Find the KID:KEY pair (the KID might match $KID)"
  echo
  
  read -p "📝 Paste the KID:KEY pair (format KID:KEY): " DRM_KEY
  
  if [ -z "$DRM_KEY" ]; then
    echo "❌ No DRM key provided."
    exit 1
  fi
  
  # Save the key for future use
  jq --arg pssh "$PSSH" --arg key "$DRM_KEY" '.[$pssh] = $key' "$KEYS_FILE" > "${KEYS_FILE}.tmp" && mv "${KEYS_FILE}.tmp" "$KEYS_FILE"
  echo "✅ Saved key for future use."
}

# Function to download subtitle
download_subtitle() {
  if [ -n "$SUBTITLE_URL" ]; then
    echo "📥 Downloading subtitle..."
    SUBTITLE_FILE="$TEMP_DIR/${OUTPUT_NAME}.vtt"
    curl -s -H "User-Agent: $USER_AGENT" "$SUBTITLE_URL" -o "$SUBTITLE_FILE"
    
    if [ -s "$SUBTITLE_FILE" ]; then
      echo "✅ Subtitle downloaded to: $SUBTITLE_FILE"
      return 0
    else
      echo "❌ Failed to download subtitle."
      rm -f "$SUBTITLE_FILE"
      SUBTITLE_FILE=""
      return 1
    fi
  else
    echo "⚠️ No subtitle URL provided. Continuing without subtitles."
    SUBTITLE_FILE=""
    return 1
  fi
}

# Function to download and decrypt video
download_and_decrypt() {
  echo "📥 Downloading and decrypting video..."
  
  # Create temporary working directory
  WORK_DIR="$TEMP_DIR/$OUTPUT_NAME"
  mkdir -p "$WORK_DIR"
  
  # Build the command
  echo "🧰 Running N_m3u8DL-RE..."
  dotnet "$N_M3U8DL_RE_PATH" \
    --url "$MPD_URL" \
    --key "$DRM_KEY" \
    --saveName "$OUTPUT_NAME" \
    --workDir "$WORK_DIR" \
    --useSystemProxy true \
    --autoSelect \
    --binaryMerge \
    --header "User-Agent: $USER_AGENT" \
    --header "Accept: */*"
  
  # Check if download was successful
  if [ $? -eq 0 ]; then
    # Find the output file (could be .mkv or .mp4)
    if [ -f "$WORK_DIR/$OUTPUT_NAME.mkv" ]; then
      VIDEO_FILE="$WORK_DIR/$OUTPUT_NAME.mkv"
    elif [ -f "$WORK_DIR/$OUTPUT_NAME.mp4" ]; then
      VIDEO_FILE="$WORK_DIR/$OUTPUT_NAME.mp4"
    else
      echo "❌ Output file not found."
      return 1
    fi
    
    echo "✅ Video downloaded and decrypted: $VIDEO_FILE"
    return 0
  else
    echo "❌ Failed to download and decrypt video."
    return 1
  fi
}

# Function to mux subtitle into video
mux_subtitle_into_video() {
  if [ -n "$SUBTITLE_FILE" ] && [ -f "$SUBTITLE_FILE" ] && [ -n "$VIDEO_FILE" ] && [ -f "$VIDEO_FILE" ]; then
    echo "🔄 Muxing subtitle into video..."
    
    FINAL_OUTPUT="$DOWNLOAD_DIR/${OUTPUT_NAME}_FINAL.mkv"
    
    ffmpeg -i "$VIDEO_FILE" -i "$SUBTITLE_FILE" \
           -c copy -c:s mov_text \
           "$FINAL_OUTPUT" -v quiet
    
    if [ $? -eq 0 ]; then
      echo "✅ Final output with subtitles: $FINAL_OUTPUT"
    else
      echo "❌ Failed to mux subtitle. Saving video without subtitles."
      cp "$VIDEO_FILE" "$DOWNLOAD_DIR/${OUTPUT_NAME}.mkv"
      echo "✅ Final output without subtitles: $DOWNLOAD_DIR/${OUTPUT_NAME}.mkv"
    fi
  else
    echo "🔄 Moving video to final location..."
    cp "$VIDEO_FILE" "$DOWNLOAD_DIR/${OUTPUT_NAME}.mkv"
    echo "✅ Final output: $DOWNLOAD_DIR/${OUTPUT_NAME}.mkv"
  fi
}

# Function to clean up temporary files
cleanup() {
  echo "🧹 Cleaning up temporary files..."
  rm -rf "$TEMP_DIR/$OUTPUT_NAME"
  rm -f "$TEMP_DIR/mpd_content.xml"
}

# Main execution
extract_mpd_and_pssh
get_drm_key
download_subtitle
download_and_decrypt
mux_subtitle_into_video
cleanup

echo "✨ All done! Your video is ready."
echo "📺 You can find it at: $DOWNLOAD_DIR"
