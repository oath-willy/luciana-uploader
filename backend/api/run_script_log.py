from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import os
import paramiko
import io

# Azure Key Vault (opzionale, come nell'altro script)
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

router = APIRouter()

class ScriptRequest(BaseModel):
    script_path: str

def load_ssh_key():
    use_keyvault = os.getenv("USE_KEYVAULT", "false").lower() == "true"

    if use_keyvault:
        try:
            key_vault_name = "luciana-project"
            key_vault_url = f"https://{key_vault_name}.vault.azure.net/"
            credential = DefaultAzureCredential()
            client = SecretClient(vault_url=key_vault_url, credential=credential)
            secret = client.get_secret("ssh-private-key-lucianauser")
            key_file = io.StringIO(secret.value)
            return paramiko.RSAKey.from_private_key(key_file)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Errore Key Vault: {str(e)}")
    else:
        key_path = os.getenv("SSH_PRIVATE_KEY_PATH", "./keys/lucianauser_key.pem")
        return paramiko.RSAKey.from_private_key_file(key_path)

@router.post("/run-r-script/stream")
def run_r_script_stream(request: ScriptRequest = Body(...)):
    def generate():
        try:
            hostname = "108.142.241.77"
            username = "lucianauser"
            key = load_ssh_key()

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(hostname=hostname, username=username, pkey=key)

            script_path = request.script_path.strip()
            if not script_path.endswith(".R"):
                yield "❌ Il file deve avere estensione .R\n"
                return

            command = f"Rscript {script_path}"
            stdin, stdout, stderr = ssh.exec_command(command)

            for line in iter(stdout.readline, ""):
                yield line

            error_output = stderr.read().decode()
            if error_output:
                yield f"❌ Errore nello script R:\n{error_output}"

            ssh.close()

        except Exception as e:
            yield f"❌ Errore backend: {str(e)}\n"

    return StreamingResponse(generate(), media_type="text/plain")
