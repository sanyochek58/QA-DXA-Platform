#!/usr/bin/env bash
# Сборка и запуск всей платформы (веб-интерфейс + API) в Docker.
#   ./run.sh          — собрать и запустить
#   ./run.sh stop     — остановить
#   ./run.sh logs     — логи
# После запуска: http://localhost:3000 (интерфейс), http://localhost:8000/docs, http://localhost:8001/docs (API)
set -euo pipefail
cd "$(dirname "$0")"

command -v docker >/dev/null || { echo "Нужен Docker: https://docs.docker.com/engine/install/" >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Нужен Docker Compose v2 (docker compose)" >&2; exit 1; }

case "${1:-up}" in
  stop) docker compose down; exit 0 ;;
  logs) docker compose logs -f; exit 0 ;;
esac

if [ ! -f .env ]; then
  cp .env.example .env
  # случайный секрет для JWT вместо значения из примера
  secret=$(head -c 48 /dev/urandom | base64 | tr -d '\n/+=' | head -c 64)
  sed -i.bak "s|^JWT_SECRET=.*|JWT_SECRET=${secret}|" .env && rm -f .env.bak
  echo "Создан .env с новым JWT_SECRET"
fi

docker compose up -d --build
echo
echo "Готово. Интерфейс: http://localhost:3000"
echo "Тестовые входы: admin@dxa-qa.ru / admin12345, doctor@dxa-qa.ru / doctor12345, lab@dxa-qa.ru / lab12345"
