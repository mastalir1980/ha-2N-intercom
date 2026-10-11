# Run a command on the Pi: over ssh from the Mac, or directly when PI_SSH=local (running on the Pi).
pi() { if [ "${PI_SSH:-}" = "local" ]; then bash -c "$1"; else ssh -o BatchMode=yes -o ConnectTimeout=10 "$PI_SSH" "$1"; fi; }
