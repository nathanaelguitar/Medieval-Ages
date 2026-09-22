#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ "$(uname -s)" != "Darwin" ]; then
    echo "Xcode generation needs macOS. Portable tests: ./scripts/test.sh" >&2
    exit 1
fi
if ! command -v cmake >/dev/null 2>&1; then
    echo "Install CMake first (for example: brew install cmake), then run this again." >&2
    exit 1
fi
if ! xcrun --sdk iphoneos --show-sdk-path >/dev/null 2>&1; then
    echo "Install/open Xcode and select it with xcode-select before continuing." >&2
    exit 1
fi
if [ "${1:-}" = "--simulator" ]; then
    build=build-simulator
    sdk=iphonesimulator
    arch=$(uname -m)
else
    build=build-ios
    sdk=iphoneos
    arch=arm64
fi
cmake -S . -B "$build" -G Xcode \
    -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT="$sdk" \
    -DCMAKE_OSX_ARCHITECTURES="$arch" -DCMAKE_OSX_DEPLOYMENT_TARGET=15.0
open "$build/OpenEmpire.xcodeproj"
echo "In Xcode: select OpenEmpire, choose your Team under Signing & Capabilities, then Run."
