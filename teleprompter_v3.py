#!/usr/bin/env python3
"""
teleprompter_v3.py - Sistema de reconocimiento de voz para sordos
Pipeline: sounddevice (callback) -> scipy resample -> Vosk

Uso:
    python3 teleprompter_v3.py
    python3 teleprompter_v3.py --verbose
    python3 teleprompter_v3.py --test 15
"""

import sys
import os
import argparse
import signal
import json
import time
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
VAD_THRESHOLD = 150
SILENCE_TIMEOUT = 1.5


# --- Utilidades ---
def rms(audio: np.ndarray) -> float:
    return np.sqrt(np.mean(audio.astype(np.float32) ** 2))


def max_val(audio: np.ndarray) -> int:
    return int(np.max(np.abs(audio)))


def clipping_percent(audio: np.ndarray, threshold=30000) -> float:
    clipped = np.sum(np.abs(audio) >= threshold)
    return clipped / len(audio) * 100


# --- Clase Teleprompter ---
class Teleprompter:
    def __init__(self, model_path=MODEL_PATH, vad_threshold=VAD_THRESHOLD,
                 silence_timeout=SILENCE_TIMEOUT, verbose=False, test_duration=None,
                 device=None):
        self.model_path = model_path
        self.vad_threshold = vad_threshold
        self.silence_timeout = silence_timeout
        self.verbose = verbose
        self.test_duration = test_duration
        self.device = device

        self.model = None
        self.rec = None
        self.stream = None
        self.running = False

        self.historial = []
        self.ultimo_tiempo_voz = 0
        self.frase_activa = False
        self.chunk_count = 0

    def load_model(self):
        print(f"  [Vosk] Cargando modelo '{self.model_path}'...")
        try:
            self.model = Model(self.model_path)
            self.rec = KaldiRecognizer(self.model, SAMPLE_RATE_VOSK)
            print("  [Vosk] Modelo cargado")
            return True
        except Exception as e:
            print(f"  [Vosk] ERROR: {e}")
            return False

    def find_mic(self):
        if self.device is not None:
            return self.device

        for i, dev in enumerate(sd.query_devices()):
            if 'USB' in dev['name'] and dev['max_input_channels'] > 0:
                print(f"  [Audio] Micrófono USB encontrado: {i} - {dev['name']}")
                return i

        print("  [Audio] ERROR: No se encontró micrófono USB")
        return None

    def resample_audio(self, chunk_44100):
        num_out = int(len(chunk_44100) * SAMPLE_RATE_VOSK / SAMPLE_RATE_DEV)
        resampled = resample(chunk_44100.astype(np.float32), num_out)
        return np.clip(resampled, -32768, 32767).astype(np.int16)

    def audio_callback(self, indata, frames, time_info, status):
        if status:
            print(f"  [Audio] status: {status}")

        chunk_44100 = indata[:, 0].astype(np.int16)
        chunk_16000 = self.resample_audio(chunk_44100)
        self.chunk_count += 1

        energia = np.abs(chunk_44100).mean()
        hay_voz = energia > self.vad_threshold

        if hay_voz:
            self.ultimo_tiempo_voz = time.time()
            self.frase_activa = True
        elif self.frase_activa and (time.time() - self.ultimo_tiempo_voz > self.silence_timeout):
            self._fin_frase()
            self.frase_activa = False

        if self.verbose and self.chunk_count % 10 == 0:
            clip_pct = clipping_percent(chunk_44100)
            print(f"\r  [{self.chunk_count*0.1:.1f}s] RMS: {energia:6.0f}  Max: {max_val(chunk_44100):6d}  Clip%: {clip_pct:5.2f}",
                  end="", flush=True)

        if self.rec.AcceptWaveform(chunk_16000.tobytes()):
            resultado = json.loads(self.rec.Result())
            texto = resultado.get("text", "").strip()
            if texto and len(texto) > 1:
                print(f"\n  [parcial] {texto}", end="", flush=True)
        else:
            parcial = json.loads(self.rec.PartialResult()).get("partial", "")
            if parcial and len(parcial) > 2:
                print(f"\r  ... {parcial}", end="", flush=True)

    def _fin_frase(self):
        resultado = json.loads(self.rec.FinalResult())
        texto = resultado.get("text", "").strip()
        if texto:
            self.historial.append(texto)
            print(f"\n  >>> {texto}")
        self.rec.Reset()

    def start(self):
        print("=" * 55)
        print("  TELEPROMPTER PARA SORDOS - v3")
        print("=" * 55)
        print()

        if not self.load_model():
            return False

        dev_id = self.find_mic()
        if dev_id is None:
            return False

        print(f"  [Audio] Iniciando stream ({SAMPLE_RATE_DEV}Hz -> {SAMPLE_RATE_VOSK}Hz)...")

        try:
            self.stream = sd.InputStream(
                device=dev_id,
                samplerate=SAMPLE_RATE_DEV,
                blocksize=BLOCK_SIZE,
                dtype='int16',
                channels=1,
                callback=self.audio_callback
            )
        except Exception as e:
            print(f"  [Audio] ERROR: {e}")
            return False

        print("  Sistema listo. Escuchando...")
        print("  Ctrl+C para salir")
        print("-" * 55)
        return True

    def run(self):
        if self.test_duration:
            print(f"  Modo test: {self.test_duration} segundos")
            timer = threading.Timer(self.test_duration, self.stop)
            timer.start()

        try:
            with self.stream:
                sd.sleep(self.test_duration * 1000 if self.test_duration else 86400000)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        self.running = False
        if self.stream:
            self.stream.close()
            self.stream = None

        if self.rec:
            final = json.loads(self.rec.FinalResult())
            texto = final.get("text", "").strip()
            if texto:
                self.historial.append(texto)

        print("\n")
        print("=" * 55)
        print(f"  RESUMEN: {len(self.historial)} frases")
        print("=" * 55)
        for i, texto in enumerate(self.historial):
            print(f"  {i+1}. {texto}")


# --- Signal Handler ---
def signal_handler(signum, frame):
    raise KeyboardInterrupt


# --- Main ---
import threading

def main():
    parser = argparse.ArgumentParser(description="Teleprompter v3 - Reconocimiento de voz para sordos")
    parser.add_argument('--vosk-model', type=str, default=MODEL_PATH,
                        help='Ruta al modelo Vosk (default: modelo)')
    parser.add_argument('--vad-threshold', type=int, default=VAD_THRESHOLD,
                        help=f'Umbral VAD RMS (default: {VAD_THRESHOLD})')
    parser.add_argument('--silence-timeout', type=float, default=SILENCE_TIMEOUT,
                        help=f'Segundos de silencio para fin de frase (default: {SILENCE_TIMEOUT})')
    parser.add_argument('--verbose', action='store_true',
                        help='Imprimir RMS y Max del audio procesado')
    parser.add_argument('--test', type=int, metavar='SEGUNDOS',
                        help='Modo test: ejecutar por N segundos y salir')
    parser.add_argument('--device', type=int, default=None,
                        help='ID del dispositivo de audio')

    args = parser.parse_args()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    tp = Teleprompter(
        model_path=args.vosk_model,
        vad_threshold=args.vad_threshold,
        silence_timeout=args.silence_timeout,
        verbose=args.verbose,
        test_duration=args.test,
        device=args.device
    )

    if not tp.start():
        print("ERROR: No se pudo iniciar el sistema")
        sys.exit(1)

    tp.run()
    tp.stop()


if __name__ == "__main__":
    main()