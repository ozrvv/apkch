import threading
import time
import json
import os
import sys
import random
import logging
import signal
import subprocess
from collections import deque
from copy import deepcopy
from datetime import datetime
import pytz

from flask import Flask, render_template, request, jsonify, redirect, send_file
from pythonosc.udp_client import SimpleUDPClient

from settings import SETTINGS, SETTINGS_FILE
import spotify
import window_tracker
import heart_rate_monitor
import github_updater
import openai_client
import weather_service
import profiles_manager
import text_effects
import chatbox_frames
import system_stats
import afk_detector
import quick_phrases
import message_history
import vrchat_service

# Determine the correct directory for error log
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

ERROR_LOG_FILE = os.path.join(DATA_DIR, "vrchat_errors.log")

logging.basicConfig(
    filename=ERROR_LOG_FILE,
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

chatbox_visible = SETTINGS.get("chatbox_visible", False)
show_time = SETTINGS.get("show_time", True)
show_custom = SETTINGS.get("show_custom", True)
show_music = SETTINGS.get("show_music", True)
show_window = SETTINGS.get("show_window", False)
show_heartrate = SETTINGS.get("show_heartrate", False)
show_weather = SETTINGS.get("show_weather", False)

settings_changed = False
if SETTINGS.get("window_tracking_enabled", False):
    if not show_window:
        show_window = True
        SETTINGS["show_window"] = True
        settings_changed = True
if SETTINGS.get("heart_rate_enabled", False):
    if not show_heartrate:
        show_heartrate = True
        SETTINGS["show_heartrate"] = True
        settings_changed = True
if SETTINGS.get("weather_enabled", False):
    if not show_weather:
        show_weather = True
        SETTINGS["show_weather"] = True
        settings_changed = True

print(f"[Startup] show_weather={show_weather}, weather_enabled={SETTINGS.get('weather_enabled', False)}, LAYOUT_ORDER will be: {SETTINGS.get('layout_order', [])}")

if settings_changed:
    try:
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
    except Exception as e:
        print(f"[Startup] Failed to sync settings: {e}")

auto_send_paused = False
connection_status = "disconnected"
last_successful_send = None
last_osc_send_time = 0

typing_state_lock = threading.Lock()
typing_state = {
    "is_typing": False,
    "typed_message": "",
    "display_until": 0,
    "show_indicator": False,
    "message_sent": False
}

current_time_text = ""
current_custom_text = SETTINGS.get("custom_texts", ["Custom Message Test"])[0]
last_message_sent = ""
text_cycle_index = 0
next_custom_in = SETTINGS.get("osc_send_interval", 3)
per_message_timers = {}
message_queue = []

CUSTOM_TEXTS = SETTINGS.get("custom_texts", [])
OSC_SEND_INTERVAL = SETTINGS.get("osc_send_interval", 3)
DASHBOARD_UPDATE_INTERVAL = SETTINGS.get("dashboard_update_interval", 1)
TIMEZONE = SETTINGS.get("timezone", "local")
MUSIC_PROGRESS = SETTINGS.get("music_progress", True)
PROGRESS_STYLE = SETTINGS.get("progress_style", "bar")
LAYOUT_ORDER = SETTINGS.get("layout_order", ["time","custom","song","window","heartrate","weather","system_stats","afk"])

current_custom_text = CUSTOM_TEXTS[0] if CUSTOM_TEXTS else "Custom Message Test"
current_time_text = datetime.now().strftime("%I:%M %p").lstrip("0")

def log_error(message, exception=None):
    if SETTINGS.get("error_log_enabled", True):
        if exception:
            logging.error(f"{message}: {str(exception)}")
        else:
            logging.error(message)

def make_client():
    ip = SETTINGS.get("quest_ip", "") or "127.0.0.1"
    port = int(SETTINGS.get("quest_port", 9000))
    return SimpleUDPClient(ip, port)

client = make_client()

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TRACKER_DIR = os.path.join(WORKSPACE_ROOT, "osc_body_tracker")
TRACKER_RUN_SCRIPT = os.path.join(TRACKER_DIR, "run.sh")
OSC_ROUTER_SCRIPT = os.path.join(TRACKER_DIR, "osc_router.py")
RECENTER_REQUEST_FILE = os.path.join(TRACKER_DIR, ".recenter_request")

tracker_lock = threading.Lock()
tracker_process = None
tracker_mode = ""
tracker_started_at = 0.0
tracker_exit_code = None
tracker_logs = deque(maxlen=200)

osc_router_lock = threading.Lock()
osc_router_process = None
osc_router_started_at = 0.0
osc_router_exit_code = None
osc_router_logs = deque(maxlen=200)

VRCX_PLUS_FILE = os.path.join(DATA_DIR, "vrcx_plus_data.json")
vrcx_plus_lock = threading.Lock()


def _vrcx_plus_now_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _vrcx_plus_default_data():
    now_iso = _vrcx_plus_now_iso()
    return {
        "items": [
            {
                "id": "avatar_demo_1",
                "type": "avatar",
                "name": "Neon Fox",
                "author": "CrystalTeam",
                "status": "public",
                "description": "Starter VRCX+ avatar entry",
                "created_at": now_iso,
                "updated_at": now_iso
            },
            {
                "id": "world_demo_1",
                "type": "world",
                "name": "Crystal Lounge",
                "author": "CrystalTeam",
                "status": "public",
                "description": "Starter VRCX+ world entry",
                "created_at": now_iso,
                "updated_at": now_iso
            },
            {
                "id": "friend_demo_1",
                "type": "friend",
                "name": "Sapph1r3",
                "author": "",
                "status": "friend",
                "description": "Starter friend entry",
                "created_at": now_iso,
                "updated_at": now_iso
            }
        ],
        "favorites": {
            "avatar": ["avatar_demo_1"],
            "world": ["world_demo_1"],
            "friend": ["friend_demo_1"],
            "group": []
        },
        "notes": [
            {
                "id": "note_demo_1",
                "text": "Welcome to VRC+ inside Crystal Client.",
                "created_at": now_iso
            }
        ],
        "events": [
            {
                "id": "event_demo_1",
                "kind": "notification",
                "title": "VRCX+ initialized",
                "detail": "Your VRCX+ data store is ready.",
                "created_at": now_iso
            }
        ],
        "friend_logs": []
    }


def _vrcx_plus_normalize(data):
    out = deepcopy(data) if isinstance(data, dict) else {}
    out.setdefault("items", [])
    out.setdefault("favorites", {})
    out.setdefault("notes", [])
    out.setdefault("events", [])
    out.setdefault("friend_logs", [])
    for key in ("avatar", "world", "friend", "group"):
        out["favorites"].setdefault(key, [])
    return out


def _load_vrcx_plus_data():
    with vrcx_plus_lock:
        if not os.path.exists(VRCX_PLUS_FILE):
            data = _vrcx_plus_default_data()
            with open(VRCX_PLUS_FILE, "wb") as f:
                f.write(json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))
            return data

        try:
            with open(VRCX_PLUS_FILE, "rb") as f:
                parsed = json.loads(f.read().decode("utf-8"))
            return _vrcx_plus_normalize(parsed)
        except Exception as e:
            log_error("Failed to load VRCX+ data", e)
            data = _vrcx_plus_default_data()
            with open(VRCX_PLUS_FILE, "wb") as f:
                f.write(json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))
            return data


def _save_vrcx_plus_data(data):
    normalized = _vrcx_plus_normalize(data)
    with vrcx_plus_lock:
        with open(VRCX_PLUS_FILE, "wb") as f:
            f.write(json.dumps(normalized, indent=2, ensure_ascii=False).encode("utf-8"))
    return normalized


def _vrcx_plus_make_id(prefix):
    return f"{prefix}_{int(time.time() * 1000)}_{random.randint(100, 999)}"


def _vrcx_plus_append_event(data, kind, title, detail=""):
    events = data.get("events", [])
    events.insert(
        0,
        {
            "id": _vrcx_plus_make_id("event"),
            "kind": str(kind),
            "title": str(title),
            "detail": str(detail),
            "created_at": _vrcx_plus_now_iso()
        }
    )
    data["events"] = events[:200]


def _vrcx_plus_split_provider_text(value):
    text = str(value or "").replace("\r", "\n")
    tokens = []
    for line in text.split("\n"):
        for chunk in line.replace(";", ",").split(","):
            cleaned = str(chunk or "").strip()
            if cleaned:
                tokens.append(cleaned)
    return tokens


def _vrcx_plus_normalize_provider_urls(raw_urls, legacy_url=""):
    urls = []
    seen = set()

    def add_url(value):
        url = str(value or "").strip()
        if not url or url in seen:
            return
        seen.add(url)
        urls.append(url)

    if isinstance(raw_urls, str):
        for candidate in _vrcx_plus_split_provider_text(raw_urls):
            add_url(candidate)
    elif isinstance(raw_urls, (list, tuple, set)):
        for item in raw_urls:
            if isinstance(item, str):
                parsed = _vrcx_plus_split_provider_text(item)
                if parsed:
                    for candidate in parsed:
                        add_url(candidate)
                    continue
            add_url(item)

    if not urls:
        add_url(legacy_url)
    return urls


def _vrcx_plus_provider_settings():
    enabled = bool(SETTINGS.get("vrcx_plus_avatar_provider_enabled", False))
    legacy_url = str(SETTINGS.get("vrcx_plus_avatar_provider_url", "")).strip()
    urls = _vrcx_plus_normalize_provider_urls(
        SETTINGS.get("vrcx_plus_avatar_provider_urls", []),
        legacy_url=legacy_url
    )
    return {
        "enabled": enabled,
        "url": urls[0] if urls else "",
        "urls": urls,
        "count": len(urls)
    }


def _vrcx_plus_parse_iso_ts(value):
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        # Persisted timestamps are UTC ISO strings like "2026-02-19T14:03:00Z".
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _vrcx_plus_recent_cutoff(recent):
    mode = str(recent or "all").strip().lower()
    now_ts = time.time()
    if mode in {"24h", "day", "1d"}:
        return now_ts - (24 * 60 * 60)
    if mode in {"7d", "week"}:
        return now_ts - (7 * 24 * 60 * 60)
    if mode in {"30d", "month"}:
        return now_ts - (30 * 24 * 60 * 60)
    return 0.0


def _vrcx_plus_recent_match(created_at, recent):
    cutoff = _vrcx_plus_recent_cutoff(recent)
    if cutoff <= 0:
        return True
    return _vrcx_plus_parse_iso_ts(created_at) >= cutoff


def _vrcx_plus_collect_avatar_history(data, query="", recent="all", user_id="", limit=300):
    q = str(query or "").strip().lower()
    selected_user_id = str(user_id or "").strip()
    avatars = {}

    for snapshot in data.get("friend_logs", []):
        created_at = snapshot.get("created_at")
        if not _vrcx_plus_recent_match(created_at, recent):
            continue

        for friend in snapshot.get("friends", []):
            friend_id = str(friend.get("id") or "").strip()
            if not friend_id:
                continue
            if selected_user_id and friend_id != selected_user_id:
                continue

            avatar_id = str(friend.get("currentAvatarId") or friend.get("currentAvatar") or "").strip()
            if not avatar_id:
                continue

            display_name = str(friend.get("displayName") or friend_id or "Unknown").strip()
            avatar_name = str(friend.get("currentAvatarName") or friend.get("avatarName") or "").strip()
            avatar_thumb = str(
                friend.get("currentAvatarThumbnailImageUrl")
                or friend.get("avatarThumbnailImageUrl")
                or ""
            ).strip()
            avatar_image = str(
                friend.get("currentAvatarImageUrl")
                or friend.get("avatarImageUrl")
                or avatar_thumb
                or ""
            ).strip()

            entry = avatars.get(avatar_id)
            if entry is None:
                entry = {
                    "avatar_id": avatar_id,
                    "name": avatar_name,
                    "thumbnail_image_url": avatar_thumb,
                    "image_url": avatar_image,
                    "first_seen": created_at,
                    "last_seen": created_at,
                    "seen_count": 0,
                    "users": {}
                }
                avatars[avatar_id] = entry
            else:
                if avatar_name and not entry.get("name"):
                    entry["name"] = avatar_name
                if avatar_thumb and not entry.get("thumbnail_image_url"):
                    entry["thumbnail_image_url"] = avatar_thumb
                if avatar_image and not entry.get("image_url"):
                    entry["image_url"] = avatar_image
                if created_at and (entry.get("first_seen", "") == "" or created_at < entry.get("first_seen", "")):
                    entry["first_seen"] = created_at
                if created_at and created_at > (entry.get("last_seen") or ""):
                    entry["last_seen"] = created_at

            entry["seen_count"] = int(entry.get("seen_count", 0)) + 1
            users_map = entry.get("users", {})
            user_entry = users_map.get(friend_id) or {
                "id": friend_id,
                "displayName": display_name,
                "snapshots": 0,
                "last_seen": created_at
            }
            user_entry["displayName"] = display_name or user_entry.get("displayName") or friend_id
            user_entry["snapshots"] = int(user_entry.get("snapshots", 0)) + 1
            if created_at and created_at > (user_entry.get("last_seen") or ""):
                user_entry["last_seen"] = created_at
            users_map[friend_id] = user_entry
            entry["users"] = users_map

    results = []
    max_results = max(1, min(int(limit), 600))
    for entry in avatars.values():
        users_map = entry.get("users", {})
        users = sorted(users_map.values(), key=lambda x: str(x.get("last_seen", "")), reverse=True)
        user_names = ", ".join([str(user.get("displayName") or user.get("id") or "") for user in users[:8]])
        haystack = " ".join(
            [
                str(entry.get("avatar_id") or ""),
                str(entry.get("name") or ""),
                user_names
            ]
        ).lower()
        if q and q not in haystack:
            continue
        results.append(
            {
                "avatar_id": entry.get("avatar_id"),
                "name": entry.get("name") or "Unknown Avatar",
                "thumbnail_image_url": entry.get("thumbnail_image_url") or "",
                "image_url": entry.get("image_url") or "",
                "first_seen": entry.get("first_seen"),
                "last_seen": entry.get("last_seen"),
                "seen_count": int(entry.get("seen_count", 0)),
                "users": users[:12],
                "user_count": len(users),
                "user_names": user_names
            }
        )

    results.sort(key=lambda x: (str(x.get("last_seen", "")), int(x.get("seen_count", 0))), reverse=True)
    results = results[:max_results]

    # Enrich unknown names from VRChat API so "unknown avatar" entries resolve over time.
    enrich_budget = 25
    auth_blocked = False
    for row in results:
        if enrich_budget <= 0 or auth_blocked:
            break
        current_name = str(row.get("name") or "").strip().lower()
        if current_name and current_name not in {"unknown avatar", "unknown"}:
            continue
        avatar_id = str(row.get("avatar_id") or "").strip()
        if not avatar_id.startswith("avtr_"):
            continue
        enrich_budget -= 1
        details = vrchat_service.get_avatar(avatar_id)
        if not details.get("ok"):
            err = str(details.get("error") or "").lower()
            if "authorization required" in err or "2fa required" in err or "unauthorized" in err:
                auth_blocked = True
            continue
        avatar = details.get("avatar") or {}
        resolved_name = str(avatar.get("name") or "").strip()
        resolved_thumb = str(avatar.get("thumbnailImageUrl") or "").strip()
        resolved_image = str(avatar.get("imageUrl") or "").strip()
        if resolved_name:
            row["name"] = resolved_name
        if resolved_thumb and not row.get("thumbnail_image_url"):
            row["thumbnail_image_url"] = resolved_thumb
        if resolved_image and not row.get("image_url"):
            row["image_url"] = resolved_image

    return results


vrcx_plus_worker_started = False
vrcx_plus_worker_lock = threading.Lock()
vrcx_plus_last_auto_snapshot_at = 0.0


def _capture_vrcx_plus_friend_snapshot(include_offline=False, max_results=120, source="manual"):
    payload = vrchat_service.get_friends(n=max_results, offline=include_offline)
    if not payload.get("ok"):
        return {"ok": False, "error": payload.get("error", "Failed to fetch friends")}

    friends = payload.get("friends", [])
    now_iso = _vrcx_plus_now_iso()
    compact = []
    for friend in friends:
        compact.append(
            {
                "id": friend.get("id"),
                "displayName": friend.get("displayName") or friend.get("username"),
                "status": friend.get("status"),
                "statusDescription": friend.get("statusDescription"),
                "location": friend.get("location"),
                "last_login": friend.get("last_login"),
                "currentAvatarId": friend.get("currentAvatar"),
                "currentAvatarName": friend.get("currentAvatarName"),
                "currentAvatarImageUrl": friend.get("currentAvatarImageUrl"),
                "currentAvatarThumbnailImageUrl": friend.get("currentAvatarThumbnailImageUrl")
            }
        )

    data = _load_vrcx_plus_data()
    entry = {
        "id": _vrcx_plus_make_id("friendsnap"),
        "created_at": now_iso,
        "count": len(compact),
        "source": source,
        "friends": compact
    }
    logs = data.get("friend_logs", [])
    logs.insert(0, entry)
    data["friend_logs"] = logs[:50]
    _vrcx_plus_append_event(data, "group", "Friend snapshot captured", f"{len(compact)} entries ({source})")
    _save_vrcx_plus_data(data)
    return {"ok": True, "snapshot": entry}


def _start_vrcx_plus_worker():
    global vrcx_plus_worker_started, vrcx_plus_last_auto_snapshot_at
    with vrcx_plus_worker_lock:
        if vrcx_plus_worker_started:
            return
        vrcx_plus_worker_started = True

    def worker():
        global vrcx_plus_last_auto_snapshot_at
        while True:
            try:
                enabled = bool(SETTINGS.get("vrcx_plus_auto_snapshot_enabled", False))
                minutes = int(SETTINGS.get("vrcx_plus_auto_snapshot_minutes", 10))
                include_offline = bool(SETTINGS.get("vrcx_plus_auto_snapshot_include_offline", False))
                minutes = max(1, min(minutes, 180))
                interval_seconds = minutes * 60
                now_ts = time.time()

                if enabled and (now_ts - vrcx_plus_last_auto_snapshot_at) >= interval_seconds:
                    auth_status = vrchat_service.status()
                    if auth_status.get("logged_in"):
                        result = _capture_vrcx_plus_friend_snapshot(
                            include_offline=include_offline,
                            max_results=120,
                            source="auto"
                        )
                        if result.get("ok"):
                            vrcx_plus_last_auto_snapshot_at = now_ts
                        else:
                            log_error(f"VRCX+ auto snapshot failed: {result.get('error')}")
                    else:
                        vrcx_plus_last_auto_snapshot_at = now_ts
            except Exception as e:
                log_error("VRCX+ worker error", e)

            time.sleep(30)

    threading.Thread(target=worker, daemon=True).start()


def _is_running(proc):
    return proc is not None and proc.poll() is None


def _append_log(log_buffer, line):
    if line:
        log_buffer.append(line.rstrip())


def _stream_process_output(proc, log_buffer, prefix):
    if proc.stdout is None:
        return
    try:
        for line in proc.stdout:
            _append_log(log_buffer, f"[{prefix}] {line.rstrip()}")
    except Exception as e:
        _append_log(log_buffer, f"[{prefix}] log stream error: {e}")


def _terminate_process_group(proc):
    if not _is_running(proc):
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass


def _kill_process_group(proc):
    if not _is_running(proc):
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _tracker_status():
    global tracker_process, tracker_exit_code, tracker_mode, tracker_started_at
    running = _is_running(tracker_process)
    if not running and tracker_process is not None:
        tracker_exit_code = tracker_process.poll()
        tracker_process = None
        tracker_mode = ""
        tracker_started_at = 0.0
    return {
        "running": running,
        "mode": tracker_mode if running else "",
        "pid": tracker_process.pid if running else None,
        "started_at": tracker_started_at if running else 0,
        "exit_code": tracker_exit_code if not running else None,
        "logs": list(tracker_logs)[-12:],
    }


def _osc_router_status():
    global osc_router_process, osc_router_exit_code, osc_router_started_at
    running = _is_running(osc_router_process)
    if not running and osc_router_process is not None:
        osc_router_exit_code = osc_router_process.poll()
        osc_router_process = None
        osc_router_started_at = 0.0
    return {
        "running": running,
        "pid": osc_router_process.pid if running else None,
        "started_at": osc_router_started_at if running else 0,
        "exit_code": osc_router_exit_code if not running else None,
        "listen_ip": SETTINGS.get("osc_router_listen_ip", "127.0.0.1"),
        "listen_port": int(SETTINGS.get("osc_router_listen_port", 9010)),
        "logs": list(osc_router_logs)[-12:],
    }


FBT_DEFAULTS = {
    "mode": "vrchat_trackers",
    "camera_source": "local",
    "phone_camera_url": "",
    "camera": 0,
    "smoothing": 0.40,
    "position_scale": 1.0,
    "height_m": 1.65,
    "floor_offset_m": 0.0,
    "hips_offset_m": 0.0,
    "feet_y_offset_m": -0.02,
    "lower_body_y_offset_m": 0.0,
    "x_offset_m": 0.0,
    "z_offset_m": 0.0,
    "send_rate": 60.0,
    "preview_fps": 30.0,
    "foot_yaw_blend": 0.78,
    "foot_yaw_offset_deg": 0.0,
    "mirror": False,
    "show_overlay": True,
    "send_head_align": False,
    "send_chest_tracker": False,
    "send_knee_trackers": True,
    "send_elbow_trackers": False,
    "estimation_enabled": True,
    "estimation_strength": 0.82,
    "occlusion_confidence_threshold": 0.45,
    "occlusion_velocity_damping": 0.86,
    "secondary_enabled": False,
    "secondary_source": "phone",
    "secondary_phone_camera_url": "",
    "secondary_camera": 1,
    "secondary_blend": 0.35,
    "secondary_target": "lower_body",
    "secondary_rotation": "90cw",
    "secondary_mount_preset": "right",
    "secondary_yaw_deg": 0.0,
    "secondary_pitch_deg": 0.0,
}


def _get_fbt_settings():
    out = {}
    for key, default in FBT_DEFAULTS.items():
        out[key] = SETTINGS.get(f"fbt_{key}", default)
    return out


def _save_fbt_settings(data):
    valid_modes = {"vrchat_trackers", "vrchat", "generic"}
    valid_cam_source = {"local", "phone"}
    valid_secondary_target = {"lower_body", "full"}
    valid_rotation = {"0", "90cw", "90ccw", "180"}
    valid_mount = {"right", "left", "back", "front", "custom"}

    current = _get_fbt_settings()
    current["mode"] = data.get("mode", current["mode"])
    if current["mode"] not in valid_modes:
        current["mode"] = FBT_DEFAULTS["mode"]
    current["camera_source"] = data.get("camera_source", current["camera_source"])
    if current["camera_source"] not in valid_cam_source:
        current["camera_source"] = FBT_DEFAULTS["camera_source"]
    current["phone_camera_url"] = str(data.get("phone_camera_url", current["phone_camera_url"])).strip()

    def _as_int(name, low, high):
        try:
            v = int(data.get(name, current[name]))
        except Exception:
            v = int(current[name])
        return max(low, min(high, v))

    def _as_float(name, low, high):
        try:
            v = float(data.get(name, current[name]))
        except Exception:
            v = float(current[name])
        return max(low, min(high, v))

    def _as_bool(name):
        raw = data.get(name, current[name])
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.lower() in ("1", "true", "yes", "on")
        return bool(raw)

    current["camera"] = _as_int("camera", 0, 8)
    current["smoothing"] = _as_float("smoothing", 0.0, 0.95)
    current["position_scale"] = _as_float("position_scale", 0.1, 4.0)
    current["height_m"] = _as_float("height_m", 1.0, 2.5)
    current["floor_offset_m"] = _as_float("floor_offset_m", -1.0, 1.0)
    current["hips_offset_m"] = _as_float("hips_offset_m", -1.0, 1.0)
    current["feet_y_offset_m"] = _as_float("feet_y_offset_m", -1.0, 1.0)
    current["lower_body_y_offset_m"] = _as_float("lower_body_y_offset_m", -1.0, 1.0)
    current["x_offset_m"] = _as_float("x_offset_m", -2.0, 2.0)
    current["z_offset_m"] = _as_float("z_offset_m", -2.0, 2.0)
    current["send_rate"] = _as_float("send_rate", 10.0, 120.0)
    current["preview_fps"] = _as_float("preview_fps", 10.0, 60.0)
    current["foot_yaw_blend"] = _as_float("foot_yaw_blend", 0.0, 1.0)
    current["foot_yaw_offset_deg"] = _as_float("foot_yaw_offset_deg", -45.0, 45.0)
    current["mirror"] = _as_bool("mirror")
    current["show_overlay"] = _as_bool("show_overlay")
    current["send_head_align"] = _as_bool("send_head_align")
    current["send_chest_tracker"] = _as_bool("send_chest_tracker")
    current["send_knee_trackers"] = _as_bool("send_knee_trackers")
    current["send_elbow_trackers"] = _as_bool("send_elbow_trackers")
    current["estimation_enabled"] = _as_bool("estimation_enabled")
    current["estimation_strength"] = _as_float("estimation_strength", 0.1, 1.0)
    current["occlusion_confidence_threshold"] = _as_float("occlusion_confidence_threshold", 0.1, 0.95)
    current["occlusion_velocity_damping"] = _as_float("occlusion_velocity_damping", 0.5, 0.995)
    current["secondary_enabled"] = _as_bool("secondary_enabled")
    current["secondary_source"] = data.get("secondary_source", current["secondary_source"])
    if current["secondary_source"] not in valid_cam_source:
        current["secondary_source"] = FBT_DEFAULTS["secondary_source"]
    current["secondary_phone_camera_url"] = str(data.get("secondary_phone_camera_url", current["secondary_phone_camera_url"])).strip()
    current["secondary_camera"] = _as_int("secondary_camera", 0, 8)
    current["secondary_blend"] = _as_float("secondary_blend", 0.0, 1.0)
    current["secondary_target"] = data.get("secondary_target", current["secondary_target"])
    if current["secondary_target"] not in valid_secondary_target:
        current["secondary_target"] = FBT_DEFAULTS["secondary_target"]
    current["secondary_rotation"] = data.get("secondary_rotation", current["secondary_rotation"])
    if current["secondary_rotation"] not in valid_rotation:
        current["secondary_rotation"] = FBT_DEFAULTS["secondary_rotation"]
    current["secondary_mount_preset"] = data.get("secondary_mount_preset", current["secondary_mount_preset"])
    if current["secondary_mount_preset"] not in valid_mount:
        current["secondary_mount_preset"] = FBT_DEFAULTS["secondary_mount_preset"]
    current["secondary_yaw_deg"] = _as_float("secondary_yaw_deg", -180.0, 180.0)
    current["secondary_pitch_deg"] = _as_float("secondary_pitch_deg", -90.0, 90.0)

    for key, value in current.items():
        SETTINGS[f"fbt_{key}"] = value
    with open(SETTINGS_FILE, "wb") as f:
        f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
    return current


def _build_fbt_cli_args(fbt):
    args = [
        "--cli",
        "--mode", str(fbt["mode"]),
        "--camera-source", str(fbt["camera_source"]),
        "--camera", str(fbt["camera"]),
        "--smoothing", str(fbt["smoothing"]),
        "--position-scale", str(fbt["position_scale"]),
        "--height-m", str(fbt["height_m"]),
        "--floor-offset-m", str(fbt["floor_offset_m"]),
        "--hips-offset-m", str(fbt["hips_offset_m"]),
        "--feet-y-offset-m", str(fbt["feet_y_offset_m"]),
        "--lower-body-y-offset-m", str(fbt["lower_body_y_offset_m"]),
        "--x-offset-m", str(fbt["x_offset_m"]),
        "--z-offset-m", str(fbt["z_offset_m"]),
        "--send-rate", str(fbt["send_rate"]),
        "--preview-fps", str(fbt["preview_fps"]),
        "--foot-yaw-blend", str(fbt["foot_yaw_blend"]),
        "--foot-yaw-offset-deg", str(fbt["foot_yaw_offset_deg"]),
        "--estimation-strength", str(fbt["estimation_strength"]),
        "--occlusion-confidence-threshold", str(fbt["occlusion_confidence_threshold"]),
        "--occlusion-velocity-damping", str(fbt["occlusion_velocity_damping"]),
    ]

    if fbt["camera_source"] == "phone" and fbt.get("phone_camera_url"):
        args.extend(["--phone-camera-url", str(fbt["phone_camera_url"])])
    if fbt["secondary_enabled"]:
        args.extend(
            [
                "--secondary-enabled",
                "--secondary-source", str(fbt["secondary_source"]),
                "--secondary-camera", str(fbt["secondary_camera"]),
                "--secondary-blend", str(fbt["secondary_blend"]),
                "--secondary-target", str(fbt["secondary_target"]),
                "--secondary-rotation", str(fbt["secondary_rotation"]),
                "--secondary-mount-preset", str(fbt["secondary_mount_preset"]),
                "--secondary-yaw-deg", str(fbt["secondary_yaw_deg"]),
                "--secondary-pitch-deg", str(fbt["secondary_pitch_deg"]),
            ]
        )
        if fbt["secondary_source"] == "phone" and fbt.get("secondary_phone_camera_url"):
            args.extend(["--secondary-phone-camera-url", str(fbt["secondary_phone_camera_url"])])
    args.append("--estimation-enabled" if fbt["estimation_enabled"] else "--no-estimation-enabled")
    args.append("--mirror" if fbt["mirror"] else "")
    args.append("--no-preview" if not fbt["show_overlay"] else "")
    args.append("--head-align" if fbt["send_head_align"] else "--no-head-align")
    args.append("--send-chest-tracker" if fbt["send_chest_tracker"] else "--no-send-chest-tracker")
    args.append("--send-knee-trackers" if fbt["send_knee_trackers"] else "--no-send-knee-trackers")
    args.append("--send-elbow-trackers" if fbt["send_elbow_trackers"] else "--no-send-elbow-trackers")
    return [a for a in args if a]

def replace_variables(text):
    """Replace variable tags like {song} and {time} in messages"""
    if not text:
        return text
    
    result = text
    
    tz_setting = SETTINGS.get("timezone", "local")
    if tz_setting == "local":
        now = datetime.now()
    else:
        now = datetime.now(pytz.timezone(str(tz_setting)))
    time_str = now.strftime("%I:%M %p").lstrip("0")
    
    sstate = spotify.get_spotify_state()
    song_str = sstate.get("song_text", "No song playing")
    
    result = result.replace("{time}", time_str)
    result = result.replace("{song}", song_str)
    
    return result

def get_next_custom_message():
    """Get next custom message based on random/weighted settings"""
    global text_cycle_index, CUSTOM_TEXTS
    
    if not CUSTOM_TEXTS:
        return ""
    
    if SETTINGS.get("random_order", False):
        weighted_messages = SETTINGS.get("weighted_messages", {})
        
        if weighted_messages:
            weights = []
            for idx in range(len(CUSTOM_TEXTS)):
                weight = weighted_messages.get(str(idx), 1)
                weights.append(weight)
            
            text_cycle_index = random.choices(range(len(CUSTOM_TEXTS)), weights=weights, k=1)[0]
        else:
            text_cycle_index = random.randint(0, len(CUSTOM_TEXTS) - 1)
    else:
        text_cycle_index = (text_cycle_index + 1) % len(CUSTOM_TEXTS)
    
    return CUSTOM_TEXTS[text_cycle_index]

def update_message_queue():
    """Update the preview of next messages to be sent"""
    global message_queue, CUSTOM_TEXTS
    
    queue_count = SETTINGS.get("message_queue_preview_count", 3)
    message_queue = []
    
    if not CUSTOM_TEXTS:
        return
    
    temp_index = text_cycle_index
    for i in range(queue_count):
        if SETTINGS.get("random_order", False):
            message_queue.append("Random")
        else:
            next_idx = (temp_index + i) % len(CUSTOM_TEXTS)
            msg = CUSTOM_TEXTS[next_idx]
            message_queue.append(msg[:30] + "..." if len(msg) > 30 else msg)

def get_current_preview():
    global current_time_text, current_custom_text
    
    if show_time:
        tz_setting = SETTINGS.get("timezone", "local")
        if tz_setting == "local":
            now = datetime.now()
        else:
            now = datetime.now(pytz.timezone(str(tz_setting)))
        current_time_text = now.strftime("%I:%M %p").lstrip("0")
    else:
        current_time_text = ""

    sstate = spotify.get_spotify_state()
    song_line = ""
    if show_music and sstate.get("song_text"):
        pos = int(sstate.get("song_pos", 0))
        dur = int(sstate.get("song_dur", 0))
        elapsed_min, elapsed_sec = divmod(pos, 60)
        total_min, total_sec = divmod(dur, 60)
        show_icons = SETTINGS.get("show_module_icons", True)
        song_emoji = SETTINGS.get("song_emoji", "🎶")
        icon = f"{song_emoji} " if show_icons and song_emoji else ""
        song_line = f"{icon}{sstate['song_text']} [{elapsed_min}:{elapsed_sec:02d} / {total_min}:{total_sec:02d}]"

    wstate = window_tracker.get_window_state()
    window_line = ""
    if show_window and wstate.get("app_name"):
        show_icons = SETTINGS.get("show_module_icons", True)
        window_emoji = SETTINGS.get("window_emoji", "💻")
        icon = f"{window_emoji} " if show_icons and window_emoji else ""
        window_prefix = SETTINGS.get("window_prefix", "Currently on:")
        if window_prefix:
            window_line = f"{icon}{window_prefix} {wstate['app_name']}"
        else:
            window_line = f"{icon}{wstate['app_name']}"

    hrstate = heart_rate_monitor.get_heart_rate_state()
    heartrate_line = ""
    if show_heartrate and hrstate.get("is_connected") and hrstate.get("bpm", 0) > 0:
        show_icons = SETTINGS.get("show_module_icons", True)
        heartrate_emoji = SETTINGS.get("heartrate_emoji", "❤️")
        icon = f"{heartrate_emoji} " if show_icons and heartrate_emoji else ""
        heartrate_line = f"{icon}{hrstate['bpm']} BPM"

    weather_line = ""
    if show_weather:
        temp_unit = SETTINGS.get("weather_temp_unit", "F")
        weather_text = weather_service.get_weather_text(temp_unit)
        if weather_text:
            weather_line = weather_text

    system_stats_line = ""
    if SETTINGS.get("system_stats_enabled", False):
        stats = system_stats.get_system_stats()
        if stats and stats.get("available", False):
            show_icons = SETTINGS.get("show_module_icons", True)
            stats_emoji = SETTINGS.get("system_stats_emoji", "📊")
            icon = f"{stats_emoji} " if show_icons and stats_emoji else ""
            parts = []
            if SETTINGS.get("system_stats_show_cpu", True):
                parts.append(f"CPU: {stats.get('cpu_percent', 0)}%")
            if SETTINGS.get("system_stats_show_ram", True):
                parts.append(f"RAM: {stats.get('ram_percent', 0)}%")
            if SETTINGS.get("system_stats_show_gpu", False) and stats.get("gpu_available", False):
                parts.append(f"GPU: {stats.get('gpu_percent', 0)}%")
            if SETTINGS.get("system_stats_show_network", False):
                down = stats.get("network_recv_speed", 0)
                up = stats.get("network_sent_speed", 0)
                if down >= 1024:
                    down_str = f"{round(down/1024, 1)}MB/s"
                else:
                    down_str = f"{round(down)}KB/s"
                if up >= 1024:
                    up_str = f"{round(up/1024, 1)}MB/s"
                else:
                    up_str = f"{round(up)}KB/s"
                parts.append(f"↓{down_str} ↑{up_str}")
            if parts:
                system_stats_line = f"{icon}{' | '.join(parts)}"

    afk_line = ""
    if SETTINGS.get("afk_enabled", False):
        timeout = SETTINGS.get("afk_timeout", 300)
        afk_detector.check_afk(timeout)
        if afk_detector.is_afk():
            afk_msg = afk_detector.get_afk_message(
                SETTINGS.get("afk_message", ""),
                SETTINGS.get("afk_show_duration", True)
            )
            if afk_msg:
                show_icons = SETTINGS.get("show_module_icons", True)
                afk_emoji = SETTINGS.get("afk_emoji", "💤")
                icon = f"{afk_emoji} " if show_icons and afk_emoji else ""
                afk_line = f"{icon}{afk_msg}"

    show_icons = SETTINGS.get("show_module_icons", True)
    lines = []
    layout = SETTINGS.get("layout_order", ["time","custom","song","window","heartrate","weather","system_stats","afk"])
    
    if SETTINGS.get("system_stats_enabled", False) and "system_stats" not in layout:
        layout = list(layout) + ["system_stats"]
    if SETTINGS.get("afk_enabled", False) and "afk" not in layout:
        layout = list(layout) + ["afk"]
    
    for part in layout:
        if part == "time" and current_time_text:
            time_emoji = SETTINGS.get("time_emoji", "⏰")
            icon = f"{time_emoji} " if show_icons and time_emoji else ""
            lines.append(f"{icon}{current_time_text}")
        elif part == "custom" and current_custom_text:
            processed_text = replace_variables(current_custom_text)
            lines.append(processed_text)
        elif part == "song" and song_line:
            lines.append(song_line)
        
            if SETTINGS.get("music_progress", True):
                style = SETTINGS.get("progress_style", "bar")
                progress_percent = 0
                dur = int(sstate.get("song_dur", 0))
                pos = int(sstate.get("song_pos", 0))
                if dur > 0:
                    progress_percent = int((pos / dur) * 100)
                progress_str = ""
                if style == "bar":
                    filled = int(progress_percent / 10)
                    empty = 10 - filled
                    progress_str = "█" * filled + "░" * empty
                elif style == "dots":
                    filled = int(progress_percent / 10)
                    empty = 10 - filled
                    progress_str = "●" * filled + "○" * empty
                elif style == "percentage":
                    progress_str = f"{progress_percent}%"
                if progress_str:
                    lines.append(progress_str)
        elif part == "window" and window_line:
            lines.append(window_line)
        elif part == "heartrate" and heartrate_line:
            lines.append(heartrate_line)
        elif part == "weather" and weather_line:
            lines.append(weather_line)
        elif part == "system_stats" and system_stats_line:
            lines.append(system_stats_line)
        elif part == "afk" and afk_line:
            lines.append(afk_line)

    result = "\n".join(lines).strip()
    
    text_effect = SETTINGS.get("text_effect", "none")
    if text_effect and text_effect != "none":
        try:
            result = text_effects.apply_effect(result, text_effect)
        except Exception as e:
            log_error(f"Failed to apply text effect '{text_effect}'", e)
    
    frame_style = SETTINGS.get("chatbox_frame", "none")
    if frame_style and frame_style != "none":
        try:
            result = chatbox_frames.apply_frame(result, frame_style)
        except Exception as e:
            log_error(f"Failed to apply frame style '{frame_style}'", e)
    
    result = smart_truncate_message(result)
    
    return result

VRCHAT_CHAR_LIMIT = 144
SLIM_SUFFIX_LENGTH = 2

def smart_truncate_message(message):
    """
    Smart truncation to fit VRChat's ~144 character limit.
    Preserves room for slim chatbox suffix if enabled.
    Prioritizes keeping first lines (usually time/important info).
    """
    if not message:
        return message
    
    max_len = VRCHAT_CHAR_LIMIT
    if SETTINGS.get("slim_chatbox", False):
        max_len = VRCHAT_CHAR_LIMIT - SLIM_SUFFIX_LENGTH
    
    if len(message) <= max_len:
        return message
    
    lines = message.split('\n')
    
    if len(lines) == 1:
        return message[:max_len-3] + "..."
    
    result_lines = []
    current_length = 0
    
    for i, line in enumerate(lines):
        line_with_newline = line if i == 0 else '\n' + line
        new_length = current_length + len(line_with_newline)
        
        if new_length <= max_len:
            result_lines.append(line)
            current_length = new_length
        else:
            remaining = max_len - current_length
            if i == 0:
                result_lines.append(line[:max_len-3] + "...")
            elif remaining > 10:
                truncated = line[:remaining - 4] + "..."
                result_lines.append(truncated)
            break
    
    if not result_lines:
        return message[:max_len-3] + "..."
    
    return '\n'.join(result_lines)

SLIM_CHATBOX_SUFFIX = "\x03\x1f"

def send_to_vrchat(message):
    global last_message_sent, connection_status, last_successful_send, last_osc_send_time
    
    current_time = time.time()
    if current_time - last_osc_send_time < 0.5:
        return False
    
    last_osc_send_time = current_time
    
    if message:
        try:
            if SETTINGS.get("slim_chatbox", False):
                if len(message) + SLIM_SUFFIX_LENGTH <= VRCHAT_CHAR_LIMIT:
                    message = message + SLIM_CHATBOX_SUFFIX
                else:
                    message = message[:VRCHAT_CHAR_LIMIT - SLIM_SUFFIX_LENGTH] + SLIM_CHATBOX_SUFFIX
            elif len(message) > VRCHAT_CHAR_LIMIT:
                message = message[:VRCHAT_CHAR_LIMIT]
            client.send_message("/chatbox/input", [message, True])
            last_message_sent = message
            connection_status = "connected"
            last_successful_send = datetime.now()
            print(f"[VRChat OSC SENT]\n{message}\n------------------")
            return True
        except Exception as e:
            connection_status = "disconnected"
            log_error("Failed to send OSC message", e)
            print("[VRChat OSC ERROR]", e)
            return False
    return False

def test_osc_connection():
    """Test OSC connection by sending a ping message"""
    global connection_status
    try:
        client.send_message("/chatbox/visible", 1)
        time.sleep(0.1)
        client.send_message("/chatbox/input", ["🔔 Connection Test", True])
        connection_status = "connected"
        return True
    except Exception as e:
        connection_status = "disconnected"
        log_error("OSC connection test failed", e)
        return False

def format_typed_message(text):
    """Format a typed message with effects, frame, and slim chatbox suffix"""
    if not text:
        return text
    
    result = text
    
    effect = SETTINGS.get("text_effect", "none")
    if effect != "none":
        result = text_effects.apply_effect(result, effect)
    
    frame_style = SETTINGS.get("chatbox_frame", "none")
    if frame_style != "none":
        result = chatbox_frames.apply_frame(result, frame_style)
    
    if SETTINGS.get("slim_chatbox", False):
        result = result + "\x03\x1f"
    
    return result


def start_vrc_updater():
    def updater():
        global current_time_text, current_custom_text, last_message_sent
        global text_cycle_index, next_custom_in, per_message_timers, client
        global typing_state
        print("[VRChat Updater] Thread started")
        print(f"[VRChat Updater] Initial CUSTOM_TEXTS count: {len(CUSTOM_TEXTS)}")
        print(f"[VRChat Updater] Initial show_custom: {show_custom}")

        osc_interval = max(1, int(SETTINGS.get("osc_send_interval", 3)))
        next_osc_send = osc_interval
        
        per_message_intervals = SETTINGS.get("per_message_intervals", {})
        for idx in range(len(CUSTOM_TEXTS)):
            key = str(idx)
            if key not in per_message_timers:
                per_message_timers[key] = per_message_intervals.get(key, osc_interval)

        last_quest_ip = SETTINGS.get("quest_ip", "")
        rotation_log_counter = 0
        last_typing_indicator = False

        while True:
            try:
                time.sleep(1)
                
                current_quest_ip = SETTINGS.get("quest_ip", "")
                if current_quest_ip != last_quest_ip:
                    print(f"[Auto-Reconnect] Quest or Desktop IP changed from {last_quest_ip} to {current_quest_ip}")
                    client = make_client()
                    last_quest_ip = current_quest_ip
                
                with typing_state_lock:
                    is_typing = typing_state["is_typing"]
                    typed_message = typing_state["typed_message"]
                    display_until = typing_state["display_until"]
                    show_indicator = typing_state["show_indicator"]
                
                current_time_val = time.time()
                
                with typing_state_lock:
                    message_sent_flag = typing_state.get("message_sent", False)
                
                if is_typing:
                    if show_indicator and not last_typing_indicator:
                        try:
                            client.send_message("/chatbox/typing", True)
                            last_typing_indicator = True
                            print("[VRChat] Typing indicator ON")
                        except Exception as e:
                            print(f"[VRChat] Failed to send typing indicator: {e}")
                    continue
                
                if typed_message and current_time_val < display_until:
                    if not message_sent_flag:
                        formatted_msg = format_typed_message(typed_message)
                        if chatbox_visible:
                            send_to_vrchat(formatted_msg)
                            print(f"[VRChat] Sent typed message: '{typed_message[:30]}...'")
                        
                        with typing_state_lock:
                            typing_state["message_sent"] = True
                        
                        if last_typing_indicator:
                            try:
                                client.send_message("/chatbox/typing", False)
                                last_typing_indicator = False
                                print("[VRChat] Typing indicator OFF")
                            except:
                                pass
                    continue
                
                if typed_message and current_time_val >= display_until:
                    with typing_state_lock:
                        typing_state["typed_message"] = ""
                        typing_state["display_until"] = 0
                        typing_state["message_sent"] = False
                    print("[VRChat] Typed message display ended, resuming rotation")
                
                if last_typing_indicator:
                    try:
                        client.send_message("/chatbox/typing", False)
                        last_typing_indicator = False
                    except:
                        pass
                
                next_osc_send -= 1
                next_custom_in = next_osc_send

                if next_osc_send <= 0:
                    if CUSTOM_TEXTS:
                        current_idx = str(text_cycle_index)
                        per_msg_interval = SETTINGS.get("per_message_intervals", {}).get(current_idx, osc_interval)
                        
                        current_custom_text = get_next_custom_message()
                        update_message_queue()
                        
                        rotation_log_counter += 1
                        if rotation_log_counter <= 5 or rotation_log_counter % 10 == 0:
                            print(f"[VRChat Updater] Message rotated to index {text_cycle_index}: '{current_custom_text[:30]}...' (show_custom={show_custom})")
                        
                        next_idx = str(text_cycle_index)
                        next_osc_send = SETTINGS.get("per_message_intervals", {}).get(next_idx, osc_interval)
                        
                        if not show_custom:
                            current_custom_text = ""
                    else:
                        current_custom_text = ""
                        osc_interval = max(1, int(SETTINGS.get("osc_send_interval", 3)))
                        next_osc_send = osc_interval

                    preview_msg = get_current_preview()

                    if chatbox_visible and not auto_send_paused and preview_msg:
                        send_to_vrchat(preview_msg)
                    elif chatbox_visible:
                        try:
                            client.send_message("/chatbox/visible", 1)
                        except:
                            pass
                    else:
                        try:
                            client.send_message("/chatbox/visible", 0)
                        except:
                            pass

            except Exception as e:
                log_error("VRC Updater error", e)
                print("[VRC Updater ERROR]", e)
                time.sleep(1)

    threading.Thread(target=updater, daemon=True).start()

def create_app():
    # Handle PyInstaller's temporary directory
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        base_path = sys._MEIPASS
        template_folder = os.path.join(base_path, 'templates')
        static_folder = os.path.join(base_path, 'static')
    else:
        # Running as normal Python script
        template_folder = "templates"
        static_folder = "static"
    
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
    vrchat_service.init()
    _start_vrcx_plus_worker()

    spotify.start_spotify_tracker(interval=1)
    window_tracker.start_window_tracker(interval=SETTINGS.get("window_tracking_interval", 2))
    heart_rate_monitor.start_heart_rate_tracker(interval=SETTINGS.get("heart_rate_update_interval", 5))
    weather_service.start_weather_tracker(
        interval=SETTINGS.get("weather_update_interval", 600),
        location=SETTINGS.get("weather_location", "auto"),
        enabled=SETTINGS.get("weather_enabled", False)
    )
    
    if SETTINGS.get("system_stats_enabled", False):
        system_stats.start_system_stats()
    
    if SETTINGS.get("afk_enabled", False):
        afk_detector.set_afk_enabled(True)
    
    start_vrc_updater()

    @app.route("/")
    def index():
        COMMON_TIMEZONES = [
            "UTC", "US/Eastern", "US/Central", "US/Mountain", "US/Pacific",
            "Europe/London", "Europe/Paris", "Asia/Tokyo", "Asia/Shanghai",
            "Australia/Sydney"
        ]
        
        redirect_uri = f"{request.host_url}spotify-callback"
        
        return render_template(
            "dashboard.html",
            quest_ip=SETTINGS.get("quest_ip",""),
            quest_port=SETTINGS.get("quest_port",9000),
            spotify_client_id=SETTINGS.get("spotify_client_id",""),
            spotify_client_secret=SETTINGS.get("spotify_client_secret",""),
            spotify_redirect_uri=redirect_uri,
            spotify_needs_restart=SETTINGS.get("spotify_needs_restart", False),
            customs_text="\n".join(SETTINGS.get("custom_texts", [])),
            osc_send_interval=SETTINGS.get("osc_send_interval", 3),
            dashboard_update_interval=SETTINGS.get("dashboard_update_interval", 1),
            music_progress=SETTINGS.get("music_progress", True),
            progress_style=SETTINGS.get("progress_style", "bar"),
            timezone=SETTINGS.get("timezone", "local"),
            timezones=COMMON_TIMEZONES,
            layout_order=SETTINGS.get("layout_order", ["time","custom","song","window","heartrate","weather","system_stats","afk"]),
            per_message_intervals=SETTINGS.get("per_message_intervals", {}),
            theme=SETTINGS.get("theme", "dark"),
            random_order=SETTINGS.get("random_order", False),
            weighted_messages=SETTINGS.get("weighted_messages", {}),
            show_module_icons=SETTINGS.get("show_module_icons", True),
            streamer_mode=SETTINGS.get("streamer_mode", False),
            compact_mode=SETTINGS.get("compact_mode", False),
            window_tracking_enabled=SETTINGS.get("window_tracking_enabled", False),
            window_tracking_interval=SETTINGS.get("window_tracking_interval", 2),
            window_tracking_mode=SETTINGS.get("window_tracking_mode", "both"),
            heart_rate_enabled=SETTINGS.get("heart_rate_enabled", False),
            heart_rate_source=SETTINGS.get("heart_rate_source", "pulsoid"),
            heart_rate_pulsoid_token=SETTINGS.get("heart_rate_pulsoid_token", ""),
            heart_rate_hyperate_id=SETTINGS.get("heart_rate_hyperate_id", ""),
            heart_rate_custom_api=SETTINGS.get("heart_rate_custom_api", ""),
            heart_rate_update_interval=SETTINGS.get("heart_rate_update_interval", 5),
            time_emoji=SETTINGS.get("time_emoji", "⏰"),
            song_emoji=SETTINGS.get("song_emoji", "🎶"),
            window_emoji=SETTINGS.get("window_emoji", "💻"),
            heartrate_emoji=SETTINGS.get("heartrate_emoji", "❤️"),
            custom_background=SETTINGS.get("custom_background", ""),
            custom_button_color=SETTINGS.get("custom_button_color", ""),
            slim_chatbox=SETTINGS.get("slim_chatbox", False),
            window_prefix=SETTINGS.get("window_prefix", ""),
            weather_location=SETTINGS.get("weather_location", "auto"),
            weather_temp_unit=SETTINGS.get("weather_temp_unit", "F"),
            typed_message_duration=SETTINGS.get("typed_message_duration", 5),
            typing_indicator_enabled=SETTINGS.get("typing_indicator_enabled", True),
            system_stats_enabled=SETTINGS.get("system_stats_enabled", False),
            show_cpu=SETTINGS.get("show_cpu", True),
            show_ram=SETTINGS.get("show_ram", True),
            show_gpu=SETTINGS.get("show_gpu", False),
            show_network=SETTINGS.get("show_network", False),
            afk_enabled=SETTINGS.get("afk_enabled", False),
            afk_timeout=SETTINGS.get("afk_timeout", 300),
            afk_message=SETTINGS.get("afk_message", ""),
            afk_show_duration=SETTINGS.get("afk_show_duration", True),
            hr_show_trend=SETTINGS.get("hr_show_trend", True),
            hr_show_stats=SETTINGS.get("hr_show_stats", False),
            osc_router_listen_ip=SETTINGS.get("osc_router_listen_ip", "127.0.0.1"),
            osc_router_listen_port=SETTINGS.get("osc_router_listen_port", 9010),
            fbt_settings=_get_fbt_settings(),
            quick_phrases=quick_phrases.get_phrases()
        )

    @app.route("/status")
    def status():
        global current_time_text, current_custom_text, last_message_sent
        global show_time, show_custom, show_music, show_window, show_heartrate, auto_send_paused
        global connection_status, last_successful_send, message_queue

        time_text = current_time_text if show_time else "OFF"
        custom_text = current_custom_text if show_custom else "OFF"
        
        wstate = window_tracker.get_window_state()
        window_text = wstate.get("app_name", "No window detected") if show_window else "OFF"
        
        hrstate = heart_rate_monitor.get_heart_rate_state()
        heartrate_text = "Not connected"
        hr_trend = ""
        if show_heartrate:
            if hrstate.get("is_connected") and hrstate.get("bpm", 0) > 0:
                bpm = hrstate['bpm']
                hr_stats = heart_rate_monitor.get_hr_stats()
                trend = hr_stats.get("trend", "stable")
                if trend == "rising":
                    hr_trend = " 📈"
                elif trend == "falling":
                    hr_trend = " 📉"
                heartrate_text = f"{bpm} BPM{hr_trend}"
            elif heart_rate_monitor.is_simulator_enabled():
                heartrate_text = "Simulator running..."
            else:
                heartrate_text = "Waiting for data..."

        sstate = spotify.get_spotify_state()
        song_text = "No song playing"
        progress_percent = 0
        album_art = ""

        if show_music and sstate.get("song_text"):
            try:
                pos = int(sstate.get("song_pos", 0))
                dur = int(sstate.get("song_dur", 0))
                elapsed_min, elapsed_sec = divmod(pos, 60)
                total_min, total_sec = divmod(dur, 60)
                song_text = f"{sstate['song_text']} [{elapsed_min}:{elapsed_sec:02d} / {total_min}:{total_sec:02d}]"
                if dur > 0:
                    progress_percent = int((pos / dur) * 100)
                album_art = sstate.get("album_art", "")
            except Exception:
                song_text = sstate.get("song_text", "No song playing")
                progress_percent = 0

        progress_str = ""
        if SETTINGS.get("music_progress", True) and show_music and sstate.get("song_text"):
            style = SETTINGS.get("progress_style", "bar")
            if style == "bar":
                filled = int(progress_percent / 10)
                empty = 10 - filled
                progress_str = "█" * filled + "░" * empty
            elif style == "dots":
                filled = int(progress_percent / 10)
                empty = 10 - filled
                progress_str = "●" * filled + "○" * empty
            elif style == "percentage":
                progress_str = f"{progress_percent}%"

        preview_msg = get_current_preview()

        weather_text = "OFF"
        try:
            weath_state = weather_service.get_weather_state()
            if show_weather:
                if weath_state.get("temperature"):
                    weather_text = f"{weath_state.get('temperature')} - {weath_state.get('condition', 'N/A')}"
                else:
                    weather_text = "Loading..."
        except Exception as e:
            log_error("Failed to get weather state", e)
            weather_text = "Error"
        
        last_send_str = "Never"
        try:
            if last_successful_send:
                if isinstance(last_successful_send, datetime):
                    last_send_str = last_successful_send.strftime("%I:%M:%S %p")
                else:
                    last_send_str = str(last_successful_send)
        except Exception as e:
            log_error("Failed to format last_successful_send", e)
            last_send_str = "Error"
        
        return jsonify({
            "chatbox": chatbox_visible,
            "auto_send_paused": auto_send_paused,
            "time": time_text,
            "time_on": show_time,
            "custom": custom_text,
            "custom_on": show_custom,
            "song": song_text,
            "music_on": show_music,
            "music_progress": SETTINGS.get("music_progress", True),
            "progress_style": SETTINGS.get("progress_style", "bar"),
            "progress_percent": progress_percent,
            "progress_string": progress_str,
            "last_message": last_message_sent,
            "preview": preview_msg,
            "album_art": album_art,
            "next_custom": next_custom_in,
            "connection_status": connection_status,
            "last_successful_send": last_send_str,
            "message_queue": message_queue,
            "theme": SETTINGS.get("theme", "dark"),
            "streamer_mode": SETTINGS.get("streamer_mode", False),
            "compact_mode": SETTINGS.get("compact_mode", False),
            "custom_texts": SETTINGS.get("custom_texts", []),
            "per_message_intervals": SETTINGS.get("per_message_intervals", {}),
            "weighted_messages": SETTINGS.get("weighted_messages", {}),
            "random_order": SETTINGS.get("random_order", False),
            "show_module_icons": SETTINGS.get("show_module_icons", True),
            "window": window_text,
            "window_on": show_window,
            "window_tracking_enabled": SETTINGS.get("window_tracking_enabled", False),
            "heartrate": heartrate_text,
            "heartrate_on": show_heartrate,
            "heart_rate_enabled": SETTINGS.get("heart_rate_enabled", False),
            "weather": weather_text,
            "weather_on": show_weather,
            "weather_enabled": SETTINGS.get("weather_enabled", False),
            "text_effect": SETTINGS.get("text_effect", "none"),
            "slim_chatbox": SETTINGS.get("slim_chatbox", False),
            "system_stats_enabled": SETTINGS.get("system_stats_enabled", False),
            "system_stats": system_stats.get_system_stats() if SETTINGS.get("system_stats_enabled", False) else {},
            "afk_enabled": SETTINGS.get("afk_enabled", False),
            "is_afk": (afk_detector.check_afk(SETTINGS.get("afk_timeout", 300)) or afk_detector.is_afk()) if SETTINGS.get("afk_enabled", False) else False,
            "afk_message": afk_detector.get_afk_message(SETTINGS.get("afk_message", ""), SETTINGS.get("afk_show_duration", True)) if SETTINGS.get("afk_enabled", False) else "",
            "afk_countdown": afk_detector.get_time_until_afk(SETTINGS.get("afk_timeout", 300)) if SETTINGS.get("afk_enabled", False) else -1,
            "afk_countdown_formatted": afk_detector.format_countdown(afk_detector.get_time_until_afk(SETTINGS.get("afk_timeout", 300))) if SETTINGS.get("afk_enabled", False) else "",
            "hr_stats": heart_rate_monitor.get_hr_stats() if show_heartrate else {},
            "hr_simulator_enabled": heart_rate_monitor.is_simulator_enabled(),
            "hr_trend": hr_trend,
            "fbt": _tracker_status(),
            "fbt_settings": _get_fbt_settings(),
            "osc_router": _osc_router_status(),
        })

    @app.route("/vrcx-plus/state", methods=["GET"])
    def vrcx_plus_state():
        data = _load_vrcx_plus_data()
        items = data.get("items", [])
        favorites = data.get("favorites", {})
        vrchat_status = vrchat_service.status()
        stats = {
            "total_items": len(items),
            "avatars": sum(1 for item in items if item.get("type") == "avatar"),
            "worlds": sum(1 for item in items if item.get("type") == "world"),
            "friends": sum(1 for item in items if item.get("type") == "friend"),
            "groups": sum(1 for item in items if item.get("type") == "group"),
            "favorite_avatars": len(favorites.get("avatar", [])),
            "favorite_worlds": len(favorites.get("world", [])),
            "favorite_friends": len(favorites.get("friend", [])),
            "friend_logs": len(data.get("friend_logs", []))
        }
        provider = _vrcx_plus_provider_settings()
        auto_snapshot = {
            "enabled": bool(SETTINGS.get("vrcx_plus_auto_snapshot_enabled", False)),
            "minutes": int(SETTINGS.get("vrcx_plus_auto_snapshot_minutes", 10)),
            "include_offline": bool(SETTINGS.get("vrcx_plus_auto_snapshot_include_offline", False))
        }
        return jsonify(
            {
                "ok": True,
                "data": data,
                "stats": stats,
                "vrchat": vrchat_status,
                "provider": provider,
                "auto_snapshot": auto_snapshot
            }
        )

    @app.route("/vrcx-plus/search", methods=["POST"])
    def vrcx_plus_search():
        body = request.get_json() or {}
        query = str(body.get("query", "")).strip().lower()
        type_filter = str(body.get("type", "all")).strip().lower()
        status_filter = str(body.get("status", "all")).strip().lower()
        author_filter = str(body.get("author", "")).strip().lower()
        favorites_only = bool(body.get("favorites_only", False))
        sort_by = str(body.get("sort", "updated")).strip().lower()

        valid_types = {"all", "avatar", "world", "friend", "group"}
        if type_filter not in valid_types:
            type_filter = "all"

        data = _load_vrcx_plus_data()
        favorites = data.get("favorites", {})
        favorite_lookup = {k: set(v) for k, v in favorites.items()}
        results = []

        for item in data.get("items", []):
            item_type = str(item.get("type", "")).lower()
            if type_filter != "all" and item_type != type_filter:
                continue
            if status_filter != "all" and item_type == "avatar":
                item_status = str(item.get("status", "public")).lower()
                if item_status != status_filter:
                    continue
            if favorites_only and item.get("id") not in favorite_lookup.get(item_type, set()):
                continue

            haystack = " ".join(
                [
                    str(item.get("name", "")),
                    str(item.get("description", "")),
                    str(item.get("author", "")),
                    str(item.get("status", ""))
                ]
            ).lower()
            if query and query not in haystack:
                continue
            if author_filter and author_filter not in str(item.get("author", "")).lower():
                continue
            results.append(item)

        reverse = True
        if sort_by == "name":
            results.sort(key=lambda x: str(x.get("name", "")).lower())
        elif sort_by == "created":
            results.sort(key=lambda x: str(x.get("created_at", "")), reverse=reverse)
        else:
            results.sort(key=lambda x: str(x.get("updated_at", "")), reverse=reverse)

        return jsonify({"ok": True, "results": results[:500], "count": len(results)})

    @app.route("/vrcx-plus/item", methods=["POST"])
    def vrcx_plus_add_item():
        body = request.get_json() or {}
        item_type = str(body.get("type", "")).strip().lower()
        name = str(body.get("name", "")).strip()
        description = str(body.get("description", "")).strip()
        author = str(body.get("author", "")).strip()
        status = str(body.get("status", "public")).strip().lower()
        external_id = str(body.get("external_id", "")).strip()

        valid_types = {"avatar", "world", "friend", "group"}
        if item_type not in valid_types:
            return jsonify({"ok": False, "error": "Invalid type"}), 400
        if not name:
            return jsonify({"ok": False, "error": "Name is required"}), 400

        if item_type != "avatar":
            status = "public"
        elif status not in {"public", "private"}:
            status = "public"

        now_iso = _vrcx_plus_now_iso()
        item = {
            "id": _vrcx_plus_make_id(item_type),
            "type": item_type,
            "name": name,
            "author": author,
            "status": status,
            "description": description,
            "external_id": external_id,
            "created_at": now_iso,
            "updated_at": now_iso
        }
        data = _load_vrcx_plus_data()
        data["items"].insert(0, item)
        _vrcx_plus_append_event(data, "feed", f"Added {item_type}", name)
        _save_vrcx_plus_data(data)
        return jsonify({"ok": True, "item": item})

    @app.route("/vrcx-plus/item/delete", methods=["POST"])
    def vrcx_plus_delete_item():
        body = request.get_json() or {}
        item_id = str(body.get("id", "")).strip()
        if not item_id:
            return jsonify({"ok": False, "error": "Item id required"}), 400

        data = _load_vrcx_plus_data()
        items = data.get("items", [])
        keep = []
        removed = None
        for item in items:
            if str(item.get("id")) == item_id:
                removed = item
                continue
            keep.append(item)
        if not removed:
            return jsonify({"ok": False, "error": "Item not found"}), 404

        data["items"] = keep
        for fav_type in ("avatar", "world", "friend", "group"):
            data["favorites"][fav_type] = [
                fav_id for fav_id in data["favorites"].get(fav_type, []) if fav_id != item_id
            ]
        _vrcx_plus_append_event(data, "moderation", "Removed item", removed.get("name", item_id))
        _save_vrcx_plus_data(data)
        return jsonify({"ok": True})

    @app.route("/vrcx-plus/favorite/toggle", methods=["POST"])
    def vrcx_plus_toggle_favorite():
        body = request.get_json() or {}
        item_id = str(body.get("id", "")).strip()
        item_type = str(body.get("type", "")).strip().lower()
        if item_type not in {"avatar", "world", "friend", "group"}:
            return jsonify({"ok": False, "error": "Invalid type"}), 400
        if not item_id:
            return jsonify({"ok": False, "error": "Item id required"}), 400

        data = _load_vrcx_plus_data()
        fav_list = data["favorites"].setdefault(item_type, [])
        is_favorite = item_id in fav_list
        if is_favorite:
            data["favorites"][item_type] = [x for x in fav_list if x != item_id]
        else:
            fav_list.insert(0, item_id)
            data["favorites"][item_type] = fav_list

        item_name = item_id
        for item in data.get("items", []):
            if item.get("id") == item_id:
                item_name = item.get("name", item_id)
                break
        _vrcx_plus_append_event(
            data,
            "favorite",
            "Favorited" if not is_favorite else "Unfavorited",
            item_name
        )
        _save_vrcx_plus_data(data)
        return jsonify({"ok": True, "is_favorite": not is_favorite})

    @app.route("/vrcx-plus/note", methods=["POST"])
    def vrcx_plus_add_note():
        body = request.get_json() or {}
        text = str(body.get("text", "")).strip()
        if not text:
            return jsonify({"ok": False, "error": "Note text required"}), 400

        data = _load_vrcx_plus_data()
        note = {
            "id": _vrcx_plus_make_id("note"),
            "text": text[:500],
            "created_at": _vrcx_plus_now_iso()
        }
        data["notes"].insert(0, note)
        data["notes"] = data["notes"][:200]
        _vrcx_plus_append_event(data, "note", "Added note", text[:120])
        _save_vrcx_plus_data(data)
        return jsonify({"ok": True, "note": note})

    @app.route("/vrcx-plus/event", methods=["POST"])
    def vrcx_plus_add_event():
        body = request.get_json() or {}
        kind = str(body.get("kind", "notification")).strip().lower()
        title = str(body.get("title", "")).strip()
        detail = str(body.get("detail", "")).strip()
        if not title:
            return jsonify({"ok": False, "error": "Event title required"}), 400
        if kind not in {"notification", "feed", "moderation", "group", "system"}:
            kind = "notification"

        data = _load_vrcx_plus_data()
        _vrcx_plus_append_event(data, kind, title[:120], detail[:240])
        _save_vrcx_plus_data(data)
        return jsonify({"ok": True})

    @app.route("/vrcx-plus/vrchat/status", methods=["GET"])
    def vrcx_plus_vrchat_status():
        return jsonify(vrchat_service.status())

    @app.route("/vrcx-plus/vrchat/login", methods=["POST"])
    def vrcx_plus_vrchat_login():
        body = request.get_json() or {}
        username = str(body.get("username", "")).strip()
        password = str(body.get("password", "")).strip()
        if not username or not password:
            return jsonify({"ok": False, "error": "Username and password required"}), 400
        payload = vrchat_service.login(username, password)
        if not payload.get("ok"):
            return jsonify(payload), 400
        return jsonify(payload)

    @app.route("/vrcx-plus/vrchat/2fa", methods=["POST"])
    def vrcx_plus_vrchat_2fa():
        body = request.get_json() or {}
        code = str(body.get("code", "")).strip()
        method = str(body.get("method", "totp")).strip()
        if not code:
            return jsonify({"ok": False, "error": "2FA code required"}), 400
        payload = vrchat_service.verify_2fa(code, method)
        if not payload.get("ok"):
            return jsonify(payload), 400
        return jsonify(payload)

    @app.route("/vrcx-plus/vrchat/email-otp", methods=["POST"])
    def vrcx_plus_vrchat_email_otp():
        payload = vrchat_service.request_email_otp()
        if not payload.get("ok"):
            return jsonify(payload), 400
        return jsonify(payload)

    @app.route("/vrcx-plus/vrchat/logout", methods=["POST"])
    def vrcx_plus_vrchat_logout():
        return jsonify(vrchat_service.logout())

    @app.route("/vrcx-plus/vrchat/avatar-search", methods=["POST"])
    def vrcx_plus_vrchat_avatar_search():
        body = request.get_json() or {}
        query = str(body.get("query", "")).strip()
        n = int(body.get("n", 40))
        offset = int(body.get("offset", 0))
        if len(query) < 2:
            return jsonify({"ok": False, "error": "Query must be at least 2 chars", "results": []}), 400
        source = str(body.get("source", "auto")).strip().lower()
        provider = _vrcx_plus_provider_settings()
        provider_enabled = bool(provider.get("enabled"))
        provider_urls = list(provider.get("urls") or [])
        body_provider_urls = _vrcx_plus_normalize_provider_urls(
            body.get("urls", []),
            legacy_url=str(body.get("provider_url", "")).strip()
        )
        if body_provider_urls:
            provider_urls = body_provider_urls
        use_provider = source in {"provider", "external", "providers"} or (
            source == "auto" and provider_enabled and bool(provider_urls)
        )

        if use_provider:
            payload = vrchat_service.external_avatar_search_many(provider_urls, query, n=n)
            payload["source"] = "provider"
        else:
            payload = vrchat_service.avatar_search(query, n=n, offset=offset)
            payload["source"] = "vrchat"
        if not payload.get("ok"):
            return jsonify(payload), 400
        return jsonify(payload)

    @app.route("/vrcx-plus/vrchat/avatar-info", methods=["POST"])
    def vrcx_plus_vrchat_avatar_info():
        body = request.get_json() or {}
        avatar_id = str(body.get("avatar_id", "")).strip()
        if not avatar_id:
            return jsonify({"ok": False, "error": "avatar_id is required"}), 400
        payload = vrchat_service.get_avatar(avatar_id)
        if not payload.get("ok"):
            return jsonify(payload), 400
        return jsonify(payload)

    @app.route("/vrcx-plus/vrchat/provider", methods=["POST"])
    def vrcx_plus_vrchat_provider():
        body = request.get_json() or {}
        enabled = bool(body.get("enabled", False))
        legacy_url = str(body.get("url", "")).strip()
        raw_urls = body.get("urls", [])
        if isinstance(raw_urls, str) and not raw_urls.strip() and legacy_url:
            raw_urls = [legacy_url]
        urls = _vrcx_plus_normalize_provider_urls(raw_urls, legacy_url=legacy_url)
        SETTINGS["vrcx_plus_avatar_provider_enabled"] = enabled
        SETTINGS["vrcx_plus_avatar_provider_urls"] = urls
        SETTINGS["vrcx_plus_avatar_provider_url"] = urls[0] if urls else ""
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        provider = _vrcx_plus_provider_settings()
        return jsonify(
            {
                "ok": True,
                "enabled": provider["enabled"],
                "url": provider["url"],
                "urls": provider["urls"],
                "count": provider["count"]
            }
        )

    @app.route("/vrcx-plus/vrchat/avatar-select", methods=["POST"])
    def vrcx_plus_vrchat_avatar_select():
        body = request.get_json() or {}
        avatar_id = str(body.get("avatar_id", "")).strip()
        if not avatar_id:
            return jsonify({"ok": False, "error": "avatar_id is required"}), 400
        payload = vrchat_service.select_avatar(avatar_id)
        if not payload.get("ok"):
            return jsonify(payload), 400
        return jsonify(payload)

    @app.route("/vrcx-plus/vrchat/auto-snapshot", methods=["POST"])
    def vrcx_plus_auto_snapshot_config():
        body = request.get_json() or {}
        enabled = bool(body.get("enabled", False))
        minutes = int(body.get("minutes", 10))
        include_offline = bool(body.get("include_offline", False))
        minutes = max(1, min(minutes, 180))
        SETTINGS["vrcx_plus_auto_snapshot_enabled"] = enabled
        SETTINGS["vrcx_plus_auto_snapshot_minutes"] = minutes
        SETTINGS["vrcx_plus_auto_snapshot_include_offline"] = include_offline
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return jsonify(
            {
                "ok": True,
                "enabled": SETTINGS["vrcx_plus_auto_snapshot_enabled"],
                "minutes": SETTINGS["vrcx_plus_auto_snapshot_minutes"],
                "include_offline": SETTINGS["vrcx_plus_auto_snapshot_include_offline"]
            }
        )

    @app.route("/vrcx-plus/vrchat/friends-snapshot", methods=["POST"])
    def vrcx_plus_vrchat_friends_snapshot():
        body = request.get_json() or {}
        include_offline = bool(body.get("include_offline", False))
        max_results = int(body.get("max_results", 120))
        result = _capture_vrcx_plus_friend_snapshot(
            include_offline=include_offline,
            max_results=max_results,
            source="manual"
        )
        if not result.get("ok"):
            return jsonify(result), 400
        return jsonify(result)

    @app.route("/vrcx-plus/friend-history/users", methods=["GET"])
    def vrcx_plus_friend_history_users():
        query = str(request.args.get("q", "")).strip().lower()
        recent = str(request.args.get("recent", "all")).strip().lower()
        try:
            limit = int(request.args.get("limit", 300))
        except Exception:
            limit = 300
        limit = max(1, min(limit, 600))
        data = _load_vrcx_plus_data()
        users = {}
        for snapshot in data.get("friend_logs", []):
            created_at = snapshot.get("created_at")
            if not _vrcx_plus_recent_match(created_at, recent):
                continue
            for friend in snapshot.get("friends", []):
                user_id = friend.get("id")
                if not user_id:
                    continue
                display_name = str(friend.get("displayName") or user_id)
                if query:
                    haystack = f"{display_name} {user_id}".lower()
                    if query not in haystack:
                        continue
                record = users.get(user_id) or {
                    "id": user_id,
                    "displayName": display_name,
                    "last_seen": created_at,
                    "snapshots": 0,
                    "last_avatar_id": friend.get("currentAvatarId")
                }
                record["displayName"] = display_name or record["displayName"]
                record["last_seen"] = max(record.get("last_seen") or "", created_at or "")
                record["snapshots"] = int(record.get("snapshots", 0)) + 1
                if created_at == record.get("last_seen"):
                    record["last_avatar_id"] = friend.get("currentAvatarId")
                users[user_id] = record
        ordered = sorted(users.values(), key=lambda x: x.get("last_seen", ""), reverse=True)
        return jsonify({"ok": True, "users": ordered[:limit]})

    @app.route("/vrcx-plus/friend-history", methods=["POST"])
    def vrcx_plus_friend_history():
        body = request.get_json() or {}
        user_id = str(body.get("user_id", "")).strip()
        if not user_id:
            return jsonify({"ok": False, "error": "user_id is required", "history": []}), 400
        data = _load_vrcx_plus_data()
        history = []
        for snapshot in data.get("friend_logs", []):
            created_at = snapshot.get("created_at")
            for friend in snapshot.get("friends", []):
                if str(friend.get("id")) != user_id:
                    continue
                history.append(
                    {
                        "snapshot_id": snapshot.get("id"),
                        "created_at": created_at,
                        "displayName": friend.get("displayName"),
                        "status": friend.get("status"),
                        "statusDescription": friend.get("statusDescription"),
                        "location": friend.get("location"),
                        "currentAvatarId": friend.get("currentAvatarId"),
                        "currentAvatarName": friend.get("currentAvatarName"),
                        "currentAvatarImageUrl": friend.get("currentAvatarImageUrl"),
                        "currentAvatarThumbnailImageUrl": friend.get("currentAvatarThumbnailImageUrl")
                    }
                )
        history.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return jsonify({"ok": True, "history": history})

    @app.route("/vrcx-plus/avatar-history", methods=["GET"])
    def vrcx_plus_avatar_history():
        query = str(request.args.get("q", "")).strip()
        recent = str(request.args.get("recent", "all")).strip().lower()
        user_id = str(request.args.get("user_id", "")).strip()
        try:
            limit = int(request.args.get("limit", 300))
        except Exception:
            limit = 300
        data = _load_vrcx_plus_data()
        avatars = _vrcx_plus_collect_avatar_history(
            data,
            query=query,
            recent=recent,
            user_id=user_id,
            limit=limit
        )
        return jsonify({"ok": True, "avatars": avatars})

    @app.route("/fbt/status", methods=["GET"])
    def fbt_status():
        return jsonify(_tracker_status())

    @app.route("/fbt/settings", methods=["GET"])
    def fbt_settings_get():
        return jsonify({"ok": True, "settings": _get_fbt_settings()})

    @app.route("/fbt/settings", methods=["POST"])
    def fbt_settings_save():
        data = request.get_json(silent=True) or {}
        settings = _save_fbt_settings(data)
        return jsonify({"ok": True, "settings": settings})

    @app.route("/fbt/start", methods=["POST"])
    def fbt_start():
        global tracker_process, tracker_mode, tracker_started_at, tracker_exit_code
        mode = "gui"

        quest_ip = (SETTINGS.get("quest_ip", "") or "").strip()
        quest_port = int(SETTINGS.get("quest_port", 9000))
        if not quest_ip:
            return jsonify({"ok": False, "error": "Set Quest/Desktop IP in Settings first."}), 400
        if not os.path.exists(TRACKER_RUN_SCRIPT):
            return jsonify({"ok": False, "error": f"Tracker launcher not found: {TRACKER_RUN_SCRIPT}"}), 404

        with tracker_lock:
            if _is_running(tracker_process):
                return jsonify({"ok": False, "error": "Tracker is already running.", "status": _tracker_status()}), 409

            tracker_logs.clear()
            tracker_exit_code = None

            cmd = ["bash", TRACKER_RUN_SCRIPT, quest_ip, str(quest_port), "--auto-start"]
            # Always launch integrated tracker GUI from dashboard.

            try:
                tracker_process = subprocess.Popen(
                    cmd,
                    cwd=TRACKER_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    start_new_session=True,
                )
            except Exception as e:
                return jsonify({"ok": False, "error": f"Failed to start tracker: {e}"}), 500

            tracker_mode = mode
            tracker_started_at = time.time()
            _append_log(tracker_logs, f"[tracker] starting in {mode} mode to {quest_ip}:{quest_port}")
            _append_log(tracker_logs, f"[tracker] cmd: {' '.join(cmd)}")

            threading.Thread(
                target=_stream_process_output,
                args=(tracker_process, tracker_logs, "tracker"),
                daemon=True,
            ).start()

        return jsonify({"ok": True, "status": _tracker_status()})

    @app.route("/fbt/stop", methods=["POST"])
    def fbt_stop():
        global tracker_process, tracker_mode, tracker_started_at, tracker_exit_code
        with tracker_lock:
            if not _is_running(tracker_process):
                return jsonify({"ok": True, "status": _tracker_status()})
            _terminate_process_group(tracker_process)
            try:
                tracker_process.wait(timeout=5)
            except Exception:
                _kill_process_group(tracker_process)
                try:
                    tracker_process.wait(timeout=2)
                except Exception:
                    pass
            tracker_exit_code = tracker_process.poll()
            _append_log(tracker_logs, f"[tracker] stopped (exit={tracker_exit_code})")
            tracker_process = None
            tracker_mode = ""
            tracker_started_at = 0.0
        return jsonify({"ok": True, "status": _tracker_status()})

    @app.route("/fbt/recenter", methods=["POST"])
    def fbt_recenter():
        with tracker_lock:
            if not _is_running(tracker_process):
                return jsonify({"ok": False, "error": "Tracker is not running."}), 409
            try:
                # File-based trigger avoids signaling wrapper shells/process groups.
                with open(RECENTER_REQUEST_FILE, "w", encoding="utf-8") as f:
                    f.write(str(time.time()))
                _append_log(tracker_logs, "[tracker] recenter requested from dashboard")
                return jsonify({"ok": True}), 200
            except Exception as e:
                return jsonify({"ok": False, "error": f"Failed to request recenter: {e}"}), 500

    @app.route("/osc-router/status", methods=["GET"])
    def osc_router_status():
        return jsonify(_osc_router_status())

    @app.route("/osc-router/start", methods=["POST"])
    def osc_router_start():
        global osc_router_process, osc_router_started_at, osc_router_exit_code
        data = request.get_json(silent=True) or {}

        target_ip = (SETTINGS.get("quest_ip", "") or "").strip()
        target_port = int(SETTINGS.get("quest_port", 9000))
        listen_ip = (data.get("listen_ip") or SETTINGS.get("osc_router_listen_ip", "127.0.0.1")).strip()
        listen_port = int(data.get("listen_port", SETTINGS.get("osc_router_listen_port", 9010)))

        if not target_ip:
            return jsonify({"ok": False, "error": "Set Quest/Desktop IP in Settings first."}), 400
        if not os.path.exists(OSC_ROUTER_SCRIPT):
            return jsonify({"ok": False, "error": f"OSC router not found: {OSC_ROUTER_SCRIPT}"}), 404

        with osc_router_lock:
            if _is_running(osc_router_process):
                return jsonify({"ok": False, "error": "OSC router is already running.", "status": _osc_router_status()}), 409

            osc_router_logs.clear()
            osc_router_exit_code = None

            SETTINGS["osc_router_listen_ip"] = listen_ip
            SETTINGS["osc_router_listen_port"] = listen_port
            with open(SETTINGS_FILE, "wb") as f:
                f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))

            cmd = [
                sys.executable,
                OSC_ROUTER_SCRIPT,
                "--listen-ip",
                listen_ip,
                "--listen-port",
                str(listen_port),
                "--target-ip",
                target_ip,
                "--target-port",
                str(target_port),
            ]
            try:
                osc_router_process = subprocess.Popen(
                    cmd,
                    cwd=TRACKER_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    start_new_session=True,
                )
            except Exception as e:
                return jsonify({"ok": False, "error": f"Failed to start OSC router: {e}"}), 500

            osc_router_started_at = time.time()
            _append_log(
                osc_router_logs,
                f"[osc-router] listening on {listen_ip}:{listen_port} -> {target_ip}:{target_port}",
            )
            threading.Thread(
                target=_stream_process_output,
                args=(osc_router_process, osc_router_logs, "osc-router"),
                daemon=True,
            ).start()

        return jsonify({"ok": True, "status": _osc_router_status()})

    @app.route("/osc-router/stop", methods=["POST"])
    def osc_router_stop():
        global osc_router_process, osc_router_started_at, osc_router_exit_code
        with osc_router_lock:
            if not _is_running(osc_router_process):
                return jsonify({"ok": True, "status": _osc_router_status()})
            _terminate_process_group(osc_router_process)
            try:
                osc_router_process.wait(timeout=5)
            except Exception:
                _kill_process_group(osc_router_process)
                try:
                    osc_router_process.wait(timeout=2)
                except Exception:
                    pass
            osc_router_exit_code = osc_router_process.poll()
            _append_log(osc_router_logs, f"[osc-router] stopped (exit={osc_router_exit_code})")
            osc_router_process = None
            osc_router_started_at = 0.0
        return jsonify({"ok": True, "status": _osc_router_status()})

    @app.route("/send", methods=["POST"])
    def send():
        global last_message_sent
        if request.is_json:
            data = request.get_json(force=True)
            msg = data.get("message", "").strip()
        else:
            msg = request.form.get("message", "").strip()
        if msg:
            if send_to_vrchat(msg):
                return jsonify({"ok": True}), 200
            else:
                return jsonify({"ok": False, "error": "OSC send failed"}), 500
        return jsonify({"ok": False, "error": "empty"}), 400

    @app.route("/send_now", methods=["POST"])
    def send_now():
        preview_msg = get_current_preview()
        if preview_msg and send_to_vrchat(preview_msg):
            return jsonify({"ok": True}), 200
        return jsonify({"ok": False}), 400

    @app.route("/typing_state", methods=["POST"])
    def set_typing_state():
        """Set the typing state - when user is typing a message"""
        global typing_state
        data = request.get_json(force=True) if request.is_json else {}
        is_typing = data.get("typing", False)
        
        with typing_state_lock:
            typing_state["is_typing"] = is_typing
            typing_state["show_indicator"] = SETTINGS.get("typing_indicator_enabled", True)
            if not is_typing:
                typing_state["show_indicator"] = False
        
        print(f"[Typing] State changed: is_typing={is_typing}")
        return jsonify({"ok": True}), 200

    @app.route("/send_typed_message", methods=["POST"])
    def send_typed_message():
        """Send a typed message - pauses rotation and displays the message"""
        global typing_state
        data = request.get_json(force=True) if request.is_json else {}
        message = data.get("message", "").strip()
        
        if not message:
            return jsonify({"ok": False, "error": "empty message"}), 400
        
        display_duration = SETTINGS.get("typed_message_duration", 5)
        
        with typing_state_lock:
            typing_state["is_typing"] = False
            typing_state["typed_message"] = message
            typing_state["display_until"] = time.time() + display_duration
            typing_state["show_indicator"] = False
            typing_state["message_sent"] = False
        
        print(f"[Typing] Message sent: '{message[:30]}...' (display for {display_duration}s)")
        return jsonify({"ok": True}), 200

    @app.route("/cancel_typing", methods=["POST"])
    def cancel_typing():
        """Cancel typing mode without sending a message"""
        global typing_state
        
        with typing_state_lock:
            typing_state["is_typing"] = False
            typing_state["typed_message"] = ""
            typing_state["display_until"] = 0
            typing_state["show_indicator"] = False
            typing_state["message_sent"] = False
        
        print("[Typing] Cancelled")
        return jsonify({"ok": True}), 200

    @app.route("/system_stats")
    def get_system_stats():
        stats = system_stats.get_system_stats()
        return jsonify(stats)

    @app.route("/toggle_system_stats", methods=["POST"])
    def toggle_system_stats():
        enabled = SETTINGS.get("system_stats_enabled", False)
        SETTINGS["system_stats_enabled"] = not enabled
        if not enabled:
            system_stats.start_system_stats()
        else:
            system_stats.stop_system_stats()
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return jsonify({"enabled": not enabled})

    @app.route("/afk_status")
    def get_afk_status():
        if SETTINGS.get("afk_enabled", False):
            timeout = SETTINGS.get("afk_timeout", 300)
            afk_detector.check_afk(timeout)
        
        state = afk_detector.get_afk_state()
        return jsonify({
            "is_afk": state["is_afk"],
            "afk_message": afk_detector.get_afk_message(
                SETTINGS.get("afk_message", ""),
                SETTINGS.get("afk_show_duration", True)
            ),
            "duration": afk_detector.get_afk_duration()
        })

    @app.route("/toggle_afk", methods=["POST"])
    def toggle_afk():
        enabled = SETTINGS.get("afk_enabled", False)
        SETTINGS["afk_enabled"] = not enabled
        afk_detector.set_afk_enabled(not enabled)
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return jsonify({"enabled": not enabled})

    @app.route("/afk_activity", methods=["POST"])
    def afk_activity():
        afk_detector.update_activity()
        return jsonify({"ok": True})

    @app.route("/toggle_hr_simulator", methods=["POST"])
    def toggle_hr_simulator():
        """Toggle heart rate simulator for testing without actual HR device"""
        current = heart_rate_monitor.is_simulator_enabled()
        heart_rate_monitor.set_simulator_enabled(not current)
        if not current:
            SETTINGS["heart_rate_enabled"] = True
        return jsonify({"enabled": not current})

    @app.route("/quick_phrases")
    def get_quick_phrases():
        return jsonify(quick_phrases.get_phrases())

    @app.route("/send_quick_phrase", methods=["POST"])
    def send_quick_phrase():
        global typing_state
        data = request.get_json(force=True) if request.is_json else {}
        phrase = data.get("phrase", "").strip()
        
        if not phrase:
            return jsonify({"ok": False, "error": "empty phrase"}), 400
        
        display_duration = SETTINGS.get("typed_message_duration", 5)
        
        with typing_state_lock:
            typing_state["is_typing"] = False
            typing_state["typed_message"] = phrase
            typing_state["display_until"] = time.time() + display_duration
            typing_state["show_indicator"] = False
            typing_state["message_sent"] = False
        
        message_history.add_typed_message(phrase)
        print(f"[Quick Phrase] Sent: '{phrase[:30]}...'")
        return jsonify({"ok": True})

    @app.route("/add_quick_phrase", methods=["POST"])
    def add_quick_phrase():
        data = request.get_json(force=True) if request.is_json else {}
        text = data.get("text", "").strip()
        emoji = data.get("emoji", "")
        category = data.get("category", "custom")
        
        if not text:
            return jsonify({"ok": False, "error": "empty text"}), 400
        
        quick_phrases.add_phrase(text, emoji, category)
        return jsonify({"ok": True, "phrases": quick_phrases.get_phrases()})

    @app.route("/remove_quick_phrase", methods=["POST"])
    def remove_quick_phrase():
        data = request.get_json(force=True) if request.is_json else {}
        index = data.get("index", -1)
        
        if index < 0:
            return jsonify({"ok": False, "error": "invalid index"}), 400
        
        quick_phrases.remove_phrase(index)
        return jsonify({"ok": True, "phrases": quick_phrases.get_phrases()})

    @app.route("/message_history")
    def get_message_history():
        return jsonify({
            "recent": message_history.get_recent_messages(20),
            "typed": message_history.get_typed_history(10),
            "stats": message_history.get_message_stats()
        })

    @app.route("/hr_stats")
    def get_hr_stats():
        stats = heart_rate_monitor.get_hr_stats()
        state = heart_rate_monitor.get_heart_rate_state()
        return jsonify({
            "current_bpm": state.get("bpm", 0),
            "is_connected": state.get("is_connected", False),
            "session_min": stats.get("session_min", 0),
            "session_max": stats.get("session_max", 0),
            "session_avg": stats.get("session_avg", 0),
            "trend": stats.get("trend", "stable"),
            "samples": stats.get("samples", 0)
        })

    @app.route("/reset_hr_stats", methods=["POST"])
    def reset_hr_stats():
        heart_rate_monitor.reset_hr_stats()
        return jsonify({"ok": True})

    @app.route("/test_connection", methods=["POST"])
    def test_connection():
        if test_osc_connection():
            return jsonify({"ok": True, "status": "connected"}), 200
        return jsonify({"ok": False, "status": "disconnected"}), 500

    @app.route("/ping_quest", methods=["POST"])
    def ping_quest():
        try:
            client.send_message("/chatbox/visible", 1)
            return jsonify({"ok": True}), 200
        except Exception as e:
            log_error("Ping Quest failed", e)
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/toggle_chatbox", methods=["POST"])
    def toggle_chatbox():
        global chatbox_visible
        chatbox_visible = not chatbox_visible
        SETTINGS["chatbox_visible"] = chatbox_visible
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        if chatbox_visible:
            try:
                client.send_message("/chatbox/visible", 1)
            except:
                pass
        else:
            try:
                client.send_message("/chatbox/visible", 0)
            except:
                pass
        return ("", 204)

    @app.route("/toggle_auto_send", methods=["POST"])
    def toggle_auto_send():
        global auto_send_paused
        auto_send_paused = not auto_send_paused
        return ("", 204)

    @app.route("/toggle_time", methods=["POST"])
    def toggle_time():
        global show_time
        show_time = not show_time
        SETTINGS["show_time"] = show_time
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return ("", 204)

    @app.route("/toggle_custom", methods=["POST"])
    def toggle_custom():
        global show_custom
        show_custom = not show_custom
        SETTINGS["show_custom"] = show_custom
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return ("", 204)

    @app.route("/toggle_music", methods=["POST"])
    def toggle_music():
        global show_music
        show_music = not show_music
        SETTINGS["show_music"] = show_music
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return ("", 204)

    @app.route("/toggle_music_progress", methods=["POST"])
    def toggle_music_progress():
        SETTINGS["music_progress"] = not SETTINGS.get("music_progress", True)
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return ("", 204)

    @app.route("/toggle_theme", methods=["POST"])
    def toggle_theme():
        current = SETTINGS.get("theme", "dark")
        SETTINGS["theme"] = "light" if current == "dark" else "dark"
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return jsonify({"theme": SETTINGS["theme"]}), 200

    @app.route("/toggle_random_order", methods=["POST"])
    def toggle_random_order():
        SETTINGS["random_order"] = not SETTINGS.get("random_order", False)
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return ("", 204)

    @app.route("/toggle_module_icons", methods=["POST"])
    def toggle_module_icons():
        SETTINGS["show_module_icons"] = not SETTINGS.get("show_module_icons", True)
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return ("", 204)

    @app.route("/toggle_streamer_mode", methods=["POST"])
    def toggle_streamer_mode():
        SETTINGS["streamer_mode"] = not SETTINGS.get("streamer_mode", False)
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return jsonify({"streamer_mode": SETTINGS["streamer_mode"]}), 200

    @app.route("/toggle_compact_mode", methods=["POST"])
    def toggle_compact_mode():
        SETTINGS["compact_mode"] = not SETTINGS.get("compact_mode", False)
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return jsonify({"compact_mode": SETTINGS["compact_mode"]}), 200

    @app.route("/set_progress_style", methods=["POST"])
    def set_progress_style():
        data = request.get_json(force=True)
        style = data.get("style", "bar")
        if style in ["bar", "dots", "percentage"]:
            SETTINGS["progress_style"] = style
            with open(SETTINGS_FILE, "wb") as f:
                f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return ("", 204)
    
    @app.route("/toggle_window", methods=["POST"])
    def toggle_window():
        global show_window
        show_window = not show_window
        SETTINGS["show_window"] = show_window
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return ("", 204)
    
    @app.route("/toggle_window_tracking", methods=["POST"])
    def toggle_window_tracking():
        global show_window
        SETTINGS["window_tracking_enabled"] = not SETTINGS.get("window_tracking_enabled", False)
        show_window = SETTINGS["window_tracking_enabled"]
        SETTINGS["show_window"] = show_window
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return jsonify({"window_tracking_enabled": SETTINGS["window_tracking_enabled"]}), 200
    
    @app.route("/save_window_tracking_mode", methods=["POST"])
    def save_window_tracking_mode():
        data = request.get_json(force=True)
        mode = data.get("mode", "both")
        if mode in ["app", "browser", "both"]:
            SETTINGS["window_tracking_mode"] = mode
            with open(SETTINGS_FILE, "wb") as f:
                f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return jsonify({"ok": True}), 200
    
    @app.route("/toggle_heartrate", methods=["POST"])
    def toggle_heartrate():
        global show_heartrate
        show_heartrate = not show_heartrate
        SETTINGS["show_heartrate"] = show_heartrate
        if show_heartrate and not SETTINGS.get("heart_rate_enabled", False):
            SETTINGS["heart_rate_enabled"] = True
            heart_rate_monitor.start_heart_rate_tracker(interval=SETTINGS.get("heart_rate_update_interval", 5))
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return ("", 204)
    
    @app.route("/toggle_heart_rate_enabled", methods=["POST"])
    def toggle_heart_rate_enabled():
        global show_heartrate
        SETTINGS["heart_rate_enabled"] = not SETTINGS.get("heart_rate_enabled", False)
        show_heartrate = SETTINGS["heart_rate_enabled"]
        SETTINGS["show_heartrate"] = show_heartrate
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return jsonify({"heart_rate_enabled": SETTINGS["heart_rate_enabled"]}), 200
    
    @app.route("/save_heart_rate_settings", methods=["POST"])
    def save_heart_rate_settings():
        data = request.get_json(force=True)
        SETTINGS["heart_rate_source"] = data.get("source", "pulsoid")
        SETTINGS["heart_rate_pulsoid_token"] = data.get("pulsoid_token", "")
        SETTINGS["heart_rate_hyperate_id"] = data.get("hyperate_id", "")
        SETTINGS["heart_rate_custom_api"] = data.get("custom_api", "")
        SETTINGS["heart_rate_update_interval"] = int(data.get("update_interval", 5))
        if "hr_show_trend" in data:
            SETTINGS["hr_show_trend"] = data.get("hr_show_trend", True)
        if "hr_show_stats" in data:
            SETTINGS["hr_show_stats"] = data.get("hr_show_stats", False)
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return jsonify({"ok": True}), 200
    
    @app.route("/save_emoji_settings", methods=["POST"])
    def save_emoji_settings():
        data = request.get_json(force=True)
        time_emoji = data.get("time_emoji", "⏰")
        song_emoji = data.get("song_emoji", "🎶")
        window_emoji = data.get("window_emoji", "💻")
        heartrate_emoji = data.get("heartrate_emoji", "❤️")
        
        SETTINGS["time_emoji"] = time_emoji[:5] if time_emoji else "⏰"
        SETTINGS["song_emoji"] = song_emoji[:5] if song_emoji else "🎶"
        SETTINGS["window_emoji"] = window_emoji[:5] if window_emoji else "💻"
        SETTINGS["heartrate_emoji"] = heartrate_emoji[:5] if heartrate_emoji else "❤️"
        
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return jsonify({"ok": True}), 200
    
    @app.route("/save_typing_settings", methods=["POST"])
    def save_typing_settings():
        data = request.get_json(force=True)
        duration = int(data.get("typed_message_duration", 5))
        duration = max(2, min(15, duration))
        SETTINGS["typed_message_duration"] = duration
        SETTINGS["typing_indicator_enabled"] = data.get("typing_indicator_enabled", True)
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return jsonify({"ok": True}), 200

    @app.route("/save_window_settings", methods=["POST"])
    def save_window_settings():
        data = request.get_json(force=True)
        SETTINGS["window_prefix"] = data.get("window_prefix", "")[:30]
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return jsonify({"ok": True}), 200

    @app.route("/save_afk_settings", methods=["POST"])
    def save_afk_settings():
        data = request.get_json(force=True)
        timeout = int(data.get("afk_timeout", 300))
        timeout = max(60, min(900, timeout))
        SETTINGS["afk_timeout"] = timeout
        SETTINGS["afk_message"] = data.get("afk_message", "")[:50]
        SETTINGS["afk_show_duration"] = data.get("afk_show_duration", True)
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return jsonify({"ok": True}), 200

    @app.route("/save_system_stats_settings", methods=["POST"])
    def save_system_stats_settings():
        data = request.get_json(force=True)
        SETTINGS["system_stats_show_cpu"] = data.get("show_cpu", True)
        SETTINGS["system_stats_show_ram"] = data.get("show_ram", True)
        SETTINGS["system_stats_show_gpu"] = data.get("show_gpu", False)
        SETTINGS["system_stats_show_network"] = data.get("show_network", False)
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return jsonify({"ok": True}), 200

    @app.route("/save_hr_settings", methods=["POST"])
    def save_hr_settings():
        data = request.get_json(force=True)
        SETTINGS["hr_show_trend"] = data.get("hr_show_trend", True)
        SETTINGS["hr_show_stats"] = data.get("hr_show_stats", False)
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return jsonify({"ok": True}), 200
    
    @app.route("/save_premium_styling", methods=["POST"])
    def save_premium_styling():
        data = request.get_json(force=True)
        custom_background = data.get("custom_background", "")
        custom_button_color = data.get("custom_button_color", "")
        
        SETTINGS["custom_background"] = custom_background[:200] if custom_background else ""
        SETTINGS["custom_button_color"] = custom_button_color[:50] if custom_button_color else ""
        
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return jsonify({"ok": True}), 200

    @app.route("/save_settings", methods=["POST"])
    def save_settings():
        try:
            global client
            ip = request.form.get("quest_ip", SETTINGS.get("quest_ip"))
            
            # Safe integer parsing
            try:
                port = int(request.form.get("quest_port", SETTINGS.get("quest_port")))
            except (ValueError, TypeError):
                port = SETTINGS.get("quest_port", 9000)
            
            try:
                osc_send_interval = int(request.form.get("osc_send_interval", SETTINGS.get("osc_send_interval", 3)))
            except (ValueError, TypeError):
                osc_send_interval = SETTINGS.get("osc_send_interval", 3)
            
            try:
                dashboard_update_interval = int(request.form.get("dashboard_update_interval", SETTINGS.get("dashboard_update_interval", 1)))
            except (ValueError, TypeError):
                dashboard_update_interval = SETTINGS.get("dashboard_update_interval", 1)
            
            timezone = request.form.get("timezone", SETTINGS.get("timezone"))
            spotify_id = request.form.get("spotify_client_id", SETTINGS.get("spotify_client_id"))
            spotify_secret = request.form.get("spotify_client_secret", SETTINGS.get("spotify_client_secret"))
            
            redirect_uri = f"{request.host_url}spotify-callback"
            
            # Check if Spotify credentials changed
            spotify_changed = (
                spotify_id != SETTINGS.get("spotify_client_id") or
                spotify_secret != SETTINGS.get("spotify_client_secret")
            )

            SETTINGS.update({
                "quest_ip": ip,
                "quest_port": port,
                "osc_send_interval": osc_send_interval,
                "dashboard_update_interval": dashboard_update_interval,
                "timezone": timezone,
                "spotify_client_id": spotify_id,
                "spotify_client_secret": spotify_secret,
                "spotify_redirect_uri": redirect_uri
            })
            with open(SETTINGS_FILE, "wb") as f:
                f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
            
            # Reload settings in all modules to pick up changes
            from settings import reload_settings
            reload_settings()
            
            client = make_client()
            
            # Force immediate Spotify re-initialization if credentials changed
            if spotify_changed and (spotify_id.strip() and spotify_secret.strip()):
                print("[Settings] Spotify credentials changed - showing restart banner")
                spotify.force_reinit()
                # Set flag to show restart banner - user needs to authorize then restart
                SETTINGS["spotify_needs_restart"] = True
                with open(SETTINGS_FILE, "wb") as f:
                    f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
            
            print("[Settings] ✓ Settings saved successfully, redirecting to dashboard...")
            return redirect("/")
            
        except Exception as e:
            print(f"[Save Settings ERROR] {e}")
            import traceback
            traceback.print_exc()
            error_msg = f"Error saving settings: {str(e)}\n{traceback.format_exc()}"
            print(f"[ERROR] Full traceback:\n{error_msg}")
            return f"Error saving settings: {str(e)}", 500

    @app.route("/restart_app", methods=["POST"])
    def restart_app():
        """Close the application so user can manually restart"""
        print("[Server] ========================================")
        print("[Server] CLOSE REQUESTED BY USER")
        print("[Server] ========================================")
        
        # Clear the restart flag
        SETTINGS["spotify_needs_restart"] = False
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        print("[Server] ✓ Cleared restart flag in settings.json")
        
        import os
        import sys
        import threading
        
        def delayed_shutdown():
            import time
            time.sleep(2.0)  # Give time for response to send
            print("[Server] ========================================")
            print("[Server] SHUTTING DOWN - PLEASE RELAUNCH APP")
            print("[Server] ========================================")
            os._exit(0)
        
        threading.Thread(target=delayed_shutdown, daemon=True).start()
        return jsonify({"ok": True, "message": "Closing app... Please relaunch Crystal_Chatbox.exe"}), 200

    @app.route("/save_customs", methods=["POST"])
    def save_customs():
        text = request.form.get("customs", "").strip()
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            lines = ["Custom Message Test"]
        SETTINGS["custom_texts"] = lines
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        nonlocal_vars_update_customs(lines)
        return redirect("/")

    @app.route("/update_custom_inline", methods=["POST"])
    def update_custom_inline():
        data = request.get_json(force=True)
        index = int(data.get("index", 0))
        new_text = data.get("text", "").strip()
        
        if 0 <= index < len(SETTINGS["custom_texts"]):
            SETTINGS["custom_texts"][index] = new_text
            with open(SETTINGS_FILE, "wb") as f:
                f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
            nonlocal_vars_update_customs(SETTINGS["custom_texts"])
            return jsonify({"ok": True}), 200
        return jsonify({"ok": False}), 400

    @app.route("/add_custom_message", methods=["POST"])
    def add_custom_message():
        data = request.get_json(force=True)
        new_text = data.get("text", "").strip()
        
        if new_text:
            SETTINGS["custom_texts"].append(new_text)
            with open(SETTINGS_FILE, "wb") as f:
                f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
            nonlocal_vars_update_customs(SETTINGS["custom_texts"])
            return jsonify({"ok": True}), 200
        return jsonify({"ok": False}), 400

    @app.route("/delete_custom_message", methods=["POST"])
    def delete_custom_message():
        data = request.get_json(force=True)
        index = int(data.get("index", 0))
        
        if 0 <= index < len(SETTINGS["custom_texts"]):
            SETTINGS["custom_texts"].pop(index)
            if not SETTINGS["custom_texts"]:
                SETTINGS["custom_texts"] = ["Custom Message Test"]
            with open(SETTINGS_FILE, "wb") as f:
                f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
            nonlocal_vars_update_customs(SETTINGS["custom_texts"])
            return jsonify({"ok": True}), 200
        return jsonify({"ok": False}), 400

    @app.route("/move_custom_message", methods=["POST"])
    def move_custom_message():
        data = request.get_json(force=True)
        index = int(data.get("index", 0))
        direction = data.get("direction", "up")
        
        messages = SETTINGS["custom_texts"]
        if direction == "up" and index > 0:
            messages[index], messages[index - 1] = messages[index - 1], messages[index]
        elif direction == "down" and index < len(messages) - 1:
            messages[index], messages[index + 1] = messages[index + 1], messages[index]
        else:
            return jsonify({"ok": False}), 400
        
        SETTINGS["custom_texts"] = messages
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        nonlocal_vars_update_customs(SETTINGS["custom_texts"])
        return jsonify({"ok": True}), 200

    @app.route("/set_message_weight", methods=["POST"])
    def set_message_weight():
        data = request.get_json(force=True)
        index = str(data.get("index", 0))
        weight = int(data.get("weight", 1))
        
        if "weighted_messages" not in SETTINGS:
            SETTINGS["weighted_messages"] = {}
        
        SETTINGS["weighted_messages"][index] = max(1, weight)
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return jsonify({"ok": True}), 200

    def nonlocal_vars_update_customs(lines):
        global CUSTOM_TEXTS, current_custom_text, text_cycle_index
        CUSTOM_TEXTS = lines
        text_cycle_index = 0
        current_custom_text = CUSTOM_TEXTS[0] if CUSTOM_TEXTS else ""

    @app.route("/save_per_message_intervals", methods=["POST"])
    def save_per_message_intervals():
        data = request.get_json(force=True)
        intervals = data.get("intervals", {})
        SETTINGS["per_message_intervals"] = intervals
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return jsonify({"ok": True}), 200

    @app.route("/save_layout", methods=["POST"])
    def save_layout():
        data = request.get_json(force=True)
        layout = data.get("layout_order") or data.get("layout", SETTINGS.get("layout_order", ["time","custom","song","window","heartrate","weather"]))
        allowed = {"time", "custom", "song", "window", "heartrate", "weather", "system_stats", "afk"}
        filtered = [p for p in layout if p in allowed]
        if not filtered:
            filtered = ["time", "custom", "song", "window", "heartrate", "weather", "system_stats", "afk"]
        SETTINGS["layout_order"] = filtered
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return jsonify({"ok": True}), 200

    @app.route("/reset_settings", methods=["POST"])
    def reset_settings():
        global client, CUSTOM_TEXTS, current_custom_text, text_cycle_index
        
        from settings import DEFAULTS
        
        SETTINGS.clear()
        SETTINGS.update(DEFAULTS)
        
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        
        CUSTOM_TEXTS = DEFAULTS["custom_texts"]
        text_cycle_index = 0
        current_custom_text = CUSTOM_TEXTS[0]
        client = make_client()
        
        return jsonify({"ok": True}), 200

    @app.route("/download_settings", methods=["GET"])
    def download_settings():
        try:
            abs_path = os.path.abspath(SETTINGS_FILE)
            if not os.path.exists(abs_path):
                return jsonify({"error": "Settings file not found"}), 404
            
            response = send_file(
                abs_path,
                as_attachment=True,
                download_name=f"vrchat_chatbox_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mimetype='application/octet-stream',
                etag=False,
                conditional=False
            )
            response.headers['Content-Disposition'] = f'attachment; filename="vrchat_chatbox_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json"'
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
        except Exception as e:
            log_error("Failed to download settings", e)
            return jsonify({"error": str(e)}), 500

    @app.route("/upload_settings", methods=["POST"])
    def upload_settings():
        try:
            data = request.get_json(force=True)
            if not data:
                return jsonify({"error": "No data provided"}), 400
            
            from settings import DEFAULTS
            validated_settings = {}
            for key, default_value in DEFAULTS.items():
                if key in data:
                    validated_settings[key] = data[key]
                else:
                    validated_settings[key] = default_value
            
            SETTINGS.clear()
            SETTINGS.update(validated_settings)
            
            with open(SETTINGS_FILE, "wb") as f:
                f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
            
            global client, CUSTOM_TEXTS, current_custom_text, text_cycle_index
            CUSTOM_TEXTS = SETTINGS.get("custom_texts", [])
            text_cycle_index = 0
            current_custom_text = CUSTOM_TEXTS[0] if CUSTOM_TEXTS else "Custom Message Test"
            client = make_client()
            
            return jsonify({"ok": True}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/download_log", methods=["GET"])
    def download_log():
        abs_path = os.path.abspath(ERROR_LOG_FILE)
        if not os.path.exists(abs_path):
            return jsonify({"error": "No error log found"}), 404
        
        response = send_file(
            abs_path,
            as_attachment=True,
            download_name=f"vrchat_errors_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
            mimetype='application/octet-stream',
            etag=False,
            conditional=False
        )
        response.headers['Content-Disposition'] = f'attachment; filename="vrchat_errors_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log"'
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    @app.route("/spotify-auth", methods=["GET"])
    def spotify_auth():
        try:
            if spotify.sp is None:
                spotify.init_spotify_web()
            
            if spotify.sp is None:
                return render_template("error.html",
                    title="Spotify Not Configured",
                    message="Please add your Spotify Client ID and Client Secret in the Settings panel on the dashboard before authorizing."), 400
            
            auth_manager = spotify.sp.auth_manager
            auth_url = auth_manager.get_authorize_url()
            print(f"[Spotify Auth] Redirecting to Spotify authorization URL")
            return redirect(auth_url)
            
        except Exception as e:
            print(f"[Spotify Auth ERROR] {e}")
            import traceback
            traceback.print_exc()
            return render_template("error.html",
                title="Spotify Authorization Error",
                message=f"An error occurred while starting Spotify authorization: {str(e)}"), 500

    @app.route("/spotify-callback")
    def spotify_callback():
        try:
            if spotify.sp is None:
                spotify.init_spotify_web()
            
            if spotify.sp is None:
                return render_template("error.html", 
                    title="Spotify Not Configured",
                    message="Please add your Spotify Client ID and Client Secret in the Settings panel on the dashboard."), 400
            
            code = request.args.get('code')
            error = request.args.get('error')
            
            if error:
                print(f"[Spotify Callback] Authorization error: {error}")
                return render_template("error.html",
                    title="Spotify Authorization Denied", 
                    message="You denied Spotify access. Please try again if you want to connect Spotify."), 400
            
            if code:
                print(f"[Spotify Callback] Received authorization code, exchanging for token...")
                auth_manager = spotify.sp.auth_manager
                token_info = auth_manager.get_access_token(code)
                print(f"[Spotify Callback] ✓ Token received successfully!")
                
                # Set flag to show restart button - full restart needed for Spotify to work
                print(f"[Spotify Callback] Authorization complete - restart required")
                SETTINGS["spotify_needs_restart"] = True
                with open(SETTINGS_FILE, "wb") as f:
                    f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
                
                return redirect("/?spotify=connected")
            
            return render_template("error.html",
                title="Authorization Failed", 
                message="Spotify authorization was not successful. Please try again from the dashboard."), 400
                
        except Exception as e:
            print(f"[Spotify Callback ERROR] {e}")
            import traceback
            traceback.print_exc()
            return render_template("error.html",
                title="Spotify Connection Error",
                message=f"An error occurred while connecting to Spotify: {str(e)}"), 500

    @app.route("/toggle_weather", methods=["POST"])
    def toggle_weather():
        global show_weather
        show_weather = not show_weather
        SETTINGS["show_weather"] = show_weather
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        
        if show_weather and not SETTINGS.get("weather_enabled"):
            weather_service.enable_weather()
            SETTINGS["weather_enabled"] = True
            with open(SETTINGS_FILE, "wb") as f:
                f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        
        return jsonify({"show_weather": show_weather, "weather_enabled": SETTINGS.get("weather_enabled", False)}), 200

    @app.route("/toggle_slim_chatbox", methods=["POST"])
    def toggle_slim_chatbox():
        SETTINGS["slim_chatbox"] = not SETTINGS.get("slim_chatbox", False)
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return jsonify({"slim_chatbox": SETTINGS["slim_chatbox"]}), 200

    @app.route("/get_frame_styles", methods=["GET"])
    def get_frame_styles():
        styles = chatbox_frames.get_frame_styles()
        current = SETTINGS.get("chatbox_frame", "none")
        return jsonify({"styles": styles, "current": current}), 200

    @app.route("/set_chatbox_frame", methods=["POST"])
    def set_chatbox_frame():
        data = request.get_json()
        frame_id = data.get("frame", "none")
        SETTINGS["chatbox_frame"] = frame_id
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        preview = chatbox_frames.get_frame_preview(frame_id)
        return jsonify({"ok": True, "frame": frame_id, "preview": preview}), 200

    @app.route("/preview_frame", methods=["POST"])
    def preview_frame():
        data = request.get_json()
        frame_id = data.get("frame", "none")
        preview = chatbox_frames.get_frame_preview(frame_id)
        return jsonify({"preview": preview}), 200

    @app.route("/weather_status", methods=["GET"])
    def weather_status():
        state = weather_service.get_weather_state()
        return jsonify(state), 200

    @app.route("/save_weather_settings", methods=["POST"])
    def save_weather_settings():
        data = request.get_json()
        location = data.get("location", "auto")
        temp_unit = data.get("temp_unit", "F")
        SETTINGS["weather_location"] = location
        SETTINGS["weather_temp_unit"] = temp_unit
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        return jsonify({"ok": True}), 200

    @app.route("/check_updates", methods=["GET"])
    def check_updates():
        update_info = github_updater.check_for_updates(force=True)
        return jsonify(update_info or {"error": "Could not check for updates"}), 200

    @app.route("/update_info", methods=["GET"])
    def update_info():
        current_version = github_updater.get_current_version()
        update_info = github_updater.check_for_updates(force=False)
        return jsonify({
            "current_version": current_version,
            "update_info": update_info
        }), 200

    @app.route("/generate_ai_message", methods=["POST"])
    def generate_ai_message():
        if not openai_client.is_configured():
            return jsonify({"error": "OpenAI not configured. Please set OPENAI_API_KEY environment variable."}), 400
        
        data = request.get_json()
        mood = data.get("mood", "funny")
        theme = data.get("theme", "")
        max_length = data.get("max_length", 30)
        
        message = openai_client.generate_message(mood, theme, max_length)
        
        if message:
            return jsonify({"message": message, "ok": True}), 200
        else:
            return jsonify({"error": "Failed to generate message"}), 500

    @app.route("/ai_moods", methods=["GET"])
    def ai_moods():
        return jsonify({"moods": list(openai_client.MOODS.keys())}), 200

    @app.route("/profiles", methods=["GET"])
    def get_profiles():
        profiles = profiles_manager.list_profiles()
        return jsonify({"profiles": profiles}), 200

    @app.route("/save_profile", methods=["POST"])
    def save_profile():
        data = request.get_json()
        name = data.get("name", "")
        
        if not name or not name.strip():
            return jsonify({"error": "Profile name is required"}), 400
        
        settings_to_save = {
            "show_time": show_time,
            "show_custom": show_custom,
            "show_music": show_music,
            "show_window": show_window,
            "show_heartrate": show_heartrate,
            "show_weather": show_weather,
            "custom_texts": SETTINGS.get("custom_texts", []),
            "time_emoji": SETTINGS.get("time_emoji", "⏰"),
            "song_emoji": SETTINGS.get("song_emoji", "🎶"),
            "window_emoji": SETTINGS.get("window_emoji", "💻"),
            "heartrate_emoji": SETTINGS.get("heartrate_emoji", "❤️"),
            "layout_order": SETTINGS.get("layout_order", ["time", "custom", "song", "window", "heartrate", "weather"]),
            "osc_send_interval": SETTINGS.get("osc_send_interval", 3),
            "music_progress": SETTINGS.get("music_progress", True),
            "progress_style": SETTINGS.get("progress_style", "bar"),
            "text_effect": SETTINGS.get("text_effect", "none")
        }
        
        if profiles_manager.get_profile(name):
            if profiles_manager.update_profile(name, settings_to_save):
                return jsonify({"ok": True, "message": "Profile updated"}), 200
            else:
                return jsonify({"error": "Failed to update profile"}), 500
        else:
            if profiles_manager.create_profile(name, settings_to_save):
                return jsonify({"ok": True, "message": "Profile created"}), 200
            else:
                return jsonify({"error": "Failed to create profile"}), 500

    @app.route("/load_profile", methods=["POST"])
    def load_profile():
        global show_time, show_custom, show_music, show_window, show_heartrate, show_weather
        
        data = request.get_json()
        name = data.get("name", "")
        
        if not name:
            return jsonify({"error": "Profile name is required"}), 400
        
        profile = profiles_manager.get_profile(name)
        
        if not profile:
            return jsonify({"error": "Profile not found"}), 404
        
        settings = profile.get("settings", {})
        
        show_time = settings.get("show_time", True)
        show_custom = settings.get("show_custom", True)
        show_music = settings.get("show_music", True)
        show_window = settings.get("show_window", False)
        show_heartrate = settings.get("show_heartrate", False)
        show_weather = settings.get("show_weather", False)
        
        for key, value in settings.items():
            SETTINGS[key] = value
        
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        
        return jsonify({"ok": True, "message": "Profile loaded"}), 200

    @app.route("/delete_profile", methods=["POST"])
    def delete_profile():
        data = request.get_json()
        name = data.get("name", "")
        
        if not name:
            return jsonify({"error": "Profile name is required"}), 400
        
        if profiles_manager.delete_profile(name):
            return jsonify({"ok": True, "message": "Profile deleted"}), 200
        else:
            return jsonify({"error": "Failed to delete profile or cannot delete default profile"}), 500

    @app.route("/text_effects", methods=["GET"])
    def get_text_effects():
        effects = text_effects.get_available_effects()
        return jsonify({"effects": effects}), 200

    @app.route("/set_text_effect", methods=["POST"])
    def set_text_effect():
        data = request.get_json()
        effect = data.get("effect", "none")
        
        SETTINGS["text_effect"] = effect
        with open(SETTINGS_FILE, "wb") as f:
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False).encode("utf-8"))
        
        return jsonify({"ok": True, "effect": effect}), 200

    return app

app = create_app()
