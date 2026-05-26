"""
Network Map - Live connection monitor
Visualizes incoming and outgoing network connections on a 3D globe
"""

import threading
import time
import socket
import ipaddress
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import psutil
import requests

app = Flask(__name__)
app.config['SECRET_KEY'] = 'netmap2024secure'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ── Globaler State ──────────────────────────────────────────────
geo_cache: dict = {}
geo_cache_lock = threading.Lock()
geo_rate_lock = threading.Lock()
last_geo_request: float = 0.0

active_connections: dict = {}   # conn_key → conn_data
active_conn_lock = threading.Lock()

selected_adapter: str = 'all'
my_location: dict = {}

executor = ThreadPoolExecutor(max_workers=6)

# ── Port-Namen ──────────────────────────────────────────────────
PORT_NAMES = {
    20: 'FTP-Data', 21: 'FTP', 22: 'SSH', 23: 'Telnet',
    25: 'SMTP', 53: 'DNS', 80: 'HTTP', 110: 'POP3',
    143: 'IMAP', 443: 'HTTPS', 465: 'SMTPS', 587: 'SMTP-Sub',
    993: 'IMAPS', 995: 'POP3S', 1433: 'MSSQL', 3306: 'MySQL',
    3389: 'RDP', 5432: 'Postgres', 6379: 'Redis',
    8080: 'HTTP-Alt', 8443: 'HTTPS-Alt', 27017: 'MongoDB',
    1194: 'OpenVPN', 51820: 'WireGuard', 500: 'IKE/VPN',
}


def port_name(port: int) -> str:
    return PORT_NAMES.get(port, str(port))


def is_private_ip(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
        return a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_reserved
    except Exception:
        return True


def get_geo(ip: str) -> Optional[dict]:
    """Geolocate an IP with caching and rate limiting (45 req/min)."""
    if is_private_ip(ip):
        return None

    with geo_cache_lock:
        if ip in geo_cache:
            return geo_cache[ip]

    # Rate limit: max 45 requests / minute -> min. 1.35 s spacing
    with geo_rate_lock:
        global last_geo_request
        elapsed = time.time() - last_geo_request
        if elapsed < 1.35:
            time.sleep(1.35 - elapsed)
        last_geo_request = time.time()

    try:
        r = requests.get(
            f'http://ip-api.com/json/{ip}',
            params={'fields': 'status,lat,lon,city,country,countryCode,isp,query,org'},
            timeout=6,
        )
        data = r.json()
        if data.get('status') == 'success':
            result = {
                'lat': data['lat'],
                'lon': data['lon'],
                'city': data.get('city', ''),
                'country': data.get('country', ''),
                'countryCode': data.get('countryCode', '').lower(),
                'isp': data.get('isp') or data.get('org', ''),
                'ip': ip,
            }
            with geo_cache_lock:
                geo_cache[ip] = result
            return result
    except Exception as e:
        print(f'[GEO] Error for {ip}: {e}')
    return None


def get_my_location() -> dict:
    """Determine this machine's public IP and location."""
    try:
        r = requests.get(
            'http://ip-api.com/json/',
            params={'fields': 'status,lat,lon,city,country,countryCode,isp,query'},
            timeout=6,
        )
        data = r.json()
        if data.get('status') == 'success':
            return {
                'lat': data['lat'],
                'lon': data['lon'],
                'city': data.get('city', 'Unknown'),
                'country': data.get('country', 'Unknown'),
                'countryCode': data.get('countryCode', '').lower(),
                'ip': data.get('query', ''),
            }
    except Exception as e:
        print(f'[GEO] Failed to resolve local location: {e}')
    # Fallback: Germany
    return {'lat': 51.16, 'lon': 10.45, 'city': 'Unknown', 'country': 'Germany',
            'countryCode': 'de', 'ip': ''}


def get_adapters() -> list:
    """List all network adapters with IPv4 addresses."""
    adapters = [{'name': 'all', 'display': '🌐  All Adapters', 'ips': [], 'is_up': True}]
    stats = psutil.net_if_stats()
    addrs = psutil.net_if_addrs()

    for name, addr_list in addrs.items():
        ipv4 = [a.address for a in addr_list if a.family == socket.AF_INET]
        if ipv4:
            stat = stats.get(name)
            up = stat.isup if stat else False
            adapters.append({
                'name': name,
                'display': f"{'🟢' if up else '🔴'}  {name}  ({', '.join(ipv4)})",
                'ips': ipv4,
                'is_up': up,
            })
    return adapters


def determine_direction(conn) -> str:
    """Determine whether a connection is incoming or outgoing."""
    if conn.status in ('LISTEN',):
        return 'incoming'
    # ESTABLISHED: if local port < 1024 or remote port < 1024 -> often server-side
    if conn.raddr and conn.laddr:
        if conn.laddr.port < 1024 and conn.raddr.port >= 1024:
            return 'incoming'
    return 'outgoing'


def get_process_details(pid: Optional[int]) -> dict:
    """Safely read process details for a connection."""
    if pid is None:
        return {
            'pid': None,
            'process_name': 'Unknown',
            'process_path': '',
        }

    try:
        proc = psutil.Process(pid)
        return {
            'pid': pid,
            'process_name': proc.name() or f'PID {pid}',
            'process_path': proc.exe() or '',
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return {
            'pid': pid,
            'process_name': f'PID {pid}',
            'process_path': '',
        }


def monitor_connections():
    """Background thread that monitors active TCP/UDP connections."""
    global selected_adapter

    while True:
        try:
            conns = psutil.net_connections(kind='inet')

            # Adapter IPs for filtering
            adapter_ips: set = set()
            if selected_adapter and selected_adapter != 'all':
                for addr in psutil.net_if_addrs().get(selected_adapter, []):
                    if addr.family == socket.AF_INET:
                        adapter_ips.add(addr.address)

            current_keys: set = set()

            for conn in conns:
                if not conn.raddr or not conn.raddr.ip:
                    continue
                remote_ip = conn.raddr.ip
                local_ip = conn.laddr.ip if conn.laddr else ''
                local_port = conn.laddr.port if conn.laddr else 0
                remote_port = conn.raddr.port if conn.raddr else 0

                if is_private_ip(remote_ip):
                    continue
                if adapter_ips and local_ip not in adapter_ips:
                    continue

                key = f"{local_ip}:{local_port}↔{remote_ip}:{remote_port}"
                current_keys.add(key)

                with active_conn_lock:
                    if key not in active_connections:
                        # Mark as pending to avoid duplicate lookups
                        active_connections[key] = {'id': key, '_pending': True}

                        direction = determine_direction(conn)
                        status_str = conn.status or 'UNKNOWN'
                        proc_info = get_process_details(conn.pid)

                        def _process(k, rip, lip, lp, rp, direc, stat, proc):
                            geo = get_geo(rip)
                            if not geo:
                                with active_conn_lock:
                                    active_connections.pop(k, None)
                                return
                            data = {
                                'id': k,
                                'local_ip': lip,
                                'remote_ip': rip,
                                'local_port': lp,
                                'remote_port': rp,
                                'port_name': port_name(rp),
                                'status': stat,
                                'direction': direc,
                                'pid': proc['pid'],
                                'process_name': proc['process_name'],
                                'process_path': proc['process_path'],
                                'src_lat': my_location.get('lat', 0),
                                'src_lon': my_location.get('lon', 0),
                                'src_city': my_location.get('city', ''),
                                'src_country': my_location.get('country', ''),
                                'dst_lat': geo['lat'],
                                'dst_lon': geo['lon'],
                                'dst_city': geo['city'],
                                'dst_country': geo['country'],
                                'dst_country_code': geo['countryCode'],
                                'dst_isp': geo['isp'],
                            }
                            with active_conn_lock:
                                active_connections[k] = data
                            socketio.emit('new_connection', data)

                        executor.submit(_process, key, remote_ip, local_ip,
                                        local_port, remote_port, direction, status_str,
                                        proc_info)

            # Remove closed connections
            with active_conn_lock:
                closed = [k for k in list(active_connections.keys()) if k not in current_keys]
                for k in closed:
                    entry = active_connections.pop(k, {})
                    if not entry.get('_pending'):
                        socketio.emit('connection_closed', {'id': k})

        except Exception as e:
            print(f'[MONITOR] Error: {e}')

        time.sleep(2)


# ── Flask-Routen ────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/adapters')
def api_adapters():
    return jsonify(get_adapters())


@app.route('/api/location')
def api_location():
    return jsonify(my_location)


@app.route('/api/set_adapter', methods=['POST'])
def api_set_adapter():
    global selected_adapter
    data = request.get_json(force=True)
    selected_adapter = data.get('adapter', 'all')
    return jsonify({'ok': True, 'adapter': selected_adapter})


@socketio.on('connect')
def on_connect():
    emit('my_location', my_location)
    emit('adapters', get_adapters())
    # Send active connections for newly opened browser sessions
    with active_conn_lock:
        for entry in active_connections.values():
            if not entry.get('_pending'):
                emit('new_connection', entry)


@socketio.on('set_adapter')
def on_set_adapter(data):
    global selected_adapter
    selected_adapter = data.get('adapter', 'all')
    print(f'[ADAPTER] Selected: {selected_adapter}')
    # Reset all existing connections
    with active_conn_lock:
        for k in list(active_connections.keys()):
            entry = active_connections.pop(k)
            if not entry.get('_pending'):
                socketio.emit('connection_closed', {'id': k})


# ── Start ───────────────────────────────────────────────────────

if __name__ == '__main__':
    import sys
    # Windows: force UTF-8 output
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    print('===========================================')
    print('       NETWORK MAP - Live Monitor         ')
    print('===========================================')
    print()
    print('[*] Resolving your location...')
    my_location = get_my_location()
    print(f"[+] Location: {my_location.get('city')}, {my_location.get('country')}  ({my_location.get('ip')})")

    t = threading.Thread(target=monitor_connections, daemon=True)
    t.start()
    print('[+] Connection monitor started')
    print()
    print('[>] Open http://localhost:5000 in your browser')
    print('    (Ctrl+C to quit)')
    print()

    socketio.run(app, host='0.0.0.0', port=5000, debug=False,
                 allow_unsafe_werkzeug=True)
