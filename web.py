from aiohttp import web
import aiosqlite
import json
import os
import psutil
from datetime import datetime
import io
import base64
import matplotlib
matplotlib.use('Agg')
from matplotlib.figure import Figure

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
        .modal {
            display: none; position: fixed; z-index: 1000; left: 0; top: 0;
            width: 100%; height: 100%; overflow: auto; background-color: rgba(0,0,0,0.8);
        }
        .modal-content {
            background-color: #111; margin: 10% auto; padding: 20px;
            border: 1px solid #00ff00; width: 80%; max-width: 600px;
            color: #00ff00; font-family: monospace;
        }
        .close {
            color: #00ff00; float: right; font-size: 28px; font-weight: bold; cursor: pointer;
        }
        .close:hover { color: #ffffff; }
        .details-table th { width: 40%; text-align: left; }
        .details-table td { word-break: break-all; }
    </style>
</head>
<body>
    <div id="apModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="document.getElementById('apModal').style.display='none'">&times;</span>
            <h2 id="modal-title" style="border-bottom:1px solid #00ff00; margin-top:0;">Szczegóły Sieci</h2>
            <table class="details-table" style="width: 100%; margin-top: 15px;">
                <tbody id="modal-body">
                </tbody>
            </table>
            <div id="modal-actions" style="margin-top: 20px; text-align: right;"></div>
        </div>
    </div>
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
            <strong style="color: #1f940b;">CPU:</strong> <span id="stat-cpu" style="color: #ffffff; font-weight: bold;">0.0%</span>
        </span>
        <span class="stat-sep">|</span>
        <span class="stat-group">
            <strong style="color: #1f940b;">RAM:</strong> <span id="stat-ram" style="color: #ffffff; font-weight: bold;">0.0%</span>
        </span>
        <span class="stat-sep">|</span>
        <span class="stat-group">
            <strong style="color: #1f940b;">TEMPO:</strong> <span id="stat-discovery-rate" style="color: #00ff00; font-weight: bold;">—</span>
        </span>
        <span class="stat-sep">|</span>
        <span id="stat-datetime" style="color: #666666; font-family: monospace; white-space: nowrap;">-</span>
    </div>

    <h2>Widok: <span id="view-title">Aktywne sieci</span></h2>
    
    <div class="control-panel">
        <button id="btn-view-active" class="active" onclick="switchView('active')">[ AKTYWNE SIECI ]</button>
        <button id="btn-view-database" onclick="switchView('database')">[ BAZA DANYCH ]</button>
        <button id="btn-view-banned" onclick="switchView('banned')">[ ZBANOWANE ]</button>
        <button id="btn-view-stats" onclick="switchView('stats')">[ STATYSTYKI ]</button>
        
        <input type="text" id="search-bar" placeholder="Szukaj (BSSID, ESSID)..." style="flex-grow: 1;">
        
        <select id="status-filter">
            <option value="">Wszystkie statusy</option>
            <option value="captured">Tylko przechwycone</option>
            <option value="new">Tylko nowe</option>
        </select>
        
        <label id="filter-today-container" style="display: none; align-items: center; color: #fff; cursor: pointer; user-select: none;">
            <input type="checkbox" id="filter-today" style="margin-right: 5px;"> Tylko dzisiejsze
        </label>
        
        <div id="pagination" style="display: none; align-items: center; gap: 10px;">
            <button id="btn-prev-page" onclick="changePage(-1)">&#8592;</button>
            <span id="page-info" style="color: #ffffff; font-weight: bold;">Str. 1</span>
            <button id="btn-next-page" onclick="changePage(1)">&#8594;</button>
        </div>
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

    <!-- Widok Statystyk -->
    <div id="stats-view" style="display: none; padding: 20px;">
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
            <div style="background-color: rgba(255, 255, 255, 0.4); padding: 15px; border-radius: 8px; text-align: center;">
                <h3 style="margin-top: 0; color: #000000;">Nowe Sieci (Ostatnie 14 Dni)</h3>
                <img id="chart-dates" src="" style="max-width: 100%; height: auto; display: none;" />
                <div id="chart-dates-loading" style="color: #666;">Generowanie wykresu...</div>
            </div>
            <div style="padding: 15px; border: 1px solid #333; border-radius: 8px; text-align: left;">
                <h3 style="margin-top: 0; color: #00ff00; border-bottom: 1px solid #333; padding-bottom: 10px;">Producenci (Wszyscy)</h3>
                <pre id="text-vendors" style="display: none; color: #00ff00; font-family: monospace; font-size: 14px; max-height: 380px; overflow-y: auto; margin: 0;"></pre>
                <div id="chart-vendors-loading" style="color: #666; font-family: monospace;">Ładowanie danych...</div>
            </div>
        </div>
    </div>

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
        let currentPage = 1;
        let sortCol = 'default';
        let sortDir = 'desc';

        function setSort(col) {
            if (sortCol === col) {
                sortDir = sortDir === 'asc' ? 'desc' : 'asc';
            } else {
                sortCol = col;
                sortDir = 'asc';
            }
            fetchAPs();
        }

        function getSortIcon(col) {
            if (sortCol !== col) return ' <span style="color:#555">⇅</span>';
            return sortDir === 'asc' ? ' <span style="color:#00ff00">↑</span>' : ' <span style="color:#00ff00">↓</span>';
        }


        function switchView(view) {
            currentView = view;
            currentPage = 1;
            const pageInfo = document.getElementById('page-info');
            if (pageInfo) pageInfo.innerText = `Str. ${currentPage}`;
            
            document.getElementById('btn-view-active').classList.toggle('active', view === 'active');
            document.getElementById('btn-view-database').classList.toggle('active', view === 'database');
            document.getElementById('btn-view-banned').classList.toggle('active', view === 'banned');
            document.getElementById('btn-view-stats').classList.toggle('active', view === 'stats');
            
            const paginationEl = document.getElementById('pagination');
            if (paginationEl) paginationEl.style.display = view === 'database' ? 'flex' : 'none';
            
            // Pokaż/ukryj odpowiednie elementy
            document.getElementById('networks-table').style.display = view === 'stats' ? 'none' : 'table';
            searchBar.style.display = view === 'stats' ? 'none' : 'block';
            statusFilter.style.display = (view === 'stats' || view === 'banned') ? 'none' : 'block';
            
            const filterTodayEl = document.getElementById('filter-today-container');
            if (filterTodayEl) filterTodayEl.style.display = view === 'database' ? 'flex' : 'none';
            
            document.getElementById('stats-view').style.display = view === 'stats' ? 'block' : 'none';
            
            if (view === 'active') {
                viewTitle.innerText = 'Aktywne sieci (w locie)';
                fetchAPs();
            } else if (view === 'database') {
                viewTitle.innerText = 'Zapisane w bazie';
                fetchAPs();
            } else if (view === 'banned') {
                viewTitle.innerText = 'Zbanowane sieci';
                fetchAPs();
            } else if (view === 'stats') {
                viewTitle.innerText = 'Statystyki i Wykresy';
                fetchDashboardStats();
            }
        }
        
        function changePage(delta) {
            const btnNext = document.getElementById('btn-next-page');
            if (delta === 1 && btnNext && btnNext.disabled) return;
            const btnPrev = document.getElementById('btn-prev-page');
            if (delta === -1 && btnPrev && btnPrev.disabled) return;
            
            if (currentPage + delta > 0) {
                currentPage += delta;
                document.getElementById('page-info').innerText = `Str. ${currentPage}`;
                fetchAPs();
            }
        }

        async function showApDetails(bssid) {
            try {
                const res = await fetch(`/api/ap?bssid=${bssid}`);
                const data = await res.json();
                if (data.error) {
                    alert('Błąd: ' + data.error);
                    return;
                }
                
                document.getElementById('modal-title').innerText = `Szczegóły Sieci: ${data.essid || '<ukryty>'}`;
                
                let html = '';
                for (const [key, value] of Object.entries(data)) {
                    let displayValue = value !== null ? value : '-';
                    
                    // Formatowanie czasu UNIX (last_attacked_at jest w sekundach)
                    if (key === 'last_attacked_at') {
                        if (value > 0) {
                            displayValue = new Date(value * 1000).toLocaleString('pl-PL');
                        } else {
                            displayValue = 'Nigdy';
                        }
                    }
                    
                    html += `<tr><th style="color: #1f940b;">${key.toUpperCase()}</th><td>${displayValue}</td></tr>`;
                }
                
                document.getElementById('modal-body').innerHTML = html;
                document.getElementById('modal-actions').innerHTML = `<button onclick="deleteNetwork('${data.bssid}')" style="background-color: #000; color: #ff3333; border: none; padding: 6px 12px; font-weight: bold; cursor: pointer; transition: all 0.2s; font-family: monospace;" onmouseover="this.style.backgroundColor='#ff3333'; this.style.color='#000';" onmouseout="this.style.backgroundColor='#000'; this.style.color='#ff3333';">USUŃ SIEĆ Z BAZY</button>`;
                document.getElementById('apModal').style.display = 'block';
            } catch (err) {
                console.error(err);
                alert('Błąd podczas pobierania szczegółów.');
            }
        }

        async function deleteNetwork(bssid) {
            if (!confirm('CZY NA PEWNO CHCESZ CAŁKOWICIE USUNĄĆ TĘ SIEĆ Z BAZY?\\n\\nUsunięty zostanie tylko rekord z bazy danych. Pliki pcap pozostaną na dysku.')) return;
            try {
                const res = await fetch(`/api/delete?bssid=${bssid}`, { method: 'POST' });
                if (res.ok) {
                    document.getElementById('apModal').style.display = 'none';
                    fetchAPs();
                } else {
                    alert('Wystąpił błąd podczas usuwania sieci.');
                }
            } catch(err) {
                console.error(err);
                alert('Błąd podczas nawiązywania połączenia z serwerem.');
            }
        }

        async function resetScore(bssid) {
            if (!confirm('Zresetować liczniki błędów i ponowić ataki dla ' + bssid + '?')) return;
            try {
                const res = await fetch(`/api/reset_attacks?bssid=${bssid}`, { method: 'POST' });
                if (res.ok) {
                    fetchAPs();
                } else {
                    alert('Wystąpił błąd podczas resetowania.');
                }
            } catch(err) {
                console.error(err);
            }
        }

        async function launchOneshot(bssid, essid) {
            const label = essid ? `${essid} (${bssid})` : bssid;
            if (!confirm(`Uruchomić atak WPS Pixie Dust na:\n${label}\n\noneshot.py -i wlan1 -b ${bssid} -K`)) return;
            try {
                const res = await fetch(`/api/oneshot?bssid=${encodeURIComponent(bssid)}`, { method: 'POST' });
                const data = await res.json();
                if (res.ok) {
                    alert(`✅ Atak WPS uruchomiony!\nPID procesu: ${data.pid}\n\nSprawdź logi bettercap / konsolę tmux.`);
                } else {
                    alert(`❌ Błąd: ${data.error || 'Nieznany błąd'}`);
                }
            } catch(err) {
                console.error(err);
                alert('❌ Błąd połączenia z serwerem.');
            }
        }

        async function toggleBan(bssid, isBanned) {
            const endpoint = isBanned ? '/api/unban' : '/api/ban';
            try {
                const res = await fetch(`${endpoint}?bssid=${bssid}`, { method: 'POST' });
                if (res.ok) {
                    fetchAPs();
                } else {
                    alert('Wystąpił błąd podczas zmiany statusu banowania.');
                }
            } catch(err) {
                console.error(err);
            }
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

                // Discovery Rate Tempo Update
                const statDisc = document.getElementById('stat-discovery-rate');
                if (statDisc && data.discovery_rate !== undefined) {
                    const rate = data.discovery_rate;
                    const trend = data.discovery_trend || '\u2014';
                    const sinceLast = data.seconds_since_last;
                    
                    let label = '';
                    let color = '#00ff00';
                    
                    if (sinceLast === null) {
                        // Pierwsza sesja, pusta baza — czekamy na dane
                        label = 'CZEKAM...';
                        color = '#555555';
                    } else if (rate > 0) {
                        label = rate.toFixed(1) + '/min ' + trend;
                        color = '#00ff00'; // zielony — odkrywamy nowe
                    } else if (sinceLast !== null && sinceLast < 300) {
                        // 0 rate ale ostatnia nowa < 5 min temu
                        const mins = Math.floor(sinceLast / 60);
                        const secs = Math.floor(sinceLast % 60);
                        label = '0/min ' + trend + ' (' + mins + ':' + (secs < 10 ? '0' : '') + secs + ' temu)';
                        color = '#ffaa00'; // żółty — cisza ale świeża
                    } else if (sinceLast !== null && sinceLast < 600) {
                        // Cisza 5-10 min
                        const mins = Math.floor(sinceLast / 60);
                        label = '0/min \u25bc (cisza ' + mins + ' min)';
                        color = '#ff3333'; // czerwony — sucho
                    } else {
                        // Cisza > 10 min lub Infinity (same znane sieci, brak nowych)
                        label = '0/min \u2014 (same znane)';
                        color = '#ff3333';
                    }
                    
                    statDisc.innerText = label;
                    statDisc.style.color = color;
                }
                
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
                const today = document.getElementById('filter-today').checked;
                const res = await fetch(`/api/aps?view=${currentView}&search=${search}&status=${status}&today=${today}&page=${currentPage}&sort=${sortCol}&dir=${sortDir}`);
                const aps = await res.json();

                if (currentView === 'database') {
                    const btnNext = document.getElementById('btn-next-page');
                    if (btnNext) {
                        btnNext.disabled = aps.length < 100;
                        btnNext.style.opacity = aps.length < 100 ? '0.5' : '1';
                    }
                    const btnPrev = document.getElementById('btn-prev-page');
                    if (btnPrev) {
                        btnPrev.disabled = currentPage <= 1;
                        btnPrev.style.opacity = currentPage <= 1 ? '0.5' : '1';
                    }
                }

                const thead = document.getElementById('networks-table').querySelector('thead');
                if (currentView === 'active') {
                    thead.innerHTML = `
                        <tr>
                            <th style="width: 40px;">#</th>
                            <th>SIGNAL</th>
                            <th>BRAIN</th>
                            <th>BSSID</th>
                            <th onclick="setSort('essid')" style="cursor: pointer;" title="Sortuj">ESSID${getSortIcon('essid')}</th>
                            <th onclick="setSort('vendor')" style="cursor: pointer;" title="Sortuj">PRODUCENT${getSortIcon('vendor')}</th>
                            <th>CH</th>
                            <th>ENC</th>
                            <th>WPS</th>
                            <th>CLI</th>
                            <th>ATK</th>
                            <th>STATUS</th>
                            <th style="width: 60px; text-align: center;">AKCJE</th>
                        </tr>
                    `;
                } else {
                    thead.innerHTML = `
                        <tr>
                            <th onclick="setSort('id')" style="width: 50px; color: #00ff00; cursor: pointer;" title="Sortuj">ID${getSortIcon('id')}</th>
                            <th>BSSID</th>
                            <th onclick="setSort('essid')" style="cursor: pointer;" title="Sortuj">ESSID${getSortIcon('essid')}</th>
                            <th onclick="setSort('vendor')" style="cursor: pointer;" title="Sortuj">PRODUCENT${getSortIcon('vendor')}</th>
                            <th>ENC</th>
                            <th>GPS</th>
                            <th>STATUS</th>
                            <th onclick="setSort('first_seen')" style="cursor: pointer;" title="Sortuj">DODANO${getSortIcon('first_seen')}</th>
                            <th style="width: 60px; text-align: center;">AKCJE</th>
                        </tr>
                    `;
                }

                networksTbody.innerHTML = '';

                if (aps.length === 0) {
                    const colSpan = currentView === 'active' ? 13 : 9;
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


                    // Color code brain scores (banned=grey, captured=dim, normal=white/green)
                    const scoreColor = (ap.status === 'zbanowany') ? '#555555' : (isCaptured ? '#888' : (ap.score >= -100 ? '#ffffff' : 'var(--terminal-green-dim)'));

                    // Display special labels instead of numeric score
                    const scoreText = isCaptured ? "CRACKED" : (ap.status === 'zbanowany' ? '-' : ap.score);


                    const isBanned = ap.status === 'zbanowany';
                    const banText = isBanned ? '+' : 'x';
                    const banColor = isBanned ? '#00ff00' : '#ff5555';
                    const banTitle = isBanned ? 'Odbanuj sieć (przywróć do skanowania)' : 'Zbanuj sieć (ignoruj)';
                    const banButtonHtml = `<span onclick="toggleBan('${ap.bssid}', ${isBanned})" style="cursor: pointer; color: ${banColor}; font-weight: bold; font-family: monospace; font-size: 1.1rem; padding: 2px 8px; display: inline-block;" title="${banTitle}">${banText}</span>`;
                    const finalStatusText = isBanned ? 'BANNED' : statusText;
                    const finalStatusClass = isBanned ? '' : statusClass;

                    if (currentView === 'active') {
                        const isWpsActive = ap.wps && ap.wps.startsWith('TAK');
                        const wpsColor = isWpsActive ? '#ffaa00' : 'inherit';
                        const wpsWeight = isWpsActive ? 'bold' : 'normal';
                        const wpsCell = isWpsActive
                            ? `<a href="#" onclick="launchOneshot('${ap.bssid}', '${(ap.essid || '').replace(/'/g, '\\&#39;')}'); return false;" style="color: #ffaa00; font-weight: bold; text-decoration: none;" title="Uruchom atak WPS Pixie Dust (oneshot.py)">WPS &#9889;</a>`
                            : `<span style="color: inherit;">NIE</span>`;

                        tr.innerHTML = `
                            <td style="color: #888;">${idx + 1}</td>
                            <td style="font-weight: bold; color: ${rssiColor};">${ap.rssi} dBm</td>
                            <td style="font-weight: bold; color: ${scoreColor}; cursor: pointer; text-decoration: underline;" onclick="resetScore('${ap.bssid}')" title="Kliknij, by zresetować liczniki ataków">[${scoreText}]</td>
                            <td>${ap.bssid}</td>
                            <td class="${statusClass}">${ap.essid || '<ukryty>'}</td>
                            <td style="color: var(--terminal-green-dim); font-size: 0.85rem;">${ap.vendor || 'UNKNOWN'}</td>
                            <td>${ap.channel || '?'}</td>
                            <td>${ap.encryption || 'WPA2'}</td>
                            <td>${wpsCell}</td>
                            <td style="font-weight: ${ap.client_count > 0 ? 'bold' : 'normal'}; color: ${ap.client_count > 0 ? '#ffffff' : 'inherit'};">${ap.client_count}</td>
                            <td>${ap.liczba_atakow_deauth || 0}/${ap.liczba_atakow_pmkid || 0}/<span style="color: ${(ap.liczba_atakow_pixiedust || 0) > 0 ? '#ffaa00' : 'inherit'}; font-weight: ${(ap.liczba_atakow_pixiedust || 0) > 0 ? 'bold' : 'normal'}">${ap.liczba_atakow_pixiedust || 0}</span></td>
                            <td class="${finalStatusClass}">${finalStatusText}</td>
                            <td style="text-align: center;">${banButtonHtml}</td>
                        `;
                    } else {
                        const gpsHtml = (ap.gps_lat && ap.gps_lon) ? `<a href="https://maps.google.com/?q=${ap.gps_lat},${ap.gps_lon}" target="_blank" style="color: #00ff00; text-decoration: none;" title="${ap.gps_lat}, ${ap.gps_lon}">[ MAPA ]</a>` : '-';
                        tr.innerHTML = `
                            <td style="color: #00ff00; font-weight: bold; cursor: pointer; text-decoration: underline;" onclick="showApDetails('${ap.bssid}')" title="Pokaż szczegóły">${ap.id || '-'}</td>
                            <td>${ap.bssid}</td>
                            <td class="${statusClass}">${ap.essid || '<ukryty>'}</td>
                            <td>${ap.vendor || 'UNKNOWN'}</td>
                            <td>${ap.encryption || '-'}</td>
                            <td style="white-space: nowrap;">${gpsHtml}</td>
                            <td class="${finalStatusClass}">${finalStatusText}</td>
                            <td>${ap.first_seen || '-'}</td>
                            <td style="text-align: center;">${banButtonHtml}</td>
                        `;
                    }
                    networksTbody.appendChild(tr);
                });
            } catch (err) {
                console.error(err);
                const colSpan = currentView === 'active' ? 11 : 8;
                networksTbody.innerHTML = `<tr><td colspan="${colSpan}" style="color: red;">BŁĄD ZAPISU BAZY / I/O</td></tr>`;
            }
        }

        let debounceTimer;
        searchBar.addEventListener('input', () => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(fetchAPs, 300);
        });

        statusFilter.addEventListener('change', fetchAPs);
        document.getElementById('filter-today').addEventListener('change', fetchAPs);

        // Spinner animation setup - Restored classic terminal spinner, pure ASCII text, 100% layout stable
        // Note: 4 backslashes in Python source compiles to 2 backslashes in HTML, which JS parses as a single backslash '\'
        let spinnerFrames = ['[|]', '[/]', '[-]', '[\\\\]'];
        let spinnerIndex = 0;
        const statusSpinnerElement = document.getElementById('status-spinner');
        
        setInterval(() => {
            if (statusSpinnerElement) {
                statusSpinnerElement.innerText = spinnerFrames[spinnerIndex];
                spinnerIndex = (spinnerIndex + 1) % spinnerFrames.length;
            }
        }, 150);

        async function fetchDashboardStats() {
            if (currentView !== 'stats') return;
            try {
                // Pokaz ładowanie
                ['dates'].forEach(id => {
                    document.getElementById(`chart-${id}`).style.display = 'none';
                    document.getElementById(`chart-${id}-loading`).style.display = 'block';
                });
                document.getElementById('text-vendors').style.display = 'none';
                document.getElementById('chart-vendors-loading').style.display = 'block';

                const res = await fetch('/api/dashboard_stats');
                const data = await res.json();
                
                // Ustaw obrazki
                if (data.chart_dates) {
                    const img = document.getElementById('chart-dates');
                    img.src = data.chart_dates;
                    img.style.display = 'inline-block';
                    document.getElementById('chart-dates-loading').style.display = 'none';
                }
                if (data.vendors) {
                    const container = document.getElementById('text-vendors');
                    let text = '';
                    for (const v of data.vendors) {
                        text += `[ ${v.count.toString().padStart(4, ' ')} ]  ${v.vendor}\n`;
                    }
                    container.innerText = text;
                    container.style.display = 'block';
                    document.getElementById('chart-vendors-loading').style.display = 'none';
                }
            } catch (err) {
                console.error("Błąd ładowania statystyk:", err);
            }
        }

        fetchStats();
        fetchAPs();
        setInterval(fetchStats, 1000);
        setInterval(() => { if (currentView !== 'stats') fetchAPs(); }, 5000);
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

        # Tempo odkryć nowych sieci (discovery rate)
        try:
            disc_rate, disc_trend, since_last = self.db.get_discovery_rate()
            # float('inf') nie jest poprawnym JSON-em — konwertujemy na dużą liczbę
            if since_last is not None and since_last == float('inf'):
                since_last = 99999
        except Exception:
            disc_rate, disc_trend, since_last = 0.0, '\u2014', None

        data = {
            "total": total,
            "captured": captured,
            "action": action,
            "face": face,
            "cpu": cpu,
            "ram": ram,
            "datetime": now_str,
            "discovery_rate": disc_rate,
            "discovery_trend": disc_trend,
            "seconds_since_last": since_last
        }
        return web.json_response(data)

    async def get_aps(self, request):
        query_params = request.query
        search = query_params.get('search', '').strip().lower()
        status_filter = query_params.get('status', '').strip()
        today_filter = query_params.get('today', 'false') == 'true'
        view = query_params.get('view', 'active').strip()
        try:
            page = int(query_params.get('page', 1))
        except ValueError:
            page = 1
        
        sort_col = query_params.get('sort', 'default').strip()
        sort_dir = query_params.get('dir', 'desc').strip()
        
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
                
            if sort_col == 'essid':
                filtered_aps.sort(key=lambda x: (x.get('essid') or '').lower(), reverse=(sort_dir == 'desc'))
            elif sort_col == 'vendor':
                filtered_aps.sort(key=lambda x: (x.get('vendor') or '').lower(), reverse=(sort_dir == 'desc'))
                
            return web.json_response(filtered_aps)
            
        if view == 'banned':
            async with aiosqlite.connect(self.db_path) as conn:
                conn.row_factory = aiosqlite.Row
                sql = "SELECT id, bssid, essid, vendor, status, first_seen, encryption, gps_lat, gps_lon FROM handshakes WHERE status = 'zbanowany'"
                args = []
                if search:
                    sql += " AND (bssid LIKE ? OR essid LIKE ? OR vendor LIKE ?)"
                    like_str = f"%{search}%"
                    args.extend([like_str, like_str, like_str])
                
                order_clause = "id DESC"
                if sort_col == 'essid':
                    order_clause = f"essid {'DESC' if sort_dir == 'desc' else 'ASC'}"
                elif sort_col == 'vendor':
                    order_clause = f"vendor {'DESC' if sort_dir == 'desc' else 'ASC'}"
                elif sort_col == 'first_seen':
                    order_clause = f"first_seen {'DESC' if sort_dir == 'desc' else 'ASC'}"
                elif sort_col == 'id':
                    order_clause = f"id {'DESC' if sort_dir == 'desc' else 'ASC'}"
                
                sql += f" ORDER BY {order_clause}"
                
                async with conn.execute(sql, args) as cursor:
                    rows = await cursor.fetchall()
                    aps = [dict(row) for row in rows]
                    return web.json_response(aps)
            
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            sql = "SELECT id, bssid, essid, vendor, status, first_seen, encryption, gps_lat, gps_lon FROM handshakes"
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
            
            if today_filter:
                date_str = datetime.now().strftime("%Y-%m-%d")
                conditions.append("first_seen LIKE ?")
                args.append(f"{date_str}%")
            
            if conditions:
                sql += " WHERE " + " AND ".join(conditions)
                
            limit = 100
            offset = (page - 1) * limit
            
            order_clause = "id DESC"
            if sort_col == 'essid':
                order_clause = f"essid {'DESC' if sort_dir == 'desc' else 'ASC'}"
            elif sort_col == 'vendor':
                order_clause = f"vendor {'DESC' if sort_dir == 'desc' else 'ASC'}"
            elif sort_col == 'first_seen':
                order_clause = f"first_seen {'DESC' if sort_dir == 'desc' else 'ASC'}"
            elif sort_col == 'id':
                order_clause = f"id {'DESC' if sort_dir == 'desc' else 'ASC'}"
                
            sql += f" ORDER BY {order_clause} LIMIT {limit} OFFSET {offset}"
            
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

    async def get_ap_details(self, request):
        bssid = request.query.get('bssid', '').strip()
        if not bssid:
            return web.json_response({"error": "No bssid provided"})
            
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT * FROM handshakes WHERE bssid = ?", (bssid,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return web.json_response(dict(row))
                else:
                    return web.json_response({"error": "Network not found"})

    async def reset_attacks(self, request):
        bssid = request.query.get('bssid', '').strip()
        if not bssid:
            return web.json_response({"error": "No bssid provided"}, status=400)
        
        await self.db.reset_attacks(bssid)
        return web.json_response({"status": "ok"})

    async def delete_network(self, request):
        bssid = request.query.get('bssid', '').strip()
        if not bssid:
            return web.json_response({"error": "No bssid provided"}, status=400)
        
        await self.db.delete_ap(bssid)
        return web.json_response({"status": "ok", "message": "Network deleted"})

    async def ban_network(self, request):
        bssid = request.query.get('bssid', '').strip()
        if not bssid:
            return web.json_response({"error": "No bssid provided"}, status=400)
        
        existing = await self.db.get_ap(bssid)
        if not existing:
            active_aps = await self.db.get_active_aps()
            active_ap = next((ap for ap in active_aps if ap['bssid'] == bssid), None)
            if active_ap:
                await self.db.update_ap(
                    bssid=bssid,
                    essid=active_ap.get('essid'),
                    vendor=active_ap.get('vendor'),
                    encryption=active_ap.get('encryption')
                )
            else:
                await self.db.update_ap(bssid=bssid)
        
        await self.db.update_status(bssid, 'zbanowany')
        await self.db.flush()
        return web.json_response({"status": "ok", "message": "Network banned"})

    async def unban_network(self, request):
        bssid = request.query.get('bssid', '').strip()
        if not bssid:
            return web.json_response({"error": "No bssid provided"}, status=400)
        
        await self.db.update_status(bssid, 'nowy')
        await self.db.flush()
        return web.json_response({"status": "ok", "message": "Network unbanned"})

    def _generate_plot_base64(self, fig):
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight', transparent=True, edgecolor='none')
        buf.seek(0)
        img_str = base64.b64encode(buf.read()).decode('utf-8')
        return f"data:image/png;base64,{img_str}"

    def _apply_light_theme(self, ax):
        ax.set_facecolor('none')
        ax.tick_params(colors='black')
        for spine in ax.spines.values():
            spine.set_color('black')
        ax.xaxis.label.set_color('black')
        ax.yaxis.label.set_color('black')
        ax.title.set_color('black')
        ax.yaxis.grid(True, linestyle='-', color='#d1d5db')

    async def get_dashboard_stats(self, request):
        chart_dates = ""
        
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            
            # Vendors (All)
            async with conn.execute("SELECT vendor, COUNT(*) as count FROM handshakes WHERE vendor != '' AND vendor IS NOT NULL GROUP BY vendor ORDER BY count DESC") as cursor:
                vendor_data = [dict(row) for row in await cursor.fetchall()]
                
            # New networks per day (last 14 days)
            async with conn.execute("SELECT substr(first_seen, 1, 10) as date, COUNT(*) as count FROM handshakes WHERE first_seen IS NOT NULL AND first_seen != '' GROUP BY date ORDER BY date DESC LIMIT 14") as cursor:
                date_data_raw = [dict(row) for row in await cursor.fetchall()]
                date_data = list(reversed(date_data_raw))
                if date_data:
                    fig = Figure(figsize=(6, 4), facecolor='none')
                    ax = fig.subplots()
                    self._apply_light_theme(ax)
                    dates = [d['date'][5:] for d in date_data] # MM-DD
                    counts = [d['count'] for d in date_data]
                    ax.plot(dates, counts, color='#2563eb', linestyle='-', linewidth=1.5, zorder=2)
                    ax.scatter(dates, counts, color='#2563eb', edgecolors='black', s=10, zorder=3)
                    ax.set_yscale('log')
                    
                    if counts:
                        max_val = max(counts)
                        ax.axhline(max_val, color='#2563eb', linestyle='--', linewidth=1, alpha=0.6, zorder=1)
                        # Umieszczenie tekstu nad linią po prawej stronie wykresu
                        ax.text(len(dates) - 1, max_val, f' Max: {max_val} ', color='#2563eb', va='bottom', ha='right', fontsize=8, fontweight='bold')

                    from matplotlib.ticker import ScalarFormatter
                    y_formatter = ScalarFormatter()
                    y_formatter.set_scientific(False)
                    ax.yaxis.set_major_formatter(y_formatter)
                    ax.set_title('Nowe sieci (ost. 14 dni)')
                    ax.tick_params(axis='x', rotation=45)
                    for label in ax.get_xticklabels():
                        label.set_ha('right')
                    fig.subplots_adjust(bottom=0.2)
                    chart_dates = self._generate_plot_base64(fig)

        return web.json_response({
            'chart_dates': chart_dates,
            'vendors': vendor_data
        })

    async def run_oneshot(self, request):
        """Uruchamia oneshot.py (atak WPS Pixie Dust) w tle dla podanego BSSID."""
        import asyncio
        bssid = request.query.get('bssid', '').strip()
        if not bssid:
            return web.json_response({'error': 'Brak parametru bssid'}, status=400)

        # Interfejs: użyj wlan1 (strzelec) jeśli dostępny, wpp wlan0
        iface = 'wlan1'

        # Ścieżka do oneshot.py — relatywna do katalogu roboczego skanerb
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'oneshot.py')

        try:
            proc = await asyncio.create_subprocess_exec(
                'python3', script_path,
                '-i', iface,
                '-b', bssid,
                '-K',
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            # Inkrementuj licznik ataków Pixie Dust w bazie
            await self.db.mark_attack(bssid, 'pixiedust')
            await self.db.flush()

            if self.shared_state is not None:
                self.shared_state['action'] = f'[WPS PIXIE DUST] Cel: {bssid}'
            return web.json_response({'status': 'started', 'pid': proc.pid, 'bssid': bssid})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
