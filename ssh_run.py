import paramiko
import sys

host = '192.168.2.108'
user = 'kali'
password = 'kali'

command = sys.argv[1]

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    ssh.connect(host, username=user, password=password, timeout=10)
    stdin, stdout, stderr = ssh.exec_command(command)
    out = stdout.read().decode('utf-8')
    err = stderr.read().decode('utf-8')
    print("STDOUT:")
    print(out)
    print("STDERR:")
    print(err)
except Exception as e:
    print("ERROR:", e)
finally:
    ssh.close()
