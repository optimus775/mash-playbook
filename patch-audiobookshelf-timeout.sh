#!/usr/bin/env bash
set -euo pipefail

# Re-apply audiobookshelf upload timeout override after running the playbook.
# - Copies the current Server.js from the image
# - Adds requestTimeout=0
# - Mounts it into the systemd unit
# - Restarts the service
#
# Fixed version that properly handles service file formatting

SERVICE_FILE="/etc/systemd/system/mash-audiobookshelf.service"
OVERRIDE_DIR="/mash/audiobookshelf/overrides/server"
OVERRIDE_FILE="${OVERRIDE_DIR}/Server.js"
MOUNT_LINE="      --mount type=bind,src=${OVERRIDE_FILE},dst=/app/server/Server.js,ro \\"

log() { printf '[patch-abs] %s\n' "$*"; }

if ! command -v docker >/dev/null 2>&1; then
  log "docker not found"
  exit 1
fi

if [ ! -f "$SERVICE_FILE" ]; then
  log "service file not found: $SERVICE_FILE"
  exit 1
fi

# Detect image tag from service file; fallback to known default.
IMAGE="$(grep -o 'ghcr.io/advplyr/audiobookshelf:[^ ]*' "$SERVICE_FILE" | head -n1 || true)"
IMAGE="${IMAGE:-ghcr.io/advplyr/audiobookshelf:2.32.1}"

tmp_server="$(mktemp)"
cleanup() { rm -f "$tmp_server"; }
trap cleanup EXIT

log "Extracting Server.js from image ${IMAGE}"
docker run --rm "$IMAGE" cat /app/server/Server.js >"$tmp_server"

# Inject requestTimeout=0 if missing.
# Insert requestTimeout if missing
TMP_SERVER="$tmp_server" python3 - <<'PY'
import os
from pathlib import Path
p = Path(os.environ["TMP_SERVER"])
text = p.read_text()
if "requestTimeout" not in text:
    marker = "this.server = http.createServer(app)"
    if marker in text:
        text = text.replace(marker, f"{marker}\n    this.server.requestTimeout = 0", 1)
        p.write_text(text)
    else:
        raise SystemExit("marker_not_found")
PY

log "Installing override to ${OVERRIDE_FILE}"
mkdir -p "$OVERRIDE_DIR"
cp "$tmp_server" "$OVERRIDE_FILE"

# Ensure mount line exists in service file.
if ! grep -qF "$OVERRIDE_FILE" "$SERVICE_FILE"; then
  log "Injecting mount line into service file"
  
  # Create a temporary service file with the correct formatting
  temp_service=$(mktemp)
  awk '
  /^ExecStartPre=\/usr\/bin\/env docker create/ { 
    in_docker_create = 1
    print $0
    next
  }
  in_docker_create && /^      ghcr\.io/ { 
    print "      --mount type=bind,src=/mash/audiobookshelf/overrides/server/Server.js,dst=/app/server/Server.js,ro \\"
    print $0
    in_docker_create = 0
    next
  }
  in_docker_create && /^[[:space:]]*$/ { 
    # Skip empty lines within docker create section
    next
  }
  in_docker_create && /^[^[:space:]-]/ { 
    # End of docker create section, print mount line before continuing
    print "      --mount type=bind,src=/mash/audiobookshelf/overrides/server/Server.js,dst=/app/server/Server.js,ro \\"
    in_docker_create = 0
    print $0
    next
  }
  /ExecStartPre=\/usr\/bin\/env docker network/ { 
    # If we reach the next command without finding the image line, 
    # insert the mount line before this command
    if (in_docker_create) {
      print "      --mount type=bind,src=/mash/audiobookshelf/overrides/server/Server.js,dst=/app/server/Server.js,ro \\"
      in_docker_create = 0
    }
    print $0
    next
  }
  { print $0 }
  ' "$SERVICE_FILE" > "$temp_service"
  
  # Check if the mount line was actually added
  if ! grep -qF "$OVERRIDE_FILE" "$temp_service"; then
    # If not added, try a simpler approach - find the docker create and add mount before the image
    sed "s|\(ghcr\.io/advplyr/audiobookshelf:[^\"]*\)|--mount type=bind,src=/mash/audiobookshelf/overrides/server/Server.js,dst=/app/server/Server.js,ro \\\\\n      \1|" "$SERVICE_FILE" > "$temp_service"
  fi
  
  # Copy the modified service file back
  cp "$temp_service" "$SERVICE_FILE"
  rm "$temp_service"
  
else
  log "Mount line already present"
fi

log "Reloading systemd and restarting service"
systemctl daemon-reload
systemctl restart mash-audiobookshelf
systemctl --no-pager --full status mash-audiobookshelf

log "Done"