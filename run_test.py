import paramiko
import sys
import io
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

host = "195.133.63.34"
user = "root"
password = "hdp-k.PD6u8K7U"

try:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, username=user, password=password, timeout=10)
    
    sftp = client.open_sftp()
    with open("test_elevenlabs.py", "rb") as f:
        sftp.putfo(f, "/tmp/test_elevenlabs.py")
    sftp.close()

    print("=== Running test on remote ===")
    stdin, stdout, stderr = client.exec_command("/opt/navo-radio/venv/bin/python3 /tmp/test_elevenlabs.py")
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    if out:
        print(out)
    if err:
        print("ERROR:")
        print(err)
    print("========================================\n")
    client.close()
except Exception as e:
    print(f"Failed: {e}")
