#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${ROOT_DIR}/build/lambda"
PACKAGE_DIR="${BUILD_DIR}/package"
ZIP_PATH="${BUILD_DIR}/pet-sitting-palantir-lambda.zip"

rm -rf "${PACKAGE_DIR}" "${ZIP_PATH}"
mkdir -p "${PACKAGE_DIR}"

uv --cache-dir "${ROOT_DIR}/.uv-cache" pip install \
    --python 3.14 \
    --target "${PACKAGE_DIR}" \
    "${ROOT_DIR}"

PACKAGE_DIR="${PACKAGE_DIR}" ZIP_PATH="${ZIP_PATH}" uv --cache-dir "${ROOT_DIR}/.uv-cache" run --python 3.14 python - <<'PY'
from os import environ
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

package_dir = Path(environ["PACKAGE_DIR"])
zip_path = Path(environ["ZIP_PATH"])

with ZipFile(zip_path, "w", ZIP_DEFLATED) as archive:
    for path in sorted(package_dir.rglob("*")):
        if path.is_file():
            archive.write(path, path.relative_to(package_dir))
PY

printf '%s\n' "${ZIP_PATH}"
