"""Configure tenant-specific SWA login without printing or storing client secrets locally."""
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


def az(*args):
    result = subprocess.run(["az.cmd", *args, "--only-show-errors", "-o", "json"],
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def token(resource):
    return az("account", "get-access-token", "--resource", resource)["accessToken"]


def api(method, url, bearer, body=None):
    response = requests.request(method, url, headers={"Authorization": "Bearer " + bearer}, json=body, timeout=60)
    if not response.ok:
        raise RuntimeError(f"Azure request failed: {response.status_code} {url.split('?')[0]}")
    return response.json() if response.content else {}


if __name__ == "__main__":
    graph = token("https://graph.microsoft.com/")
    arm = token("https://management.azure.com/")
    sub = az("account", "show")["id"]
    apps = az("ad", "app", "list", "--display-name", "Luciana-WebApp")
    app = next((a for a in apps if a["displayName"] == "Luciana-WebApp"), None)
    if app is None:
        app = api("POST", "https://graph.microsoft.com/v1.0/applications", graph, {
            "displayName": "Luciana-WebApp", "signInAudience": "AzureADMyOrg",
            "web": {"redirectUris": ["https://yellow-forest-0ad79d503.6.azurestaticapps.net/.auth/login/aad/callback"]},
        })
    expires = datetime.now(timezone.utc) + timedelta(days=365)
    password = api("POST", f"https://graph.microsoft.com/v1.0/applications/{app['id']}/addPassword", graph,
                   {"passwordCredential": {"displayName": "SWA login", "endDateTime": expires.isoformat()}})
    base = f"https://management.azure.com/subscriptions/{sub}/resourceGroups/luciana_resource_group/providers/Microsoft.Web/staticSites/luciana-frontend/config/appsettings"
    site = base.rsplit("/config/", 1)[0]
    current = api("POST", site + "/listAppSettings?api-version=2024-11-01", arm).get("properties", {})
    current.update({"LUCIANA_AAD_CLIENT_ID": app["appId"], "LUCIANA_AAD_CLIENT_SECRET": password["secretText"]})
    api("PUT", base + "?api-version=2024-11-01", arm, {"properties": current})
    vault = token("https://vault.azure.net")
    api("PUT", "https://luciana-project.vault.azure.net/secrets/webapp-aad-client-secret?api-version=7.4", vault,
        {"value": password["secretText"], "attributes": {"enabled": True, "exp": int(expires.timestamp())}})
    service_principals = az("ad", "sp", "list", "--filter", f"appId eq '{app['appId']}'")
    if not service_principals:
        api("POST", "https://graph.microsoft.com/v1.0/servicePrincipals", graph, {"appId": app["appId"]})
    folder = Path(__file__).resolve().parent.parent / ".local-logs" / "security"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "identity.json").write_text(json.dumps({"appId": app["appId"], "objectId": app["id"], "secretExpires": expires.isoformat()}), encoding="utf-8")
    print(json.dumps({"appId": app["appId"], "tenantOnly": True, "settingsConfigured": True, "secretExpires": expires.isoformat()}))
