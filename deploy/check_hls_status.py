#!/usr/bin/env python3
"""Check HLS generation status on server."""
import paramiko
import os

HOST = os.environ.get("NAVO_SSH_HOST", "195.133.63.34")
USER = os.environ.get("NAVO_SSH_USER", "root")
PASSWORD = os.environ.get("NAVO_SSH_PASSWORD", "hdp-k.PD6u8K7U")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASSWORD, timeout=15)

cmds = [
    ("run_hls process", "pgrep -af run_hls || echo 'not running'"),
    ("ffmpeg HLS (hls_time)", "pgrep -af 'hls_time' || echo 'no HLS ffmpeg'"),
    ("Lock file", "stat /opt/navo-radio/uploads/hls_generating_2026-02-21.lock 2>/dev/null || echo 'no lock'"),
    ("Segments per hash", "for d in /opt/navo-radio/uploads/hls/2026-02-21/*/; do echo -n \"$(basename $d): \"; ls $d/seg_*.ts 2>/dev/null | wc -l; done"),
    ("Latest 3 segments", "ls -lt /opt/navo-radio/uploads/hls/2026-02-21/*/seg_*.ts 2>/dev/null | head -3"),
]
for name, cmd in cmds:
    i, o, e = c.exec_command(cmd)
    out = o.read().decode().strip()
    err = e.read().decode().strip()
    print(f"--- {name} ---")
    print(out[:500] if out else "(empty)")
    if err:
        print("stderr:", err[:200])
    print()
c.close()
