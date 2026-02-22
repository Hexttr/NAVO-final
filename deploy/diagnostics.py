#!/usr/bin/env python3
"""
Диагностика NAVO RADIO на сервере.
Запуск: python deploy/diagnostics.py

Проверяет: systemd-сервисы, Icecast, backend API, stream.
"""
import os
import sys

# credentials из deploy_to_server
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
sys.path.insert(0, _project_root)
try:
    from deploy.deploy_to_server import HOST, USER, PASSWORD
except ImportError:
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("dts", os.path.join(_script_dir, "deploy_to_server.py"))
        dts = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dts)
        HOST, USER, PASSWORD = dts.HOST, dts.USER, dts.PASSWORD
    except Exception:
        HOST = os.environ.get("NAVO_SSH_HOST", "195.133.63.34")
        USER = os.environ.get("NAVO_SSH_USER", "root")
        PASSWORD = os.environ.get("NAVO_SSH_PASSWORD")


def run(ssh, cmd, check=False):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    code = stdout.channel.recv_exit_status()
    return out, err, code

try:
    import paramiko
except ImportError:
    print("Установите paramiko: pip install paramiko")
    sys.exit(1)


def run(ssh, cmd, check=False):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    code = stdout.channel.recv_exit_status()
    return out, err, code


def main():
    if not PASSWORD:
        print("Задайте NAVO_SSH_PASSWORD или запустите из папки проекта с deploy")
        sys.exit(1)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(HOST, username=USER, password=PASSWORD, timeout=15)
    except Exception as e:
        print(f"Ошибка SSH: {e}")
        sys.exit(1)

    print("=" * 60)
    print("NAVO RADIO — Диагностика сервера")
    print("=" * 60)

    # 1. Systemd services
    print("\n[1] Systemd сервисы:")
    for svc in ["navo-radio", "navo-radio-source", "icecast2"]:
        out, _, code = run(client, f"systemctl is-active {svc} 2>/dev/null || echo inactive")
        status = out.strip() if out.strip() else "not-found"
        icon = "[OK]" if status == "active" else "[--]"
        print(f"    {icon} {svc}: {status}")

    # 2. Icecast port
    print("\n[2] Icecast (порт 8001):")
    out, _, code = run(client, "curl -s -o /dev/null -w '%{http_code}' --connect-timeout 2 http://127.0.0.1:8001/live 2>/dev/null || echo 'err'")
    ic_status = "доступен" if out.strip() in ("200", "403", "000") else f"HTTP {out.strip() or 'timeout'}"
    print(f"    Icecast /live: {ic_status}")

    # 3. Backend API
    print("\n[3] Backend API (порт 8000):")
    out, _, code = run(client, "curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 http://127.0.0.1:8000/ 2>/dev/null || echo 'err'")
    api_status = "доступен" if out.strip() == "200" else f"HTTP {out.strip() or 'timeout'}"
    print(f"    API /: {api_status}")

    # 4. Diagnostics endpoint
    print("\n[4] Диагностика API (/api/diagnostics):")
    out, err, code = run(client, "curl -s --connect-timeout 5 http://127.0.0.1:8000/api/diagnostics 2>/dev/null")
    if out and "moscow_date" in out:
        import json
        try:
            d = json.loads(out)
            checks = d.get("checks", {})
            print(f"    moscow_date: {d.get('moscow_date', '?')}")
            print(f"    broadcast_items: {checks.get('broadcast_items', 0)}")
            print(f"    broadcast_ready: {checks.get('broadcast_ready', False)}")
            print(f"    icecast_live: {checks.get('icecast_live', '?')}")
            print(f"    stream_ready: {checks.get('stream_ready', False)}")
            if d.get("error"):
                print(f"    ERROR: {d['error']}")
        except json.JSONDecodeError:
            print(f"    Ответ: {out[:300]}...")
    else:
        print(f"    Не получен: code={code}, out={out[:200] if out else 'empty'}")

    # 5. Stream test
    print("\n[5] Проверка /stream (первые 1KB):")
    out, err, code = run(client, "curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8000/stream 2>/dev/null || echo 'err'")
    http_code = (out or "").strip().split()[0][:10] if out else "?"
    stream_ok = http_code == "200"
    icon = "[OK]" if stream_ok else "[--]"
    print(f"    {icon} HTTP {http_code}")

    # 6. navo-radio-source journal (last errors)
    print("\n[7] navo-radio-source (последние ошибки journalctl):")
    out, _, _ = run(client, "journalctl -u navo-radio-source -n 8 --no-pager 2>/dev/null | tail -8")
    for line in (out or "").strip().split("\n"):
        if line.strip() and ("error" in line.lower() or "exception" in line.lower() or "traceback" in line.lower() or "failed" in line.lower() or "ERR" in line):
            print(f"    {line[:100]}...")
        elif line.strip():
            print(f"    {line[:100]}")
    if not out or not out.strip():
        print("    (нет записей или сервис не активен)")

    print("\n" + "=" * 60)
    client.close()


if __name__ == "__main__":
    main()
