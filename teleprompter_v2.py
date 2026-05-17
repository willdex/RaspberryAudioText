#!/usr/bin/env python3
"""
Teleprompter para Sordos - v2 (streaming en tiempo real)
Raspberry Pi 3 + USB mic (44100Hz) + Vosk español

Mejoras sobre v1:
- Resampling en memoria con numpy (sin ffmpeg ni archivos temporales)
- Streaming continuo en lugar de bloques grandes
- Resultados parciales en tiempo real
- Reset automático del reconocedor entre frases
- Validación de nivel de audio antes de procesar
- Buffer circular para audio continuo
"""

import sounddevice as sd
import numpy as np
import json
import time
import threading
import queue
import sys
from vosk import Model, KaldiRecognizer, SetLogLevel

# ── Silenciar logs internos de Vosk ──────────────────────────────────────────
SetLogLevel(-1)

# ── Configuración ─────────────────────────────────────────────────────────────
MIC_DEVICE      = "hw:2,0"   # USB PnP Sound Device
MIC_SAMPLERATE  = 44100      # Hz que soporta el micrófono
VOSK_SAMPLERATE = 16000      # Hz que espera Vosk
BLOCKSIZE       = 4096       # Muestras por bloque a 44100 Hz (~93ms)
MODEL_PATH      = "modelo"   # Ruta al modelo vosk-model-small-es-0.42

# Umbral mínimo de energía para considerar que hay voz (evita procesar silencio)
VAD_THRESHOLD   = 300        # RMS mínimo (ajustar según el micrófono)
SILENCE_TIMEOUT = 2.0        # Segundos de silencio para marcar fin de frase

# ── Display (reemplaza con pygame/pantalla HDMI real) ─────────────────────────
def mostrar_texto(texto, tipo="parcial"):
    """
    Muestra texto en pantalla.
    tipo='parcial' → texto provisional mientras el usuario habla
    tipo='final'   → texto confirmado al detectar pausa
    """
    if tipo == "final":
        print(f"\n✅ FINAL: {texto}\n")
    else:
        print(f"  ... {texto}", end="\r")


# ── Resampling en memoria (sin ffmpeg) ────────────────────────────────────────
def resample_44100_a_16000(audio_44k: np.ndarray) -> bytes:
    """
    Convierte audio int16 de 44100Hz a 16000Hz usando interpolación lineal.
    Mucho más rápido que ffmpeg para bloques pequeños.
    Retorna bytes raw PCM int16 listos para Vosk.
    """
    # Factor de conversión: 16000/44100 ≈ 0.3628
    ratio = VOSK_SAMPLERATE / MIC_SAMPLERATE
    n_out = int(len(audio_44k) * ratio)

    # Interpolación lineal con numpy (eficiente en Raspberry Pi 3)
    x_in  = np.arange(len(audio_44k))
    x_out = np.linspace(0, len(audio_44k) - 1, n_out)
    audio_16k = np.interp(x_out, x_in, audio_44k.astype(np.float32))

    return audio_16k.astype(np.int16).tobytes()


# ── Detección de voz simple (VAD por energía) ─────────────────────────────────
def tiene_voz(audio: np.ndarray) -> bool:
    """Retorna True si el bloque de audio supera el umbral de energía mínimo."""
    rms = np.sqrt(np.mean(audio.astype(np.float32) ** 2))
    return rms > VAD_THRESHOLD


# ── Cola de audio entre callback y procesador ────────────────────────────────
audio_queue = queue.Queue()

def audio_callback(indata, frames, time_info, status):
    """Callback del stream de sounddevice. Se ejecuta en hilo separado."""
    if status:
        print(f"[AUDIO STATUS] {status}", file=sys.stderr)
    audio_queue.put(indata[:, 0].copy())  # Solo canal 0 (mono)


# ── Procesador principal ───────────────────────────────────────────────────────
def procesar_audio(rec: KaldiRecognizer):
    """
    Loop principal: toma bloques de la cola, resamplea, alimenta a Vosk.
    Muestra resultados parciales y finales.
    """
    ultimo_final = time.time()
    frase_en_curso = False

    while True:
        try:
            bloque = audio_queue.get(timeout=0.5)
        except queue.Empty:
            # Timeout: si llevamos SILENCE_TIMEOUT segundos sin voz, cerrar frase
            if frase_en_curso and (time.time() - ultimo_final > SILENCE_TIMEOUT):
                resultado = json.loads(rec.FinalResult())
                texto = resultado.get("text", "").strip()
                if texto:
                    mostrar_texto(texto, tipo="final")
                # Crear nuevo reconocedor para limpiar estado interno
                rec.Reset()
                frase_en_curso = False
            continue

        # Validar que haya voz antes de procesar
        if not tiene_voz(bloque):
            continue

        frase_en_curso = True
        ultimo_final = time.time()

        # Resamplear a 16kHz
        audio_16k = resample_44100_a_16000(bloque)

        # Alimentar a Vosk
        if rec.AcceptWaveform(audio_16k):
            # Resultado final de una oración
            resultado = json.loads(rec.Result())
            texto = resultado.get("text", "").strip()
            if texto:
                mostrar_texto(texto, tipo="final")
        else:
            # Resultado parcial (texto provisional)
            parcial = json.loads(rec.PartialResult())
            texto_parcial = parcial.get("partial", "").strip()
            if texto_parcial:
                mostrar_texto(texto_parcial, tipo="parcial")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print("=" * 50)
    print("  TELEPROMPTER PARA SORDOS - v2")
    print("=" * 50)

    # Cargar modelo Vosk
    print(f"[INIT] Cargando modelo desde '{MODEL_PATH}'...")
    try:
        model = Model(MODEL_PATH)
        rec   = KaldiRecognizer(model, VOSK_SAMPLERATE)
        rec.SetWords(True)  # Habilitar info de palabras individuales
        print("[INIT] Modelo cargado ✓")
    except Exception as e:
        print(f"[ERROR] No se pudo cargar el modelo: {e}")
        sys.exit(1)

    # Iniciar stream de audio
    print(f"[INIT] Iniciando micrófono '{MIC_DEVICE}' a {MIC_SAMPLERATE}Hz...")
    try:
        stream = sd.InputStream(
            device=MIC_DEVICE,
            samplerate=MIC_SAMPLERATE,
            blocksize=BLOCKSIZE,
            dtype="int16",
            channels=1,
            callback=audio_callback,
        )
    except Exception as e:
        print(f"[ERROR] No se pudo abrir el micrófono: {e}")
        print("  Dispositivos disponibles:")
        print(sd.query_devices())
        sys.exit(1)

    # Hilo de procesamiento (no bloquea el stream)
    hilo = threading.Thread(target=procesar_audio, args=(rec,), daemon=True)
    hilo.start()

    print("[OK] Escuchando... (Ctrl+C para salir)\n")
    print("-" * 50)

    try:
        with stream:
            while True:
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n\n[EXIT] Teleprompter detenido.")


if __name__ == "__main__":
    main()
