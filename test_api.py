import paramiko
import json

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('192.168.2.108', username='kali', password='kali')

stdin, stdout, stderr = client.exec_command('curl -s -u kali:kali http://127.0.0.1:8081/api/session')
out = stdout.read()
try:
    data = json.loads(out.decode('utf-8'))
    aps = data.get('wifi', {}).get('aps', [])
    print(f"Found {len(aps)} APs.")
    for ap in aps[:3]:
        print("AP KEYS:", ap.keys())
        # Print anything that looks like GPS
        for k, v in ap.items():
            if 'gps' in k.lower() or 'lat' in k.lower() or 'lon' in k.lower():
                print(f"  {k} = {v}")
except Exception as e:
    print("Error parsing JSON:", e)
