#!/bin/bash

TUNNEL_HOST=${TUNNEL_HOST:-tunnel}
TUNNEL_PORT=${TUNNEL_PORT:-4040}

echo "tunnel end point [$TUNNEL_HOST:$TUNNEL_PORT]"

while [[ "$(curl -s -o /dev/null -w ''%{http_code}'' "${TUNNEL_HOST}:${TUNNEL_PORT}/status")" != "200" ]]; do
    echo "Waiting for tunnel..."
    sleep 1
done
export ENDPOINT=$(curl --silent "${TUNNEL_HOST}:${TUNNEL_PORT}/start" | ./jq -r '.url')
echo "fetched end point [$ACAPY_ENDPOINT]"
exec "$@"
