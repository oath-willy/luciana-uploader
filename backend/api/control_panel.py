import json
import os
import socket
import urllib.error
import urllib.request
import io
from typing import Any, Dict, Literal

import paramiko
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel


router = APIRouter()

VmAction = Literal["start", "stop"]

SUBSCRIPTION_ID = os.getenv(
    "AZURE_SUBSCRIPTION_ID",
    "96852fa0-7e3c-45f3-a68e-55aa80a742b3",
)
VM_RESOURCE_GROUP = os.getenv("AZURE_VM_RESOURCE_GROUP", "luciana_resource_group")
ARM_API_VERSION = "2024-07-01"

CONTROL_PANEL_VMS = [
    {
        "name": "lucianavm03",
        "public_ip": "108.142.241.77",
        "rstudio_url": "http://108.142.241.77:8787/",
    },
    {
        "name": "lucianavm04",
        "public_ip": "20.160.158.80",
        "rstudio_url": "http://20.160.158.80:8787/",
    },
]

RSTUDIO_USERS_SCRIPT = r"""
if command -v rstudio-server >/dev/null 2>&1; then
  sessions="$(rstudio-server active-sessions 2>/dev/null || true)"
  if [ -n "$sessions" ]; then
    printf "%s\n" "$sessions" | grep -o -- '-u [^ ]*' | awk '{ print $2 }' | sort -u
  else
    true
  fi
else
  pgrep -af '[r]session' 2>/dev/null | grep -o -- '-u [^ ]*' | awk '{ print $2 }' | sort -u
fi
"""

SSH_USERNAME = os.getenv("CONTROL_PANEL_VM_USERNAME", "lucianauser")
SSH_PASSWORD = os.getenv("CONTROL_PANEL_VM_PASSWORD", "")
SSH_PRIVATE_KEY_SECRET = os.getenv(
    "CONTROL_PANEL_SSH_PRIVATE_KEY_SECRET",
    "ssh-private-key-lucianauser",
)
SSH_PRIVATE_KEY_PATH = os.getenv("SSH_PRIVATE_KEY_PATH", "./keys/lucianauser_key.pem")
KEY_VAULT_NAME = os.getenv("KEY_VAULT_NAME", "luciana-project")


class VmActionRequest(BaseModel):
    action: VmAction


def _credential():
    return DefaultAzureCredential(exclude_interactive_browser_credential=True)


def _arm_request(
    method: str,
    path: str,
    body: Dict[str, Any] | None = None,
    timeout: int = 60,
):
    token = _credential().get_token("https://management.azure.com/.default").token
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        f"https://management.azure.com{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(
            status_code=exc.code,
            detail=f"Errore Azure ARM: {detail or exc.reason}",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Errore Azure ARM: {exc}")


def _vm_path(vm_name: str, suffix: str = ""):
    return (
        f"/subscriptions/{SUBSCRIPTION_ID}"
        f"/resourceGroups/{VM_RESOURCE_GROUP}"
        f"/providers/Microsoft.Compute/virtualMachines/{vm_name}{suffix}"
    )


def _get_power_state(vm_name: str):
    result = _arm_request(
        "GET",
        f"{_vm_path(vm_name, '/instanceView')}?api-version={ARM_API_VERSION}",
    )
    statuses = result.get("statuses", [])
    power_status = next(
        (status for status in statuses if status.get("code", "").startswith("PowerState/")),
        {},
    )
    code = power_status.get("code", "PowerState/unknown").split("/", 1)[-1]

    return {
        "code": code,
        "label": power_status.get("displayStatus", "Unknown"),
        "is_running": code == "running",
    }


def _parse_rstudio_usernames(output: str):
    return sorted(
        {
            line.strip()
            for line in output.splitlines()
            if line.strip() and " " not in line.strip()
        }
    )


def _load_ssh_key():
    key_errors = []

    if os.getenv("USE_KEYVAULT", "false").lower() == "true":
        try:
            key_vault_url = f"https://{KEY_VAULT_NAME}.vault.azure.net/"
            client = SecretClient(vault_url=key_vault_url, credential=_credential())
            secret = client.get_secret(SSH_PRIVATE_KEY_SECRET)
            return paramiko.RSAKey.from_private_key(io.StringIO(secret.value))
        except Exception as exc:
            key_errors.append(f"Key Vault: {exc}")

    try:
        return paramiko.RSAKey.from_private_key_file(SSH_PRIVATE_KEY_PATH)
    except Exception as exc:
        key_errors.append(f"file key: {exc}")

    return None, "; ".join(key_errors)


def _get_rstudio_users_via_ssh(vm: Dict[str, str]):
    key_result = _load_ssh_key()
    if isinstance(key_result, tuple):
        ssh_key = None
        key_error = key_result[1]
    else:
        ssh_key = key_result
        key_error = ""

    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_kwargs = {
            "hostname": vm["public_ip"],
            "username": SSH_USERNAME,
            "timeout": 12,
            "banner_timeout": 12,
            "auth_timeout": 12,
            "look_for_keys": False,
            "allow_agent": False,
        }
        if ssh_key:
            connect_kwargs["pkey"] = ssh_key
        elif SSH_PASSWORD:
            connect_kwargs["password"] = SSH_PASSWORD
        else:
            return None, f"Chiave SSH/password non configurata ({key_error})"

        ssh.connect(**connect_kwargs)
        _, stdout, stderr = ssh.exec_command(RSTUDIO_USERS_SCRIPT, timeout=20)
        output = stdout.read().decode("utf-8", errors="replace").strip()
        error = stderr.read().decode("utf-8", errors="replace").strip()
        ssh.close()

        if error and not output:
            return None, error

        return _parse_rstudio_usernames(output), ""
    except (paramiko.SSHException, socket.timeout, OSError) as exc:
        return None, f"SSH non disponibile: {exc}"


def _get_rstudio_users_via_run_command(vm: Dict[str, str]):
    try:
        result = _arm_request(
            "POST",
            f"{_vm_path(vm['name'], '/runCommand')}?api-version={ARM_API_VERSION}",
            body={
                "commandId": "RunShellScript",
                "script": RSTUDIO_USERS_SCRIPT.strip().splitlines(),
            },
            timeout=90,
        )

        stdout_messages = []
        stderr_messages = []
        for item in result.get("value", []):
            code = item.get("code", "")
            message = item.get("message", "")
            if "StdOut" in code:
                stdout_messages.append(message)
            elif "StdErr" in code:
                stderr_messages.append(message)

        output = "\n".join(stdout_messages).strip()
        error = "\n".join(stderr_messages).strip()
        if error and not output:
            return None, f"Azure Run Command: {error}"

        return _parse_rstudio_usernames(output), ""
    except HTTPException as exc:
        return None, str(exc.detail)
    except Exception as exc:
        return None, f"Azure Run Command non disponibile: {exc}"


def _get_rstudio_users(vm: Dict[str, str], is_running: bool):
    if not is_running:
        return {
            "count": None,
            "usernames": [],
            "available": False,
            "message": "VM spenta",
        }

    usernames, ssh_error = _get_rstudio_users_via_ssh(vm)
    if usernames is None:
        usernames, run_command_error = _get_rstudio_users_via_run_command(vm)
    else:
        run_command_error = ""

    if usernames is None:
        return {
            "count": None,
            "usernames": [],
            "available": False,
            "message": run_command_error or ssh_error or "Utenti RStudio non disponibili",
        }

    return {
        "count": len(usernames),
        "usernames": usernames,
        "available": True,
        "message": "",
    }


def _vm_status(vm: Dict[str, str]):
    power = _get_power_state(vm["name"])
    users = _get_rstudio_users(vm, power["is_running"])

    return {
        "name": vm["name"],
        "power_state": power["code"],
        "power_label": power["label"],
        "is_running": power["is_running"],
        "rstudio_url": vm["rstudio_url"],
        "rstudio_users": users["count"],
        "rstudio_usernames": users["usernames"],
        "rstudio_users_available": users["available"],
        "rstudio_users_message": users["message"],
    }


@router.get("/control-panel/vms")
def get_control_panel_vms():
    return jsonable_encoder([_vm_status(vm) for vm in CONTROL_PANEL_VMS])


@router.post("/control-panel/vms/{vm_name}/action")
def run_vm_action(vm_name: str, request: VmActionRequest):
    if vm_name not in {vm["name"] for vm in CONTROL_PANEL_VMS}:
        raise HTTPException(status_code=404, detail="VM non gestita dal control panel")

    suffix = "/start" if request.action == "start" else "/deallocate"
    _arm_request(
        "POST",
        f"{_vm_path(vm_name, suffix)}?api-version={ARM_API_VERSION}",
        timeout=30,
    )

    return jsonable_encoder({"message": f"Azione {request.action} inviata", "vm": vm_name})
