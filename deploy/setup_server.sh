#!/bin/bash
# Installs the dashboard on a Debian VM from files staged in /tmp/nids (see deploy/README.md).
set -euo pipefail
DOMAIN="${1:-ids.batch5ai.lol}"
EMAIL="${2:-}"

echo "== 1. system packages"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv python3-pip nginx certbot python3-certbot-nginx >/dev/null

echo "== 2. code, model and venv in /opt/nids"
sudo mkdir -p /opt/nids
sudo tar -xzf /tmp/nids/code.tar.gz -C /opt/nids
sudo mkdir -p /opt/nids/models
sudo cp /tmp/nids/nids_bundle.joblib /tmp/nids/demo_test_flows.csv /opt/nids/models/
[ -d /opt/nids/venv ] || sudo python3 -m venv /opt/nids/venv
sudo /opt/nids/venv/bin/pip install -q --upgrade pip
sudo /opt/nids/venv/bin/pip install -q -r /opt/nids/deploy/requirements-server.txt
sudo chmod -R a+rX /opt/nids

echo "== 3. systemd service"
sudo cp /opt/nids/deploy/nids-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable nids-dashboard
sudo systemctl restart nids-dashboard
sleep 8
systemctl is-active nids-dashboard

echo "== 4. nginx"
sudo cp /opt/nids/deploy/nids-dashboard.nginx /etc/nginx/sites-available/nids-dashboard
sudo sed -i "s/server_name .*;/server_name ${DOMAIN};/" /etc/nginx/sites-available/nids-dashboard
sudo ln -sf /etc/nginx/sites-available/nids-dashboard /etc/nginx/sites-enabled/nids-dashboard
sudo nginx -t && sudo systemctl reload nginx

echo "== 5. TLS"
if [ -n "$EMAIL" ]; then
  sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL" --redirect
  sudo nginx -t && sudo systemctl reload nginx
fi

echo "== 6. verify"
curl -s http://127.0.0.1:8001/health; echo
free -h | head -2
echo "== DONE"
