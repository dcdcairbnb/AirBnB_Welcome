#!/bin/bash
# Deploy splash page, welcome sign, and hero image from omada-controller to 192.168.0.217
# Expects source files in ~/webroot-src/
# Run with: bash deploy-splash.sh

PI_USER="pi"
PI_HOST="192.168.0.217"
PI_PATH="/var/www/html"
SRC_DIR="$HOME/webroot-src"

FILES=(
  "splash.html"
  "living-room.jpg"
  "welcome_sign.html"
)

echo "Deploying to $PI_HOST..."

for f in "${FILES[@]}"; do
  if [ ! -f "$SRC_DIR/$f" ]; then
    echo "SKIP  $f - not found in $SRC_DIR"
    continue
  fi
  echo "COPY  $f"
  scp "$SRC_DIR/$f" "${PI_USER}@${PI_HOST}:/tmp/$f"
  if [ $? -ne 0 ]; then
    echo "FAIL  $f on scp"
    continue
  fi
  ssh -t "${PI_USER}@${PI_HOST}" "sudo mv /tmp/$f $PI_PATH/$f && sudo chown www-data:www-data $PI_PATH/$f"
  if [ $? -eq 0 ]; then
    echo "OK    $f"
  else
    echo "FAIL  $f on move"
  fi
done

echo
echo "URLs:"
echo "  http://$PI_HOST/splash.html"
echo "  http://$PI_HOST/welcome_sign.html"
