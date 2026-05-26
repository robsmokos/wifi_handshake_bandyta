from aiohttp import web
import aiosqlite
import json
import os
import psutil
from datetime import datetime

class WebServer:
    def __init__(self, db, shared_state=None):
        self.db = db
        self.db_path = db.db_path
        self.shared_state = shared_state or {"action": "Skanowanie..."}

    async def get_index(self, request):
        html_content = """<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BetterCup Console</title>
    <style>
        body {
            background-color: #121212;
            color: #00ff00;
            font-family: monospace;
            padding: 15px;
            margin: 0;
        }
        h1, h2 {
            font-size: 1.2rem;
            margin: 10px 0;
            border-bottom: 1px solid #00ff00;
            padding-bottom: 5px;
        }
        .stats-box {
            padding: 5px 0px;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            gap: 5px;
        }
        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 5px;
            transition: all 0.3s ease;
            flex-shrink: 0;
        }
        .pulse-green {
            background-color: #00ff00;
            box-shadow: 0 0 8px #00ff00;
            animation: pulse 1.2s infinite alternate;
        }
        .pulse-yellow {
            background-color: #ffaa00;
            box-shadow: 0 0 8px #ffaa00;
            animation: pulse 0.6s infinite alternate;
        }
        .pulse-red {
            background-color: #ff3333;
            box-shadow: 0 0 8px #ff3333;
            animation: pulse 0.4s infinite alternate;
        }
        .pulse-white {
            background-color: #ffffff;
            box-shadow: 0 0 10px #ffffff;
            animation: pulse 0.8s infinite alternate;
        }
        @keyframes pulse {
            from { opacity: 0.4; transform: scale(0.85); }
            to { opacity: 1; transform: scale(1.15); }
        }
        .status-spinner {
            display: inline-block;
            font-family: monospace;
            font-weight: bold;
            margin-right: 3px;
            width: 3ch;
            text-align: center;
            flex-shrink: 0;
            white-space: nowrap;
        }
        .stat-group {
            display: inline-flex;
            align-items: center;
            white-space: nowrap;
            gap: 4px;
        }
        .stat-sep {
            color: #1f940b;
            margin: 0 6px;
            user-select: none;
        }
        .control-panel {
            margin-bottom: 15px;
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        input, select, button {
            background-color: #000;
            color: #00ff00;
            border: 1px solid #00ff00;
            padding: 5px 10px;
            font-family: monospace;
            cursor: pointer;
        }
        button.active {
            background-color: #00ff00;
            color: #000;
            font-weight: bold;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }
        th, td {
            padding: 2px 8px;
            text-align: left;
        }
        th {
            background-color: #003300;
        }
        tr:hover {
            background-color: #001100;
        }
        a {
            color: #ffffff;
            text-decoration: underline;
        }
        a:hover {
            color: #00ff00;
        }
        .captured {
            color: #ffffff;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div style="display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 1px solid #00ff00; padding-bottom: 10px; margin-bottom: 15px;">
        <div>
            <h1 style="border: none; margin: 0; padding: 0;">BetterCup WiFi Console</h1>
            <div style="font-size: 0.8rem; color: #1f940b; margin-top: 5px; font-weight: bold;">[ HACK THE PLANET ]</div>
        </div>
        <!-- Pwnagotchi Monitor Face in Top Right - Pure ASCII / No Border -->
        <div style="padding: 5px 15px; display: flex; flex-direction: column; align-items: center; justify-content: center; min-width: 120px; text-shadow: none;">
            <span id="pwn-face" style="font-size: 1.8rem; font-weight: bold; color: #00ff00; text-shadow: 0 0 4px rgba(57, 255, 20, 0.45); font-family: monospace;">(o_O)</span>
            <div id="pwn-face-lbl" style="font-size: 0.65rem; color: #1f940b; font-weight: bold; margin-top: 3px; text-transform: uppercase; font-family: monospace;">AWAKE</div>
        </div>
    </div>
    
    <div class="stats-box">
        <span class="stat-group">
            <strong>STATUS:</strong>
            <span id="status-dot" class="status-dot pulse-green"></span>
            <span id="status-spinner" class="status-spinner">[/]</span>
            <span id="pwn-status" style="color: #00ff00; font-weight: bold;">Inicjalizacja...</span>
        </span>
        <span class="stat-sep">|</span>
        <span class="stat-group">
            <strong>SIECI:</strong> <span id="stat-total" style="color: #ffffff;">0</span>
        </span>
        <span class="stat-sep">|</span>
        <span class="stat-group">
            <strong>ZŁAPANE:</strong> <span id="stat-captured" style="color: #ffffff;">0</span>
        </span>
        <span class="stat-sep">|</span>
        <span class="stat-group">
            <strong>SKUTECZNOŚĆ:</strong> <span id="stat-rate" style="color: #ffffff;">0.0%</span>
        </span>
        <span class="stat-sep">|</span>
        <span class="stat-group">
            <strong style="color: #1f940b;">CPU:</strong> <span id="stat-cpu" style="color: #00ddff; font-weight: bold;">0.0%</span>
        </span>
        <span class="stat-sep">|</span>
        <span class="stat-group">
            <strong style="color: #1f940b;">RAM:</strong> <span id="stat-ram" style="color: #00ddff; font-weight: bold;">0.0%</span>
        </span>
        <span class="stat-sep">|</span>
        <span id="stat-datetime" style="color: #666666; font-family: monospace; white-space: nowrap;">-</span>
    </div>

    <h2>Widok: <span id="view-title">Aktywne sieci</span></h2>
    
    <div class="control-panel">
        <button id="btn-view-active" class="active" onclick="switchView('active')">[ AKTYWNE SIECI ]</button>
        <button id="btn-view-database" onclick="switchView('database')">[ BAZA DANYCH ]</button>
        
        <input type="text" id="search-bar" placeholder="Szukaj (BSSID, ESSID)..." style="flex-grow: 1;">
        
        <select id="status-filter">
            <option value="">Wszystkie statusy</option>
            <option value="captured">Tylko przechwycone</option>
            <option value="new">Tylko nowe</option>
        </select>
    </div>

    <table id="networks-table">
        <thead>
            <!-- Wypelniane dynamicznie w JS -->
        </thead>
        <tbody id="networks-tbody">
            <tr>
                <td colspan="9">Ładowanie rekordów...</td>
            </tr>
        </tbody>
    </table>

    <script>
        const searchBar = document.getElementById('search-bar');
        const statusFilter = document.getElementById('status-filter');
        const networksTbody = document.getElementById('networks-tbody');
        const viewTitle = document.getElementById('view-title');

        const statTotal = document.getElementById('stat-total');
        const statCaptured = document.getElementById('stat-captured');
        const statRate = document.getElementById('stat-rate');
        const pwnStatus = document.getElementById('pwn-status');

        let currentView = 'active';

        function switchView(view) {
            currentView = view;
            document.getElementById('btn-view-active').classList.toggle('active', view === 'active');
            document.getElementById('btn-view-database').classList.toggle('active', view === 'database');
            viewTitle.innerText = view === 'active' ? 'Aktywne sieci (w locie)' : 'Zapisane w bazie';
            fetchAPs();
        }

        // Mappings from ASCII states to Text Status Labels
        const faceNameMap = {
            "(o_O)": "AWAKE",
            "(>_<)": "INTENSE",
            "(^_^)": "HAPPY",
            "(X_X)": "SAD"
        };

        async function fetchStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();
                statTotal.innerText = data.total;
                statCaptured.innerText = data.captured;
                const rate = data.total > 0 ? ((data.captured / data.total) * 100).toFixed(1) : 0;
                statRate.innerText = rate + '%';
                
                // Update CPU, RAM, and Datetime
                const statCpu = document.getElementById('stat-cpu');
                const statRam = document.getElementById('stat-ram');
                const statDatetime = document.getElementById('stat-datetime');
                
                if (statCpu) statCpu.innerText = (data.cpu || 0.0).toFixed(1) + '%';
                if (statRam) statRam.innerText = (data.ram || 0.0).toFixed(1) + '%';
                if (statDatetime) statDatetime.innerText = data.datetime || '';
                
                const action = data.action || 'Skanowanie eteru...';
                pwnStatus.innerText = action;

                // Color code and animate status dynamically
                const pwnStatusSpan = document.getElementById('pwn-status');
                const statusDot = document.getElementById('status-dot');
                const statusSpinner = document.getElementById('status-spinner');
                
                if (pwnStatusSpan && statusDot && statusSpinner) {
                    if (action.includes('ATAK') || action.includes('Wysyłanie') || action.includes('Deauth') || action.includes('PMKID')) {
                        pwnStatusSpan.style.color = '#ffaa00';
                        statusDot.className = 'status-dot pulse-yellow';
                        statusSpinner.style.color = '#ffaa00';
                    } else if (action.includes('Błąd') || action.includes('Error') || action.includes('nie powiodło')) {
                        pwnStatusSpan.style.color = '#ff3333';
                        statusDot.className = 'status-dot pulse-red';
                        statusSpinner.style.color = '#ff3333';
                    } else if (action.includes('ZŁAPANO') || action.includes('SUKCES') || action.includes('przechwycono')) {
                        pwnStatusSpan.style.color = '#ffffff';
                        statusDot.className = 'status-dot pulse-white';
                        statusSpinner.style.color = '#ffffff';
                    } else {
                        pwnStatusSpan.style.color = '#00ff00';
                        statusDot.className = 'status-dot pulse-green';
                        statusSpinner.style.color = '#00ff00';
                    }
                }

                // Pure ASCII Face Updates
                const faceCode = data.face;
                const mappedName = faceNameMap[faceCode] || "AWAKE";
                
                const pwnFace = document.getElementById('pwn-face');
                const pwnFaceLbl = document.getElementById('pwn-face-lbl');
                
                if (pwnFace) pwnFace.innerText = faceCode;
                if (pwnFaceLbl) pwnFaceLbl.innerText = mappedName;
            } catch (err) {
                console.error(err);
                pwnStatus.innerText = "BŁĄD POŁĄCZENIA";
                const statusDot = document.getElementById('status-dot');
                const statusSpinner = document.getElementById('status-spinner');
                if (statusDot) {
                    statusDot.className = 'status-dot pulse-red';
                }
                if (statusSpinner) {
                    statusSpinner.style.color = '#ff3333';
                }
                const pwnFace = document.getElementById('pwn-face');
                const pwnFaceLbl = document.getElementById('pwn-face-lbl');
                if (pwnFace) pwnFace.innerText = "(X_X)";
                if (pwnFaceLbl) pwnFaceLbl.innerText = "SAD";
            }
        }

        async function fetchAPs() {
            try {
                const search = encodeURIComponent(searchBar.value);
                const status = statusFilter.value;
                const res = await fetch(`/api/aps?view=${currentView}&search=${search}&status=${status}`);
                const aps = await res.json();

                const thead = document.getElementById('networks-table').querySelector('thead');
                if (currentView === 'active') {
                    thead.innerHTML = `
                        <tr>
                            <th style="width: 40px;">#</th>
                            <th>SIGNAL</th>
                            <th>BRAIN</th>
                            <th>BSSID</th>
                            <th>ESSID</th>
                            <th>PRODUCENT</th>
                            <th>CH</th>
                            <th>ENC</th>
                            <th>CLI</th>
                            <th>ATK</th>
                            <th>STATUS</th>
                        </tr>
                    `;
                } else {
                    thead.innerHTML = `
                        <tr>
                            <th style="width: 40px;">#</th>
                            <th>BSSID</th>
                            <th>ESSID</th>
                            <th>PRODUCENT</th>
                            <th>STATUS</th>
                            <th>OSTATNIO</th>
                        </tr>
                    `;
                }

                networksTbody.innerHTML = '';

                if (aps.length === 0) {
                    const colSpan = currentView === 'active' ? 11 : 6;
                    networksTbody.innerHTML = `<tr><td colspan="${colSpan}">-- Brak wyników wyszukiwania --</td></tr>`;
                    return;
                }

                aps.forEach((ap, idx) => {
                    const tr = document.createElement('tr');
                    const isCaptured = ap.status.includes('przechwycono');
                    const statusText = isCaptured ? 'CAPTURED' : 'NEW';
                    const statusClass = isCaptured ? 'captured' : '';

                    let rssiColor = "#00ff00";
                    if (ap.rssi >= -60) rssiColor = "#ffffff";
                    else if (ap.rssi >= -70) rssiColor = "#00ff00";
                    else if (ap.rssi >= -80) rssiColor = "#aaff00";
                    else if (ap.rssi >= -90) rssiColor = "#ffaa00";
                    else rssiColor = "#ff5555";

                    // Color code brain scores
                    let scoreColor = "var(--terminal-green-dim)";
                    if (isCaptured) {
                        scoreColor = "#888";
                    } else if (ap.score >= -100) {
                        scoreColor = "#ffffff";
                    } else if (ap.score >= -150) {
                        scoreColor = "var(--terminal-green)";
                    }

                    // Display 'CRACKED' instead of numeric score for captured handshakes for neatness
                    const scoreText = isCaptured ? "CRACKED" : ap.score;

                    if (currentView === 'active') {
                        tr.innerHTML = `
                            <td style="color: #888;">${idx + 1}</td>
                            <td style="font-weight: bold; color: ${rssiColor};">${ap.rssi} dBm</td>
                            <td style="font-weight: bold; color: ${scoreColor};">[${scoreText}]</td>
                            <td>${ap.bssid}</td>
                            <td class="${statusClass}">${ap.essid || '<ukryty>'}</td>
                            <td style="color: var(--terminal-green-dim); font-size: 0.85rem;">${ap.vendor || 'UNKNOWN'}</td>
                            <td>${ap.channel || '?'}</td>
                            <td>${ap.encryption || 'WPA2'}</td>
                            <td style="font-weight: ${ap.client_count > 0 ? 'bold' : 'normal'}; color: ${ap.client_count > 0 ? '#ffffff' : 'inherit'};">${ap.client_count}</td>
                            <td>${ap.liczba_atakow_deauth || 0}/${ap.liczba_atakow_pmkid || 0}</td>
                            <td class="${statusClass}">${statusText}</td>
                        `;
                    } else {
                        tr.innerHTML = `
                            <td style="color: #888;">${idx + 1}</td>
                            <td>${ap.bssid}</td>
                            <td class="${statusClass}">${ap.essid || '<ukryty>'}</td>
                            <td>${ap.vendor || 'UNKNOWN'}</td>
                            <td class="${statusClass}">${statusText}</td>
                            <td>${ap.last_seen || '-'}</td>
                        `;
                    }
                    networksTbody.appendChild(tr);
                });
            } catch (err) {
                console.error(err);
                const colSpan = currentView === 'active' ? 11 : 6;
                networksTbody.innerHTML = `<tr><td colspan="${colSpan}" style="color: red;">BŁĄD ZAPISU BAZY / I/O</td></tr>`;
            }
        }

        let debounceTimer;
        searchBar.addEventListener('input', () => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(fetchAPs, 300);
        });

        statusFilter.addEventListener('change', fetchAPs);

        // Spinner animation setup - 4 backslashes in Python source code compiles to 2 backslashes in served HTML,
        // which JavaScript compiles to a single backslash '\', guaranteeing exactly 3 characters width and no shifting!
        let spinnerFrames = ['[|]', '[/]', '[-]', '[\\\\]'];
        let spinnerIndex = 0;
        const statusSpinnerElement = document.getElementById('status-spinner');
        
        setInterval(() => {
            if (statusSpinnerElement) {
                statusSpinnerElement.innerText = spinnerFrames[spinnerIndex];
                spinnerIndex = (spinnerIndex + 1) % spinnerFrames.length;
            }
        }, 150);

        fetchStats();
        fetchAPs();
        setInterval(fetchStats, 1000);
        setInterval(fetchAPs, 5000);
    </script>
</body>
</html>"""
        return web.Response(text=html_content, content_type='text/html')

    async def get_stats(self, request):
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute("SELECT COUNT(*) FROM handshakes") as cursor:
                total = (await cursor.fetchone())[0]
            async with conn.execute("SELECT COUNT(*) FROM handshakes WHERE status IN ('przechwycono', 'pmkid_przechwycono')") as cursor:
                captured = (await cursor.fetchone())[0]
        
        action = self.shared_state.get('action', 'Skanowanie eteru...')
        
        # ASCII Reactive faces representing Pwnagotchi states
        face = "(o_O)"
        if "ATAK" in action:
            face = "(>_<)"
        elif "SUKCES" in action or "ZŁAPANO" in action:
            face = "(^_^)"
        elif "Błąd" in action or "error" in action.lower():
            face = "(X_X)"

        try:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
        except Exception:
            cpu = 0.0
            ram = 0.0
            
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        data = {
            "total": total,
            "captured": captured,
            "action": action,
            "face": face,
            "cpu": cpu,
            "ram": ram,
            "datetime": now_str
        }
        return web.json_response(data)

    async def get_aps(self, request):
        query_params = request.query
        search = query_params.get('search', '').strip().lower()
        status_filter = query_params.get('status', '').strip()
        view = query_params.get('view', 'active').strip()
        
        if view == 'active':
            active_aps = await self.db.get_active_aps_with_status()
            filtered_aps = []
            for ap in active_aps:
                if search:
                    bssid_match = search in ap['bssid'].lower()
                    essid_match = search in (ap['essid'] or '').lower()
                    vendor_match = search in (ap['vendor'] or '').lower()
                    if not (bssid_match or essid_match or vendor_match):
                        continue
                
                if status_filter:
                    is_captured = ap['status'] in ('przechwycono', 'pmkid_przechwycono')
                    if status_filter == 'captured' and not is_captured:
                        continue
                    if status_filter == 'new' and ap['status'] != 'nowy':
                        continue
                filtered_aps.append(ap)
            return web.json_response(filtered_aps)
            
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            sql = "SELECT bssid, essid, vendor, status, last_seen FROM handshakes"
            args = []
            
            conditions = []
            if search:
                conditions.append("(bssid LIKE ? OR essid LIKE ? OR vendor LIKE ?)")
                like_str = f"%{search}%"
                args.extend([like_str, like_str, like_str])
            if status_filter:
                if status_filter == 'captured':
                    conditions.append("status IN ('przechwycono', 'pmkid_przechwycono')")
                elif status_filter == 'new':
                    conditions.append("status = 'nowy'")
            
            if conditions:
                sql += " WHERE " + " AND ".join(conditions)
                
            sql += " ORDER BY last_seen DESC LIMIT 100"
            
            async with conn.execute(sql, args) as cursor:
                rows = await cursor.fetchall()
                aps = []
                for row in rows:
                    ap = dict(row)
                    bssid_file_name = ap['bssid'].replace(":", "-")
                    
                    essid_raw = ap.get('essid') or 'ukryta'
                    essid_safe = "".join([c for c in str(essid_raw) if c.isalnum() or c in ('_', '-')]).strip()
                    if not essid_safe:
                        essid_safe = "ukryta"
                    
                    pcap_name = f"{essid_safe}_{bssid_file_name}.pcap"
                    hash_name = f"{essid_safe}_{bssid_file_name}.hc22000"
                    
                    ap['pcap_exists'] = os.path.exists(os.path.join('handshakes', pcap_name))
                    ap['hash_exists'] = os.path.exists(os.path.join('handshakes', hash_name))
                    ap['pcap_filename'] = pcap_name
                    ap['hash_filename'] = hash_name
                    aps.append(ap)
                
        return web.json_response(aps)
