#!/usr/bin/env bash
# Build dist/Orbit.app: a menu-bar agent (no Dock icon) with a stable bundle id.
#
#   pip install -r requirements.txt pyinstaller && bash packaging/mac/build_app.sh
#
# Signing: macOS ties the Accessibility grant to the signature. An ad-hoc signature
# changes with every build, so the grant is lost on each rebuild. Sign with a stable
# identity to keep it:
#   - ORBIT_SIGN_ID="Developer ID Application: ..." (or any code-signing identity), or
#   - a self-signed code-signing certificate named "Orbit Dev" in the login keychain
#     (Keychain Access > Certificate Assistant > Create a Certificate..., Name: Orbit Dev,
#     Identity Type: Self Signed Root, Certificate Type: Code Signing).
# With neither, the build is ad-hoc signed. For distribution use a Developer ID and
# notarize (docs/research-macos.md section 6).
set -euo pipefail
cd "$(dirname "$0")/../.."

# app icon: .icns from the 1024 px master (tools/make_icon.py)
ICONSET=build/Orbit.iconset
rm -rf "$ICONSET" && mkdir -p "$ICONSET"
for px in 16 32 128 256 512; do
  sips -z $px $px orbit/ui/icons/orbit.png --out "$ICONSET/icon_${px}x${px}.png" >/dev/null
  sips -z $((px * 2)) $((px * 2)) orbit/ui/icons/orbit.png --out "$ICONSET/icon_${px}x${px}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o build/Orbit.icns

python -m PyInstaller --noconfirm --windowed --name Orbit --icon build/Orbit.icns \
  --osx-bundle-identifier app.orbit.dial \
  --add-data "orbit/ui/qml:orbit/ui/qml" \
  --add-data "orbit/ui/icons:orbit/ui/icons" \
  --add-data "config.toml:." \
  --hidden-import orbit.platform.mac \
  --hidden-import orbit.platform.mac.input_volume \
  --hidden-import orbit.platform.mac.input_media \
  --hidden-import orbit.platform.mac.output \
  --hidden-import orbit.platform.mac.overlay \
  --hidden-import orbit.platform.mac.input_keys \
  --hidden-import orbit.platform.mac.keytap \
  --hidden-import orbit.ui.controls_ui \
  --hidden-import orbit.ui.settings_window \
  packaging/orbit_main.py

PLIST=dist/Orbit.app/Contents/Info.plist
VERSION=$(python -c "import orbit; print(orbit.__version__)")
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion ${VERSION%%-*}" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string ${VERSION%%-*}" "$PLIST"   # PyInstaller may not write it
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string 13.0" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :NSAppleEventsUsageDescription string 'Orbit forwards play/pause/next from the dial to your music app.'" "$PLIST"
SIGN_ID="${ORBIT_SIGN_ID:-}"
# no -v: a self-signed root is never "valid" (not trusted) unless marked Always Trust,
# yet codesign signs with it fine and the designated requirement stays stable
if [ -z "$SIGN_ID" ] && security find-identity -p codesigning 2>/dev/null | grep -q '"Orbit Dev"'; then
  SIGN_ID="Orbit Dev"
fi
if [ -n "$SIGN_ID" ]; then
  codesign --force --deep --sign "$SIGN_ID" dist/Orbit.app
  echo "built dist/Orbit.app (signed: $SIGN_ID; the Accessibility grant survives rebuilds)"
else
  codesign --force --deep --sign - dist/Orbit.app
  echo "built dist/Orbit.app (ad-hoc signed: re-grant Accessibility after each rebuild)"
fi
