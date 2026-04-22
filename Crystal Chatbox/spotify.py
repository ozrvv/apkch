import threading
import time
import os
import sys
from settings import SETTINGS

# Determine the correct directory for cache file
if getattr(sys, 'frozen', False):
    # Running as compiled executable - save in data folder next to the .exe
    BASE_DIR = os.path.dirname(sys.executable)
    DATA_DIR = os.path.join(BASE_DIR, "Crystal Chatbox Data")
else:
    # Running as Python script - save in script directory
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = BASE_DIR

# Create data directory if it doesn't exist
os.makedirs(DATA_DIR, exist_ok=True)

SPOTIFY_CACHE_PATH = os.path.join(DATA_DIR, ".spotify_cache")

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    SPOTIFY_AVAILABLE = True
except ImportError:
    SPOTIFY_AVAILABLE = False

spotify_state = {
    "song_text": "",
    "song_pos": 0,
    "song_dur": 0,
    "album_art": ""
}

spotify_lock = threading.Lock()
sp = None
force_reinit_event = threading.Event()

def get_spotify_state():
    with spotify_lock:
        return spotify_state.copy()

def init_spotify_web():
    global sp
    if not SPOTIFY_AVAILABLE:
        print("[Spotify] spotipy library not available")
        return
    
    client_id = SETTINGS.get("spotify_client_id", "").strip()
    client_secret = SETTINGS.get("spotify_client_secret", "").strip()
    redirect_uri = SETTINGS.get("spotify_redirect_uri", "")
    
    print(f"[Spotify] Initializing with Client ID: {'set' if client_id else 'NOT SET'}")
    print(f"[Spotify] Redirect URI: {redirect_uri}")
    
    if not client_id or not client_secret:
        print("[Spotify] ⚠️ Missing client ID or secret, Spotify integration disabled")
        print("[Spotify] Please enter your Spotify credentials in the Settings tab")
        sp = None
        return
    
    try:
        scope = "user-read-currently-playing user-read-playback-state"
        
        # IMPORTANT: Always create a fresh auth_manager to pick up newly saved tokens
        auth_manager = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope,
            cache_path=SPOTIFY_CACHE_PATH,
            open_browser=False
        )
        
        # Force refresh from cache file to pick up tokens saved by other instances
        token_info = auth_manager.get_cached_token()
        
        if token_info:
            # Create new Spotify client with the token
            sp = spotipy.Spotify(auth_manager=auth_manager)
            print("[Spotify] ✓ OAuth setup complete!")
            print("[Spotify] ✓ Already authorized - ready to fetch music!")
            print(f"[Spotify] Token expires at: {token_info.get('expires_at', 'unknown')}")
        else:
            sp = spotipy.Spotify(auth_manager=auth_manager)
            print("[Spotify] ✓ OAuth setup complete!")
            print("[Spotify] ⚠️ Not authorized yet - please click 'Connect to Spotify' in dashboard")
    except Exception as e:
        print(f"[Spotify Init Error] {e}")
        import traceback
        traceback.print_exc()
        sp = None

def force_reinit():
    """Force immediate Spotify re-initialization (call after settings change)"""
    global sp
    sp = None  # Reset to trigger fresh init
    force_reinit_event.set()  # Wake up tracker thread
    print("[Spotify] 🔄 Force re-initialization triggered")

def start_spotify_tracker(interval=1):
    def tracker():
        global spotify_state, sp
        print("[Spotify Tracker] Thread started")
        last_error_time = 0
        logged_not_init = False
        last_init_attempt = 0
        
        while True:
            try:
                # Check if force reinit was requested
                if force_reinit_event.is_set():
                    print("[Spotify Tracker] Immediate re-initialization requested!")
                    force_reinit_event.clear()
                    last_init_attempt = 0  # Reset timer to allow immediate init
                
                # Try to initialize if not yet initialized
                if sp is None:
                    current_time = time.time()
                    # Try to initialize every 10 seconds OR immediately after force_reinit
                    if current_time - last_init_attempt > 10 or last_init_attempt == 0:
                        client_id = SETTINGS.get("spotify_client_id", "").strip()
                        if client_id:  # Only try if credentials exist
                            print("[Spotify Tracker] Attempting initialization...")
                            init_spotify_web()
                        last_init_attempt = current_time
                    
                    if sp is None:
                        if not logged_not_init:
                            print("[Spotify Tracker] ⚠️ Spotify client not initialized - waiting for setup")
                            logged_not_init = True
                        time.sleep(5)
                        continue
                
                logged_not_init = False
                
                try:
                    current = sp.current_playback()
                    print(f"[Spotify Tracker] Polled playback: {current is not None}, playing={current.get('is_playing') if current else 'N/A'}")
                except spotipy.exceptions.SpotifyException as e:
                    if e.http_status == 401:
                        current_time = time.time()
                        if current_time - last_error_time > 60:
                            print("[Spotify] Not authenticated or token expired. Please connect to Spotify via the dashboard.")
                            last_error_time = current_time
                        time.sleep(5)
                        continue
                    else:
                        raise
                
                with spotify_lock:
                    if current and current.get("is_playing") and current.get("item"):
                        item = current["item"]
                        artists = ", ".join([artist["name"] for artist in item.get("artists", [])])
                        track_name = item.get("name", "Unknown")
                        spotify_state["song_text"] = f"{track_name} - {artists}"
                        spotify_state["song_pos"] = current.get("progress_ms", 0) // 1000
                        spotify_state["song_dur"] = item.get("duration_ms", 0) // 1000
                        
                        images = item.get("album", {}).get("images", [])
                        if images:
                            spotify_state["album_art"] = images[0].get("url", "")
                        else:
                            spotify_state["album_art"] = ""
                    else:
                        spotify_state["song_text"] = ""
                        spotify_state["song_pos"] = 0
                        spotify_state["song_dur"] = 0
                        spotify_state["album_art"] = ""
                
                time.sleep(interval)
            except Exception as e:
                current_time = time.time()
                if current_time - last_error_time > 60:
                    print(f"[Spotify Tracker ERROR] {e}")
                    last_error_time = current_time
                time.sleep(interval)
    
    threading.Thread(target=tracker, daemon=True).start()
