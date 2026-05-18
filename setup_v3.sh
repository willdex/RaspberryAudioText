#!/bin/bash
# setup_v3.sh - Configuracion ALSA para Teleprompter v3
# Ejecutar con permisos sudo

set -e

echo "=================================================="
echo "  SETUP TELEPROMPTER v3 - CIRUGIA DE AUDIO"
echo "=================================================="

# --- 1. Instalar dependencias ---
echo ""
echo "[1/3] Instalando dependencias..."
sudo apt update
sudo apt install -y sox alsa-utils git wget

# --- 2. Configurar ALSA ---
echo ""
echo "[2/3] Configurando ALSA..."

# Dispositivo 2 (USB PnP Sound Device)
# Bajar volumen al minimo absoluto (1 es el ultimo reducto, 0 apaga)
sudo amixer -c 2 cset numid=3 1 2>/dev/null || echo "  (numid=3 no disponible)"
sudo amixer -c 2 sset "Mic" 1 2>/dev/null || echo "  (Mic no disponible)"
sudo amixer -c 2 sset "Capture" 1 2>/dev/null || echo "  (Capture no disponible)"

# Apagar AGC si existe
sudo amixer -c 2 sset "Auto Gain Control" off 2>/dev/null || echo "  (AGC no disponible)"

# Guardar configuracion
sudo alsactl store 2>/dev/null || echo "  (No se pudo guardar ALSA)"

# --- 3. Verificar ---
echo ""
echo "[3/3] Verificacion..."
echo "  - sox:         $(which sox)"
echo "  - arecord:     $(which arecord)"

# Test de audio
echo ""
echo "  Test de audio (2 segundos)..."
timeout 3 arecord -D plughw:2,0 -f S16_LE -r 44100 -c 1 -d 2 /tmp/test_setup.wav 2>/dev/null && \
sox /tmp/test_setup.wav -n stats 2>/dev/null && echo "  AUDIO OK" || echo "  REVISAR MICROFONO"

echo ""
echo "=================================================="
echo "  SETUP COMPLETO"
echo "=================================================="
echo ""
echo "  Configuracion ALSA aplicada:"
echo "    - Volumen de captura: MINIMO (1)"
echo "    - AGC: OFF"
echo ""
echo "  Siguiente paso:"
echo "    python3 diagnostico_v3.py --test-pipeline"
echo ""