#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

load_env_file() {
  local env_file="$1"
  if [[ ! -f "${env_file}" ]]; then
    return 0
  fi

  while IFS= read -r raw_line || [[ -n "${raw_line}" ]]; do
    local line="${raw_line%$'\r'}"
    if [[ -z "${line}" || "${line}" == \#* ]]; then
      continue
    fi
    if [[ ! "${line}" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
      continue
    fi

    local key="${line%%=*}"
    local value="${line#*=}"
    if [[ -n "${!key+x}" ]]; then
      continue
    fi
    if [[ "${value}" =~ ^\".*\"$ || "${value}" =~ ^\'.*\'$ ]]; then
      value="${value:1:${#value}-2}"
    fi
    export "${key}=${value}"
  done < "${env_file}"
}

load_env_file "${ENV_FILE}"

INSTANCE_CONNECTION_NAME="${CLOUDSQL_INSTANCE_CONNECTION_NAME:-${INSTANCE_CONNECTION_NAME:-}}"
if [[ -z "${INSTANCE_CONNECTION_NAME}" ]]; then
  echo "CLOUDSQL_INSTANCE_CONNECTION_NAME is required." >&2
  exit 1
fi

LOCAL_HOST="${TAILMATE_LOCAL_TUNNEL_HOST:-127.0.0.1}"
LOCAL_PORT="${LOCAL_PORT:-${TAILMATE_LOCAL_TUNNEL_PORT:-5432}}"

exec cloud-sql-proxy \
  --address "${LOCAL_HOST}" \
  --port "${LOCAL_PORT}" \
  "${INSTANCE_CONNECTION_NAME}"
