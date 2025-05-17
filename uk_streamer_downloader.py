#!/usr/bin/env python3
"""
UK Streaming Service Downloader
A tool to download and decrypt content from UK streaming services (Channel 4, ITV, Channel 5)
with automatic MPD/subtitle extraction and DRM decryption.

Requirements:
- Python 3.7+
- N_m3u8DL-RE (for downloading and decryption)
- ffmpeg (for muxing)
- selenium with Firefox webdriver
- requests, beautifulsoup4

Installation:
pip install selenium requests beautifulsoup4 pycryptodome

Usage:
python uk_streamer_downloader.py
"""

import os
import sys
import re
import json
import time
import base64
import subprocess
import argparse
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# Configuration
DOWNLOAD_DIR = os.path.expanduser("~/Downloads/UKStreamDownloads")
TEMP_DIR = os.path.join(DOWNLOAD_DIR, "temp")
N_M3U8DL_RE_PATH = os.path.expanduser("~/tools/N_m3u8DL-RE/N_m3u8DL-RE.dll")
WIDEVINE_PROXY_DATA_FILE = os.path.expanduser("~/.widevine_proxy_data.json")
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:138.0) Gecko/20100101 Firefox/138.0"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "*/*"
}

class UKStreamerDownloader:
    def __init__(self, headless=True):
        self.setup_directories()
        self.driver = None
        self.headless = headless
        
    def setup_directories(self):
        """Create necessary directories if they don't exist"""
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        os.makedirs(TEMP_DIR, exist_ok=True)
        
    def initialize_browser(self):
        """Initialize Firefox browser with Stream Detector and Widevine Proxy extensions"""
        print("📊 Initializing browser...")
        
        options = Options()
        if self.headless:
            options.add_argument("--headless")
        
        # Set preferences to automatically save extensions' data
        options.set_preference("browser.download.folderList", 2)
        options.set_preference("browser.download.dir", TEMP_DIR)
        options.set_preference("browser.download.useDownloadDir", True)
        options.set_preference("browser.helperApps.neverAsk.saveToDisk", "application/octet-stream")
        
        service = Service(log_path=os.path.devnull)
        
        self.driver = webdriver.Firefox(options=options, service=service)
        self.driver.set_window_size(1200, 800)
        
        # Load Widevine proxy data if available
        self.load_widevine_proxy_data()
        
        print("✅ Browser initialized")
        
    def load_widevine_proxy_data(self):
        """Load saved Widevine proxy data if available"""
        if os.path.exists(WIDEVINE_PROXY_DATA_FILE):
            try:
                with open(WIDEVINE_PROXY_DATA_FILE, 'r') as f:
                    self.widevine_data = json.load(f)
                print("✅ Loaded existing Widevine proxy data")
            except Exception as e:
                print(f"❌ Error loading Widevine data: {e}")
                self.widevine_data = {}
        else:
            self.widevine_data = {}
            
    def save_widevine_proxy_data(self):
        """Save Widevine proxy data for future use"""
        try:
            with open(WIDEVINE_PROXY_DATA_FILE, 'w') as f:
                json.dump(self.widevine_data, f, indent=2)
            print("✅ Saved Widevine proxy data")
        except Exception as e:
            print(f"❌ Error saving Widevine data: {e}")
            
    def close_browser(self):
        """Close browser if open"""
        if self.driver:
            self.driver.quit()
            self.driver = None
            
    def extract_channel4_data(self, url):
        """Extract MPD URL, PSSH, and subtitle URL from Channel 4 page"""
        print(f"🔍 Analyzing Channel 4 URL: {url}")
        
        if not self.driver:
            self.initialize_browser()
            
        # Navigate to the page
        self.driver.get(url)
        
        # Wait for the page to load and video to initialize
        try:
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "video"))
            )
            time.sleep(5)  # Allow time for video player to initialize
        except TimeoutException:
            print("❌ Timeout waiting for video player to load")
            return None, None, None
            
        # Capture network traffic
        mpd_url = None
        pssh = None
        subtitle_url = None
        
        # Check for .mpd requests in network logs
        network_items = self.driver.execute_script("""
            var performance = window.performance || window.mozPerformance || window.msPerformance || window.webkitPerformance || {};
            var network = performance.getEntries() || [];
            return network;
        """)
        
        for item in network_items:
            url = item.get('name', '')
            if '.mpd' in url:
                mpd_url = url
            elif '.vtt' in url or '/subs.' in url:
                subtitle_url = url
        
        if not mpd_url:
            print("❌ Failed to detect MPD URL")
            return None, None, None
            
        # Fetch the MPD content to extract PSSH
        try:
            response = requests.get(mpd_url, headers=HEADERS)
            root = ET.fromstring(response.content)
            # Extract PSSH from MPD
            for elem in root.findall(".//{urn:mpeg:dash:schema:mpd:2011}ContentProtection[@schemeIdUri='urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed']"):
                for pssh_elem in elem.findall(".//{urn:mpeg:cenc:2013}pssh"):
                    pssh = pssh_elem.text.strip()
            
            # If we didn't find the PSSH in standard format, look for it in a different format
            if not pssh:
                for elem in root.findall(".//*"):
                    if "pssh" in elem.tag.lower() and elem.text:
                        pssh = elem.text.strip()
                        break
        except Exception as e:
            print(f"❌ Error parsing MPD: {e}")
            
        # If we still don't have a subtitle URL, look for it in the page source
        if not subtitle_url:
            try:
                page_source = self.driver.page_source
                soup = BeautifulSoup(page_source, 'html.parser')
                subtitle_elems = soup.find_all('track', attrs={'kind': 'subtitles'})
                if subtitle_elems:
                    subtitle_url = subtitle_elems[0].get('src')
                    if subtitle_url and not subtitle_url.startswith('http'):
                        parsed_url = urlparse(url)
                        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
                        subtitle_url = base_url + subtitle_url
            except Exception as e:
                print(f"❌ Error finding subtitles: {e}")
                
        print(f"✅ MPD URL: {mpd_url}")
        print(f"✅ PSSH: {pssh[:20]}..." if pssh else "❌ PSSH not found")
        print(f"✅ Subtitle URL: {subtitle_url}" if subtitle_url else "⚠️ No subtitles found")
        
        # Extract program ID for naming
        program_id = None
        match = re.search(r'/(\d+)(?:-\d+)?(?:/|$)', url)
        if match:
            program_id = match.group(1)
            
        return {
            "mpd_url": mpd_url,
            "pssh": pssh,
            "subtitle_url": subtitle_url,
            "program_id": program_id
        }
    
    def extract_itv_data(self, url):
        """Extract MPD URL, PSSH, and subtitle URL from ITV page"""
        print(f"🔍 Analyzing ITV URL: {url}")
        
        if not self.driver:
            self.initialize_browser()
            
        # Navigate to the page
        self.driver.get(url)
        
        # Wait for the page to load and video to initialize
        try:
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "video"))
            )
            time.sleep(5)  # Allow time for video player to initialize
        except TimeoutException:
            print("❌ Timeout waiting for video player to load")
            return None
            
        # Capture network traffic
        mpd_url = None
        pssh = None
        subtitle_url = None
        
        # Check for .mpd requests in network logs
        network_items = self.driver.execute_script("""
            var performance = window.performance || window.mozPerformance || window.msPerformance || window.webkitPerformance || {};
            var network = performance.getEntries() || [];
            return network;
        """)
        
        for item in network_items:
            url = item.get('name', '')
            if '.mpd' in url or '.ism/' in url:
                mpd_url = url
            elif '.vtt' in url or '/subs.' in url or 'subtitles' in url:
                subtitle_url = url
        
        if not mpd_url:
            print("❌ Failed to detect MPD URL")
            return None
            
        # Fetch the MPD content to extract PSSH
        try:
            response = requests.get(mpd_url, headers=HEADERS)
            root = ET.fromstring(response.content)
            # Extract PSSH from MPD
            for elem in root.findall(".//{urn:mpeg:dash:schema:mpd:2011}ContentProtection[@schemeIdUri='urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed']"):
                for pssh_elem in elem.findall(".//{urn:mpeg:cenc:2013}pssh"):
                    pssh = pssh_elem.text.strip()
            
            # If we didn't find the PSSH in standard format, look for it in a different format
            if not pssh:
                for elem in root.findall(".//*"):
                    if "pssh" in elem.tag.lower() and elem.text:
                        pssh = elem.text.strip()
                        break
        except Exception as e:
            print(f"❌ Error parsing MPD: {e}")
            
        # Extract program ID for naming
        program_id = None
        match = re.search(r'/([0-9a-zA-Z]+)(?:/|$)', url)
        if match:
            program_id = match.group(1)
            
        print(f"✅ MPD URL: {mpd_url}")
        print(f"✅ PSSH: {pssh[:20]}..." if pssh else "❌ PSSH not found")
        print(f"✅ Subtitle URL: {subtitle_url}" if subtitle_url else "⚠️ No subtitles found")
        
        return {
            "mpd_url": mpd_url,
            "pssh": pssh,
            "subtitle_url": subtitle_url,
            "program_id": program_id
        }
        
    def extract_channel5_data(self, url):
        """Extract MPD URL, PSSH, and subtitle URL from Channel 5 page"""
        print(f"🔍 Analyzing Channel 5 URL: {url}")
        
        if not self.driver:
            self.initialize_browser()
            
        # Navigate to the page
        self.driver.get(url)
        
        # Wait for the page to load and video to initialize
        try:
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "video"))
            )
            time.sleep(5)  # Allow time for video player to initialize
        except TimeoutException:
            print("❌ Timeout waiting for video player to load")
            return None
            
        # Capture network traffic
        mpd_url = None
        pssh = None
        subtitle_url = None
        
        # Check for .mpd requests in network logs
        network_items = self.driver.execute_script("""
            var performance = window.performance || window.mozPerformance || window.msPerformance || window.webkitPerformance || {};
            var network = performance.getEntries() || [];
            return network;
        """)
        
        for item in network_items:
            url = item.get('name', '')
            if '.mpd' in url:
                mpd_url = url
            elif '.vtt' in url or 'subtitles' in url:
                subtitle_url = url
        
        if not mpd_url:
            print("❌ Failed to detect MPD URL")
            return None
            
        # Fetch the MPD content to extract PSSH
        try:
            response = requests.get(mpd_url, headers=HEADERS)
            root = ET.fromstring(response.content)
            # Extract PSSH from MPD
            for elem in root.findall(".//{urn:mpeg:dash:schema:mpd:2011}ContentProtection[@schemeIdUri='urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed']"):
                for pssh_elem in elem.findall(".//{urn:mpeg:cenc:2013}pssh"):
                    pssh = pssh_elem.text.strip()
            
            # If we didn't find the PSSH in standard format, look for it in a different format
            if not pssh:
                for elem in root.findall(".//*"):
                    if "pssh" in elem.tag.lower() and elem.text:
                        pssh = elem.text.strip()
                        break
        except Exception as e:
            print(f"❌ Error parsing MPD: {e}")
            
        # Extract program ID for naming
        program_id = None
        match = re.search(r'/([0-9a-zA-Z]+)(?:/|$)', url)
        if match:
            program_id = match.group(1)
            
        print(f"✅ MPD URL: {mpd_url}")
        print(f"✅ PSSH: {pssh[:20]}..." if pssh else "❌ PSSH not found")
        print(f"✅ Subtitle URL: {subtitle_url}" if subtitle_url else "⚠️ No subtitles found")
        
        return {
            "mpd_url": mpd_url,
            "pssh": pssh,
            "subtitle_url": subtitle_url,
            "program_id": program_id
        }

    def get_drm_key(self, pssh, url, service_name):
        """Get DRM key for the given PSSH"""
        if not pssh:
            print("❌ No PSSH available to extract key")
            return None
            
        # Check if we already have the key for this PSSH
        if pssh in self.widevine_data:
            print(f"✅ Found cached key for PSSH: {self.widevine_data[pssh]}")
            return self.widevine_data[pssh]
            
        # We need to use Widevine Proxy extension to get the key
        if not self.driver:
            self.initialize_browser()
            
        # Decode PSSH to extract KID
        try:
            pssh_bytes = base64.b64decode(pssh)
            # The KID is typically at bytes 32-48 in the PSSH box
            kid = pssh_bytes[32:48].hex()
            print(f"✅ Extracted KID from PSSH: {kid}")
        except Exception as e:
            print(f"❌ Error extracting KID from PSSH: {e}")
            kid = None
            
        # Manual key extraction via browser
        print("\n🔑 DRM KEY EXTRACTION 🔑")
        print("I'll now guide you through extracting the DRM key using the browser.")
        print(f"1. Opening {service_name} video page...")
        
        self.driver.get(url)
        time.sleep(5)  # Wait for page to load
        
        print("2. I'm looking for the Widevine license request...")
        print("   Please wait while the video initializes...")
        
        # Try to play the video to trigger license requests
        try:
            play_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.play-button, .play-icon, [aria-label='Play'], video"))
            )
            play_button.click()
            time.sleep(5)  # Wait for license requests to happen
        except:
            print("   (Could not find play button, but continuing)")
            
        print("\n3. Please check your Widevine Proxy extension in Firefox:")
        print("   a. Look for license requests in the extension")
        print("   b. Find the correct KID/KEY pair")
        if kid:
            print(f"   c. The KID you need is: {kid}")
        
        # Ask user for key
        key_input = input("\n📝 Please paste the KID:KEY pair (format KID:KEY): ")
        key_input = key_input.strip()
        
        # Validate and store key
        if ':' in key_input:
            kid, key = key_input.split(':', 1)
            # Clean up the input
            kid = kid.strip().lower()
            key = key.strip().lower()
            
            self.widevine_data[pssh] = key_input
            self.save_widevine_proxy_data()
            return key_input
        else:
            print("❌ Invalid key format. Expected KID:KEY")
            return None
    
    def download_subtitle(self, subtitle_url, output_path):
        """Download subtitle file from URL"""
        if not subtitle_url:
            return None
            
        try:
            response = requests.get(subtitle_url, headers=HEADERS)
            with open(output_path, 'wb') as f:
                f.write(response.content)
            print(f"✅ Subtitle downloaded to: {output_path}")
            return output_path
        except Exception as e:
            print(f"❌ Error downloading subtitle: {e}")
            return None
    
    def download_and_decrypt(self, mpd_url, drm_key, output_name, subtitle_path=None):
        """Download and decrypt video using N_m3u8DL-RE"""
        print(f"📥 Downloading and decrypting video...")
        
        # Ensure output directory exists
        output_dir = os.path.join(DOWNLOAD_DIR, output_name)
        os.makedirs(output_dir, exist_ok=True)
        
        # Build the command
        cmd = [
            "dotnet", N_M3U8DL_RE_PATH,
            "--url", mpd_url,
            "--key", drm_key,
            "--saveName", output_name,
            "--workDir", output_dir,
            "--useSystemProxy", "true",
            "--autoSelect",
            "--binaryMerge"
        ]
        
        # Add custom headers if needed
        cmd.extend(["--header", f"User-Agent: {USER_AGENT}"])
        cmd.extend(["--header", "Accept: */*"])
        cmd.extend(["--header", f"Referer: {urlparse(mpd_url).netloc}"])
        
        try:
            print(f"🧰 Running N_m3u8DL-RE...")
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            # Read and display output in real-time
            for line in process.stdout:
                print(line.strip())
                
            process.wait()
            
            if process.returncode == 0:
                # Check if the output file was created
                expected_output = os.path.join(output_dir, f"{output_name}.mkv")
                if not os.path.exists(expected_output):
                    # Sometimes N_m3u8DL-RE outputs .mp4 instead of .mkv
                    expected_output = os.path.join(output_dir, f"{output_name}.mp4")
                
                if os.path.exists(expected_output):
                    print(f"✅ Video downloaded and decrypted: {expected_output}")
                    
                    # If we have subtitles, mux them into the video
                    if subtitle_path and os.path.exists(subtitle_path):
                        self.mux_subtitle_into_video(expected_output, subtitle_path)
                    
                    # Move the final file to the main download directory
                    final_output = os.path.join(DOWNLOAD_DIR, f"{output_name}_FINAL.mkv")
                    os.rename(expected_output, final_output)
                    print(f"✅ Final output: {final_output}")
                    return final_output
                else:
                    print(f"❌ Expected output file not found: {expected_output}")
            else:
                error = process.stderr.read()
                print(f"❌ N_m3u8DL-RE failed with return code {process.returncode}")
                print(f"Error: {error}")
                
        except Exception as e:
            print(f"❌ Error running N_m3u8DL-RE: {e}")
            
        return None
    
    def mux_subtitle_into_video(self, video_path, subtitle_path):
        """Mux subtitle into video using ffmpeg"""
        print(f"🔄 Muxing subtitle into video...")
        
        output_path = os.path.splitext(video_path)[0] + "_with_subs.mkv"
        
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-i", subtitle_path,
            "-c", "copy",
            "-c:s", "mov_text",
            output_path
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"✅ Muxed video with subtitles: {output_path}")
            
            # Replace the original file with the one with subtitles
            os.remove(video_path)
            os.rename(output_path, video_path)
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Error muxing subtitle: {e}")
            print(f"ffmpeg stderr: {e.stderr}")
    
    def process_url(self, url):
        """Process a URL from any supported streaming service"""
        print(f"\n🎬 PROCESSING URL: {url}")
        
        # Detect the service type
        service_name = None
        extract_func = None
        
        if "channel4.com" in url or "all4.com" in url:
            service_name = "Channel 4"
            extract_func = self.extract_channel4_data
        elif "itv.com" in url or "itvx.com" in url:
            service_name = "ITV"
            extract_func = self.extract_itv_data
        elif "channel5.com" in url or "my5.tv" in url:
            service_name = "Channel 5"
            extract_func = self.extract_channel5_data
        else:
            print(f"❌ Unsupported URL: {url}")
            print("   Supported services: Channel 4, ITV, Channel 5")
            return False
            
        # Extract data
        print(f"🔍 Detected service: {service_name}")
        data = extract_func(url)
        
        if not data or not data.get("mpd_url"):
            print("❌ Failed to extract required data from URL")
            return False
            
        # Get DRM key
        drm_key = self.get_drm_key(data.get("pssh"), url, service_name)
        if not drm_key:
            print("❌ Failed to get DRM key")
            return False
            
        # Generate output name
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        program_id = data.get("program_id", "program")
        output_name = f"{service_name.replace(' ', '')}-{program_id}-{timestamp}"
        
        # Download subtitle if available
        subtitle_path = None
        if data.get("subtitle_url"):
            subtitle_output = os.path.join(TEMP_DIR, f"{output_name}.vtt")
            subtitle_path = self.download_subtitle(data["subtitle_url"], subtitle_output)
            
        # Download and decrypt video
        output_file = self.download_and_decrypt(
            data["mpd_url"], 
            drm_key, 
            output_name,
            subtitle_path
        )
        
        if output_file:
            print(f"\n✅ DOWNLOAD COMPLETE!")
            print(f"📺 Final video file: {output_file}")
            return True
        else:
            print("❌ Failed to download and decrypt video")
            return False
            
    def cleanup(self):
        """Clean up temporary files"""
        print("🧹 Cleaning up temporary files...")
        self.close_browser()
        
        # Keep temp directory but remove its contents
        for file in os.listdir(TEMP_DIR):
            file_path = os.path.join(TEMP_DIR, file)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"❌ Error deleting {file_path}: {e}")
                
def main():
    parser = argparse.ArgumentParser(description="UK Streaming Service Downloader")
    parser.add_argument("--url", type=str, help="URL of the show to download")
    parser.add_argument("--no-headless", action="store_true", help="Disable headless browser mode")
    args = parser.parse_args()
    
    print("🎬 UK STREAMING SERVICE DOWNLOADER")
    print("==================================")
    
    # Verify dependencies
    if not os.path.exists(N_M3U8DL_RE_PATH):
        print(f"❌ N_m3u8DL-RE not found at {N_M3U8DL_RE_PATH}")
        print("Please install N_m3u8DL-RE and make sure the path is correct.")
        return
        
    try:
        subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True)
    except:
        print("❌ ffmpeg not found. Please install ffmpeg.")
        return
        
    # Initialize downloader
    downloader = UKStreamerDownloader(headless=not args.no_headless)
    
    try:
        if args.url:
            url = args.url
        else:
            url = input("📎 Please paste the show URL: ")
            
        # Process the URL
        downloader.process_url(url)
            
    except KeyboardInterrupt:
        print("\n⚠️ Operation cancelled by user")
    except Exception as e:
        print(f"❌ An error occurred: {e}")
    finally:
        downloader.cleanup()
        
if __name__ == "__main__":
    main()
