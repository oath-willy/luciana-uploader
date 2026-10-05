"""Replace repository SSH keys, verify the replacement, then revoke exposed keys."""
import io
import json
import runpy
import subprocess
import sys
from pathlib import Path

import paramiko
import requests

common = runpy.run_path(str(Path(__file__).with_name("azure-security-identity.py")))
az, token, api = (common[name] for name in ("az", "token", "api"))
root = Path(__file__).resolve().parent.parent
private_path = Path.home() / ".ssh" / "luciana-webapp-20261005.pem"
private_path.parent.mkdir(parents=True, exist_ok=True)
if not private_path.exists():
    paramiko.RSAKey.generate(4096).write_private_key_file(str(private_path))
key = paramiko.RSAKey.from_private_key_file(str(private_path))
public = key.get_name() + " " + key.get_base64()
private_path.with_suffix(".pem.pub").write_text(public + " luciana-webapp\n", encoding="utf-8")
retired = set()
for name in ("backend/keys/lucianauser_key.pem", "luciana_key_nopass.pem"):
    p = root / name
    if p.exists():
        old = paramiko.RSAKey.from_private_key_file(str(p))
        if old.get_base64() != key.get_base64():
            retired.add(old.get_base64())
arm, vault = token("https://management.azure.com/"), token("https://vault.azure.net")
old_response = requests.get("https://luciana-project.vault.azure.net/secrets/ssh-private-key-lucianauser?api-version=7.4",
                            headers={"Authorization": "Bearer " + vault}, timeout=30)
if old_response.ok:
    old = paramiko.RSAKey.from_private_key(io.StringIO(old_response.json()["value"]))
    if old.get_base64() != key.get_base64():
        retired.add(old.get_base64())
elif old_response.status_code != 404:
    raise RuntimeError(f"Cannot read existing SSH secret: {old_response.status_code}")
sub = az("account", "show")["id"]
hosts = [("lucianavm03", "108.142.241.77", "10.0.0.4"), ("lucianavm04", "20.160.158.80", "10.0.0.5")]
known = []


def run(name, script):
    folder = root / ".local-logs" / "security"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}-keys.sh"
    path.write_text(script, encoding="utf-8")
    return az("vm", "run-command", "invoke", "--resource-group", "luciana_resource_group", "--name", name,
              "--command-id", "RunShellScript", "--scripts", "@" + str(path))


for name, host, private in hosts:
    if "--revoke-only" in sys.argv:
        continue
    print(f"Registering replacement key on {name}", flush=True)
    script = f'''set -eu
install -d -m 700 -o lucianauser -g lucianauser /home/lucianauser/.ssh
touch /home/lucianauser/.ssh/authorized_keys
if ! grep -qF '{key.get_base64()}' /home/lucianauser/.ssh/authorized_keys; then
  printf '%s\\n' '{public} luciana-webapp-20261005' >>/home/lucianauser/.ssh/authorized_keys
fi
chown lucianauser:lucianauser /home/lucianauser/.ssh/authorized_keys
chmod 600 /home/lucianauser/.ssh/authorized_keys
cat /etc/ssh/ssh_host_ed25519_key.pub
'''
    result = run(name, script)
    message = "\n".join(value.get("message", "") for value in result.get("value", []))
    host_key = next((line.strip() for line in message.splitlines() if line.startswith("ssh-ed25519 ")), None)
    if not host_key:
        raise RuntimeError(f"No verified host key returned by Azure for {name}")
    known.append(f"{host},{private},{name} {host_key}")
known_path = root / "backend" / "keys" / "known_hosts"
if known:
    known_path.write_text("\n".join(known) + "\n", encoding="utf-8")
for name, host, _ in hosts:
    ssh = paramiko.SSHClient()
    ssh.load_host_keys(str(known_path))
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(hostname=host, username="lucianauser", pkey=key, timeout=20, look_for_keys=False, allow_agent=False)
    _, out, _ = ssh.exec_command("printf SECURITY_KEY_OK", timeout=10)
    if out.read() != b"SECURITY_KEY_OK":
        raise RuntimeError(f"Replacement key verification failed for {name}")
    ssh.close()
    print(f"Replacement key and server identity verified for {name}", flush=True)
api("PUT", "https://luciana-project.vault.azure.net/secrets/ssh-private-key-lucianauser?api-version=7.4", vault,
    {"value": private_path.read_text(), "attributes": {"enabled": True}})
az("keyvault", "set-policy", "--name", "luciana-project", "--object-id", "d9b5f121-f3d4-4577-ac27-afb0755b549f", "--secret-permissions", "get")
base = f"https://management.azure.com/subscriptions/{sub}/resourceGroups/luciana_resource_group/providers/Microsoft.Web/sites/luciana-backend/config/appsettings"
settings = api("POST", base + "/list?api-version=2024-11-01", arm)["properties"]
settings.update({"USE_KEYVAULT": "true", "PDB_REF_VM_HOST": "10.0.0.5",
                 "CONTROL_PANEL_VM03_HOST": "10.0.0.4", "CONTROL_PANEL_VM04_HOST": "10.0.0.5",
                 "SSH_KNOWN_HOSTS": "./keys/known_hosts"})
settings.pop("CONTROL_PANEL_VM_PASSWORD", None)
api("PUT", base + "?api-version=2024-11-01", arm, {"properties": settings})
retired_json = json.dumps(sorted(retired))
for name, _, _ in hosts:
    print(f"Revoking exposed keys on {name}", flush=True)
    script = r'''set -eu
python3 - <<'PY'
from pathlib import Path
import json
retired = set(json.loads(RETIRED_JSON))
paths = list(Path('/home').glob('*/.ssh/authorized_keys')) + [Path('/root/.ssh/authorized_keys')]
removed = 0
for p in paths:
    if not p.is_file() or p.is_symlink():
        continue
    lines = p.read_text().splitlines()
    keep = [line for line in lines if not retired.intersection(line.split())]
    if len(keep) != len(lines):
        # Keep a root-only recovery copy; the old keys are no longer authorized.
        backup = p.with_name('authorized_keys.before-webapp-rotation')
        if not backup.exists():
            backup.write_text('\n'.join(lines) + '\n')
            backup.chmod(0o600)
        p.write_text('\n'.join(keep) + '\n')
        removed += len(lines) - len(keep)
print('Revoked entries:', removed)
PY
'''.replace("RETIRED_JSON", repr(retired_json))
    result = run(name, script)
    if not any("Revoked entries:" in item.get("message", "") for item in result.get("value", [])):
        raise RuntimeError(f"Revocation not verified on {name}")
    print(f"Exposed keys revoked on {name}", flush=True)
print(json.dumps({"privateKeyPath": str(private_path), "knownHosts": str(known_path), "retiredKeyCount": len(retired)}))
