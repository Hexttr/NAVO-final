"""
Запуск scripts/test_elevenlabs.py на удалённом сервере через SSH.
Требует NAVO_SSH_HOST, NAVO_SSH_USER, NAVO_SSH_PASSWORD в .env или переменных окружения.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

import paramiko
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

host = os.environ.get("NAVO_SSH_HOST")
user = os.environ.get("NAVO_SSH_USER", "root")
password = os.environ.get("NAVO_SSH_PASSWORD")

if not host or not password:
    raise SystemExit("Задайте NAVO_SSH_HOST и NAVO_SSH_PASSWORD в .env или переменных окружения.")

script_path = Path(__file__).resolve().parent / "scripts" / "test_elevenlabs.py"
if not script_path.exists():
    raise SystemExit(f"Не найден {script_path}")

try:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, username=user, password=password, timeout=10)

    sftp = client.open_sftp()
    with open(script_path, "rb") as f:
        sftp.putfo(f, "/tmp/test_elevenlabs.py")
    sftp.close()

    print("=== Running test on remote ===")
    stdin, stdout, stderr = client.exec_command("/opt/navo-radio/venv/bin/python3 /tmp/test_elevenlabs.py")
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if out:
        print(out)
    if err:
        print("ERROR:")
        print(err)
    print("========================================\n")
    client.close()
except Exception as e:
    print(f"Failed: {e}")
    sys.exit(1)
