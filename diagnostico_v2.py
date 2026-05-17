#!/usr/bin/env python3
"""
diagnostico_v2.py - Diagnóstico para Teleprompter v3
Pruebas de audio y Vosk antes de ejecutar el sistema completo.

Uso:
    python3 diagnostico_v2.py --test-pipeline
    python3 diagnostico_v2.py --test-vosk
    python3 diagnostico_v2.py --test-pipeline --test-vosk
"""

import sys
import os
import argparse
import subprocess
import tempfile
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
GAIN_DEFAULT = -24
PIPELINE_DURATION = 5


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


# --- Pipeline de audio ---
def run_pipeline(duration=PIPELINE_DURATION, gain=GAIN_DEFAULT, output_file="/tmp/test_pipeline.wav"):
    """Ejecuta arecord | sox y guarda el resultado como WAV."""
    print(f"\n-- TEST PIPELINE arecord -> sox --")
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
        'gain', str(gain),
        'highpass', '200',
        'lowpass', '3200',
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
def test_vosk(wav_file="/tmp/test_pipeline.wav", model_path=MODEL_PATH):
    """Prueba reconocimiento Vosk con un archivo WAV."""
    print(f"\n-- TEST VOSK --")
    print(f"  Archivo: {wav_file}")
    print(f"  Modelo: {model_path}")

    if not os.path.exists(wav_file):
        print(f"  ERROR: No existe {wav_file}")
        return

    # Cargar modelo
    print("  Cargando modelo...")
    try:
        model = Model(model_path)
        rec = KaldiRecognizer(model, VOSK_SAMPLERATE)
        print("  Modelo cargado")
    except Exception as e:
        print(f"  ERROR cargando modelo: {e}")
        return

    # Leer WAV
    with wave.open(wav_file, 'rb') as wf:
        audio = wf.readframes(wf.getnframes())

    print(f"  Audio: {len(audio)} bytes")
    audio_np = np.frombuffer(audio, dtype=np.int16)
    print_stats(audio_np, "Audio 16kHz")

    # Reconocer
    print("  Reconociendo...")
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
        print("  VOSK NO reconocio texto (audio puede ser silencioso o distorsionado)")


# --- Test de ganancia ---
def test_gain_search():
    """Busca el gain optimo probando varios valores."""
    print("\n-- TEST GAIN SEARCH --")
    print("  Probando gains de -12 a -36 dB...")
    print()

    gains = range(-12, -37, -3)
    mejor_gain = GAIN_DEFAULT
    mejor_clip = 100.0

    for g in gains:
        print(f"  Gain={g}dB:")
        audio_data = run_pipeline(duration=2, gain=g, output_file=f"/tmp/test_gain_{g}.wav")
        if audio_data:
            audio_np = np.frombuffer(audio_data, dtype=np.int16)
            clip = clipping_percent(audio_np)
            max_v = max_val(audio_np)
            print(f"    Max={max_v}  Clip%={clip:.2f}")

            if clip < mejor_clip and max_v < 28000:
                mejor_clip = clip
                mejor_gain = g

        time.sleep(0.5)

    print()
    print(f"  MEJOR GAIN: {mejor_gain}dB (clipping: {mejor_clip:.2f}%)")
    return mejor_gain


# --- Main ---
def main():
    parser = argparse.ArgumentParser(description="Diagnostico v3 para Teleprompter")
    parser.add_argument('--test-pipeline', action='store_true',
                        help='Grabar 5s con pipeline arecord|sox y analizar audio')
    parser.add_argument('--test-vosk', action='store_true',
                        help='Probar Vosk con el WAV generado')
    parser.add_argument('--test-gain', action='store_true',
                        help='Buscar gain optimo automaticamente')
    parser.add_argument('--gain', type=float, default=GAIN_DEFAULT,
                        help=f'Gain para sox (default: {GAIN_DEFAULT})')
    parser.add_argument('--duration', type=int, default=PIPELINE_DURATION,
                        help=f'Duracion de grabacion en segundos (default: {PIPELINE_DURATION})')
    parser.add_argument('--model', type=str, default=MODEL_PATH,
                        help=f'Ruta al modelo Vosk (default: {MODEL_PATH})')

    args = parser.parse_args()

    print("====================================================")
    print("  DIAGNOSTICO v3 - TELEPROMPTER PARA SORDOS")
    print("====================================================")

    if args.test_gain:
        gain = test_gain_search()
        print(f"\n  Usar con: python3 teleprompter_v3.py --gain {gain}")
        return

    if args.test_pipeline:
        output_file = "/tmp/test_pipeline.wav"
        audio_data = run_pipeline(duration=args.duration, gain=args.gain, output_file=output_file)
        if audio_data:
            audio_np = np.frombuffer(audio_data, dtype=np.int16)
            print()
            print_stats(audio_np, "Audio procesado")
            print()
            if args.test_vosk:
                test_vosk(wav_file=output_file, model_path=args.model)
        return

    if args.test_vosk:
        test_vosk(model_path=args.model)
        return

    # Ningun argumento: mostrar ayuda
    parser.print_help()
    print()
    print("  Ejemplos:")
    print("    python3 diagnostico_v2.py --test-pipeline")
    print("    python3 diagnostico_v2.py --test-pipeline --test-vosk")
    print("    python3 diagnostico_v2.py --test-gain")
    print("    python3 diagnostico_v2.py --test-pipeline --gain -18")


if __name__ == "__main__":
    main()