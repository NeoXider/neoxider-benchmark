#!/usr/bin/env bash
# Neoxider Benchmark — запуск из любого харнесса, в том числе другим агентом.
#
#   ./bench.sh <модель> [профиль] [доп. флаги run.py]
#
# Примеры:
#   ./bench.sh opencode/x-preview-f-free minimal
#   ./bench.sh opencode/x-preview-f-free            # догонит остальное
#   ./bench.sh claude/claude-opus-5 full --tasks spatial
#   ./bench.sh --all-free minimal                   # все бесплатные подряд
#   ./bench.sh --status opencode/x-preview-f-free   # что осталось
#
# Прогон докатывается: уже посчитанные уровни не пересчитываются.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python}"

FREE_MODELS=(
  "opencode/x-preview-f-free"
  "opencode/muse-spark-1.2-contributor-free"
  "opencode/pickle-rick-free"
  "opencode/hy3-free"
  "opencode/mimo-free"
  "opencode/nemotron-ultra-free"
  "opencode/lightning-free"
)

usage() {
  sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

[ $# -eq 0 ] && usage 1
case "$1" in -h|--help|help) usage 0 ;; esac

if [ "$1" = "--status" ]; then
  shift
  "$PY" "$HERE/run.py" --status --model "${1:?нужна модель}" "${@:2}"
  exit $?
fi

if [ "$1" = "--report" ]; then
  "$PY" "$HERE/run.py" --report
  exit $?
fi

if [ "$1" = "--list" ]; then
  "$PY" "$HERE/run.py" --list
  exit $?
fi

if [ "$1" = "--all-free" ]; then
  PROFILE="${2:-minimal}"
  shift 2 2>/dev/null || shift $#
  rc=0
  for m in "${FREE_MODELS[@]}"; do
    echo ""
    echo "=============================================================="
    echo " $m  (профиль $PROFILE)"
    echo "=============================================================="
    # Падение одной модели не должно ронять всю серию: движки на бесплатных
    # моделях регулярно рвут соединение. Что не досчиталось — доберётся
    # следующим запуском, результат докатывается.
    "$PY" "$HERE/run.py" --model "$m" --profile "$PROFILE" "$@" || {
      rc=1
      echo "!! $m завершилась с ошибкой, продолжаю со следующей"
    }
  done
  "$PY" "$HERE/run.py" --report
  exit $rc
fi

MODEL="$1"; shift
PROFILE=""
if [ $# -gt 0 ]; then
  case "$1" in
    minimal|quick|full|offline) PROFILE="$1"; shift ;;
  esac
fi

if [ -n "$PROFILE" ]; then
  exec "$PY" "$HERE/run.py" --model "$MODEL" --profile "$PROFILE" "$@"
fi
exec "$PY" "$HERE/run.py" --model "$MODEL" "$@"
