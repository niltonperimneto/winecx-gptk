#!/bin/bash
# Run Rise of the Tomb Raider's built-in benchmark on one Direct3D backend in
# the ROTTR test bottle and collect its results file and logs.
#
#   run-rottr.sh BOTTLE_ROOT BACKEND OUT_DIR
#
# BACKEND: dxvk-kk (DXVK on KosmicKrisp), dxmt, d3dmetal. The backend is
# selected for ROTTR.exe only (registry AppDefaults + DLLs in the game folder);
# Steam keeps its own DXVK route. GameWorks DLL overrides already in the
# bottle are kept. Extra environment for the game: EXTRA_ENV="K=V K=V".
set -euo pipefail
root=$(cd "$1" && pwd -P); backend=$2; out=$3
case "$root" in /private/tmp/whisky-rottr-test.*) ;; *) echo "unexpected bottle $root" >&2; exit 1;; esac
mkdir -p "$out"; out=$(cd "$out" && pwd -P)
export WINEPREFIX="$root/prefix" WINESERVER="$root/runtime/Wine/bin/wineserver"
rt="$root/runtime"
game="$WINEPREFIX/drive_c/Program Files (x86)/Steam/steamapps/common/Rise of the Tomb Raider"
steam="$WINEPREFIX/drive_c/Program Files (x86)/Steam"
wine=( "$rt/Wine/bin/wine-kosmickrisp" )

if [ "$backend" = dxmt ]; then
   dxmt="$rt/DXMT/x64"
   for dll in d3d11.dll dxgi.dll d3d10core.dll; do
      [ -f "$dxmt/$dll" ] || { echo "DXMT payload missing: $dxmt/$dll" >&2; exit 1; }
   done
   # WINEDLLOVERRIDES takes precedence over ROTTR.exe's AppDefaults.
   unset WINEDLLOVERRIDES
fi

bash "$root/stop-prefix.sh" >/dev/null 2>&1 || true
trap 'bash "$root/stop-prefix.sh" >/dev/null 2>&1 || true' EXIT

# Game-folder DLLs: keep the original DXVK copies once.
bak="$game/.backend-orig"
if [ ! -d "$bak" ]; then
   mkdir "$bak"; cp -p "$game/d3d11.dll" "$game/dxgi.dll" "$bak/"
fi
rm -f "$game/d3d11.dll" "$game/dxgi.dll" "$game/d3d10core.dll" "$game/winemetal.dll"
case $backend in
   dxvk-kk)  cp -p "$bak/d3d11.dll" "$bak/dxgi.dll" "$game/"
             ovr='d3d11,dxgi=n,b' ;;
   # The runtime supplies the builtin winemetal bridge paired with these DLLs.
   dxmt)     cp -p "$dxmt/d3d11.dll" "$dxmt/dxgi.dll" "$dxmt/d3d10core.dll" "$game/"
             ovr='d3d10core,d3d11,dxgi=n;d3d12,d3d12core=' ;;
   d3dmetal) ovr='d3d10,d3d10core,d3d11,d3d12,dxgi=b' ;;
   *) echo "unknown backend $backend" >&2; exit 1 ;;
esac
key='HKCU\Software\Wine\AppDefaults\ROTTR.exe\DllOverrides'
for dll in d3d10 d3d10core d3d11 d3d12 dxgi; do
   WINEDEBUG=-all "${wine[@]}" reg delete "$key" /v $dll /f >/dev/null 2>&1 || true
done
IFS=';' read -r -a rules <<< "$ovr"
for rule in "${rules[@]}"; do
   IFS=, read -r -a names <<< "${rule%=*}"
   for dll in "${names[@]}"; do
      WINEDEBUG=-all "${wine[@]}" reg add "$key" /v "$dll" /t REG_SZ /d "${rule#*=}" /f >/dev/null
   done
done
WINEDEBUG=-all "${wine[@]}" reg query "$key" > "$out/overrides.txt" 2>&1 || true
bash "$root/stop-prefix.sh" >/dev/null 2>&1 || true

# Environment inherited by Steam and the game.
export WHISKY_CHILD_LAUNCH_POLICY_PATH="$WINEPREFIX/WhiskyGameModePolicy.json"
export WHISKY_GAME_MODE_HOST="$rt/Wine/libexec/GameModeProcessHost.app/Contents/MacOS/GameModeProcessHost"
export WINEDEBUG=-all STEAM_DISABLE_CEF_SANDBOX=1 CEF_DISABLE_SANDBOX=1
export DXVK_LOG_LEVEL=info DXVK_LOG_PATH="$out"
export MESA_KK_PRESENT_LOG="$out/present.csv"
export D3DM_WINE_UNIX_CALL=1 D3DM_VALIDATION=0 MTL_DEBUG_LAYER=0
[ "$backend" = d3dmetal ] && export WINED3DMETAL=1 || export WINED3DMETAL=0
for kv in ${EXTRA_ENV:-}; do export "$kv"; done
env | grep -E '^(WINE|DXVK|MESA_KK|D3DM|MTL_|WINED3DMETAL)' | sort > "$out/env.txt"

marker="$out/.start"; : > "$marker"
since=$(date '+%F %T')
"${wine[@]}" start /unix "$steam/steam.exe" -nooverlayui > "$out/steam.log" 2>&1
ready=0
for n in $(seq 1 60); do
   if awk -v t="$since" 'substr($0,2,19)>=t && /\[Logged On,/{f=1} END{exit !f}' "$steam/logs/connection_log.txt" &&
      awk -v t="$since" 'substr($0,2,19)>=t && /System startup time/{f=1} END{exit !f}' "$steam/logs/console_log.txt"; then
      ready=1; break
   fi
   sleep 2
done
[ $ready = 1 ] || { echo "Steam not ready" >&2; exit 2; }
sleep 5
"${wine[@]}" start /unix "$steam/steam.exe" -applaunch 391220 -nolauncher -noepic -benchmark > "$out/dispatch.log" 2>&1

# Wait for the game to start, then let the player start the in-game benchmark.
t0=$(date +%s)
until ps -axo comm= | grep -q 'ROTTR.exe$'; do
   [ $(( $(date +%s) - t0 )) -lt 300 ] || { echo "game did not start" >&2; exit 3; }
   sleep 2
done
start=$(date +%s)
echo "If the game opens at the main menu, select Start Benchmark. Quit the game after the results screen to collect the output." >&2
# A single ps listing can miss the process (seen around level loads), and
# stopping the prefix on a false miss kills the game: require 3 misses in a row.
misses=0
while [ $misses -lt 3 ]; do
   if ps -axo comm= | grep -q 'ROTTR.exe$'; then misses=0; else misses=$((misses + 1)); fi
   [ $(( $(date +%s) - start )) -lt 1200 ] || { echo "game still running after 20 min" >&2; break; }
   sleep 5
done
echo "game ran $(( $(date +%s) - start )) s" | tee "$out/duration.txt" >&2

# Benchmark results and logs written during the run.
find "$WINEPREFIX/drive_c/users" "$game" -newer "$marker" -type f \( -iname '*bench*' -o -iname '*.txt' -o -iname '*.csv' -o -iname '*.log' \) \
   -not -path '*/shadercache/*' 2>/dev/null > "$out/new-files.txt" || true
while IFS= read -r f; do cp -p "$f" "$out/" 2>/dev/null || true; done < "$out/new-files.txt"
for scene in SpineOfTheMountain ProphetsTomb GeothermalValley; do
   if ! grep -Eq "/${scene}_X_[0-9].*\.txt$" "$out/new-files.txt"; then
      echo "Benchmark did not finish: missing fresh $scene results." >&2
      exit 4
   fi
done
