#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends tinyproxy
install -d -m 0755 /var/www/luciana-vpn
cat >/var/www/luciana-vpn/luciana-proxy.pac <<'EOF'
function FindProxyForURL(url, host) {
  host = host.toLowerCase();
  if (host === "yellow-forest-0ad79d503.6.azurestaticapps.net" ||
      host === "luciana-backend.azurewebsites.net") {
    // Azure VPN resolves this name to its private address. Office clients
    // resolve the public address and keep their direct office connection.
    if (dnsResolve("rstudio-ks.westeurope.cloudapp.azure.com") === "10.0.0.5") {
      return "PROXY 10.0.0.5:3128";
    }
    return "DIRECT";
  }
  return "DIRECT";
}
EOF
cat >/etc/tinyproxy/luciana-filter <<'EOF'
^yellow-forest-0ad79d503\.6\.azurestaticapps\.net$
^luciana-backend\.azurewebsites\.net$
EOF
cat >/etc/tinyproxy/tinyproxy.conf <<'EOF'
User tinyproxy
Group tinyproxy
Port 3128
Listen 10.0.0.5
Timeout 600
LogFile "/var/log/tinyproxy/tinyproxy.log"
LogLevel Warning
PidFile "/run/tinyproxy/tinyproxy.pid"
MaxClients 50
Allow 172.27.240.0/24
Allow 10.0.0.5/32
ConnectPort 443
DisableViaHeader Yes
Filter "/etc/tinyproxy/luciana-filter"
FilterURLs No
FilterExtended On
FilterDefaultDeny Yes
EOF
python3 - <<'PY'
from pathlib import Path
p=Path('/etc/nginx/sites-available/rstudio-ks')
s=p.read_text()
marker='    location = /luciana-proxy.pac {'
if marker not in s:
    (p.parent / 'rstudio-ks.before-webapp-proxy').write_text(s)
location='''    location = /luciana-proxy.pac {
        alias /var/www/luciana-vpn/luciana-proxy.pac;
        default_type application/x-ns-proxy-autoconfig;
        add_header Cache-Control "no-store";
    }

'''
s=s.replace(location, '')
start=s.index('    location / {', s.index('ssl_certificate '))
p.write_text(s[:start]+location+s[start:])
PY
nginx -t
systemctl enable tinyproxy
systemctl restart tinyproxy
systemctl reload nginx
printf 'PROXY_SERVICE\n'
systemctl is-active tinyproxy
printf 'ALLOWED_TARGET\n'
curl --silent --show-error --max-time 20 --proxy http://10.0.0.5:3128 --output /dev/null --write-out '%{http_code}\n' https://yellow-forest-0ad79d503.6.azurestaticapps.net/login
printf 'OTHER_TARGET_MUST_BE_DENIED\n'
curl --silent --max-time 10 --proxy http://10.0.0.5:3128 --output /dev/null --write-out '%{http_connect}\n' https://example.com || true
printf 'PAC_HTTPS\n'
for attempt in 1 2 3 4 5; do
    if curl --fail --silent --show-error --max-time 15 --resolve rstudio-ks.westeurope.cloudapp.azure.com:443:10.0.0.5 https://rstudio-ks.westeurope.cloudapp.azure.com/luciana-proxy.pac | grep 'function FindProxyForURL'; then
        exit 0
    fi
    sleep 1
done
exit 1
