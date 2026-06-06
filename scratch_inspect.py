import requests
import json
try:
    print("Querying Bettercap API...")
    r = requests.get('http://192.168.2.108:8081/api/session', auth=('kali', 'kali'), timeout=5)
    data = r.json()
    aps = data.get('wifi', {}).get('aps', [])
    print(f"Total APs in Bettercap session: {len(aps)}")
    if aps:
        # Find one AP that has clients to see its structure
        ap_with_clients = next((ap for ap in aps if ap.get('clients')), aps[0])
        print("Keys of AP:", list(ap_with_clients.keys()))
        print("Sample AP Data:")
        print(json.dumps(ap_with_clients, indent=2))
    else:
        print("No APs found.")
except Exception as e:
    print("Error:", e)
