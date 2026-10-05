#!/usr/bin/env bash
set -euo pipefail
printf 'EGRESS_IP\n'
curl --silent --show-error --max-time 15 https://api.ipify.org
printf '\nNGINX_SITE_NAMES\n'
find /etc/nginx/sites-enabled -maxdepth 1 -type l -printf '%f\n'
printf 'NGINX_CONFIGURATION\n'
nginx -T 2>&1 | sed -n '/server_name rstudio-ks/,/^}/p'
printf 'SSH_HOST_KEYS\n'
for key in /etc/ssh/ssh_host_*_key.pub; do cat "$key"; done
printf 'UTILITY_USER_KEYS\n'
awk '{for (i=1; i<=NF; i++) if ($i ~ /^ssh-|^ecdsa-/) {print $i, $(i+1); break}}' /home/lucianauser/.ssh/authorized_keys
printf 'PROXY_PORT\n'
ss -lntp | awk '$4 ~ /:3128$/ {print $4}'
