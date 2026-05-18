#!/usr/bin/env python3
"""
pi_receiver.py - Recibe audio por TCP y lo pasa a Vosk
Ejecutar en Raspberry Pi

Uso:
    python3 pi_receiver.py
    python3 pi_receiver.py --port 5005
    python3 pi_receiver.py --verbose
"""

import socket
import threading
import signal
import json
import time
import sys
import numpy as np
from vosk import Model, KaldiRecognizer, SetLogLevel

SetLogLevel(-1)

# === CONFIGURACIÓN ===
TCP_PORT = 5005
MODEL_PATH = "/home/jose/RaspberryAudioText/modelo"
VOSK_SAMPLERATE = 16000
BLOCK_SIZE = 3200  # 200ms @ 16kHz
VAD_THRESHOLD = 50
SILENCE_TIMEOUT = 1.5
# ====================

running = [False]
server_socket = None
client_socket = None


def audio_callback(indata, frames, time_info, status):
    pass


def process_audio():
    global running, client_socket

    print("  Cargando modelo Vosk...")
    try:
        model = Model(MODEL_PATH)
        rec = KaldiRecognizer(model, VOSK_SAMPLERATE)
        print("  Modelo cargado")
    except Exception as e:
        print(f"  ERROR: {e}")
        running[0] = False
        return

    historial = []
    frase_activa = False
    ultimo_tiempo_voz = 0
    chunk_count = 0

    print("  Esperando audio de Windows...")
    print(" -" * 50)

    buffer = b''

    while running[0]:
        if client_socket is None:
            time.sleep(0.1)
            continue

        try:
            data = client_socket.recv(BLOCK_SIZE)
            if not data:
                print("\n  [Info] Cliente desconectado")
                break

            buffer += data

            # Procesar chunks completos
            while len(buffer) >= BLOCK_SIZE:
                chunk = buffer[:BLOCK_SIZE]
                buffer = buffer[BLOCK_SIZE:]

                # Verificar energía
                audio_np = np.frombuffer(chunk, dtype=np.int16)
                energia = np.sqrt(np.mean(audio_np.astype(np.float32) ** 2))
                hay_voz = energia > VAD_THRESHOLD

                if hay_voz:
                    ultimo_tiempo_voz = time.time()
                    frase_activa = True
                elif frase_activa and (time.time() - ultimo_tiempo_voz > SILENCE_TIMEOUT):
                    # Fin de frase
                    resultado = json.loads(rec.FinalResult())
                    texto = resultado.get("text", "").strip()
                    if texto:
                        historial.append(texto)
                        print(f"\n[FRASE] {texto}")
                    rec.Reset()
                    frase_activa = False

                # Enviar a Vosk
                if rec.AcceptWaveform(chunk):
                    resultado = json.loads(rec.Result())
                    texto = resultado.get("text", "").strip()
                    if texto and len(texto) > 1:
                        print(f"\r[Parcial] {texto}", end="", flush=True)
                else:
                    parcial = json.loads(rec.PartialResult()).get("partial", "")
                    if parcial and len(parcial) > 2:
                        print(f"\r... {parcial}", end="", flush=True)

                chunk_count += 1

        except ConnectionResetError:
            print("\n  [Info] Conexión reiniciada por cliente")
            break
        except Exception as e:
            if running[0]:
                print(f"\n  [Error] Recepción: {e}")
            break

    # Fin de conexión
    if frase_activa and buffer:
        resultado = json.loads(rec.FinalResult())
        texto = resultado.get("text", "").strip()
        if texto:
            historial.append(texto)
            print(f"\n[FRASE] {texto}")

    if historial:
        print()
        print("=" * 50)
        print(f"  RESUMEN: {len(historial)} frases reconocidas")
        print("=" * 50)
        for i, t in enumerate(historial):
            print(f"  {i+1}. {t}")


def signal_handler(signum, frame):
    global running
    print("\n\n  Deteniendo...")
    running[0] = False


def main():
    global running, server_socket, client_socket

    import argparse
    parser = argparse.ArgumentParser(description="Raspberry Pi - Receiver TCP + Vosk")
    parser.add_argument('--port', type=int, default=TCP_PORT,
                        help=f'Puerto TCP (default: {TCP_PORT})')
    parser.add_argument('--verbose', action='store_true',
                        help='Imprimir energía del audio')
    args = parser.parse_args()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("=" * 50)
    print("  RASPBERRY PI RECEIVER - TCP + Vosk")
    print("=" * 50)
    print()
    print(f"  Escuchando en: 0.0.0.0:{args.port}")
    print(f"  Modelo: {MODEL_PATH}")
    print()

    # Crear socket servidor
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('0.0.0.0', args.port))
    server_socket.listen(1)
    server_socket.settimeout(1)

    running[0] = True

    print("  Esperando conexión de Windows...")
    print("  (Ejecuta windows_sender.py en tu PC primero)")
    print()

    # Hilo para procesar audio
    process_thread = None

    while running[0]:
        try:
            client_socket, addr = server_socket.accept()
            print(f"  ✓ Cliente conectado desde {addr[0]}:{addr[1]}")

            # Iniciar procesamiento en hilo separado
            process_thread = threading.Thread(target=process_audio, daemon=True)
            process_thread.start()

        except socket.timeout:
            continue
        except Exception as e:
            if running[0]:
                print(f"  Error accept: {e}")
            break

    # Limpieza
    running[0] = False
    if client_socket:
        client_socket.close()
    if server_socket:
        server_socket.close()

    print("  Socket cerrado.")


if __name__ == "__main__":
    main()