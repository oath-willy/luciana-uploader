from pathlib import Path
import os
import paramiko


def verify_ssh_host(client: paramiko.SSHClient) -> None:
    known_hosts = Path(os.getenv("SSH_KNOWN_HOSTS", str(Path(__file__).resolve().parents[1] / "keys" / "known_hosts")))
    client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
