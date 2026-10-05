"""Require MFA specifically for Luciana-WebApp, including office access."""
import json
import runpy
from pathlib import Path

common = runpy.run_path(str(Path(__file__).with_name("azure-security-identity.py")))
api, token = common["api"], common["token"]
graph = token("https://graph.microsoft.com/")
url = "https://graph.microsoft.com/v1.0/identity/conditionalAccess/policies"
name = "MFA - Luciana WebApp"
policies = api("GET", url, graph)["value"]
existing = next((p for p in policies if p["displayName"] == name), None)
policy = {"displayName": name, "state": "enabled", "conditions": {
    "clientAppTypes": ["all"], "users": {"includeUsers": ["All"]},
    "applications": {"includeApplications": ["8d2ab2e1-15ab-47ec-9e22-69481fe30a47"]}},
    "grantControls": {"operator": "OR", "builtInControls": ["mfa"]}}
if existing:
    api("PATCH", url + "/" + existing["id"], graph, policy)
else:
    existing = api("POST", url, graph, policy)
print(json.dumps({"policy": name, "id": existing["id"], "state": "enabled", "onlyLucianaWebApp": True}))
