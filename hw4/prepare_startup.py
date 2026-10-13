import argparse
import base64
import re
import shlex
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def write_command(path, content):
    encoded = base64.b64encode(content.encode()).decode()
    return f"printf '%s' {shlex.quote(encoded)} | base64 --decode > {shlex.quote(path)}"


def build_startup(project, bucket):
    for value in (project, bucket):
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", value):
            raise ValueError("Invalid project or bucket name")

    output = ROOT / "generated"
    output.mkdir(exist_ok=True)
    requirements = (ROOT / "requirements-lock.txt").read_text()
    results = {}

    for role in ("server", "subscriber"):
        if role == "server":
            filename = "main.py"
            command = "/opt/hw4/venv/bin/python /opt/hw4/main.py"
        else:
            filename = "subscriber.py"
            command = (
                "/opt/hw4/venv/bin/python /opt/hw4/subscriber.py "
                f"--project={project} --bucket={bucket} "
                "--subscription=hw4-forbidden-requests-sub "
                "--log-object=hw4-logs/forbidden-requests.jsonl"
            )

        application = (ROOT / role / filename).read_text()
        environment = (
            f"PROJECT_ID={project}\n"
            f"BUCKET_NAME={bucket}\n"
            "TOPIC_ID=hw4-forbidden-requests\n"
            "PYTHONUNBUFFERED=1\n"
        )

        unit = f"""[Unit]
Description=CS528 HW4 {role}
Wants=network-online.target
After=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=hw4
Group=hw4
WorkingDirectory=/opt/hw4
EnvironmentFile=/etc/hw4.env
ExecStart={command}
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
"""

        lines = [
            "#!/bin/bash",
            "set -euo pipefail",
            "exec > >(tee -a /var/log/hw4-startup.log) 2>&1",
            "export DEBIAN_FRONTEND=noninteractive",
            "apt-get -o Acquire::Retries=3 update",
            "apt-get -o DPkg::Lock::Timeout=300 install -y python3-venv",
            "id hw4 >/dev/null 2>&1 || useradd --system --home /opt/hw4 --shell /usr/sbin/nologin hw4",
            "install -d -m 755 /opt/hw4",
            write_command(f"/opt/hw4/{filename}", application),
            write_command("/opt/hw4/requirements-lock.txt", requirements),
            write_command("/etc/hw4.env", environment),
            "chmod 644 /etc/hw4.env",
            "python3 -m venv /opt/hw4/venv",
            "/opt/hw4/venv/bin/python -m pip install --no-cache-dir -r /opt/hw4/requirements-lock.txt",
            write_command(f"/etc/systemd/system/hw4-{role}.service", unit),
            "systemctl daemon-reload",
            f"systemctl enable hw4-{role}.service",
            f"systemctl restart hw4-{role}.service",
            f"systemctl is-active hw4-{role}.service",
            f"echo 'HW4 {role} startup completed'",
        ]

        path = output / f"startup-{role}.sh"
        path.write_text("\n".join(lines) + "\n")
        results[role] = path

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--bucket", required=True)
    args = parser.parse_args()
    for role, path in build_startup(args.project, args.bucket).items():
        print(f"{role}: {path}")
