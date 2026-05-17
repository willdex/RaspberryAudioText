#!/bin/bash
# setup_v3.sh - Configuración completa para Teleprompter v3
# Ejecutar en Raspberry Pi 3 con permisos sudo

set -e

echo "=================================================="
echo "  SETUP TELEPROMPTER v3 PARA RASPBERRY PI 3"
echo "=================================================="

# --- 1. Actualizar sistema e instalar dependencias ---
echo ""
echo "[1/5] Actualizando sistema e instalando dependencias..."
sudo apt update
sudo apt install -y sox alsa-utils git wget

# --- 2. Configurar ALSA ---
echo ""
echo "[2/5] Configurando ALSA..."
# Intentar desactivar Auto Gain Control si existe
amixer -c 2 sset "Auto Gain Control" off 2>/dev/null || echo "  (AGC no disponible)"
amixer -c 2 sset "Master" 3 2>/dev/null || echo "  (Volume no disponible)"
amixer -c 2 sset "Mic" 3 2>/dev/null || echo "  (Mic volume no disponible)"

# Guardar config
sudo alsactl store 2>/dev/null || echo "  (No se pudo guardar ALSA)"

# --- 3. Crear directorio /opt/whisper ---
echo ""
echo "[3/5] Preparando directorio /opt/whisper..."
sudo mkdir -p /opt/whisper/models
cd /opt/whisper

# --- 4. Descargar binario pre-compilado de whisper.cpp para ARM ---
echo ""
echo "[4/5] Descargando binario whisper-linux-armv7l..."
sudo wget -q --show-progress -O whisper https://github.com/ggerganov/whisper.cpp/releases/download/v1.6.0/whisper-linux-armv7l
sudo chmod +x whisper
echo "  whisper-linux-armv7l descargado"

# --- 5. Descargar modelo ggml-tiny.bin ---
echo ""
echo "[5/5] Descargando modelo ggml-tiny.bin..."
sudo wget -q --show-progress -O models/ggml-tiny.bin https://github.com/ggerganov/whisper.cpp/releases/download/v1.6.0/ggml-tiny.bin
echo "  ggml-tiny.bin descargado"

# --- Verificación ---
echo ""
echo "=================================================="
echo "  VERIFICACION DE INSTALACION"
echo "=================================================="
echo "  - sox:         $(which sox)"
echo "  - arecord:     $(which arecord)"
echo "  - whisper:     $(ls -la /opt/whisper/whisper 2>/dev/null || echo 'NO ENCONTRADO')"
echo "  - modelo:       $(ls -la /opt/whisper/models/ 2>/dev/null || echo 'NO ENCONTRADO')"

# --- Test rápido de audio ---
echo ""
echo "  Test de audio (3 segundos)..."
timeout 5 arecord -D plughw:2,0 -f S16_LE -r 44100 -c 1 -d 2 /tmp/test_setup.wav 2>/dev/null && \
sox /tmp/test_setup.wav -n stats 2>/dev/null && echo "  AUDIO OK" || echo "  REVISAR MICROFONO"

echo ""
echo "=================================================="
echo "  SETUP COMPLETO"
echo "=================================================="
echo ""
echo "  Archivos creados:"
echo "    /opt/whisper/whisper"
echo "    /opt/whisper/models/ggml-tiny.bin"
echo ""
echo "  Siguiente paso:"
echo "    cd ~/RaspberryAudioText"
echo "    python3 diagnostico_v2.py --test-pipeline"
echo ""