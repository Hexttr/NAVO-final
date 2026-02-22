#!/usr/bin/env python3
"""Quick server diagnostics."""
import paramiko
import os

HOST = os.environ.get("NAVO_SSH_HOST", "195.133.63.34")
USER = os.environ.get("NAVO_SSH_USER", "root")
PASSWORD = os.environ.get("NAVO_SSH_PASSWORD", "hdp-k.PD6u8K7U")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASSWORD, timeout=15)

for name, cmd in [
    ("Icecast /live", "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/live"),
    ("stream_position", "cat /opt/navo-radio/uploads/stream_position.json 2>/dev/null || echo 'not found'"),
    ("Icecast", "curl -s -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:8001/live 2>/dev/null || echo 'unreachable'"),
    ("navo-source status", "systemctl is-active navo-radio-source"),
    ("icecast port", "grep port /etc/icecast2/icecast.xml 2>/dev/null | head -2"),
]:
    i, o, e = c.exec_command(cmd)
    print(f"{name}: {o.read().decode().strip()[:150]}")
c.close()
