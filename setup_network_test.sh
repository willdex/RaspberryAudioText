#!/bin/bash
# setup_network_test.sh - Verifica/configura puerto para test TCP
# Ejecutar en Raspberry Pi

set -e

echo "=================================================="
echo "  SETUP NETWORK TEST - TCP Audio"
echo "=================================================="

PORT=5005

# --- Verificar estado del puerto ---
echo ""
echo "[1/2] Verificando estado del puerto $PORT..."

# Ver si iptables está activo
if sudo iptables -L INPUT -n 2>/dev/null | grep -q "$PORT"; then
    echo "  Puerto $PORT ya está permitido en iptables"
else
    echo "  Puerto $PORT no tiene regla explícita"
fi

# Ver si el puerto está escuchando
if netstat -tlnp 2>/dev/null | grep -q "$PORT" || ss -tlnp | grep -q "$PORT"; then
    echo "  Puerto $PORT está en uso (puede ser pi_receiver.py ya corriendo)"
else
    echo "  Puerto $PORT libre"
fi

# --- Abrir puerto si es necesario (para test local) ---
echo ""
echo "[2/2] Configurando iptables para tráfico entrante..."

# Permitir tráfico entrante en puerto 5005
sudo iptables -A INPUT -p tcp --dport $PORT -j ACCEPT 2>/dev/null || \
echo "  (No se pudo agregar regla - puede ser que no sea necesario)"

# Verificar
sudo iptables -L INPUT -n | grep "$PORT" || echo "  (Puerto configurado o no disponible)"

echo ""
echo "=================================================="
echo "  CONFIGURACIÓN COMPLETA"
echo "=================================================="
echo ""
echo "  Puerto: $PORT"
echo ""
echo "  Para ejecutar el receiver:"
echo "    cd ~/RaspberryAudioText"
echo "    python3 pi_receiver.py"
echo ""
echo "  Luego en Windows:"
echo "    python3 windows_sender.py"
echo ""