from fastapi import APIRouter, HTTPException
from fastapi import Body
from pydantic import BaseModel
import os
import paramiko
import io

# SOLO IN AMBIENTE AZURE
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

router = APIRouter()

class ScriptRequest(BaseModel):
    script_path: str

def load_ssh_key():
    # ENV per decidere se sei in Azure
    use_keyvault = os.getenv("USE_KEYVAULT", "false").lower() == "true"

    if use_keyvault:
        try:
            key_vault_name = "luciana-project"
            key_vault_url = f"https://{key_vault_name}.vault.azure.net/"

            credential = DefaultAzureCredential()
            client = SecretClient(vault_url=key_vault_url, credential=credential)

            secret = client.get_secret("ssh-private-key-lucianauser")
            key_data = secret.value

            key_file = io.StringIO(key_data)
            return paramiko.RSAKey.from_private_key(key_file)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Errore Key Vault: {str(e)}")

    else:
        # Locale – legge da file
        key_path = os.getenv("SSH_PRIVATE_KEY_PATH", "./keys/lucianauser_key.pem")
        return paramiko.RSAKey.from_private_key_file(key_path)


@router.post("/run-r-script")
def run_r_script(request: ScriptRequest = Body(...)):
    try:
        print("📡 Inizio esecuzione R script")
        script_path = request.script_path.strip()

        if not script_path.endswith(".R"):
            raise HTTPException(status_code=400, detail="Il file deve essere uno script .R")

        hostname = "108.142.241.77"
        username = "lucianauser"
        print("🔐 Caricamento chiave SSH")
        key = load_ssh_key()

        print("🔌 Connessione SSH alla VM")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=hostname, username=username, pkey=key)

        print(f"🚀 Esecuzione: Rscript {script_path}")
        stdin, stdout, stderr = ssh.exec_command(f"Rscript {script_path}")
        output = stdout.read().decode()
        error = stderr.read().decode()
        ssh.close()

        if error:
            raise HTTPException(status_code=500, detail=f"Errore nello script R:\n{error}")

        return {"output": output.strip()}

    except Exception as e:
        print("❌ Errore:", str(e))
        raise HTTPException(status_code=500, detail=str(e))