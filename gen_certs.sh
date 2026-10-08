#!/bin/sh
# Generates a private CA + a server certificate for the Mosquitto broker,
# and a ca_cert.h file for the ESP8266 firmware.
# Run from the project root:  sh gen_certs.sh <PC_IP_ADDRESS>
set -e
SERVER_IP="${1:?Usage: sh gen_certs.sh <PC_IP_ADDRESS>}"
ROOT="$(pwd)"
mkdir -p "$ROOT/mosquitto/certs" "$ROOT/firmware/esp8266_node"
cd "$ROOT/mosquitto/certs"
rm -f ca.* server.* *.srl

# 1. Certificate authority (this is what the ESP and the Python server will trust)
openssl genrsa -out ca.key 2048
openssl req -x509 -new -nodes -key ca.key -sha256 -days 365 \
  -subj "/CN=SentinelX-CA" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" \
  -out ca.crt

# 2. Server key + certificate signed by the CA
openssl genrsa -out server.key 2048
openssl req -new -key server.key -subj "/CN=$SERVER_IP" -out server.csr
cat > server.ext <<EXT
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
subjectAltName = DNS:$SERVER_IP, IP:$SERVER_IP, DNS:localhost, IP:127.0.0.1, DNS:sentinelx.local
EXT
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt -days 365 -sha256 -extfile server.ext

# The broker container must be able to read the server key (lab setup)
chmod 644 server.key server.crt ca.crt
chmod 600 ca.key

# 3. CA certificate as a C++ header for the ESP8266 sketch
{
  echo 'const char CA_CERT[] PROGMEM = R"EOF('
  cat ca.crt
  echo ')EOF";'
} > "$ROOT/firmware/esp8266_node/ca_cert.h"

echo "Done. Certificates are in mosquitto/certs, ca_cert.h is in firmware/esp8266_node."
