#!/usr/bin/env bash
# Пакетная проверка набора DICOM-исследований в контейнере (без веб-интерфейса и БД).
#   ./run_batch.sh <папка_или_zip> [папка_результатов]
# Результат: results.csv, results.xlsx, series.zip (дополнительные серии с визуализацией).
# Контейнер запускается без сети: изображения никуда не передаются.
set -euo pipefail
cd "$(dirname "$0")"

IN="${1:?Использование: ./run_batch.sh <папка_или_zip_с_DICOM> [папка_результатов]}"
OUT="${2:-./results}"
IMAGE="dxa-qa-ml:1.0"

[ -e "$IN" ] || { echo "Не найдено: $IN" >&2; exit 1; }
command -v docker >/dev/null || { echo "Нужен Docker: https://docs.docker.com/engine/install/" >&2; exit 1; }

mkdir -p "$OUT"
IN_ABS="$(cd "$(dirname "$IN")" && pwd)/$(basename "$IN")"
OUT_ABS="$(cd "$OUT" && pwd)"

docker build -q -t "$IMAGE" ./services/ml >/dev/null
echo "Образ $IMAGE собран"

if [ -d "$IN_ABS" ]; then
  MOUNT=(-v "$IN_ABS":/input:ro); ARG=/input
else
  MOUNT=(-v "$IN_ABS":/input/"$(basename "$IN_ABS")":ro); ARG=/input/"$(basename "$IN_ABS")"
fi

docker run --rm --network none \
  --user "$(id -u):$(id -g)" \
  "${MOUNT[@]}" -v "$OUT_ABS":/output \
  "$IMAGE" python -m app.batch "$ARG" /output
