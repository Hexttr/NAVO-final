import paramiko
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

host = "195.133.63.34"
user = "root"
password = "hdp-k.PD6u8K7U"

def run_command(client, command):
    print(f"=== Running: {command} ===")
    stdin, stdout, stderr = client.exec_command(command)
    out = stdout.read().decode('utf-8', errors='replace')
    if out:
        print(out)
    print("========================================\n")

try:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, username=user, password=password, timeout=10)
    
    # Kill existing ffmpeg and run_hls processes
    run_command(client, "pkill -f 'ffmpeg.*-f hls'")
    run_command(client, "pkill -f 'run_hls.py'")
    
    # Remove today's HLS directory to force regeneration
    run_command(client, "rm -rf /opt/navo-radio/uploads/hls/$(date +%Y-%m-%d)")
    run_command(client, "echo 'Cleaned up old HLS and processes'")
    
    # Also trigger HLS regeneration for today using the API or CLI
    # But since it triggers on GET request to /api/broadcast/now-playing if it's missing,
    # or I can just run it via run_hls.py.
    run_command(client, "cd /opt/navo-radio && ./venv/bin/python3 backend/run_hls.py $(date +%Y-%m-%d) > /dev/null 2>&1 &")
    run_command(client, "echo 'Triggered new HLS generation in background'")

    client.close()
except Exception as e:
    print(f"Failed: {e}")
