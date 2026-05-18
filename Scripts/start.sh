#!/usr/bin/env bash
# 초기 설정 한 번에 — env 로드 → 검증 → (선택) ngrok 자동 탐지 → uvicorn 실행.
#
# 사용:
#   cp Scripts/.env.local.example Scripts/.env.local
#   # Scripts/.env.local 을 본인 값으로 채우고
#   bash Scripts/start.sh
#
# ngrok URL 자동 탐지 (ngrok 이 미리 켜져 있을 때):
#   AUTO_NGROK=1 bash Scripts/start.sh
#
# 포트 변경:
#   PORT=9000 bash Scripts/start.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$SCRIPT_DIR/.env.local"

cd "$ROOT"

# --- 1) .env.local 로드 ---------------------------------------------------
if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE 가 없습니다." >&2
    echo "       cp Scripts/.env.local.example Scripts/.env.local 후 값을 채우세요." >&2
    exit 1
fi

# set -a: 이후 정의되는 변수 자동 export. set +a 로 해제.
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# --- 2) AUTO_NGROK=1 이면 ngrok local API 에서 https URL 탐지 ----------------
# WSL 에서 실행하는데 ngrok 이 Windows 쪽에서 떠 있으면 127.0.0.1 으론 못 닿는다.
# WSL2 의 Windows 호스트 IP를 /etc/resolv.conf 또는 ip route 에서 가져와 fallback.
detect_ngrok_url() {
    local host="$1"
    curl -fsS --max-time 1 "http://${host}:4040/api/tunnels" 2>/dev/null \
        | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
urls = [t['public_url'] for t in data.get('tunnels', []) if t['public_url'].startswith('https')]
print(urls[0] if urls else '')
" 2>/dev/null || true
}

if [[ "${AUTO_NGROK:-}" == "1" ]]; then
    # 후보 호스트들: WSL 안 ngrok → Windows 호스트 ngrok 순.
    candidates=(127.0.0.1)
    if grep -qi microsoft /proc/version 2>/dev/null; then
        win_host=$(ip route show default 2>/dev/null | awk '/default/ {print $3; exit}')
        [[ -n "$win_host" ]] && candidates+=("$win_host")
        ns_host=$(awk '/^nameserver/ {print $2; exit}' /etc/resolv.conf 2>/dev/null)
        [[ -n "$ns_host" && "$ns_host" != "$win_host" ]] && candidates+=("$ns_host")
    fi

    detected=""
    for host in "${candidates[@]}"; do
        detected=$(detect_ngrok_url "$host")
        if [[ -n "$detected" ]]; then
            echo "[start.sh] AUTO_NGROK → ${host}:4040 에서 tunnel 발견"
            break
        fi
    done

    if [[ -n "$detected" ]]; then
        export PUBLIC_BASE_URL="$detected"
        echo "[start.sh] AUTO_NGROK → PUBLIC_BASE_URL=$PUBLIC_BASE_URL"
    else
        echo "[start.sh] WARN: ngrok local API에서 tunnel을 못 찾았습니다. 시도한 호스트: ${candidates[*]}" >&2
        echo "          → ngrok이 실행 중인지 확인하거나, .env.local 의 PUBLIC_BASE_URL 을 수동 설정하세요." >&2
    fi
fi

# --- 3) 환경변수 검증 -----------------------------------------------------
# 필수    : GOOGLE_CLOUD_PROJECT  (LLM/임베딩에 반드시 필요. 스텁 모드면 이마저 불필요.)
# 선택    : TWILIO_*, PUBLIC_BASE_URL  (음성 통화/Media Streams 에만 필요)
#           누락돼도 웹 채팅(/web/), /chat, /conversation 은 정상 동작.

required_missing=()
if [[ -z "${GOOGLE_CLOUD_PROJECT:-}" && -z "${CHAT_STUB_RESPONSE:-}" ]]; then
    required_missing+=("GOOGLE_CLOUD_PROJECT")
fi
if [[ ${#required_missing[@]} -gt 0 ]]; then
    echo "ERROR: 필수 환경 변수가 비어 있습니다: ${required_missing[*]}" >&2
    echo "       Scripts/.env.local 또는 셸에서 export 후 다시 실행하세요." >&2
    echo "       (LLM 호출 없이 흐름만 보고 싶다면 CHAT_STUB_RESPONSE=\"…\" 설정으로 우회 가능)" >&2
    exit 1
fi

voice_missing=()
for var in TWILIO_ACCOUNT_SID TWILIO_AUTH_TOKEN TWILIO_FROM_NUMBER PUBLIC_BASE_URL; do
    [[ -z "${!var:-}" ]] && voice_missing+=("$var")
done
VOICE_READY=true
if [[ ${#voice_missing[@]} -gt 0 ]]; then
    VOICE_READY=false
fi

# --- 4) venv 확인 --------------------------------------------------------
VENV="$ROOT/.venv"
if [[ ! -x "$VENV/bin/uvicorn" ]]; then
    echo "ERROR: $VENV/bin/uvicorn 없음." >&2
    echo "       python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

# --- 5) 요약 출력 (시크릿은 마스킹) ----------------------------------------
mask() {
    local v="$1"
    [[ -z "$v" ]] && { echo ""; return; }
    [[ ${#v} -le 8 ]] && { echo "********"; return; }
    echo "${v:0:6}…${v: -2}"
}

echo "[start.sh] 작업 디렉토리: $ROOT"
echo "[start.sh] GCP_PROJECT=${GOOGLE_CLOUD_PROJECT:-(unset)}  LOCATION=${GOOGLE_CLOUD_LOCATION:-us-central1}"
if $VOICE_READY; then
    echo "[start.sh] TWILIO_SID=$(mask "$TWILIO_ACCOUNT_SID")  FROM=$TWILIO_FROM_NUMBER"
    echo "[start.sh] PUBLIC_BASE_URL=$PUBLIC_BASE_URL"
    echo "[start.sh] TTS_VOICE=${TTS_VOICE_NAME:-en-US-Neural2-J}  STT_LANG=${STT_LANGUAGE:-en-US}"
    echo "[start.sh] 활성 기능: 웹 채팅 + 음성 통화 (Twilio)"
else
    echo "[start.sh] 활성 기능: 웹 채팅만 (음성 통화 비활성 — 누락: ${voice_missing[*]})"
fi
if [[ -n "${CHAT_STUB_RESPONSE:-}" ]]; then
    echo "[start.sh] CHAT_STUB_RESPONSE=⚠️  설정됨 (Vertex 우회 — 고정 응답)"
else
    echo "[start.sh] CHAT_STUB_RESPONSE=(unset → 실제 LLM 사용)"
fi

# --- 6) uvicorn 실행 -----------------------------------------------------
PORT="${PORT:-8000}"
echo "[start.sh] uvicorn 시작 → http://localhost:$PORT/web/"
exec "$VENV/bin/uvicorn" app.main:app --host 0.0.0.0 --port "$PORT" "$@"
