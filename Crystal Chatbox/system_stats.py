import threading
import time

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

system_stats_state = {
    "cpu_percent": 0,
    "ram_percent": 0,
    "ram_used_gb": 0,
    "ram_total_gb": 0,
    "gpu_percent": 0,
    "gpu_name": "",
    "gpu_available": False,
    "network_sent_speed": 0,
    "network_recv_speed": 0,
    "network_sent_total": 0,
    "network_recv_total": 0,
    "last_update": 0,
    "available": PSUTIL_AVAILABLE
}

_stats_thread = None
_stats_running = False
_last_net_io = None
_last_net_time = 0

def get_gpu_stats():
    gpu_percent = 0
    gpu_name = ""
    gpu_available = False
    
    try:
        import subprocess
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=utilization.gpu,name', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(',')
            if len(parts) >= 2:
                gpu_percent = int(parts[0].strip())
                gpu_name = parts[1].strip()
                gpu_available = True
    except:
        pass
    
    return gpu_percent, gpu_name, gpu_available

def update_system_stats():
    global _last_net_io, _last_net_time, system_stats_state
    
    if not PSUTIL_AVAILABLE:
        return
    
    try:
        cpu_percent = psutil.cpu_percent(interval=None)
        
        mem = psutil.virtual_memory()
        ram_percent = mem.percent
        ram_used_gb = round(mem.used / (1024**3), 1)
        ram_total_gb = round(mem.total / (1024**3), 1)
        
        current_time = time.time()
        net_io = psutil.net_io_counters()
        
        if _last_net_io is not None and _last_net_time > 0:
            time_diff = current_time - _last_net_time
            if time_diff > 0:
                sent_speed = (net_io.bytes_sent - _last_net_io.bytes_sent) / time_diff
                recv_speed = (net_io.bytes_recv - _last_net_io.bytes_recv) / time_diff
            else:
                sent_speed = 0
                recv_speed = 0
        else:
            sent_speed = 0
            recv_speed = 0
        
        _last_net_io = net_io
        _last_net_time = current_time
        
        gpu_percent, gpu_name, gpu_available = get_gpu_stats()
        
        system_stats_state.update({
            "cpu_percent": round(cpu_percent, 1),
            "ram_percent": round(ram_percent, 1),
            "ram_used_gb": ram_used_gb,
            "ram_total_gb": ram_total_gb,
            "gpu_percent": gpu_percent,
            "gpu_name": gpu_name,
            "gpu_available": gpu_available,
            "network_sent_speed": round(sent_speed / 1024, 1),
            "network_recv_speed": round(recv_speed / 1024, 1),
            "network_sent_total": round(net_io.bytes_sent / (1024**3), 2),
            "network_recv_total": round(net_io.bytes_recv / (1024**3), 2),
            "last_update": current_time,
            "available": True
        })
        
    except Exception as e:
        print(f"[System Stats] Error: {e}")

def _stats_worker():
    global _stats_running
    
    while _stats_running:
        update_system_stats()
        time.sleep(2)

def start_system_stats():
    global _stats_thread, _stats_running
    
    if not PSUTIL_AVAILABLE:
        print("[System Stats] psutil not available - stats disabled")
        return
    
    if _stats_thread is not None and _stats_thread.is_alive():
        return
    
    _stats_running = True
    _stats_thread = threading.Thread(target=_stats_worker, daemon=True)
    _stats_thread.start()
    print("[System Stats] Monitoring started")

def stop_system_stats():
    global _stats_running
    _stats_running = False
    print("[System Stats] Monitoring stopped")

def get_system_stats():
    return system_stats_state.copy()

def format_system_stats(show_cpu=True, show_ram=True, show_gpu=False, show_network=False):
    stats = get_system_stats()
    
    if not stats.get("available", False):
        return ""
    
    parts = []
    
    if show_cpu:
        parts.append(f"CPU: {stats['cpu_percent']}%")
    
    if show_ram:
        parts.append(f"RAM: {stats['ram_percent']}%")
    
    if show_gpu and stats.get("gpu_available", False):
        parts.append(f"GPU: {stats['gpu_percent']}%")
    
    if show_network:
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
    
    if not parts:
        return ""
    
    return " | ".join(parts)
