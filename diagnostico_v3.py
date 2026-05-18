#!/usr/bin/env python3
"""
diagnostico_v3.py - Diagnostico para Teleprompter v3 (Cirugia de Audio)
Pruebas del pipeline arecord | sox con filtros agresivos.

Uso:
    python3 diagnostico_v3.py --test-pipeline
    python3 diagnostico_v3.py --test-vosk
    python3 diagnostico_v3.py --test-pipeline --test-vosk
"""

import sys
import os
import argparse
import subprocess
import wave
import json
import time
import numpy as np
from vosk import Model, KaldiRecognizer, SetLogLevel

SetLogLevel(-1)

# --- Constantes ---
MIC_DEVICE = "plughw:2,0"
MIC_SAMPLERATE = 44100
VOSK_SAMPLERATE = 16000
MODEL_PATH = "modelo"
GAIN_DEFAULT = -30
PIPELINE_DURATION = 5
OUTPUT_FILE = "/tmp/test_pipeline.wav"


# --- Utilidades ---
def rms(audio: np.ndarray) -> float:
    return np.sqrt(np.mean(audio.astype(np.float32) ** 2))


def max_val(audio: np.ndarray) -> int:
    return int(np.max(np.abs(audio)))


def dc_offset(audio: np.ndarray) -> float:
    return float(np.mean(audio.astype(np.float32)))


def clipping_percent(audio: np.ndarray, threshold=30000) -> float:
    clipped = np.sum(np.abs(audio) >= threshold)
    return clipped / len(audio) * 100


def print_stats(audio: np.ndarray, label=""):
    r = rms(audio)
    m = max_val(audio)
    d = dc_offset(audio)
    c = clipping_percent(audio)
    status = "OK" if c < 1 and abs(d) < 100 else "WARNING" if c < 5 else "CLIPPING"
    print(f"  {label:20s}  Max: {m:6d}  RMS: {r:7.1f}  DC: {d:7.1f}  Clip%: {c:5.2f}  [{status}]")


# --- Test Pipeline ---
def test_pipeline(duration=PIPELINE_DURATION, gain=GAIN_DEFAULT, output_file=OUTPUT_FILE):
    """Ejecuta arecord | sox (cirugia de audio) y guarda el resultado como WAV."""
    print(f"\n-- TEST PIPELINE arecord -> sox (Cirugia) --")
    print(f"  Duracion: {duration}s  Gain: {gain}dB  Output: {output_file}")

    arecord_cmd = [
        'arecord', '-D', MIC_DEVICE,
        '-f', 'S16_LE',
        '-r', str(MIC_SAMPLERATE),
        '-c', '1',
        '-t', 'raw',
        '-'
    ]

    sox_cmd = [
        'sox', '-t', 'raw', '-r', str(MIC_SAMPLERATE),
        '-e', 'signed', '-b', '16', '-c', '1', '-',
        '-t', 'raw', '-r', '16000',
        '-e', 'signed', '-b', '16', '-c', '1',
        'highpass', '100',
        'gain', str(gain),
        'highpass', '200',
        'lowpass', '3000',
        '-'
    ]

    print("  Grabando... (habla ahora)")
    try:
        proc_arecord = subprocess.Popen(
            arecord_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )

        proc_sox = subprocess.Popen(
            sox_cmd,
            stdin=proc_arecord.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )

        proc_arecord.stdout.close()

        audio_data = b''
        start = time.time()

        while time.time() - start < duration:
            chunk = proc_sox.stdout.read(3200)
            if not chunk:
                break
            audio_data += chunk

        proc_arecord.terminate()
        proc_sox.terminate()

    except Exception as e:
        print(f"  ERROR: {e}")
        return None

    if not audio_data:
        print("  ERROR: No se capturo audio")
        return None

    print(f"  Audio capturado: {len(audio_data)} bytes")

    # Guardar como WAV
    with wave.open(output_file, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(VOSK_SAMPLERATE)
        wf.writeframes(audio_data)

    print(f"  Guardado en: {output_file}")
    return audio_data


# --- Test Vosk ---
def test_vosk(wav_file=OUTPUT_FILE, model_path=MODEL_PATH):
    """Prueba reconocimiento Vosk con un archivo WAV."""
    print(f"\n-- TEST VOSK --")
    print(f"  Archivo: {wav_file}")
    print(f"  Modelo: {model_path}")

    if not os.path.exists(wav_file):
        print(f"  ERROR: No existe {wav_file}")
        return

    print("  Cargando modelo...")
    try:
        model = Model(model_path)
        rec = KaldiRecognizer(model, VOSK_SAMPLERATE)
        print("  Modelo cargado")
    except Exception as e:
        print(f"  ERROR: {e}")
        return

    with wave.open(wav_file, 'rb') as wf:
        audio = wf.readframes(wf.getnframes())

    audio_np = np.frombuffer(audio, dtype=np.int16)
    print()
    print_stats(audio_np, "Audio procesado")

    # Esperar DC cerca de 0 y Max < 5000
    dc = dc_offset(audio_np)
    mv = max_val(audio_np)

    print()
    if abs(dc) > 100:
        print(f"  ⚠ DC offset alto: {dc:.1f} (deberia ser cercano a 0)")
    if mv > 5000:
        print(f"  ⚠ Maximo alto: {mv} (deberia ser < 5000)")
    if abs(dc) < 100 and mv < 5000:
        print("  ✓ Audio en rango esperado")

    print("\n  Reconociendo...")
    results = []

    chunk_size = 16000  # 1 segundo
    for i in range(0, len(audio), chunk_size):
        chunk = audio[i:i+chunk_size]
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
        print(f"  VOSK reconocio: '{texto}'")
    else:
        print("  ⚠ VOSK NO reconocio texto")


# --- Main ---
def main():
    parser = argparse.ArgumentParser(description="Diagnostico v3 - Cirugia de Audio")
    parser.add_argument('--test-pipeline', action='store_true',
                        help='Grabar 5s con pipeline arecord|sox y analizar audio')
    parser.add_argument('--test-vosk', action='store_true',
                        help='Probar Vosk con el WAV generado')
    parser.add_argument('--gain', type=float, default=GAIN_DEFAULT,
                        help=f'Gain para sox (default: {GAIN_DEFAULT})')
    parser.add_argument('--duration', type=int, default=PIPELINE_DURATION,
                        help=f'Duracion de grabacion (default: {PIPELINE_DURATION})')
    parser.add_argument('--model', type=str, default=MODEL_PATH,
                        help=f'Ruta al modelo Vosk (default: {MODEL_PATH})')

    args = parser.parse_args()

    print("====================================================")
    print("  DIAGNOSTICO v3 - CIRUGIA DE AUDIO")
    print("====================================================")

    if args.test_pipeline:
        audio_data = test_pipeline(duration=args.duration, gain=args.gain, output_file=OUTPUT_FILE)
        if audio_data:
            audio_np = np.frombuffer(audio_data, dtype=np.int16)
            print()
            print_stats(audio_np, "Audio procesado")
            print()
            if args.test_vosk:
                test_vosk(model_path=args.model)
        return

    if args.test_vosk:
        test_vosk(model_path=args.model)
        return

    parser.print_help()
    print()
    print("  Ejemplos:")
    print("    python3 diagnostico_v3.py --test-pipeline")
    print("    python3 diagnostico_v3.py --test-pipeline --test-vosk")
    print("    python3 diagnostico_v3.py --test-pipeline --gain -36")


if __name__ == "__main__":
    main()