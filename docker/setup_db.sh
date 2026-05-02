#!/bin/bash
echo "Criando extensões..."

docker exec trading_postgres psql -U trading -d trading_analyzer -c "
  CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
  CREATE EXTENSION IF NOT EXISTS vector;
"

echo "Verificando extensões instaladas..."
docker exec trading_postgres psql -U trading -d trading_analyzer -c "\dx"
