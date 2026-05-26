from aiohttp import web
import aiosqlite
import json
import os

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
    <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #030704;
            --terminal-green: #39ff14;
            --terminal-green-dim: #1f940b;
            --terminal-green-glow: rgba(57, 255, 20, 0.45);
            --terminal-bg-card: #060e07;
            --border-color: #39ff14;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg-color);
            color: var(--terminal-green);
            font-family: 'Share Tech Mono', monospace;
            min-height: 100vh;
            padding: 20px;
            display: flex;
            flex-direction: column;
            position: relative;
            text-shadow: 0 0 4px var(--terminal-green-glow);
            overflow-x: hidden;
        }

        /* CRT Scanlines Overlay */
        body::before {
            content: " ";
            display: block;
            position: fixed;
            top: 0; left: 0; bottom: 0; right: 0;
            background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.15) 50%), linear-gradient(90deg, rgba(255, 0, 0, 0.04), rgba(0, 255, 0, 0.01), rgba(0, 0, 255, 0.04));
            z-index: 9999;
            background-size: 100% 4px, 6px 100%;
            pointer-events: none;
        }

        /* Blinking terminal cursor */
        .cursor {
            display: inline-block;
            width: 8px;
            height: 15px;
            background-color: var(--terminal-green);
            margin-left: 4px;
            animation: blink 1s step-end infinite;
            box-shadow: 0 0 4px var(--terminal-green-glow);
        }

        @keyframes blink {
            from, to { background-color: transparent; }
            50% { background-color: var(--terminal-green); }
        }

        /* Main Terminal Window Frame */
        .terminal-window {
            border: 2px solid var(--border-color);
            background: var(--terminal-bg-card);
            border-radius: 8px;
            box-shadow: 0 0 25px rgba(57, 255, 20, 0.15);
            flex-grow: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            max-width: 1400px;
            width: 100%;
            margin: 0 auto;
        }

        /* Terminal Window Top Bar */
        .terminal-header {
            background-color: var(--terminal-green-dim);
            color: var(--bg-color);
            padding: 8px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-weight: bold;
            font-size: 0.9rem;
            text-shadow: none;
            border-bottom: 2px solid var(--border-color);
        }

        .header-dots {
            display: flex;
            gap: 6px;
        }

        .dot {
            width: 10px;
            height: 10px;
            border: 1px solid var(--bg-color);
            border-radius: 50%;
        }

        .dot.fill {
            background-color: var(--bg-color);
        }

        /* Large ASCII Art Logo Banner */
        .ascii-banner {
            padding: 20px;
            text-align: center;
            white-space: pre;
            font-size: 0.65vw;
            line-height: 1.2;
            border-bottom: 1px dashed var(--border-color);
            overflow-x: auto;
        }

        @media (max-width: 768px) {
            .ascii-banner {
                font-size: 5px;
            }
        }

        /* Dashboard Main Layout */
        .dashboard-container {
            display: grid;
            grid-template-columns: 360px 1fr;
            flex-grow: 1;
        }

        @media (max-width: 950px) {
            .dashboard-container {
                grid-template-columns: 1fr;
            }
        }

        /* Left Side: Pwnagotchi ASCII Screen */
        .pwn-panel {
            padding: 25px;
            border-right: 1px dashed var(--border-color);
            display: flex;
            flex-direction: column;
            gap: 25px;
        }

        @media (max-width: 950px) {
            .pwn-panel {
                border-right: none;
                border-bottom: 1px dashed var(--border-color);
            }
        }

        /* Pwnagotchi LCD Screen Border */
        .pwn-lcd {
            border: 1px solid var(--border-color);
            padding: 15px;
            background-color: #020502;
            display: flex;
            flex-direction: column;
            gap: 15px;
            position: relative;
        }

        .lcd-title {
            text-align: center;
            border-bottom: 1px dashed var(--border-color);
            padding-bottom: 5px;
            font-size: 0.85rem;
        }

        .lcd-face-container {
            height: 100px;
            display: flex;
            justify-content: center;
            align-items: center;
            font-size: 2.5rem;
            font-weight: bold;
        }

        .lcd-face {
            display: inline-block;
            animation: bounce 4s ease-in-out infinite;
        }

        @keyframes bounce {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-5px); }
        }

        .lcd-status {
            font-size: 0.85rem;
            text-align: center;
            border-top: 1px dashed var(--border-color);
            padding-top: 8px;
            min-height: 40px;
            display: flex;
            justify-content: center;
            align-items: center;
        }

        /* ASCII Box Cards */
        .ascii-box {
            border: 1px solid var(--border-color);
            padding: 15px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .ascii-box-title {
            font-size: 0.75rem;
            text-transform: uppercase;
            color: var(--terminal-green-dim);
            margin-bottom: 4px;
        }

        .stat-line {
            display: flex;
            justify-content: space-between;
            font-size: 1.1rem;
        }

        .stat-value {
            font-weight: bold;
        }

        /* Right Side: Explorer Panel */
        .explorer-panel {
            padding: 25px;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        .explorer-title {
            font-size: 1.3rem;
            border-bottom: 1px dashed var(--border-color);
            padding-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        /* ASCII View Toggles */
        .view-toggle-row {
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
        }

        .toggle-btn {
            background: transparent;
            border: none;
            color: var(--terminal-green-dim);
            font-family: inherit;
            font-size: 1.1rem;
            font-weight: bold;
            cursor: pointer;
            padding: 5px 10px;
            transition: all 0.2s ease;
            text-shadow: 0 0 2px var(--terminal-green-glow);
            outline: none;
        }

        .toggle-btn:hover {
            color: var(--terminal-green);
            text-shadow: 0 0 6px var(--terminal-green-glow);
        }

        .toggle-btn.active {
            color: #ffffff;
            text-shadow: 0 0 8px #ffffff, 0 0 12px var(--terminal-green-glow);
        }

        /* Inputs and Selects (ASCII Terminal Box style) */
        .controls-row {
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
        }

        .search-wrapper {
            flex-grow: 1;
            display: flex;
            border: 1px solid var(--border-color);
            background: #010301;
        }

        .search-prompt {
            padding: 10px;
            background: var(--terminal-green-dim);
            color: var(--bg-color);
            font-weight: bold;
            text-shadow: none;
        }

        .search-input {
            width: 100%;
            background: transparent;
            border: none;
            color: var(--terminal-green);
            padding: 10px;
            font-family: inherit;
            font-size: 0.95rem;
            outline: none;
            text-shadow: 0 0 4px var(--terminal-green-glow);
        }

        .filter-select {
            background: #010301;
            border: 1px solid var(--border-color);
            color: var(--terminal-green);
            font-family: inherit;
            font-size: 0.95rem;
            padding: 10px 15px;
            outline: none;
            cursor: pointer;
            text-shadow: 0 0 4px var(--terminal-green-glow);
        }

        .filter-select option {
            background-color: var(--bg-color);
            color: var(--terminal-green);
        }

        /* ASCII-styled Table */
        .table-wrapper {
            overflow-x: auto;
            border: 1px solid var(--border-color);
            background: #010301;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.9rem;
        }

        th {
            background-color: rgba(57, 255, 20, 0.06);
            color: var(--terminal-green);
            padding: 12px 15px;
            border-bottom: 2px solid var(--border-color);
            font-weight: bold;
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        td {
            padding: 12px 15px;
            border-bottom: 1px dashed rgba(57, 255, 20, 0.25);
        }

        tr:last-child td {
            border-bottom: none;
        }

        tr:hover {
            background-color: rgba(57, 255, 20, 0.03);
        }

        /* ASCII Command Buttons */
        .cmd-btn {
            color: var(--terminal-green);
            text-decoration: none;
            font-weight: bold;
            display: inline-block;
            transition: all 0.2s ease;
        }

        .cmd-btn:hover {
            color: #ffffff;
            text-shadow: 0 0 8px #ffffff;
        }

        .empty-state {
            padding: 40px;
            text-align: center;
            color: var(--terminal-green-dim);
            font-style: italic;
        }

        /* Badges */
        .status-tag {
            font-weight: bold;
        }

        .status-tag::before {
            content: "[";
            color: var(--terminal-green-dim);
        }

        .status-tag::after {
            content: "]";
            color: var(--terminal-green-dim);
        }

        .status-tag.captured {
            color: #ffffff;
            text-shadow: 0 0 6px var(--terminal-green-glow);
        }

        .status-tag.new {
            color: var(--terminal-green-dim);
        }

        /* Footer */
        .terminal-footer {
            border-top: 2px solid var(--border-color);
            padding: 12px 20px;
            text-align: center;
            font-size: 0.8rem;
            color: var(--terminal-green-dim);
            background: rgba(57, 255, 20, 0.02);
        }
    </style>
</head>
<body>
    <div class="terminal-window">
        <!-- Window Title Bar -->
        <div class="terminal-header">
            <div class="header-dots">
                <div class="dot fill"></div>
                <div class="dot"></div>
                <div class="dot"></div>
            </div>
            <span>bettercup@kali-raspberrypi:~</span>
            <span>SYS: ACTIVE</span>
        </div>

        <!-- ASCII Banner Logo -->
        <div class="ascii-banner">
 ___  ____ ____ ___ ____ ____ ____ _  _ ___     ____ ____ _  _ ____ ____ _    ____ 
 |__] |___  |    |  |___ |__/ |    |  | |__]    |    |  | |\ | [__  |  | |    |___ 
 |__] |___  |    |  |___ |  \ |___ |__| |       |___ |__| | \| ___] |__| |___ |___ 
                                                                                   
        </div>

        <!-- Dashboard Layout -->
        <div class="dashboard-container">
            <!-- Left Panel -->
            <div class="pwn-panel">
                <!-- LCD Box -->
                <div class="pwn-lcd">
                    <div class="lcd-title">--- PWNAGOTCHI MONITOR ---</div>
                    <div class="lcd-face-container">
                        <img id="pwn-face-img" src="" alt="Face" style="max-height: 80px; image-rendering: pixelated; filter: drop-shadow(0 0 4px var(--terminal-green)); display: none;">
                        <span class="lcd-face" id="pwn-face">(o_O)</span>
                    </div>
                    <div class="lcd-status" id="pwn-status">Inicjalizacja...</div>
                    <div style="font-size: 0.75rem; text-align: center; color: var(--terminal-green-dim); font-weight: bold; border-top: 1px dashed var(--border-color); padding-top: 5px;">
                        [ HACK THE PLANET ]
                    </div>
                </div>

                <!-- Stats Box -->
                <div class="ascii-box">
                    <div class="ascii-box-title">/sys/class/network/wlan1</div>
                    <div class="stat-line">
                        <span>Liczba AP:</span>
                        <span class="stat-value" id="stat-total">0</span>
                    </div>
                    <div class="stat-line">
                        <span>Zlapane :</span>
                        <span class="stat-value" id="stat-captured">0</span>
                    </div>
                    <div class="stat-line">
                        <span>Skuteczn:</span>
                        <span class="stat-value" id="stat-rate">0.0%</span>
                    </div>
                </div>

                <!-- System Info Box -->
                <div class="ascii-box">
                    <div class="ascii-box-title">/etc/systemd/wifi_scanner</div>
                    <div class="stat-line" style="font-size: 0.85rem;">
                        <span>NODE:</span>
                        <span>KALI-PI-0-2W</span>
                    </div>
                    <div class="stat-line" style="font-size: 0.85rem;">
                        <span>PORT:</span>
                        <span>8080/TCP</span>
                    </div>
                </div>
            </div>

            <!-- Right Panel -->
            <div class="explorer-panel">
                <h2 class="explorer-title" id="explorer-title">
                    &gt; SELECT * FROM active_networks;
                </h2>

                <!-- View Switcher -->
                <div class="view-toggle-row">
                    <button class="toggle-btn active" id="btn-view-active" onclick="switchView('active')">[ ACTIVE NETWORKS ]</button>
                    <button class="toggle-btn" id="btn-view-database" onclick="switchView('database')">[ ALL HANDSHAKES ]</button>
                </div>

                <!-- Search and Filters -->
                <div class="controls-row">
                    <div class="search-wrapper">
                        <span class="search-prompt">kali@pi:$</span>
                        <input type="text" class="search-input" id="search-bar" placeholder="grep 'nazwa/bssid/producent'...">
                    </div>
                    <select class="filter-select" id="status-filter">
                        <option value="">ALL_NETWORKS</option>
                        <option value="captured">CAPTURED_ONLY</option>
                        <option value="new">NEW_ONLY</option>
                    </select>
                </div>

                <!-- Console Table Output -->
                <div class="table-wrapper">
                    <table id="networks-table">
                        <thead>
                            <tr>
                                <th>SIGNAL</th>
                                <th>BSSID</th>
                                <th>ESSID</th>
                                <th>CH</th>
                                <th>ENC</th>
                                <th>CLIENTS</th>
                                <th>ATK</th>
                                <th>STATUS</th>
                                <th>DOWNLOADS</th>
                            </tr>
                        </thead>
                        <tbody id="networks-tbody">
                            <tr>
                                <td colspan="9" class="empty-state">Ladowanie rekordow...</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- Footer -->
        <div class="terminal-footer">
            [+] System asynchroniczny BetterCup v1.0.0 (aiosqlite + aiohttp) | Sesja aktywna<span class="cursor"></span>
        </div>
    </div>

    <script>
        const searchBar = document.getElementById('search-bar');
        const statusFilter = document.getElementById('status-filter');
        const networksTbody = document.getElementById('networks-tbody');

        const statTotal = document.getElementById('stat-total');
        const statCaptured = document.getElementById('stat-captured');
        const statRate = document.getElementById('stat-rate');

        const pwnFace = document.getElementById('pwn-face');
        const pwnStatus = document.getElementById('pwn-status');

        const pwnFaceImg = document.getElementById('pwn-face-img');

        let currentView = 'active';

        // Mappings from ASCII states to Hackers Movie theme PNG names
        const faceNameMap = {
            "(o_O)": "AWAKE",
            "(>_<)": "INTENSE",
            "(^_^)": "HAPPY",
            "(X_X)": "SAD"
        };

        // Render RSSI to gorgeous green retro bars
        function getRSSIBar(rssi) {
            let bars = "░░░░░";
            let color = "var(--terminal-green-dim)";
            
            if (rssi >= -60) {
                bars = "█████";
                color = "#ffffff";
            } else if (rssi >= -70) {
                bars = "████░";
                color = "var(--terminal-green)";
            } else if (rssi >= -80) {
                bars = "███░░";
                color = "var(--terminal-green)";
            } else if (rssi >= -90) {
                bars = "██░░░";
                color = "var(--terminal-green-dim)";
            } else {
                bars = "█░░░░";
                color = "var(--terminal-green-dim)";
            }
            return `<span style="color: ${color}; font-weight: bold; letter-spacing: 1px;">${bars}</span> <span style="font-size: 0.8rem; color: var(--terminal-green-dim); font-weight: bold;">[${rssi} dBm]</span>`;
        }

        // Handle View Switching
        function switchView(view) {
            currentView = view;
            
            // Toggle active styling
            document.getElementById('btn-view-active').classList.toggle('active', view === 'active');
            document.getElementById('btn-view-database').classList.toggle('active', view === 'database');
            
            // Update Terminal SQL Title
            const titleEl = document.getElementById('explorer-title');
            if (view === 'active') {
                titleEl.innerHTML = '&gt; SELECT * FROM active_networks;';
            } else {
                titleEl.innerHTML = '&gt; SELECT * FROM handshakes;';
            }
            
            // Re-fetch instantly
            fetchAPs();
        }

        // Fetch Stats
        async function fetchStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();
                
                statTotal.innerText = data.total;
                statCaptured.innerText = data.captured;
                
                const rate = data.total > 0 ? ((data.captured / data.total) * 100).toFixed(1) : 0;
                statRate.innerText = rate + '%';

                pwnStatus.innerText = data.action;
                
                // Mapped image handling
                const faceCode = data.face;
                const mappedName = faceNameMap[faceCode] || "AWAKE";
                const imgUrl = `https://github.com/roodriiigooo/PWNAGOTCHI-CUSTOM-FACES-MOD/raw/main/custom-themes/hackersMovie/_faces/${mappedName}.png`;
                
                pwnFaceImg.src = imgUrl;
                pwnFaceImg.onload = () => {
                    pwnFaceImg.style.display = 'block';
                    pwnFace.style.display = 'none';
                };
                pwnFaceImg.onerror = () => {
                    // Fallback to ASCII text if offline or GitHub is unreachable
                    pwnFaceImg.style.display = 'none';
                    pwnFace.style.display = 'inline-block';
                    pwnFace.innerText = faceCode;
                };

            } catch (err) {
                console.error("Blad API stats:", err);
                pwnFaceImg.style.display = 'none';
                pwnFace.style.display = 'inline-block';
                pwnFace.innerText = "(X_X)";
                pwnStatus.innerText = "CRITICAL_CONNECTION_ERROR";
            }
        }

        // Fetch APs
        async function fetchAPs() {
            try {
                const search = encodeURIComponent(searchBar.value);
                const status = statusFilter.value;
                const res = await fetch(`/api/aps?view=${currentView}&search=${search}&status=${status}`);
                const aps = await res.json();

                // Rebuild Thread headers
                const thead = document.getElementById('networks-table').querySelector('thead');
                if (currentView === 'active') {
                    thead.innerHTML = `
                        <tr>
                            <th>SIGNAL</th>
                            <th>BSSID</th>
                            <th>ESSID</th>
                            <th>CH</th>
                            <th>ENC</th>
                            <th>CLIENTS</th>
                            <th>ATK</th>
                            <th>STATUS</th>
                            <th>DOWNLOADS</th>
                        </tr>
                    `;
                } else {
                    thead.innerHTML = `
                        <tr>
                            <th>BSSID</th>
                            <th>ESSID</th>
                            <th>VENDOR</th>
                            <th>STATUS</th>
                            <th>LAST_SEEN</th>
                            <th>DOWNLOADS</th>
                        </tr>
                    `;
                }

                networksTbody.innerHTML = '';

                if (aps.length === 0) {
                    const colSpan = currentView === 'active' ? 9 : 6;
                    networksTbody.innerHTML = `<tr><td colspan="${colSpan}" class="empty-state">-- Brak wynikow wyszukiwania --</td></tr>`;
                    return;
                }

                aps.forEach(ap => {
                    const tr = document.createElement('tr');
                    
                    const isCaptured = ap.status.includes('przechwycono');
                    const statusClass = isCaptured ? 'captured' : 'new';
                    const statusText = isCaptured ? 'CAPTURED' : 'NEW';

                    // Prepare download buttons using retro terminal styling [ PCAP ]
                    let downloadHtml = '<span style="color: var(--terminal-green-dim); font-size: 0.8rem;">[ NONE ]</span>';
                    if (isCaptured) {
                        downloadHtml = `<div style="display: flex; gap: 12px;">`;
                        if (ap.pcap_exists) {
                            downloadHtml += `<a href="/handshakes/${ap.pcap_filename}" class="cmd-btn" download>[ PCAP ]</a>`;
                        }
                        if (ap.hash_exists) {
                            downloadHtml += `<a href="/handshakes/${ap.hash_filename}" class="cmd-btn" download style="color: #ffffff;">[ 22000 ]</a>`;
                        }
                        downloadHtml += `</div>`;
                    }

                    if (currentView === 'active') {
                        const rssiHtml = getRSSIBar(ap.rssi);
                        const chHtml = `<span style="font-weight: bold; color: var(--terminal-green-dim);">[CH ${ap.channel || '?'}]</span>`;
                        
                        let encText = (ap.encryption || 'WPA2').toUpperCase();
                        // Simplify encryption text to fit terminal
                        if (encText.includes('WPA3')) encText = 'WPA3';
                        else if (encText.includes('WPA2')) encText = 'WPA2';
                        else if (encText.includes('WEP')) encText = 'WEP';
                        else if (encText.includes('OPEN')) encText = 'OPEN';
                        const encHtml = `<span style="font-size: 0.85rem; font-weight: bold;">${encText}</span>`;
                        
                        let clientsText = `<span style="color: var(--terminal-green-dim);">[0 CLI]</span>`;
                        if (ap.client_count > 0) {
                            clientsText = `<span style="color: #ffffff; font-weight: bold; text-shadow: 0 0 6px var(--terminal-green-glow);">[${ap.client_count} CLI]</span>`;
                        }
                        
                        const atkText = `<span style="color: var(--terminal-green-dim);">[${ap.liczba_atakow_deauth || 0}/${ap.liczba_atakow_pmkid || 0}]</span>`;

                        tr.innerHTML = `
                            <td>${rssiHtml}</td>
                            <td style="font-weight: bold;">${ap.bssid}</td>
                            <td style="font-weight: bold; color: #ffffff;">${ap.essid || '&lt;ukryty&gt;'}</td>
                            <td>${chHtml}</td>
                            <td>${encHtml}</td>
                            <td>${clientsText}</td>
                            <td>${atkText}</td>
                            <td><span class="status-tag ${statusClass}">${statusText}</span></td>
                            <td>${downloadHtml}</td>
                        `;
                    } else {
                        tr.innerHTML = `
                            <td style="font-weight: bold;">${ap.bssid}</td>
                            <td style="font-weight: bold; color: #ffffff;">${ap.essid || '&lt;ukryty&gt;'}</td>
                            <td>${ap.vendor || 'UNKNOWN'}</td>
                            <td><span class="status-tag ${statusClass}">${statusText}</span></td>
                            <td style="font-size: 0.85rem;">${ap.last_seen || '-'}</td>
                            <td>${downloadHtml}</td>
                        `;
                    }
                    networksTbody.appendChild(tr);
                });
            } catch (err) {
                console.error("Blad API APs:", err);
                const colSpan = currentView === 'active' ? 9 : 6;
                networksTbody.innerHTML = `<tr><td colspan="${colSpan}" class="empty-state" style="color: #ff007f;">SYSTEM_DATABASE_IO_ERROR</td></tr>`;
            }
        }

        let debounceTimer;
        searchBar.addEventListener('input', () => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(fetchAPs, 300);
        });

        statusFilter.addEventListener('change', fetchAPs);

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

        data = {
            "total": total,
            "captured": captured,
            "action": action,
            "face": face
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
