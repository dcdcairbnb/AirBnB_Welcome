#!/bin/bash
#
# check_health.sh
# On-demand health snapshot for the Pi + Omada stack.
# Run on the Pi directly, or via SSH from your laptop:
#   ssh pi@<tailscale-ip> 'bash -s' < check_health.sh
#
# Checks:
#   - Pi uptime, load, memory, disk, CPU temp
#   - Docker containers
#   - Omada Controller API reachability + version
#   - nginx, omada-auth, cloudflared-tunnel, tailscaled, tunnel-url-watcher
#   - EAP count and adoption status (via Omada API if credentials provided)
#   - Recent errors in service journals
#
# Exit code 0 if everything is healthy, 1 if any critical check failed.

set -u

FAIL=0
PI_IP="${PI_IP:-127.0.0.1}"
OMADA_URL="${OMADA_URL:-https://${PI_IP}:8043}"

green="\033[32m"
red="\033[31m"
yellow="\033[33m"
bold="\033[1m"
reset="\033[0m"

ok()   { echo -e "  ${green}OK${reset}    $*"; }
warn() { echo -e "  ${yellow}WARN${reset}  $*"; }
bad()  { echo -e "  ${red}FAIL${reset}  $*"; FAIL=1; }
hdr()  { echo -e "\n${bold}== $* ==${reset}"; }

hdr "Pi host"
uptime_str=$(uptime -p 2>/dev/null || uptime)
ok "uptime: $uptime_str"
load=$(awk '{print $1, $2, $3}' /proc/loadavg)
ok "load avg: $load"

mem_total=$(free -m | awk '/^Mem:/{print $2}')
mem_used=$(free -m | awk '/^Mem:/{print $3}')
mem_pct=$((100 * mem_used / mem_total))
if [ "$mem_pct" -gt 90 ]; then bad "memory ${mem_used}M / ${mem_total}M (${mem_pct}%)"
elif [ "$mem_pct" -gt 75 ]; then warn "memory ${mem_used}M / ${mem_total}M (${mem_pct}%)"
else ok "memory ${mem_used}M / ${mem_total}M (${mem_pct}%)"; fi

disk_pct=$(df / | tail -1 | awk '{print $5}' | tr -d '%')
if [ "$disk_pct" -gt 90 ]; then bad "root disk ${disk_pct}% used"
elif [ "$disk_pct" -gt 80 ]; then warn "root disk ${disk_pct}% used"
else ok "root disk ${disk_pct}% used"; fi

if command -v vcgencmd >/dev/null 2>&1; then
  temp=$(vcgencmd measure_temp | cut -d= -f2)
  temp_num=$(echo "$temp" | tr -d "'C")
  temp_int=${temp_num%.*}
  if [ "$temp_int" -gt 80 ]; then bad "CPU temp $temp"
  elif [ "$temp_int" -gt 70 ]; then warn "CPU temp $temp"
  else ok "CPU temp $temp"; fi
fi

hdr "systemd services"
for svc in nginx omada-auth cloudflared-tunnel tunnel-url-watcher.timer tailscaled; do
  state=$(systemctl is-active "$svc" 2>/dev/null || echo "not-installed")
  case "$state" in
    active)   ok "$svc ($state)" ;;
    inactive|failed) bad "$svc ($state)" ;;
    not-installed)   warn "$svc not installed" ;;
    *)        warn "$svc ($state)" ;;
  esac
done

hdr "Docker"
docker_cmd=""
if command -v docker >/dev/null 2>&1; then
  if docker ps >/dev/null 2>&1; then
    docker_cmd="docker"
  elif sudo -n docker ps >/dev/null 2>&1; then
    docker_cmd="sudo -n docker"
  fi
  if [ -n "$docker_cmd" ]; then
    status=$($docker_cmd ps --filter name=omada-controller --format '{{.Status}}')
    if echo "$status" | grep -q "Up"; then
      ok "omada-controller container: $status"
    else
      # Fallback: if controller port 8043 is open, container is effectively up
      if ss -tln 2>/dev/null | grep -q ":8043 "; then
        ok "omada-controller port 8043 listening (container considered up)"
      else
        bad "omada-controller container is not running"
      fi
    fi
  else
    # No docker access. Fall back to port check.
    if ss -tln 2>/dev/null | grep -q ":8043 "; then
      ok "omada-controller port 8043 listening (docker not queryable without sudo)"
    else
      warn "docker requires sudo over SSH, and port 8043 is not listening"
    fi
  fi
else
  warn "docker not installed"
fi

hdr "Omada Controller API"
resp=$(curl -sk --max-time 5 "${OMADA_URL}/api/info" || true)
if [ -z "$resp" ]; then
  bad "controller API unreachable at ${OMADA_URL}"
else
  ver=$(echo "$resp" | python3 -c "import sys,json;print(json.load(sys.stdin).get('result',{}).get('controllerVer',''))" 2>/dev/null)
  cid=$(echo "$resp" | python3 -c "import sys,json;print(json.load(sys.stdin).get('result',{}).get('omadacId',''))" 2>/dev/null)
  if [ -n "$ver" ]; then
    ok "controller reachable, version $ver"
    ok "omadac id: $cid"
  else
    warn "API returned but no version field: $resp"
  fi
fi

hdr "Flask auth bridge"
resp=$(curl -sf --max-time 20 http://127.0.0.1/reservation 2>/dev/null || true)
if [ -z "$resp" ]; then
  bad "/reservation endpoint not responding within 20s"
else
  if echo "$resp" | grep -q '"guest_name"'; then
    guest=$(echo "$resp" | python3 -c "import sys,json;print(json.load(sys.stdin).get('guest_name',''))" 2>/dev/null)
    ok "/reservation OK (guest: ${guest:-<none>})"
  else
    warn "/reservation responded but payload looks off"
  fi
fi

resp=$(curl -sf --max-time 15 http://127.0.0.1/events 2>/dev/null || true)
if [ -z "$resp" ]; then
  warn "/events not responding (Ticketmaster fetch may have failed)"
else
  count=$(echo "$resp" | python3 -c "import sys,json;print(len(json.load(sys.stdin)))" 2>/dev/null || echo 0)
  ok "/events returned $count events"
fi

hdr "Recent service errors (last 50 lines)"
for svc in omada-auth nginx cloudflared-tunnel; do
  logs=$(journalctl -u "$svc" -n 50 --no-pager 2>/dev/null)
  if [ -z "$logs" ]; then
    logs=$(sudo -n journalctl -u "$svc" -n 50 --no-pager 2>/dev/null)
  fi
  if [ -z "$logs" ]; then
    warn "$svc: cannot read journal (needs sudo)"
    continue
  fi
  errs=$(echo "$logs" | grep -iE "error|fail|traceback" | tail -3)
  if [ -n "$errs" ]; then
    warn "$svc recent errors:"
    echo "$errs" | sed 's/^/        /'
  else
    ok "$svc: no recent errors"
  fi
done

hdr "Network"
if ping -c 1 -W 2 1.1.1.1 >/dev/null 2>&1; then
  ok "internet reachable (1.1.1.1)"
else
  bad "cannot reach 1.1.1.1"
fi

if command -v tailscale >/dev/null 2>&1; then
  ts_ip=$(tailscale ip -4 2>/dev/null | head -1)
  [ -n "$ts_ip" ] && ok "tailscale ip $ts_ip" || warn "tailscale not connected"
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo -e "${green}${bold}OVERALL: healthy${reset}"
else
  echo -e "${red}${bold}OVERALL: issues found (see FAIL lines above)${reset}"
fi
exit $FAIL
