#!/bin/bash
# Raspberry Pi WiFi Captive Portal Setup
# WiFi Network: 1011A2-5G with password NashRocks!
# Creates a captive portal that displays welcome_sign.html on first connection

set -e

echo "=== Airbnb Guest WiFi Portal Setup ==="
echo "SSID: 1011A2-5G"
echo "Password: NashRocks!"
echo ""

# Detect the WiFi interface (usually wlan0 for built-in, wlan1 for USB)
WIFI_IFACE=$(ip link show | grep -i "wlan[0-9]" | awk '{print $2}' | sed 's/://' | head -1)
if [ -z "$WIFI_IFACE" ]; then
    echo "ERROR: No WiFi interface found. Plugging in USB WiFi adapter required."
    exit 1
fi

ETH_IFACE="eth0"
echo "Using WiFi interface: $WIFI_IFACE"
echo "Using Ethernet interface: $ETH_IFACE"
echo ""

# Update system
echo "Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# Install required packages
echo "Installing required packages..."
sudo apt-get install -y \
    hostapd \
    dnsmasq \
    nginx \
    python3 \
    python3-pip \
    python3-dev \
    wireless-tools \
    net-tools \
    curl

# Install Python dependencies
echo "Installing Python dependencies..."
sudo pip3 install --break-system-packages icalendar requests

# Create app directory
echo "Creating application directory..."
APP_DIR="/opt/airbnb-welcome"
sudo mkdir -p $APP_DIR
sudo chown pi:pi $APP_DIR

# Copy welcome page files from USB or network share
# Assuming files are available at /home/pi/WelcomeSign/
if [ -d "/home/pi/WelcomeSign" ]; then
    echo "Copying welcome page files..."
    cp /home/pi/WelcomeSign/welcome_sign.html $APP_DIR/
    cp /home/pi/WelcomeSign/airbnb_welcome_parser.py $APP_DIR/
else
    echo "WARNING: WelcomeSign directory not found at /home/pi/WelcomeSign"
    echo "Please manually copy welcome_sign.html and airbnb_welcome_parser.py to $APP_DIR"
fi

chmod +x $APP_DIR/airbnb_welcome_parser.py

# Configure hostapd
echo "Configuring hostapd..."
sudo bash -c "cat > /etc/hostapd/hostapd.conf <<'EOF'
interface=$WIFI_IFACE
driver=nl80211
ssid=1011A2-5G
hw_mode=a
channel=36
ieee80211n=1
ieee80211ac=1
wmm_enabled=1
wpa=2
wpa_passphrase=NashRocks!
wpa_key_mgmt=WPA-PSK
wpa_pairwise=CCMP
wpa_ptk_rekey=600
country_code=US
EOF
"

sudo sed -i 's/#DAEMON_CONF=""/DAEMON_CONF="\/etc\/hostapd\/hostapd.conf"/' /etc/default/hostapd

# Configure dnsmasq for DHCP and DNS hijacking
echo "Configuring dnsmasq..."
sudo bash -c "cat > /etc/dnsmasq.d/captive-portal.conf <<'EOF'
# Only listen on the WiFi interface
interface=$WIFI_IFACE
listen-address=192.168.4.1

# DHCP configuration
dhcp-range=192.168.4.100,192.168.4.200,255.255.255.0,12h
dhcp-option=option:router,192.168.4.1
dhcp-option=option:dns-server,192.168.4.1

# DNS hijacking: redirect all DNS to this machine
address=/#/192.168.4.1
address=/google.com/192.168.4.1
address=/google.dns/192.168.4.1
address=/www.apple.com/192.168.4.1
address=/captive.apple.com/192.168.4.1
address=/connectivitycheck.gstatic.com/192.168.4.1
address=/msftncsi.com/192.168.4.1
EOF
"

# Backup original dnsmasq config
sudo cp /etc/dnsmasq.conf /etc/dnsmasq.conf.bak

# Disable standard DNS if it exists
sudo bash -c "cat > /etc/dnsmasq.conf <<'EOF'
# Main dnsmasq config - see /etc/dnsmasq.d/ for additional configs
bind-interfaces
user=dnsmasq
group=dnsmasq
log-facility=/var/log/dnsmasq.log
EOF
"

# Configure static IP on WiFi interface
echo "Configuring static IP..."
sudo bash -c "cat >> /etc/dhcpcd.conf <<'EOF'
interface $WIFI_IFACE
static ip_address=192.168.4.1/24
static routers=192.168.4.1
nohook wpa_supplicant
EOF
"

# Configure iptables for NAT (allow internet sharing from eth0)
echo "Configuring iptables..."
sudo bash -c "cat > /etc/iptables/rules.v4 <<'EOF'
*filter
:INPUT ACCEPT [0:0]
:FORWARD DROP [0:0]
:OUTPUT ACCEPT [0:0]
-A FORWARD -i $WIFI_IFACE -o $ETH_IFACE -m conntrack --ctstate NEW -j ACCEPT
-A FORWARD -i $WIFI_IFACE -o $ETH_IFACE -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
COMMIT
*nat
:PREROUTING ACCEPT [0:0]
:INPUT ACCEPT [0:0]
:OUTPUT ACCEPT [0:0]
:POSTROUTING ACCEPT [0:0]
-A POSTROUTING -o $ETH_IFACE -j MASQUERADE
COMMIT
EOF
"

# Make iptables permanent
sudo bash -c "cat > /etc/network/if-pre-up.d/iptables <<'EOF'
#!/bin/bash
/sbin/iptables-restore < /etc/iptables/rules.v4
EOF
"
sudo chmod +x /etc/network/if-pre-up.d/iptables

# Enable IP forwarding
sudo sed -i 's/#net.ipv4.ip_forward=1/net.ipv4.ip_forward=1/' /etc/sysctl.conf
sudo sysctl -p

# Configure nginx as reverse proxy and web server
echo "Configuring nginx..."
sudo bash -c "cat > /etc/nginx/sites-available/welcome-portal <<'EOF'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    root $APP_DIR;

    # Serve welcome page
    location / {
        try_files \$uri @fallback;
    }

    location @fallback {
        rewrite ^(.*)$ /welcome_sign.html break;
    }

    # Serve all files from app directory
    location ~* \.(html|css|js|jpg|jpeg|png|gif|ico|svg)$ {
        expires 1m;
        add_header Cache-Control "public";
    }
}
EOF
"

sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sf /etc/nginx/sites-available/welcome-portal /etc/nginx/sites-enabled/

# Test nginx config
sudo nginx -t

# Create cron job to refresh welcome page every 6 hours
echo "Setting up cron job for welcome page updates..."
(sudo crontab -u pi -l 2>/dev/null || echo "") | sudo tee /tmp/crontab.tmp > /dev/null
echo "0 */6 * * * python3 $APP_DIR/airbnb_welcome_parser.py" | sudo tee -a /tmp/crontab.tmp > /dev/null
sudo crontab -u pi /tmp/crontab.tmp
rm /tmp/crontab.tmp

# Enable and start services
echo "Enabling and starting services..."
sudo systemctl unmask hostapd
sudo systemctl enable hostapd
sudo systemctl start hostapd

sudo systemctl enable dnsmasq
sudo systemctl restart dnsmasq

sudo systemctl enable nginx
sudo systemctl restart nginx

# Reboot to apply all changes
echo ""
echo "=== Setup Complete ==="
echo "WiFi Network: 1011A2-5G"
echo "Password: NashRocks!"
echo ""
echo "Rebooting in 10 seconds to apply all changes..."
echo "After reboot, the Pi will broadcast the WiFi network."
sleep 10
sudo reboot
