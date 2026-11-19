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
            command = "/opt/hw8/venv/bin/python /opt/hw8/main.py"
        else:
            filename = "subscriber.py"
            command = (
                "/opt/hw8/venv/bin/python /opt/hw8/subscriber.py "
                f"--project={project} --bucket={bucket} "
                "--subscription=hw8-forbidden-requests-sub "
                "--log-object=hw8-logs/forbidden-requests.jsonl"
            )

        application = (ROOT / role / filename).read_text()
        environment = (
            f"PROJECT_ID={project}\n"
            f"BUCKET_NAME={bucket}\n"
            "TOPIC_ID=hw8-forbidden-requests\n"
            "PYTHONUNBUFFERED=1\n"
        )

        unit = f"""[Unit]
Description=CS528 HW8 {role}
Wants=network-online.target
After=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=hw8
Group=hw8
WorkingDirectory=/opt/hw8
EnvironmentFile=/etc/hw8.env
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
            "exec > >(tee -a /var/log/hw8-startup.log) 2>&1",
            "export DEBIAN_FRONTEND=noninteractive",
            "apt-get -o Acquire::Retries=3 update",
            "apt-get -o DPkg::Lock::Timeout=300 install -y python3-venv",
            "id hw8 >/dev/null 2>&1 || useradd --system --home /opt/hw8 --shell /usr/sbin/nologin hw8",
            "install -d -m 755 /opt/hw8",
            write_command(f"/opt/hw8/{filename}", application),
            write_command("/opt/hw8/requirements-lock.txt", requirements),
            write_command("/etc/hw8.env", environment),
            "chmod 644 /etc/hw8.env",
            "python3 -m venv /opt/hw8/venv",
            "/opt/hw8/venv/bin/python -m pip install --no-cache-dir -r /opt/hw8/requirements-lock.txt",
            write_command(f"/etc/systemd/system/hw8-{role}.service", unit),
            "systemctl daemon-reload",
            f"systemctl enable hw8-{role}.service",
            f"systemctl restart hw8-{role}.service",
            f"systemctl is-active hw8-{role}.service",
            f"echo 'HW8 {role} startup completed'",
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
