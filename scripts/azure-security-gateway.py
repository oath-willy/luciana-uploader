"""Require the SWA gateway, preserving its platform-managed registration."""
import json
import runpy
from pathlib import Path

common = runpy.run_path(str(Path(__file__).with_name("azure-security-identity.py")))
az, token, api = (common[name] for name in ("az", "token", "api"))
arm = token("https://management.azure.com/")
sub = az("account", "show")["id"]
base = f"https://management.azure.com/subscriptions/{sub}/resourceGroups/luciana_resource_group/providers/Microsoft.Web/sites/luciana-backend/config"
url = base + "/authsettingsV2?api-version=2024-11-01"
auth = api("GET", url, arm)["properties"]
linked = auth.get("identityProviders", {}).get("azureStaticWebApps", {})
if not linked.get("enabled") or not linked.get("registration", {}).get("clientId"):
    raise RuntimeError("Link the Static Web App before enabling trusted identity headers")
auth.setdefault("platform", {})["enabled"] = True
auth.setdefault("globalValidation", {}).update({
    "requireAuthentication": True,
    "unauthenticatedClientAction": "Return401",
    # Automated data publishers authenticate with their existing separate token.
    "excludedPaths": ["/ping", "/api/mc-code/snapshot", "/api/mc-code/snapshot-file",
                      "/api/codex/snapshot", "/api/codex/snapshot-file"],
})
auth.setdefault("httpSettings", {})["requireHttps"] = True
api("PUT", url, arm, {"properties": auth})
settings_url = base + "/appsettings"
settings = api("POST", settings_url + "/list?api-version=2024-11-01", arm)["properties"]
settings.update({"APP_AUTH_MODE": "linked", "APP_AUTH_GATEWAY_ENABLED": "true",
                 "FAST_TRACK_AUTH_MODE": "linked", "APP_ADMIN_EMAILS": "wilson.sgroi@key-stone.it",
                 "FRONTEND_ORIGIN": "https://yellow-forest-0ad79d503.6.azurestaticapps.net"})
api("PUT", settings_url + "?api-version=2024-11-01", arm, {"properties": settings})
print(json.dumps({"gatewayRequired": True, "directAnonymous": "Return401",
                  "publisherTokenRequired": True, "adminConfigured": True}))
