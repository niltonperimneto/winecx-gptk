#!/bin/bash
# After a failed gate: macOS crash reports for Wine processes, plus an lldb
# backtrace of a fresh wineboot, so a startup crash is diagnosable from the
# artifacts alone instead of needing a rerun on a machine with a debugger.
set -uo pipefail
out=${1:-.build/logs/crash}
mkdir -p "$out"
sw_vers > "$out/host.txt"
reports="$HOME/Library/Logs/DiagnosticReports"
[ -d "$reports" ] && find "$reports" -type f -iname '*wine*' -exec cp {} "$out/" \;
[ -x Libraries/Wine/bin/wine64 ] || exit 0
export WINEPREFIX="$PWD/debug-prefix"
export DYLD_FALLBACK_LIBRARY_PATH="$PWD/Libraries/Wine/lib"
export WINEDLLOVERRIDES="mscoree=d;mshtml=d"
python3 - "$out" <<'PY'
import os, subprocess, sys
out = sys.argv[1]
runs = (
    ('wineboot.log', ['./Libraries/Wine/bin/wine64', 'wineboot', '-u'],
     dict(os.environ, WINEDEBUG='+seh,+loaddll'), 120),
    ('lldb.txt', ['xcrun', 'lldb', '--batch', '--arch', 'x86_64',
                  '-o', 'settings set target.disable-aslr false', '-o', 'run',
                  '-o', 'thread backtrace all', '-o', 'register read', '-o', 'image list',
                  '--', './Libraries/Wine/bin/wine64', 'wineboot', '-u'], None, 90),
)
for name, command, env, seconds in runs:
    with open(os.path.join(out, name), 'w') as stream:
        try:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, env=env, timeout=seconds)
        except (OSError, subprocess.TimeoutExpired) as error:
            stream.write(f'{error}\n')
PY
exit 0
