"""
Network Map - Live connection monitor
Visualizes incoming and outgoing network connections on a 3D globe
"""

import threading
import time
import socket
import math
import ipaddress
import platform
import re
import subprocess
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
process_io_snapshots: dict = {}
network_io_snapshot: Optional[tuple] = None

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


def get_preferred_local_ip() -> str:
    """Return the preferred adapter IPv4 address, excluding loopback."""
    return get_adapter_ip(selected_adapter)


def is_loopback_or_wildcard_ip(ip: str) -> bool:
    return not ip or ip.startswith('127.') or ip in ('0.0.0.0', '::', '::1')


def get_adapter_ip(adapter_name: Optional[str]) -> str:
    """Return an active adapter IPv4, preferring the selected adapter and ignoring loopback."""
    try:
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()

        candidate_names = []
        if adapter_name and adapter_name != 'all':
            candidate_names.append(adapter_name)
        candidate_names.extend(name for name in addrs.keys() if name not in candidate_names)

        for name in candidate_names:
            stat = stats.get(name)
            if stat and not stat.isup:
                continue
            for addr in addrs.get(name, []):
                if addr.family != socket.AF_INET:
                    continue
                ip = addr.address
                if ip and not ip.startswith('127.') and ip != '0.0.0.0':
                    return ip
    except Exception:
        pass

    return ''


def get_matching_adapter_ip(remote_ip: str, adapter_name: Optional[str]) -> str:
    """Match a remote peer to the best local IPv4 on the corresponding adapter."""
    try:
        remote_addr = ipaddress.ip_address(remote_ip)
        if remote_addr.version != 4:
            return ''
    except Exception:
        return ''

    try:
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()

        candidate_names = []
        if adapter_name and adapter_name != 'all':
            candidate_names.append(adapter_name)
        candidate_names.extend(name for name in addrs.keys() if name not in candidate_names)

        fallback_ip = ''
        for name in candidate_names:
            stat = stats.get(name)
            if stat and not stat.isup:
                continue
            for addr in addrs.get(name, []):
                if addr.family != socket.AF_INET:
                    continue
                local_ip = addr.address
                if is_loopback_or_wildcard_ip(local_ip):
                    continue
                if not fallback_ip:
                    fallback_ip = local_ip
                try:
                    if addr.netmask:
                        network = ipaddress.ip_network(f'{local_ip}/{addr.netmask}', strict=False)
                        if remote_addr in network:
                            return local_ip
                except Exception:
                    continue
        return fallback_ip
    except Exception:
        return ''


def normalize_local_ip(ip: str, remote_ip: str, direction: str) -> str:
    """Prefer the matching adapter IPv4 for incoming connections over loopback/wildcard binds."""
    if direction == 'incoming' and is_loopback_or_wildcard_ip(ip):
        adapter_ip = get_matching_adapter_ip(remote_ip, selected_adapter)
        if adapter_ip:
            return adapter_ip
    return ip


def get_display_ip(local_ip: str, remote_ip: str, direction: str) -> str:
    """Choose the UI-facing primary IP without mutating the actual peer address."""
    if direction == 'incoming':
        return local_ip
    return remote_ip


def get_private_peer_geo(ip: str) -> dict:
    """Place private/LAN peers close to this device on the map."""
    base_lat = my_location.get('lat', 0)
    base_lon = my_location.get('lon', 0)
    try:
        last_octet = int(ip.split('.')[-1])
    except Exception:
        last_octet = 1

    angle = (last_octet % 360) * (3.141592653589793 / 180.0)
    distance = 1.2 + (last_octet % 7) * 0.18
    lat = max(-89.0, min(89.0, base_lat + math.sin(angle) * distance))
    lon_scale = max(0.3, math.cos(base_lat * 3.141592653589793 / 180.0))
    lon = ((base_lon + (math.cos(angle) * distance) / lon_scale + 540) % 360) - 180

    return {
        'lat': lat,
        'lon': lon,
        'city': 'Local Network',
        'country': 'Private LAN',
        'countryCode': '',
        'isp': 'Private Network',
        'ip': ip,
    }


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


def parse_traceroute_output(output: str) -> list:
    """Extract hop numbers and IPs from Windows tracert or Unix traceroute output."""
    hops = []
    seen = set()
    ip_pattern = re.compile(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])')

    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        hop_match = re.match(r'^(\d+)\b', stripped)
        if not hop_match:
            continue

        hop_no = int(hop_match.group(1))
        ips = []
        for candidate in ip_pattern.findall(stripped):
            try:
                ipaddress.ip_address(candidate)
            except ValueError:
                continue
            if candidate not in ips:
                ips.append(candidate)

        if not ips:
            if hop_no not in seen:
                hops.append({'hop': hop_no, 'ip': None, 'status': 'timeout'})
                seen.add(hop_no)
            continue

        ip = ips[-1]
        if hop_no in seen:
            continue
        hops.append({'hop': hop_no, 'ip': ip, 'status': 'ok'})
        seen.add(hop_no)

    return hops


def build_traceroute_command(target_ip: str) -> list:
    if platform.system().lower().startswith('win'):
        return ['tracert', '-d', '-w', '1000', '-h', '30', target_ip]
    return ['traceroute', '-n', '-w', '1', '-q', '1', '-m', '30', target_ip]


def run_traceroute(target_ip: str) -> dict:
    """Run a native traceroute and enrich public hops with geolocation."""
    try:
        ipaddress.ip_address(target_ip)
    except ValueError:
        return {'ok': False, 'error': 'Invalid target IP'}

    if is_private_ip(target_ip):
        return {'ok': False, 'error': 'Traceroute target must be a public IP'}

    command = build_traceroute_command(target_ip)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=45,
            encoding='utf-8',
            errors='replace',
        )
    except FileNotFoundError:
        tool_name = command[0]
        return {'ok': False, 'error': f'{tool_name} was not found on this system'}
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or '') + '\n' + (exc.stderr or '')
        completed = None
    else:
        output = (completed.stdout or '') + '\n' + (completed.stderr or '')

    hops = parse_traceroute_output(output)
    enriched = []
    last_geo_ip = None
    for hop in hops:
        ip = hop.get('ip')
        geo = None
        private = False
        if ip:
            private = is_private_ip(ip)
            geo = get_private_peer_geo(ip) if private else get_geo(ip)
            if geo:
                last_geo_ip = ip
        enriched.append({
            'hop': hop['hop'],
            'ip': ip,
            'status': hop.get('status', 'ok'),
            'is_private': private,
            'lat': geo.get('lat') if geo else None,
            'lon': geo.get('lon') if geo else None,
            'city': geo.get('city', '') if geo else '',
            'country': geo.get('country', '') if geo else '',
            'countryCode': geo.get('countryCode', '') if geo else '',
            'isp': geo.get('isp', '') if geo else '',
        })

    if not enriched:
        error = 'Traceroute returned no hops'
        if completed and completed.returncode not in (0, None):
            error = output.strip()[-300:] or error
        return {'ok': False, 'error': error, 'raw': output[-2000:]}

    return {
        'ok': True,
        'target_ip': target_ip,
        'command': ' '.join(command),
        'hops': enriched,
        'reached_target': any(h.get('ip') == target_ip for h in enriched),
        'last_geo_ip': last_geo_ip,
        'raw': output[-4000:],
    }


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


def determine_direction(conn, listener_keys: set, listener_ports: set) -> str:
    """Determine whether a connection is incoming or outgoing."""
    if conn.status in ('LISTEN',):
        return 'incoming'
    if conn.raddr and conn.laddr:
        pid = conn.pid if conn.pid is not None else -1
        local_ip = conn.laddr.ip or ''
        local_port = conn.laddr.port
        if (
            (pid, local_ip, local_port) in listener_keys or
            (pid, '0.0.0.0', local_port) in listener_keys or
            (pid, '::', local_port) in listener_keys or
            (local_ip, local_port) in listener_ports or
            ('0.0.0.0', local_port) in listener_ports or
            ('::', local_port) in listener_ports
        ):
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


def get_process_io_rate(pid: Optional[int], now: float) -> dict:
    """Approximate per-process network activity using process I/O byte deltas."""
    empty = {'rx_bytes_per_sec': 0.0, 'tx_bytes_per_sec': 0.0}
    if pid is None:
        return empty

    try:
        counters = psutil.Process(pid).io_counters()
        read_bytes = int(getattr(counters, 'read_bytes', 0) or 0)
        write_bytes = int(getattr(counters, 'write_bytes', 0) or 0)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        process_io_snapshots.pop(pid, None)
        return empty

    previous = process_io_snapshots.get(pid)
    process_io_snapshots[pid] = (read_bytes, write_bytes, now)
    if not previous:
        return empty

    prev_read, prev_write, prev_time = previous
    elapsed = max(0.001, now - prev_time)
    return {
        'rx_bytes_per_sec': max(0.0, (read_bytes - prev_read) / elapsed),
        'tx_bytes_per_sec': max(0.0, (write_bytes - prev_write) / elapsed),
    }


def get_network_io_rate(now: float) -> dict:
    """Return selected-interface throughput for Linux fallback attribution."""
    global network_io_snapshot

    try:
        if selected_adapter and selected_adapter != 'all':
            pernic = psutil.net_io_counters(pernic=True)
            counters = pernic.get(selected_adapter)
            if not counters:
                return {'rx_bytes_per_sec': 0.0, 'tx_bytes_per_sec': 0.0}
            recv = int(counters.bytes_recv or 0)
            sent = int(counters.bytes_sent or 0)
            key = selected_adapter
        else:
            pernic = psutil.net_io_counters(pernic=True)
            stats = psutil.net_if_stats()
            recv = 0
            sent = 0
            for name, counters in pernic.items():
                stat = stats.get(name)
                if stat and not stat.isup:
                    continue
                recv += int(counters.bytes_recv or 0)
                sent += int(counters.bytes_sent or 0)
            key = 'all'
    except Exception:
        return {'rx_bytes_per_sec': 0.0, 'tx_bytes_per_sec': 0.0}

    previous = network_io_snapshot
    network_io_snapshot = (key, recv, sent, now)
    if not previous or previous[0] != key:
        return {'rx_bytes_per_sec': 0.0, 'tx_bytes_per_sec': 0.0}

    _, prev_recv, prev_sent, prev_time = previous
    elapsed = max(0.001, now - prev_time)
    return {
        'rx_bytes_per_sec': max(0.0, (recv - prev_recv) / elapsed),
        'tx_bytes_per_sec': max(0.0, (sent - prev_sent) / elapsed),
    }


def distribute_network_rate(rate: dict, grouped: dict) -> dict:
    """Spread interface throughput over active entries when per-PID data is unavailable."""
    active_items = [
        (key, entry)
        for key, entry in grouped.items()
        if entry.get('conn') and entry['conn'].pid is not None
    ]
    if not active_items:
        return {}

    share_rx = rate.get('rx_bytes_per_sec', 0.0) / len(active_items)
    share_tx = rate.get('tx_bytes_per_sec', 0.0) / len(active_items)
    return {
        key: {'rx_bytes_per_sec': share_rx, 'tx_bytes_per_sec': share_tx}
        for key, _ in active_items
    }


def aggregate_connection_key(conn, local_ip: str, remote_ip: str, remote_port: int,
                             direction: str) -> str:
    """Group equivalent connections into a single UI entry."""
    pid = conn.pid if conn.pid is not None else 0
    return f"{local_ip}|{remote_ip}|{remote_port}|{direction}|{pid}"


def monitor_connections():
    """Background thread that monitors active TCP/UDP connections."""
    global selected_adapter

    while True:
        try:
            conns = psutil.net_connections(kind='inet')
            listener_keys = set()
            listener_ports = set()
            for entry in conns:
                if entry.status != 'LISTEN' or not entry.laddr:
                    continue
                pid = entry.pid if entry.pid is not None else -1
                bind_ip = entry.laddr.ip or ''
                bind_port = entry.laddr.port
                listener_keys.add((pid, bind_ip, bind_port))
                listener_ports.add((bind_ip, bind_port))

            # Adapter IPs for filtering
            adapter_ips: set = set()
            if selected_adapter and selected_adapter != 'all':
                for addr in psutil.net_if_addrs().get(selected_adapter, []):
                    if addr.family == socket.AF_INET:
                        adapter_ips.add(addr.address)

            grouped: dict = {}

            for conn in conns:
                if not conn.raddr or not conn.raddr.ip:
                    continue
                remote_ip = conn.raddr.ip
                local_ip = conn.laddr.ip if conn.laddr else ''
                local_port = conn.laddr.port if conn.laddr else 0
                remote_port = conn.raddr.port if conn.raddr else 0

                direction = determine_direction(conn, listener_keys, listener_ports)
                local_ip = normalize_local_ip(local_ip, remote_ip, direction)
                if direction == 'incoming' and is_loopback_or_wildcard_ip(local_ip):
                    continue
                if is_private_ip(remote_ip) and direction != 'incoming':
                    continue
                if adapter_ips and local_ip not in adapter_ips:
                    continue
                display_ip = get_display_ip(local_ip, remote_ip, direction)

                key = aggregate_connection_key(conn, local_ip, remote_ip, remote_port, direction)
                entry = grouped.get(key)
                if entry is None:
                    grouped[key] = {
                        'conn': conn,
                        'local_ip': local_ip,
                        'remote_ip': remote_ip,
                        'display_ip': display_ip,
                        'remote_port': remote_port,
                        'direction': direction,
                        'local_ports': {local_port},
                        'status': conn.status or 'UNKNOWN',
                    }
                else:
                    entry['local_ports'].add(local_port)
                    if entry['status'] == 'UNKNOWN' and conn.status:
                        entry['status'] = conn.status

            current_keys = set(grouped.keys())
            loop_now = time.time()
            active_pids = {entry['conn'].pid for entry in grouped.values() if entry['conn'].pid is not None}
            bandwidth_by_pid = {
                pid: get_process_io_rate(pid, loop_now)
                for pid in active_pids
            }
            bandwidth_by_key = {}
            if platform.system().lower() == 'linux':
                has_pid_bandwidth = any(
                    (rate.get('rx_bytes_per_sec', 0.0) + rate.get('tx_bytes_per_sec', 0.0)) > 0
                    for rate in bandwidth_by_pid.values()
                )
                if not has_pid_bandwidth:
                    bandwidth_by_key = distribute_network_rate(
                        get_network_io_rate(loop_now),
                        grouped,
                    )
            for pid in list(process_io_snapshots.keys()):
                if pid not in active_pids:
                    process_io_snapshots.pop(pid, None)

            for key, grouped_entry in grouped.items():
                conn = grouped_entry['conn']
                local_ip = grouped_entry['local_ip']
                remote_ip = grouped_entry['remote_ip']
                display_ip = grouped_entry['display_ip']
                remote_port = grouped_entry['remote_port']
                direction = grouped_entry['direction']
                local_ports = sorted(grouped_entry['local_ports'])
                primary_local_port = local_ports[0] if local_ports else 0
                status_str = grouped_entry['status']
                proc_info = get_process_details(conn.pid)
                io_rate = bandwidth_by_key.get(key) or bandwidth_by_pid.get(conn.pid, {
                    'rx_bytes_per_sec': 0.0,
                    'tx_bytes_per_sec': 0.0,
                })

                with active_conn_lock:
                    existing = active_connections.get(key)
                    if existing and not existing.get('_pending'):
                        updated = dict(existing)
                        updated.update({
                            'local_port': primary_local_port,
                            'local_ports': local_ports,
                            'local_port_count': len(local_ports),
                            'display_ip': display_ip,
                            'status': status_str,
                            'pid': proc_info['pid'],
                            'process_name': proc_info['process_name'],
                            'process_path': proc_info['process_path'],
                            'port_name': port_name(remote_port),
                            'rx_bytes_per_sec': io_rate['rx_bytes_per_sec'],
                            'tx_bytes_per_sec': io_rate['tx_bytes_per_sec'],
                        })
                        if updated != existing:
                            active_connections[key] = updated
                            socketio.emit('update_connection', updated)
                        continue

                    if existing:
                        continue

                    # Mark as pending to avoid duplicate lookups
                    active_connections[key] = {'id': key, '_pending': True}

                def _process(k, rip, lip, lp, lps, rp, direc, stat, proc, rate):
                    geo = get_private_peer_geo(rip) if is_private_ip(rip) else get_geo(rip)
                    if not geo:
                        with active_conn_lock:
                            active_connections.pop(k, None)
                        return
                    data = {
                        'id': k,
                        'local_ip': lip,
                        'remote_ip': rip,
                        'display_ip': get_display_ip(lip, rip, direc),
                        'local_port': lp,
                        'local_ports': lps,
                        'local_port_count': len(lps),
                        'remote_port': rp,
                        'port_name': port_name(rp),
                        'status': stat,
                        'direction': direc,
                        'pid': proc['pid'],
                        'process_name': proc['process_name'],
                        'process_path': proc['process_path'],
                        'rx_bytes_per_sec': rate['rx_bytes_per_sec'],
                        'tx_bytes_per_sec': rate['tx_bytes_per_sec'],
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
                                primary_local_port, local_ports, remote_port,
                                direction, status_str, proc_info, io_rate)

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


@app.route('/api/traceroute', methods=['POST'])
def api_traceroute():
    data = request.get_json(force=True)
    target_ip = data.get('ip', '')
    connection_id = data.get('connection_id', '')

    if connection_id:
        with active_conn_lock:
            conn = active_connections.get(connection_id, {})
        target_ip = conn.get('remote_ip') or target_ip

    return jsonify(run_traceroute(str(target_ip).strip()))


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
    print(f"[>] Open http://{get_preferred_local_ip()}:5000 in your browser")
    print('    (Ctrl+C to quit)')
    print()

    socketio.run(app, host='0.0.0.0', port=5000, debug=False,
                 allow_unsafe_werkzeug=True)
