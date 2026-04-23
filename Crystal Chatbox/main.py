#!/usr/bin/env python3
"""
Crystal Chatbox Launcher
Runs Flask app and optionally launches a PyWebview GUI.
"""

# FIX UNICODE ENCODING FOR WINDOWS BUILDS (MUST BE FIRST!)
# This prevents "charmap codec can't encode" errors in console=False builds
import sys
import os

if getattr(sys, 'frozen', False) and sys.platform == 'win32':
    # We're in a PyInstaller Windows build
    # Redirect stdout/stderr to devnull with UTF-8 to prevent Unicode crashes
    try:
        devnull = open(os.devnull, 'w', encoding='utf-8', errors='ignore')
        sys.stdout = devnull
        sys.stderr = devnull
    except:
        pass
    
    # Force UTF-8 environment
    os.environ['PYTHONUTF8'] = '1'
    os.environ['PYTHONIOENCODING'] = 'utf-8'

import threading
import time
import argparse

try:
    import setproctitle
    setproctitle.setproctitle("Crystal Client Dashboard")
except ImportError:
    pass

def _is_android() -> bool:
    # python-for-android sets ANDROID_ARGUMENT and sys.platform becomes "android".
    return sys.platform == "android" or bool(os.environ.get("ANDROID_ARGUMENT"))

try:
    import webview
    WEBVIEW_AVAILABLE = True
except ImportError:
    WEBVIEW_AVAILABLE = False

from routes import app as flask_app
import json
import shutil

def start_server(app, host=None, port=5000):
    """Start Flask server"""
    if host is None:
        host = os.environ.get("HOST", "0.0.0.0")
    print(f"[Server] Starting Flask server at http://{host}:{port} ...")
    app.run(host=host, port=port, debug=False, use_reloader=False)

def _android_open_url(url: str) -> bool:
    try:
        from jnius import autoclass  # type: ignore
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")

        intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
        current_activity = PythonActivity.mActivity
        current_activity.startActivity(intent)
        return True
    except Exception:
        return False

def _run_android_kivy(app, port: int) -> None:
    from kivy.app import App
    from kivy.clock import Clock
    from kivy.core.window import Window
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label

    host = os.environ.get("HOST", "127.0.0.1")
    url = f"http://{host}:{port}"

    def start_server_thread() -> None:
        server_thread = threading.Thread(
            target=start_server, args=(app, host, port), daemon=True
        )
        server_thread.start()

    class CrystalChatboxAndroidApp(App):
        def build(self):
            Window.clearcolor = (0.05, 0.05, 0.05, 1)
            Window.allow_screensaver = False

            root = BoxLayout(orientation="vertical", padding=20, spacing=12)

            title = Label(
                text="[b]Crystal Chatbox[/b]",
                markup=True,
                font_size="24sp",
                size_hint_y=None,
                height="48dp",
            )

            status = Label(
                text=f"Server starting…\n{url}\n\nIf the screen stays blank, tap Open Dashboard.",
                halign="center",
                valign="middle",
            )
            status.bind(size=lambda inst, *_: setattr(inst, "text_size", inst.size))

            open_btn = Button(text="Open Dashboard", size_hint_y=None, height="52dp")
            open_btn.bind(on_release=lambda *_: _android_open_url(url))

            root.add_widget(title)
            root.add_widget(status)
            root.add_widget(open_btn)

            Clock.schedule_once(lambda *_: start_server_thread(), 0)
            Clock.schedule_once(lambda *_: _android_open_url(url), 1.0)
            return root

    CrystalChatboxAndroidApp().run()

class DownloadAPI:
    """API for handling file downloads in PyWebview"""
    
    def download_settings(self):
        """Download settings.json file"""
        try:
            settings_file = os.path.join(os.path.dirname(__file__), "settings.json")
            if not os.path.exists(settings_file):
                return {"success": False, "error": "Settings file not found"}
            
            downloads_path = os.path.expanduser("~/Downloads")
            from datetime import datetime
            filename = f"vrchat_chatbox_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            dest_path = os.path.join(downloads_path, filename)
            
            shutil.copy2(settings_file, dest_path)
            return {"success": True, "path": dest_path, "filename": filename}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def download_log(self):
        """Download error log file"""
        try:
            log_file = os.path.join(os.path.dirname(__file__), "vrchat_errors.log")
            if not os.path.exists(log_file):
                return {"success": False, "error": "No error log found"}
            
            downloads_path = os.path.expanduser("~/Downloads")
            from datetime import datetime
            filename = f"vrchat_errors_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            dest_path = os.path.join(downloads_path, filename)
            
            shutil.copy2(log_file, dest_path)
            return {"success": True, "path": dest_path, "filename": filename}
        except Exception as e:
            return {"success": False, "error": str(e)}

def start_gui(app, host="127.0.0.1", port=5000):
    """Start PyWebview GUI"""
    if not WEBVIEW_AVAILABLE:
        print("[GUI] PyWebview not available, falling back to server mode...")
        start_server(app, host=host, port=port)
        return
    
    server_thread = threading.Thread(target=start_server, args=(app, host, port), daemon=True)
    server_thread.start()

    print("[GUI] Waiting for server to start...")
    time.sleep(2)

    print("[GUI] Launching PyWebview window...")
    api = DownloadAPI()
    window = webview.create_window(
        title="Crystal Client Dashboard",
        url=f"http://{host}:{port}",
        width=1200,
        height=800,
        resizable=True,
        fullscreen=False,
        min_size=(800, 600),
        background_color="#0d0d0d",
        js_api=api
    )

    webview.start(debug=False)
    print("[GUI] Application closed.")
    sys.exit(0)

def main():
    if _is_android():
        port = int(os.environ.get("PORT", 5000))
        _run_android_kivy(flask_app, port=port)
        return

    parser = argparse.ArgumentParser(description="Launch Crystal Client Dashboard.")
    parser.add_argument("--nogui", action="store_true", help="Run server only, without GUI.")
    args = parser.parse_args()

    port = int(os.environ.get("PORT", 5000))
    
    is_replit = os.environ.get("REPL_ID") or os.environ.get("REPLIT_DB_URL")
    
    if args.nogui or is_replit:
        start_server(flask_app, port=port)
    else:
        start_gui(flask_app, port=port)

if __name__ == "__main__":
    main()
