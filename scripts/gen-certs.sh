#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
CERT_DIR="$REPO_ROOT/config/traefik/certs"

mkdir -p "$CERT_DIR"

if [ -s "$CERT_DIR/ca.crt" ] && [ -s "$CERT_DIR/server.crt" ] && [ -s "$CERT_DIR/server.key" ]; then
  exit 0
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cat > "$TMP_DIR/openssl.cnf" <<'EOF'
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_ca
prompt = no

[req_distinguished_name]
CN = Orion Lab Root CA
O = Nordel Lab

[v3_ca]
basicConstraints = critical,CA:TRUE
keyUsage = critical,keyCertSign,cRLSign
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always

[v3_server]
basicConstraints = CA:FALSE
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
subjectAltName = @alt_names

[alt_names]
DNS.1 = traefik
DNS.2 = localhost
DNS.3 = orion.local
IP.1 = 127.0.0.1
EOF

openssl req -x509 -nodes -newkey rsa:2048 \
  -days 3650 \
  -keyout "$TMP_DIR/ca.key" \
  -out "$CERT_DIR/ca.crt" \
  -config "$TMP_DIR/openssl.cnf" \
  -extensions v3_ca >/dev/null 2>&1

openssl req -nodes -newkey rsa:2048 \
  -keyout "$CERT_DIR/server.key" \
  -out "$TMP_DIR/server.csr" \
  -subj "/CN=traefik/O=Nordel Lab" >/dev/null 2>&1

openssl x509 -req \
  -in "$TMP_DIR/server.csr" \
  -CA "$CERT_DIR/ca.crt" \
  -CAkey "$TMP_DIR/ca.key" \
  -CAcreateserial \
  -out "$CERT_DIR/server.crt" \
  -days 825 \
  -extfile "$TMP_DIR/openssl.cnf" \
  -extensions v3_server >/dev/null 2>&1

chmod 0644 "$CERT_DIR/ca.crt" "$CERT_DIR/server.crt" "$CERT_DIR/server.key"
