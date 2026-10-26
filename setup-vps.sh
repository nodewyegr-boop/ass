#!/usr/bin/env bash
# รันบน VPS (Ubuntu 22.04, root): bash setup-vps.sh yourdomain.example.com youremail@example.com [access-key]
# ต้องมีโดเมนที่ตั้ง A record ชี้มาที่ IP ของ VPS นี้แล้วก่อนรัน (เช็คด้วย: dig +short yourdomain.example.com)
set -euo pipefail
DOMAIN="${1:?ใช้: bash setup-vps.sh โดเมน อีเมล [access-key]}"
EMAIL="${2:?ใช้: bash setup-vps.sh โดเมน อีเมล [access-key]}"
ACCESS_KEY="${3:-$(head -c16 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c20)}"
APPDIR=/opt/dbclient

apt-get update -y
apt-get install -y curl ufw
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs certbot

ufw allow OpenSSH || true
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

mkdir -p "$APPDIR"
cp "$(dirname "$0")/dbclient.js" "$APPDIR/"

systemctl stop dbclient 2>/dev/null || true
certbot certonly --standalone --non-interactive --agree-tos -m "$EMAIL" -d "$DOMAIN"

cat > /etc/systemd/system/dbclient.service <<SERVICE
[Unit]
Description=Discord Bot Client (proxy-clone UI)
After=network.target

[Service]
Type=simple
WorkingDirectory=$APPDIR
Environment=PORT=443
Environment=DC_BIND=0.0.0.0
Environment=DC_ALLOWED_HOST=$DOMAIN
Environment=DC_TLS_CERT=/etc/letsencrypt/live/$DOMAIN/fullchain.pem
Environment=DC_TLS_KEY=/etc/letsencrypt/live/$DOMAIN/privkey.pem
Environment=DC_ACCESS_KEY=$ACCESS_KEY
Environment=DC_LIVE=1
ExecStart=/usr/bin/node $APPDIR/dbclient.js
Restart=always
RestartSec=3
AmbientCapabilities=CAP_NET_BIND_SERVICE
User=root

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable dbclient
systemctl restart dbclient

# ต่อ cert หมดอายุอัตโนมัติ + รีสตาร์ทให้ด้วย
echo "0 3 * * * certbot renew --quiet --deploy-hook 'systemctl restart dbclient'" | crontab -

sleep 2
echo "=============================================="
echo "เสร็จแล้ว เปิดนี่ในเบราว์เซอร์มือถือครั้งเดียวก่อน (ยืนยันว่าใช้ได้):"
echo "  https://$DOMAIN/?key=$ACCESS_KEY"
echo "แล้วเอา URL นี้ไปใส่ในเว็บสร้าง APK (โหมด 'จาก URL')"
echo "รหัสผ่าน (เก็บไว้): $ACCESS_KEY"
echo "ดู log: journalctl -u dbclient -f"
echo "=============================================="
