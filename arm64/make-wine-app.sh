#!/bin/bash
# Wrap an arm64 executable (the Wine loader, or tests/pagezero_probe.c) in an
# app bundle signed with com.apple.developer.cross-architecture-support, so it
# may use the low 4GB. That entitlement is restricted: macOS kills a process
# claiming it unless an Apple-issued provisioning profile authorising it is
# embedded, so the profile is checked here before anything is signed.
#
# usage: make-wine-app.sh EXECUTABLE APP_DIRECTORY PROFILE IDENTITY_SHA1 [NAME=TARGET...]
#   NAME=TARGET adds Contents/MacOS/NAME as a symlink, e.g. ntdll.so=../../../ntdll.so
#   so the loader, which looks beside its resolved path, finds ntdll.so.
set -euo pipefail
usage="usage: make-wine-app.sh EXECUTABLE APP_DIRECTORY PROFILE IDENTITY_SHA1 [NAME=TARGET...]"
executable=${1:?$usage}
app=${2:?$usage}
profile=${3:?$usage}
identity=${4:?$usage}
shift 4
entitlement=com.apple.developer.cross-architecture-support

[ -f "$executable" ] || { echo "No executable: $executable" >&2; exit 1; }
[ -f "$profile" ] || { echo "No provisioning profile: $profile" >&2; exit 1; }
[ ! -e "$app" ] || { echo "App bundle already exists: $app" >&2; exit 1; }
[[ "$identity" =~ ^[0-9A-Fa-f]{40}$ ]] || { echo "IDENTITY must be a signing identity's SHA-1" >&2; exit 1; }
identity=$(echo "$identity" | tr a-f A-F)
[ "$(lipo -archs "$executable")" = arm64 ] || { echo "Not an arm64 executable: $executable" >&2; exit 1; }
security find-identity -v -p codesigning | grep -q " $identity " || {
    echo "No valid codesigning identity $identity in the keychain" >&2; exit 1; }

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
security cms -D -i "$profile" > "$work/profile.plist"
# A profile from another team, for another App ID, without the entitlement,
# expired, not issued to this certificate or not covering this Mac would only
# fail later, as an unexplained kill at exec.
device=$(system_profiler SPHardwareDataType | awk -F': ' '/Provisioning UDID/ {print $2}')
bundle_id=$(python3 - "$work/profile.plist" "$identity" "$entitlement" "$device" <<'CHECK_PROFILE'
import datetime, hashlib, plistlib, sys
path, identity, entitlement, device = sys.argv[1:]
with open(path, "rb") as stream:
    profile = plistlib.load(stream)
def fail(message):
    sys.exit(f"Provisioning profile {profile.get('Name', '?')!r}: {message}")
entitlements = profile.get("Entitlements", {})
if entitlements.get(entitlement) is not True:
    fail(f"does not grant {entitlement}")
if not any(p in ("OSX", "macOS") for p in profile.get("Platform", [])):
    fail("is not a macOS profile")
expires = profile["ExpirationDate"]
if expires.replace(tzinfo=datetime.timezone.utc) <= datetime.datetime.now(datetime.timezone.utc):
    fail(f"expired on {expires}")
team = profile["TeamIdentifier"][0]
application = entitlements.get("com.apple.application-identifier", "")
if not application.startswith(team + ".") or application.endswith("*"):
    fail(f"needs an explicit App ID for team {team}, not {application!r}")
if identity not in {hashlib.sha1(c).hexdigest().upper() for c in profile.get("DeveloperCertificates", [])}:
    fail(f"was not issued for signing identity {identity}")
if not profile.get("ProvisionsAllDevices") and device not in profile.get("ProvisionedDevices", []):
    fail(f"does not include this Mac (provisioning UDID {device or 'unknown'})")
print(application[len(team) + 1:])
CHECK_PROFILE
)
team=$(plutil -extract TeamIdentifier.0 raw "$work/profile.plist")

# Assemble and sign in the work directory; only a verified bundle moves into place.
bundle="$work/wine.app"
mkdir -p "$bundle/Contents/MacOS"
cp "$executable" "$bundle/Contents/MacOS/wine"
cp "$profile" "$bundle/Contents/embedded.provisionprofile"
for link in "$@"; do
    [[ "$link" == ?*=?* ]] || { echo "Links are NAME=TARGET, not $link" >&2; exit 1; }
    ln -s "${link#*=}" "$bundle/Contents/MacOS/${link%%=*}"
done
cat > "$bundle/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleExecutable</key>
	<string>wine</string>
	<key>CFBundleIdentifier</key>
	<string>$bundle_id</string>
	<key>CFBundleName</key>
	<string>Wine</string>
	<key>CFBundlePackageType</key>
	<string>APPL</string>
	<key>LSUIElement</key>
	<true/>
</dict>
</plist>
EOF
cat > "$work/entitlements.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>$entitlement</key>
	<true/>
	<key>com.apple.application-identifier</key>
	<string>$team.$bundle_id</string>
	<key>com.apple.developer.team-identifier</key>
	<string>$team</string>
</dict>
</plist>
EOF
codesign --force --sign "$identity" --timestamp=none --entitlements "$work/entitlements.plist" "$bundle"
codesign --verify --verbose=1 "$bundle"
codesign -d --entitlements - --xml "$bundle" 2>/dev/null | grep -q "$entitlement" || {
    echo "Signed bundle does not carry $entitlement" >&2; exit 1; }
mv "$bundle" "$app"
echo "== signed $app as $team.$bundle_id"
