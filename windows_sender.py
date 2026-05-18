#!/usr/bin/env python3
"""
windows_sender.py - Envía audio de microphone por TCP a Raspberry Pi
Ejecutar en PC con Windows

Uso:
    python3 windows_sender.py
"""

import socket
import sounddevice as sd
import numpy as np
import threading
import time
import sys

# === CONFIGURACIÓN ===
RASPBERRY_IP = "192.168.1.110"  # Cambiar por IP de tu Raspberry Pi
TCP_PORT = 5005
SAMPLE_RATE = 16000
BLOCK_SIZE = 1600  # 100ms @ 16kHz
CHANNELS = 1
DTYPE = 'int16'
# ====================

print("=" * 50)
print("  WINDOWS SENDER - Audio por TCP")
print("=" * 50)
print()
print(f"  Raspberry Pi: {RASPBERRY_IP}:{TCP_PORT}")
print(f"  Audio: {SAMPLE_RATE}Hz, {CHANNELS} canal, {DTYPE}")
print(f"  Bloque: {BLOCK_SIZE} muestras ({BLOCK_SIZE/SAMPLE_RATE*1000:.0f}ms)")
print()

sock = None
streaming = [False]


def print_devices():
    print("  Dispositivos de audio disponibles:")
    for i, dev in enumerate(sd.query_devices()):
        if dev['max_input_channels'] > 0:
            print(f"    {i}: {dev['name']} (in={dev['max_input_channels']})")
    print()


def callback(indata, frames, time_info, status):
    if status:
        print(f"  [Audio] status: {status}", file=sys.stderr)

    if streaming[0] and sock:
        try:
            data = indata[:, 0].tobytes()
            sock.sendall(data)
        except Exception as e:
            print(f"\n  [Error] Envío: {e}")
            streaming[0] = False


def connect_to_pi():
    global sock
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        print(f"  Conectando a {RASPBERRY_IP}:{TCP_PORT}...")
        sock.connect((RASPBERRY_IP, TCP_PORT))
        sock.settimeout(None)
        print("  ✓ Conectado!")
        return True
    except socket.timeout:
        print("  ✗ Timeout: Raspberry Pi no responde")
        return False
    except ConnectionRefusedError:
        print("  ✗ Conexión rechazada: ¿Está pi_receiver.py ejecutándose en la Pi?")
        return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def main():
    print_devices()

    # Conectar a Raspberry Pi
    if not connect_to_pi():
        print("\n  No se pudo conectar. Verifica:")
        print("    1. IP correcta de Raspberry Pi")
        print("    2. pi_receiver.py ejecutándose en la Pi")
        print("    3. Red WiFi/LAN en la misma subred")
        return

    streaming[0] = True

    # Encontrar micrófono
    device = None
    for i, dev in enumerate(sd.query_devices()):
        if dev['max_input_channels'] > 0 and 'USB' in dev['name']:
            device = i
            break

    if device is None:
        # Usar default
        device = sd.default.device['input']
        print(f"  Usando dispositivo default: {device}")
    else:
        print(f"  Micrófono USB: dispositivo {device}")

    print()
    print("  Iniciando stream de audio...")
    print("  Presiona Ctrl+C para detener")
    print("-" * 50)

    try:
        stream = sd.InputStream(
            device=device,
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_SIZE,
            dtype=DTYPE,
            channels=CHANNELS,
            callback=callback
        )

        with stream:
            while streaming[0]:
                time.sleep(0.5)
                # Indicador de que está vivo
                print(f"\r  Enviando audio... ({time.strftime('%H:%M:%S')})", end="", flush=True)

    except KeyboardInterrupt:
        print("\n\n  Deteniendo...")
        streaming[0] = False

    except Exception as e:
        print(f"\n  Error: {e}")

    finally:
        if sock:
            sock.close()
        print("  Socket cerrado.")


if __name__ == "__main__":
    main()