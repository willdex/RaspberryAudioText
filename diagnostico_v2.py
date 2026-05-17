#!/usr/bin/env python3
"""
diagnostico_v2.py - Diagnóstico para Teleprompter v3
Pruebas de audio y Vosk con resampling en tiempo real usando scipy.

Uso:
    python3 diagnostico_v2.py --test-audio
    python3 diagnostico_v2.py --test-vosk
    python3 diagnostico_v2.py --test-realtime
"""

import sys
import os
import argparse
import subprocess
import tempfile
import wave
import json
import time
import threading
import numpy as np
from scipy.signal import resample
import sounddevice as sd
from vosk import Model, KaldiRecognizer, SetLogLevel

SetLogLevel(-1)

# --- Constantes ---
SAMPLE_RATE_DEV = 44100
SAMPLE_RATE_VOSK = 16000
BLOCK_SIZE = 4410  # 100ms
MODEL_PATH = "modelo"
GAIN_DEFAULT = -24
TEST_DURATION = 5


# --- Utilidades ---
def rms(audio: np.ndarray) -> float:
    return np.sqrt(np.mean(audio.astype(np.float32) ** 2))


def max_val(audio: np.ndarray) -> int:
    return int(np.max(np.abs(audio)))


def clipping_percent(audio: np.ndarray, threshold=30000) -> float:
    clipped = np.sum(np.abs(audio) >= threshold)
    return clipped / len(audio) * 100


def print_stats(audio: np.ndarray, label=""):
    r = rms(audio)
    m = max_val(audio)
    c = clipping_percent(audio)
    status = "OK" if c < 1 else "WARNING" if c < 5 else "CLIPPING"
    print(f"  {label:20s}  Max: {m:6d}  RMS: {r:7.1f}  Clip%: {c:5.2f}  [{status}]")


# --- Test Audio (graba 5s y analiza) ---
def test_audio():
    """Graba 5 segundos y muestra estadísticas del audio."""
    print(f"\n-- TEST AUDIO ({TEST_DURATION}s) --")
    print("  Habla ahora...")

    audio_data = []
    device = None

    for i, dev in enumerate(sd.query_devices()):
        if 'USB' in dev['name'] and dev['max_input_channels'] > 0:
            device = i
            break

    if device is None:
        print("  ERROR: No se encontró micrófono USB")
        return

    print(f"  Dispositivo: {device}")

    def callback(indata, frames, time_info, status):
        if status:
            print(f"  status: {status}")
        audio_data.append(indata[:, 0].copy())

    stream = sd.InputStream(
        device=device,
        samplerate=SAMPLE_RATE_DEV,
        blocksize=BLOCK_SIZE,
        dtype='int16',
        channels=1,
        callback=callback
    )

    with stream:
        sd.sleep(TEST_DURATION * 1000)

    if not audio_data:
        print("  ERROR: No se capturó audio")
        return

    all_audio = np.concatenate(audio_data)
    print_stats(all_audio, f"Audio ({TEST_DURATION}s)")

    # Guardar WAV
    output_file = "/tmp/test_audio.wav"
    with wave.open(output_file, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE_DEV)
        wf.writeframes(all_audio.tobytes())
    print(f"  Guardado en: {output_file}")

    return all_audio


# --- Test Vosk (con archivo WAV) ---
def test_vosk(wav_file="/tmp/test_audio.wav", model_path=MODEL_PATH):
    """Prueba reconocimiento Vosk con un archivo WAV y resampling."""
    print(f"\n-- TEST VOSK --")
    print(f"  Archivo: {wav_file}")
    print(f"  Modelo: {model_path}")

    if not os.path.exists(wav_file):
        print(f"  ERROR: No existe {wav_file}")
        return

    print("  Cargando modelo...")
    try:
        model = Model(model_path)
        rec = KaldiRecognizer(model, SAMPLE_RATE_VOSK)
        print("  Modelo cargado")
    except Exception as e:
        print(f"  ERROR: {e}")
        return

    with wave.open(wav_file, 'rb') as wf:
        audio_44100 = wf.readframes(wf.getnframes())

    audio_44100_np = np.frombuffer(audio_44100, dtype=np.int16)
    print_stats(audio_44100_np, "Audio 44100Hz")

    # Resample a 16000
    num_out = int(len(audio_44100_np) * SAMPLE_RATE_VOSK / SAMPLE_RATE_DEV)
    resampled = resample(audio_44100_np.astype(np.float32), num_out)
    audio_16000 = np.clip(resampled, -32768, 32767).astype(np.int16)

    print_stats(audio_16000, "Audio 16000Hz")

    print("  Reconociendo...")
    results = []

    chunk_size = 16000  # 1 segundo
    for i in range(0, len(audio_16000.tobytes()), chunk_size):
        chunk = audio_16000.tobytes()[i:i+chunk_size]
        if len(chunk) == chunk_size:
            if rec.AcceptWaveform(chunk):
                r = json.loads(rec.Result())
                if r.get('text'):
                    results.append(r['text'])
                    print(f"    [parcial] {r['text']}")

    final = json.loads(rec.FinalResult())
    if final.get('text'):
        results.append(final['text'])

    print()
    if results:
        texto = ' '.join(results)
        print(f"  VOSK reconoció: '{texto}'")
    else:
        print("  VOSK NO reconoció texto (audio puede ser silencioso o distorsionado)")


# --- Test Realtime (callback + resample + Vosk) ---
def test_realtime(duration=15, model_path=MODEL_PATH):
    """Test completo en tiempo real: audio -> resample -> Vosk."""
    print(f"\n-- TEST REALTIME ({duration}s) --")
    print("  Habla ahora...")

    print("  Cargando modelo...")
    try:
        model = Model(model_path)
        rec = KaldiRecognizer(model, SAMPLE_RATE_VOSK)
        print("  Modelo cargado")
    except Exception as e:
        print(f"  ERROR: {e}")
        return

    sentences = []
    chunk_count = [0]

    def callback(indata, frames, time_info, status):
        if status:
            print(f"  status: {status}")

        chunk_44100 = indata[:, 0].astype(np.int16)
        num_out = int(len(chunk_44100) * SAMPLE_RATE_VOSK / SAMPLE_RATE_DEV)
        resampled = resample(chunk_44100.astype(np.float32), num_out)
        chunk_16000 = np.clip(resampled, -32768, 32767).astype(np.int16)

        if rec.AcceptWaveform(chunk_16000.tobytes()):
            result = json.loads(rec.Result())
            text = result.get('text', '').strip()
            if text and len(text) > 1:
                sentences.append(text)
                print(f"\n  [FRASE] {text}")
        else:
            partial = json.loads(rec.PartialResult())
            ptext = partial.get('partial', '').strip()
            if ptext and len(ptext) > 2:
                print(f"\r  ... {ptext}", end="", flush=True)

        chunk_count[0] += 1
        if chunk_count[0] % 10 == 0:
            energy = np.abs(chunk_44100).mean()
            print(f"  [{chunk_count[0]*0.1:.1f}s] energia={energy:.0f}", end="\n")

    device = None
    for i, dev in enumerate(sd.query_devices()):
        if 'USB' in dev['name'] and dev['max_input_channels'] > 0:
            device = i
            print(f"  Micrófono USB: {i} - {dev['name']}")
            break

    if device is None:
        print("  ERROR: No se encontró micrófono USB")
        return

    stream = sd.InputStream(
        device=device,
        samplerate=SAMPLE_RATE_DEV,
        blocksize=BLOCK_SIZE,
        dtype='int16',
        channels=1,
        callback=callback
    )

    with stream:
        sd.sleep(duration * 1000)

    final = json.loads(rec.FinalResult())
    ftext = final.get('text', '').strip()
    if ftext:
        sentences.append(ftext)

    print(f"\n{'='*50}")
    print(f"Frases reconocidas: {len(sentences)}")
    for i, s in enumerate(sentences):
        print(f"  {i+1}. {s}")
    print(f"{'='*50}")

    if len(sentences) > 0:
        print("\nVosk funciona! El reconocimiento en tiempo real es consistente.")
    else:
        print("\nSin resultados. Verificar micrófono o acercarse más al hablar.")


# --- Main ---
def main():
    parser = argparse.ArgumentParser(description="Diagnostico v3 para Teleprompter")
    parser.add_argument('--test-audio', action='store_true',
                        help='Grabar audio y analizar')
    parser.add_argument('--test-vosk', action='store_true',
                        help='Probar Vosk con WAV en /tmp/test_audio.wav')
    parser.add_argument('--test-realtime', action='store_true',
                        help='Test completo en tiempo real')
    parser.add_argument('--duration', type=int, default=TEST_DURATION,
                        help=f'Duracion del test (default: {TEST_DURATION})')
    parser.add_argument('--model', type=str, default=MODEL_PATH,
                        help=f'Ruta al modelo Vosk (default: {MODEL_PATH})')

    args = parser.parse_args()

    print("====================================================")
    print("  DIAGNOSTICO v3 - TELEPROMPTER PARA SORDOS")
    print("====================================================")

    if args.test_realtime:
        test_realtime(duration=args.duration, model_path=args.model)
        return

    if args.test_audio:
        test_audio()
        if args.test_vosk:
            test_vosk(model_path=args.model)
        return

    if args.test_vosk:
        test_vosk(model_path=args.model)
        return

    parser.print_help()
    print()
    print("  Ejemplos:")
    print("    python3 diagnostico_v2.py --test-audio")
    print("    python3 diagnostico_v2.py --test-audio --test-vosk")
    print("    python3 diagnostico_v2.py --test-realtime")


if __name__ == "__main__":
    main()