#!/usr/bin/env bash
# Nasadi aktualni kod z repozitare do testovaci instance Home Assistantu na Pi.
# Pouziti: ./deploy_test.sh   (pred tim doporuceno ./run_tests.sh)
set -euo pipefail
cd "$(dirname "$0")"

HA_CFG=/home/mastix/homeassistant/config
DEST="$HA_CFG/custom_components/2n_intercom"
STAMP=$(date +%Y%m%d_%H%M%S)
BACKUP="$HA_CFG/.robins_backups/2n_intercom_pre-deploy_$STAMP"

SRC=custom_components/2n_intercom
if [ ! -d "$SRC" ]; then
  echo "✗ Ve repozitari chybi custom_components/2n_intercom"
  exit 1
fi

# 1) kontrola verze
ver=$(grep -o '"version": *"[^"]*"' "$SRC/manifest.json" | cut -d'"' -f4)
echo "== Nasazuji verzi $ver =="

# 2) zaloha soucasneho stavu
mkdir -p "$HA_CFG/.robins_backups"
if [ -d "$DEST" ]; then
  cp -r "$DEST" "$BACKUP"
  echo "✓ Zaloha predchozi verze: $BACKUP"
fi

# 3) synchronizace kodu (bez cache a git souboru)
# pycache pise kontejner jako root — mazeme proto pres docker exec, kam se dostaneme vzdy
rm -rf "$DEST" 2>/dev/null || true
if [ -d "$DEST" ]; then
  docker exec homeassistant rm -rf "/config/custom_components/2n_intercom"
fi
mkdir -p "$DEST"
rsync -a --exclude='__pycache__' --exclude='.pyc' "$SRC/" "$DEST/"
chmod -R a+rX "$DEST"
echo "✓ Kod zkopirovan do $DEST"

# 4) restart HA a cekani na nabehnuti
echo "== Restartuji Home Assistant... =="
docker restart homeassistant >/dev/null
for i in $(seq 1 30); do
  sleep 5
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://192.168.88.28:8123/ || true)
  [ "$code" = "200" ] && break
done
if [ "${code:-000}" != "200" ]; then
  echo "✗ HA se nenabil do 150 s! Koukni do: docker logs homeassistant --tail 50"
  exit 1
fi
sleep 20  # pauza na natazeni integraci po tom, co web odpovida

# 5) overeni ziveho stavu entit 2N
echo "== Kontrola entit 2N po restartu =="
python3 - <<'EOF'
import json, urllib.request
TOKEN=[l.split('=',1)[1].strip() for l in open('/home/mastix/.hermes/.env') if l.startswith('HASS_TOKEN=')][0]
req=urllib.request.Request('http://192.168.88.28:8123/api/states', headers={'Authorization':'Bearer '+TOKEN})
ents=json.load(urllib.request.urlopen(req,timeout=15))
g=[e for e in ents if e['entity_id'].split('.')[1].startswith('2n_intercom')]
for e in g: print(f"  {e['entity_id']}: {e['state']}")
unavail=[e for e in g if e['state'] in ('unavailable','unknown')]
print(f"  -> {len(g)} entit, {len(unavail)} nedostupnych")
if len(g)==0:
    raise SystemExit("✗ Zadne 2N entity! Integrace se nenatahla.")
if unavail:
    raise SystemExit(f"✗ Nedostupne entity: {[e['entity_id'] for e in unavail]}")
EOF

echo ""
echo "✅ DEPLOY OK — verze $ver bezi na testovaci instanci HA."
