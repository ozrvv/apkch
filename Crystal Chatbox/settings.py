import json
import os
import sys
import threading

# Determine the correct directory for settings.json
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

SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
settings_lock = threading.Lock()

DEFAULTS = {
    "quest_ip": "",
    "quest_port": 9000,
    "spotify_client_id": "",
    "spotify_client_secret": "",
    "spotify_redirect_uri": "",
    "custom_texts": ["Crystal Chatbox Out Now!", "Support Sapph1r3 On Patreon"],
    "refresh_interval": 3,
    "osc_send_interval": 3,
    "dashboard_update_interval": 1,
    "per_message_intervals": {},
    "music_progress": True,
    "progress_style": "bar",
    "timezone": "local",
    "layout_order": ["time", "custom", "song", "window", "heartrate", "weather", "system_stats", "afk"],
    "theme": "dark",
    "random_order": False,
    "weighted_messages": {},
    "show_module_icons": True,
    "streamer_mode": False,
    "compact_mode": False,
    "error_log_enabled": True,
    "message_queue_preview_count": 3,
    "chatbox_visible": False,
    "show_time": True,
    "show_custom": True,
    "show_music": True,
    "show_window": False,
    "show_heartrate": False,
    "window_tracking_enabled": False,
    "window_tracking_interval": 2,
    "window_tracking_mode": "both",
    "window_prefix": "",
    "weather_temp_unit": "F",
    "heart_rate_enabled": False,
    "heart_rate_source": "pulsoid",
    "heart_rate_pulsoid_token": "",
    "heart_rate_hyperate_id": "",
    "heart_rate_custom_api": "",
    "heart_rate_update_interval": 5,
    "hr_show_trend": True,
    "hr_show_stats": False,
    "time_emoji": "⏰",
    "song_emoji": "🎶",
    "window_emoji": "💻",
    "heartrate_emoji": "❤️",
    "custom_background": "",
    "custom_button_color": "",
    "weather_enabled": True,
    "weather_location": "auto",
    "weather_update_interval": 600,
    "show_weather": True,
    "text_effect": "none",
    "slim_chatbox": False,
    "chatbox_frame": "none",
    "chatbox_frame_style": "none",
    "typed_message_duration": 5,
    "typing_indicator_enabled": True,
    "system_stats_enabled": False,
    "system_stats_show_cpu": True,
    "system_stats_show_ram": True,
    "system_stats_show_gpu": False,
    "system_stats_show_network": False,
    "system_stats_emoji": "📊",
    "afk_enabled": False,
    "afk_timeout": 300,
    "afk_message": "AFK",
    "afk_show_duration": True,
    "afk_emoji": "💤",
    "osc_router_listen_ip": "127.0.0.1",
    "osc_router_listen_port": 9010,
    "fbt_mode": "vrchat_trackers",
    "fbt_camera_source": "local",
    "fbt_phone_camera_url": "",
    "fbt_camera": 0,
    "fbt_smoothing": 0.40,
    "fbt_position_scale": 1.0,
    "fbt_height_m": 1.65,
    "fbt_floor_offset_m": 0.0,
    "fbt_hips_offset_m": 0.0,
    "fbt_feet_y_offset_m": -0.02,
    "fbt_lower_body_y_offset_m": 0.0,
    "fbt_x_offset_m": 0.0,
    "fbt_z_offset_m": 0.0,
    "fbt_send_rate": 60.0,
    "fbt_preview_fps": 30.0,
    "fbt_foot_yaw_blend": 0.78,
    "fbt_foot_yaw_offset_deg": 0.0,
    "fbt_mirror": False,
    "fbt_show_overlay": True,
    "fbt_send_head_align": False,
    "fbt_send_chest_tracker": False,
    "fbt_send_knee_trackers": True,
    "fbt_send_elbow_trackers": False,
    "fbt_estimation_enabled": True,
    "fbt_estimation_strength": 0.82,
    "fbt_occlusion_confidence_threshold": 0.45,
    "fbt_occlusion_velocity_damping": 0.86,
    "fbt_secondary_enabled": False,
    "fbt_secondary_source": "phone",
    "fbt_secondary_phone_camera_url": "",
    "fbt_secondary_camera": 1,
    "fbt_secondary_blend": 0.35,
    "fbt_secondary_target": "lower_body",
    "fbt_secondary_rotation": "90cw",
    "fbt_secondary_mount_preset": "right",
    "fbt_secondary_yaw_deg": 0.0,
    "fbt_secondary_pitch_deg": 0.0,
    "vrcx_plus_avatar_provider_enabled": False,
    "vrcx_plus_avatar_provider_url": "",
    "vrcx_plus_avatar_provider_urls": [],
    "vrcx_plus_auto_snapshot_enabled": False,
    "vrcx_plus_auto_snapshot_minutes": 10,
    "vrcx_plus_auto_snapshot_include_offline": False
}

if os.path.exists(SETTINGS_FILE):
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            SETTINGS = json.load(f)
    except:
        SETTINGS = DEFAULTS.copy()
else:
    SETTINGS = DEFAULTS.copy()

for k, v in DEFAULTS.items():
    if k not in SETTINGS:
        SETTINGS[k] = v

with open(SETTINGS_FILE, "wb") as f:
    f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))

def reload_settings():
    """Reload settings from file - use after external changes"""
    global SETTINGS
    with settings_lock:
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                loaded_settings = json.load(f)
            
            # Merge with defaults to ensure all keys exist
            for k, v in DEFAULTS.items():
                if k not in loaded_settings:
                    loaded_settings[k] = v
            
            SETTINGS.clear()
            SETTINGS.update(loaded_settings)
            print("[Settings] ✓ Settings reloaded from file")
            return True
        except Exception as e:
            print(f"[Settings] ⚠️ Failed to reload settings: {e}")
            return False
