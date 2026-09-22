#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cmake -S "$root" -B "$root/build-tests" -DOE_BUILD_TESTS=ON
cmake --build "$root/build-tests" --parallel
ctest --test-dir "$root/build-tests" --output-on-failure
