#!/usr/bin/env python3
"""
diagnostico.py - Herramienta de diagnóstico y calibración
Ejecutar ANTES del teleprompter para verificar que todo funciona.

Uso:
    python3 diagnostico.py
    python3 diagnostico.py --calibrar   # Calibrar umbral VAD
    python3 diagnostico.py --test-vosk  # Test rápido de Vosk (habla 5s)
"""

import sys
import time
import json
import argparse
import numpy as np
import sounddevice as sd
from vosk import Model, KaldiRecognizer, SetLogLevel

SetLogLevel(-1)

MIC_DEVICE      = "hw:2,0"
MIC_SAMPLERATE  = 44100
VOSK_SAMPLERATE = 16000
MODEL_PATH      = "modelo"


def resample(audio_44k):
    ratio = VOSK_SAMPLERATE / MIC_SAMPLERATE
    n_out = int(len(audio_44k) * ratio)
    x_in  = np.arange(len(audio_44k))
    x_out = np.linspace(0, len(audio_44k) - 1, n_out)
    return np.interp(x_out, x_in, audio_44k.astype(np.float32)).astype(np.int16).tobytes()


def test_microfono():
    """Verifica que el micrófono funciona y muestra nivel de audio."""
    print("\n── TEST MICRÓFONO ──────────────────────────────")
    print(f"  Dispositivo: {MIC_DEVICE}")
    print(f"  Frecuencia:  {MIC_SAMPLERATE} Hz")
    print("  Grabando 3 segundos... (habla algo)")

    try:
        audio = sd.rec(
            int(3 * MIC_SAMPLERATE),
            samplerate=MIC_SAMPLERATE,
            channels=1,
            dtype="int16",
            device=MIC_DEVICE,
        )
        sd.wait()
        audio = audio[:, 0]

        max_val = np.max(np.abs(audio))
        rms     = np.sqrt(np.mean(audio.astype(np.float32) ** 2))
        print(f"  Max:  {max_val}")
        print(f"  RMS:  {rms:.1f}")

        if max_val < 100:
            print("  ⚠ ADVERTENCIA: Señal muy baja. Verifica el micrófono.")
        elif max_val > 30000:
            print("  ✓ Micrófono OK (señal fuerte)")
        else:
            print("  ✓ Micrófono OK")

        return True, rms

    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        print("\n  Dispositivos disponibles:")
        print(sd.query_devices())
        return False, 0


def calibrar_vad():
    """Guía al usuario para encontrar el umbral VAD óptimo."""
    print("\n── CALIBRACIÓN VAD ─────────────────────────────")
    print("  Paso 1: Midiendo nivel de SILENCIO (no hables, 3s)...")

    audio_s = sd.rec(int(3 * MIC_SAMPLERATE), samplerate=MIC_SAMPLERATE,
                     channels=1, dtype="int16", device=MIC_DEVICE)
    sd.wait()
    rms_silencio = np.sqrt(np.mean(audio_s[:, 0].astype(np.float32) ** 2))
    print(f"  RMS silencio: {rms_silencio:.1f}")

    print("\n  Paso 2: Midiendo nivel de VOZ (habla normalmente, 3s)...")
    audio_v = sd.rec(int(3 * MIC_SAMPLERATE), samplerate=MIC_SAMPLERATE,
                     channels=1, dtype="int16", device=MIC_DEVICE)
    sd.wait()
    rms_voz = np.sqrt(np.mean(audio_v[:, 0].astype(np.float32) ** 2))
    print(f"  RMS voz: {rms_voz:.1f}")

    umbral_recomendado = int((rms_silencio + rms_voz) / 2)
    print(f"\n  📌 Umbral recomendado: VAD_THRESHOLD = {umbral_recomendado}")
    print(f"     (Actualiza este valor en teleprompter_v2.py)")

    return umbral_recomendado


def test_vosk():
    """Test rápido del reconocimiento Vosk."""
    print("\n── TEST VOSK ────────────────────────────────────")
    print(f"  Cargando modelo desde '{MODEL_PATH}'...")

    try:
        model = Model(MODEL_PATH)
        rec   = KaldiRecognizer(model, VOSK_SAMPLERATE)
        print("  ✓ Modelo cargado")
    except Exception as e:
        print(f"  ✗ ERROR cargando modelo: {e}")
        return

    print("  Grabando 5 segundos... (habla claramente)")
    audio = sd.rec(int(5 * MIC_SAMPLERATE), samplerate=MIC_SAMPLERATE,
                   channels=1, dtype="int16", device=MIC_DEVICE)
    sd.wait()
    audio_flat = audio[:, 0]

    # Procesar en bloques de ~0.5s para simular streaming
    block_samples_44k = MIC_SAMPLERATE // 2  # 0.5s a 44100Hz
    resultados = []

    for i in range(0, len(audio_flat), block_samples_44k):
        bloque = audio_flat[i:i + block_samples_44k]
        if len(bloque) < block_samples_44k // 2:
            break
        audio_16k = resample(bloque)
        if rec.AcceptWaveform(audio_16k):
            r = json.loads(rec.Result())
            if r.get("text"):
                resultados.append(r["text"])
                print(f"  [FRASE] {r['text']}")

    final = json.loads(rec.FinalResult())
    if final.get("text"):
        resultados.append(final["text"])
        print(f"  [FINAL] {final['text']}")

    if resultados:
        print(f"\n  ✓ Vosk reconoció: '{' '.join(resultados)}'")
    else:
        print("\n  ⚠ Vosk no reconoció texto.")
        print("    → Verifica que hablaste durante la grabación")
        print("    → Verifica el umbral VAD con --calibrar")
        print("    → El modelo small-es puede tener dificultades con ruido de fondo")


def test_resampling():
    """Verifica que el resampling en memoria funciona correctamente."""
    print("\n── TEST RESAMPLING ──────────────────────────────")
    # Generar tono de prueba a 440Hz
    duracion = 1.0
    t_44k = np.linspace(0, duracion, int(MIC_SAMPLERATE * duracion))
    tono_44k = (np.sin(2 * np.pi * 440 * t_44k) * 10000).astype(np.int16)

    audio_16k = resample(tono_44k)
    n_16k_esperado = int(len(tono_44k) * VOSK_SAMPLERATE / MIC_SAMPLERATE)

    print(f"  Entrada:  {len(tono_44k)} samples @ {MIC_SAMPLERATE}Hz")
    print(f"  Salida:   {len(audio_16k)//2} samples @ {VOSK_SAMPLERATE}Hz")
    print(f"  Esperado: {n_16k_esperado} samples")

    diff = abs(len(audio_16k)//2 - n_16k_esperado)
    if diff <= 1:
        print("  ✓ Resampling OK")
    else:
        print(f"  ⚠ Diferencia de {diff} samples (puede ser aceptable)")


def main():
    parser = argparse.ArgumentParser(description="Diagnóstico teleprompter")
    parser.add_argument("--calibrar",   action="store_true", help="Calibrar umbral VAD")
    parser.add_argument("--test-vosk",  action="store_true", help="Test de reconocimiento Vosk")
    parser.add_argument("--todo",       action="store_true", help="Ejecutar todos los tests")
    args = parser.parse_args()

    print("══════════════════════════════════════════════")
    print("  DIAGNÓSTICO TELEPROMPTER PARA SORDOS")
    print("══════════════════════════════════════════════")

    # Siempre hacer test básico de resampling
    test_resampling()

    if args.calibrar or args.todo:
        ok, _ = test_microfono()
        if ok:
            calibrar_vad()

    elif args.test_vosk or args.todo:
        ok, _ = test_microfono()
        if ok:
            test_vosk()

    else:
        # Por defecto: test de micrófono
        test_microfono()
        print("\n  Opciones adicionales:")
        print("    python3 diagnostico.py --calibrar    # Calibrar VAD")
        print("    python3 diagnostico.py --test-vosk   # Probar Vosk")
        print("    python3 diagnostico.py --todo        # Todo\n")


if __name__ == "__main__":
    main()
