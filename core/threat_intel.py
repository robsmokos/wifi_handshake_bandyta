"""
core/threat_intel.py — CVE Lookup po vendorze routera (NVD API 2.0)

Asynchroniczny moduł do pobierania znanych luk (CVE) dla producentów sprzętu
WiFi (Cisco, TP-Link, Netgear, itp.) z publicznego NVD API NIST.

Architektura:
  - LRU Cache w pamięci RAM (klucz: vendor string, TTL: 6h)
  - Bez zewnętrznych zależności (tylko aiohttp który mamy już w projekcie)
  - Bez klucza API (public endpoint, rate limit ~5 req/30s)
  - Bezpieczny timeout i obsługa błędów, nie blokuje głównej pętli asyncio
"""

import asyncio
import logging
import time
import re

log = logging.getLogger(__name__)

# --- Mapowanie skrótów vendorów z Bettercap na nazwy rozpoznawane przez NVD ---
VENDOR_KEYWORD_MAP = {
    "tp-link": "tp-link",
    "tplink": "tp-link",
    "netgear": "netgear",
    "cisco": "cisco",
    "asus": "asus",
    "d-link": "d-link",
    "dlink": "d-link",
    "huawei": "huawei",
    "mikrotik": "mikrotik",
    "ubiquiti": "ubiquiti",
    "zyxel": "zyxel",
    "linksys": "linksys",
    "belkin": "belkin",
    "buffalo": "buffalo",
    "tenda": "tenda",
    "xiaomi": "xiaomi",
    "fritz": "avm",  # AVM FritzBox
    "avm": "avm",
    "technicolor": "technicolor",
    "aruba": "aruba",
    "ruckus": "ruckus",
    "fortinet": "fortinet",
}

# Czas ważności cache (6 godzin) — CVE nie zmieniają się co minutę
CACHE_TTL = 6 * 3600
# Maksymalna liczba wyników CVE na vendora
MAX_CVE_RESULTS = 10


class ThreatIntel:
    """
    Asynchroniczny moduł do lookupów CVE.
    Używaj jako singleton (jedna instancja dla całego procesu).
    """

    def __init__(self):
        # Cache: { normalized_vendor: {"ts": float, "cves": list} }
        self._cache: dict = {}
        self._lock = asyncio.Lock()
        # Semafor: max 2 równoległe żądania do NVD by nie przekroczyć rate limitu
        self._semaphore = asyncio.Semaphore(2)

    def _normalize_vendor(self, vendor_raw: str) -> str | None:
        """
        Zamienia surowy string vendora z Bettercap (np. "TP-LINK TECHNOLOGIES")
        na keyword do wyszukiwania w NVD (np. "tp-link").
        Zwraca None jeśli vendor jest nieznany / pusty.
        """
        if not vendor_raw:
            return None
        v = vendor_raw.lower().strip()
        # Poszukaj dopasowania w mapie (sprawdź każdy klucz jako substring)
        for key, nvd_name in VENDOR_KEYWORD_MAP.items():
            if key in v:
                return nvd_name
        # Słowa generyczne które nie nadają się do wyszukania
        _generic_words = {
            "unknown", "private", "device", "router", "wireless", "network",
            "systems", "limited", "corporation", "technologies", "electronics",
            "group", "other", "local", "home", "generic"
        }
        # Jeśli nie znaleziono w mapie — użyj pierwszego słowa vendora (może coś da)
        # ale tylko jeśli słowo ma sens (min. 4 znaki i nie jest generyczne)
        first_word = re.split(r'[\s,\-_]', v)[0]
        if len(first_word) >= 4 and first_word not in _generic_words:
            return first_word
        return None

    def _is_cache_fresh(self, vendor: str) -> bool:
        entry = self._cache.get(vendor)
        if not entry:
            return False
        return (time.time() - entry["ts"]) < CACHE_TTL

    async def get_cves(self, vendor_raw: str) -> list[dict]:
        """
        Główna metoda publiczna.
        Zwraca listę CVE dla podanego vendora.
        Wynik jest cachowany w RAM przez CACHE_TTL sekund.

        Każdy element listy to dict:
          {
            "id": "CVE-2024-XXXXX",
            "description": "...",
            "severity": "HIGH" | "CRITICAL" | "MEDIUM" | "LOW" | "UNKNOWN",
            "cvss_score": 7.5,   # float lub None
            "published": "2024-01-15",
            "url": "https://nvd.nist.gov/vuln/detail/CVE-..."
          }
        """
        vendor_key = self._normalize_vendor(vendor_raw)
        if not vendor_key:
            return []

        # Sprawdź cache
        async with self._lock:
            if self._is_cache_fresh(vendor_key):
                log.debug(f"[ThreatIntel] Cache HIT dla vendora: {vendor_key}")
                return self._cache[vendor_key]["cves"]

        # Pobierz z NVD API
        log.info(f"[ThreatIntel] Pobieranie CVE dla vendora: {vendor_key} (raw: {vendor_raw})")
        cves = await self._fetch_from_nvd(vendor_key)

        # Zapisz do cache
        async with self._lock:
            self._cache[vendor_key] = {
                "ts": time.time(),
                "cves": cves
            }

        return cves

    async def _fetch_from_nvd(self, vendor_keyword: str) -> list[dict]:
        """
        Pobiera CVE z NVD API 2.0.
        NVD API Public: bez klucza, rate limit = 5 req / 30s rolling window.
        Z kluczem API (nagłówek apiKey) = 50 req / 30s — opcjonalne rozszerzenie.
        """
        try:
            import aiohttp
        except ImportError:
            log.error("[ThreatIntel] Brak biblioteki aiohttp!")
            return []

        # NVD API 2.0 endpoint
        url = "https://services.nvd.nist.gov/rest/json/cves/2.0"
        params = {
            "keywordSearch": vendor_keyword,
            "resultsPerPage": MAX_CVE_RESULTS,
            "startIndex": 0,
        }
        headers = {
            "User-Agent": "BetterCup-ThreatIntel/1.0 (WiFi Security Research)"
        }

        async with self._semaphore:
            try:
                timeout = aiohttp.ClientTimeout(total=15)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, params=params, headers=headers) as resp:
                        if resp.status != 200:
                            log.warning(f"[ThreatIntel] NVD API zwróciło status {resp.status} dla {vendor_keyword}")
                            return []
                        data = await resp.json(content_type=None)
            except asyncio.TimeoutError:
                log.warning(f"[ThreatIntel] Timeout podczas pobierania CVE dla {vendor_keyword}")
                return []
            except Exception as e:
                log.warning(f"[ThreatIntel] Błąd HTTP: {e}")
                return []

        return self._parse_nvd_response(data)

    def _parse_nvd_response(self, data: dict) -> list[dict]:
        """Parsuje odpowiedź NVD API 2.0 do ujednoliconego formatu."""
        result = []
        vulnerabilities = data.get("vulnerabilities", [])

        for vuln in vulnerabilities:
            cve_obj = vuln.get("cve", {})
            cve_id = cve_obj.get("id", "UNKNOWN")

            # Opis (po angielsku)
            descriptions = cve_obj.get("descriptions", [])
            desc = ""
            for d in descriptions:
                if d.get("lang") == "en":
                    desc = d.get("value", "")
                    break
            if not desc and descriptions:
                desc = descriptions[0].get("value", "")

            # Data publikacji
            published_raw = cve_obj.get("published", "")
            published = published_raw[:10] if published_raw else "?"

            # CVSS Score i Severity (V3.1 / V3.0 / V2)
            severity = "UNKNOWN"
            cvss_score = None
            metrics = cve_obj.get("metrics", {})

            # Preferuj CVSSv3.1, potem v3.0, potem v2
            for cvss_key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
                metric_list = metrics.get(cvss_key, [])
                if metric_list:
                    primary = next((m for m in metric_list if m.get("type") == "Primary"), metric_list[0])
                    cvss_data = primary.get("cvssData", {})
                    cvss_score = cvss_data.get("baseScore")
                    severity = cvss_data.get("baseSeverity") or primary.get("baseSeverity", "UNKNOWN")
                    break

            result.append({
                "id": cve_id,
                "description": desc[:300] + "..." if len(desc) > 300 else desc,
                "severity": severity.upper(),
                "cvss_score": cvss_score,
                "published": published,
                "url": f"https://nvd.nist.gov/vuln/detail/{cve_id}"
            })

        # Sortuj: najpierw CRITICAL, potem HIGH, MEDIUM, LOW
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "UNKNOWN": 4}
        result.sort(key=lambda x: severity_order.get(x["severity"], 4))
        return result

    def get_supported_vendors(self) -> list[str]:
        """Zwraca listę obsługiwanych vendorów (do wyświetlenia w UI)."""
        return sorted(set(VENDOR_KEYWORD_MAP.values()))

    def get_cache_stats(self) -> dict:
        """Statystyki cache do debugowania."""
        now = time.time()
        entries = []
        for vendor, entry in self._cache.items():
            age_min = round((now - entry["ts"]) / 60, 1)
            entries.append({
                "vendor": vendor,
                "count": len(entry["cves"]),
                "age_min": age_min,
                "fresh": self._is_cache_fresh(vendor)
            })
        return {"entries": entries, "total": len(entries)}
