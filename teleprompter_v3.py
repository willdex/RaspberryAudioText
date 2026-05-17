#!/usr/bin/env python3
"""
teleprompter_v3.py - Sistema de reconocimiento de voz para sordos
Pipeline: arecord -> sox -> Python -> Vosk

Uso:
    python3 teleprompter_v3.py
    python3 teleprompter_v3.py --gain -24 --verbose
    python3 teleprompter_v3.py --vosk-model modelo --test 10
"""

import sys
import os
import argparse
import subprocess
import signal
import threading
import queue
import json
import time
import numpy as np

# Vosk
import wave
from vosk import Model, KaldiRecognizer, SetLogLevel
SetLogLevel(-1)

# --- Constantes ---
MIC_DEVICE = "plughw:2,0"
MIC_SAMPLERATE = 44100
VOSK_SAMPLERATE = 16000
MODEL_PATH = "modelo"
VAD_THRESHOLD = 150
SILENCE_TIMEOUT = 1.5
CHUNK_SIZE = 3200


# --- Utilidades ---
def rms(audio: np.ndarray) -> float:
    return np.sqrt(np.mean(audio.astype(np.float32) ** 2))


def max_val(audio: np.ndarray) -> int:
    return int(np.max(np.abs(audio)))


def clipping_percent(audio: np.ndarray, threshold=30000) -> float:
    clipped = np.sum(np.abs(audio) >= threshold)
    return clipped / len(audio) * 100


# --- Clase AudioPipeline ---
class AudioPipeline:
    """
    Maneja el pipeline arecord -> sox.
    Lee audio de sox.stdout en bloques y los pone en una cola.
    """

    def __init__(self, device=MIC_DEVICE, gain=-24, sample_rate=MIC_SAMPLERATE):
        self.device = device
        self.gain = gain
        self.sample_rate = sample_rate
        self.process = None
        self.sox_process = None
        self.running = False
        self.queue = queue.Queue(maxsize=200)
        self.reader_thread = None

    def build_arecord_cmd(self):
        return [
            'arecord', '-D', self.device,
            '-f', 'S16_LE',
            '-r', str(self.sample_rate),
            '-c', '1',
            '-t', 'raw',
            '-'
        ]

    def build_sox_cmd(self):
        return [
            'sox', '-t', 'raw', '-r', str(self.sample_rate),
            '-e', 'signed', '-b', '16', '-c', '1', '-',
            '-t', 'raw', '-r', '16000',
            '-e', 'signed', '-b', '16', '-c', '1',
            'gain', str(self.gain),
            'highpass', '200',
            'lowpass', '3200',
            '-'
        ]

    def start(self):
        """Inicia el pipeline arecord | sox."""
        print(f"  [Pipeline] arecord -> sox (gain={self.gain})")

        try:
            self.process = subprocess.Popen(
                self.build_arecord_cmd(),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL
            )

            self.sox_process = subprocess.Popen(
                self.build_sox_cmd(),
                stdin=self.process.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL
            )

            self.process.stdout.close()

        except Exception as e:
            print(f"  [Pipeline] ERROR al iniciar: {e}")
            return False

        self.running = True
        self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader_thread.start()
        print("  [Pipeline] Iniciado")
        return True

    def _reader_loop(self):
        """Lee del pipe de sox y pone bloques en la cola."""
        buffer = b''

        while self.running:
            try:
                data = self.sox_process.stdout.read(8192)
                if not data:
                    break
                buffer += data

                while len(buffer) >= CHUNK_SIZE:
                    chunk = buffer[:CHUNK_SIZE]
                    buffer = buffer[CHUNK_SIZE:]
                    try:
                        self.queue.put(chunk, timeout=0.5)
                    except queue.Full:
                        pass

            except Exception:
                break

    def read(self, timeout=1.0):
        """Lee un chunk de audio de la cola."""
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self):
        """Detiene el pipeline."""
        self.running = False

        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()

        if self.sox_process:
            self.sox_process.terminate()
            try:
                self.sox_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.sox_process.kill()

        if self.reader_thread:
            self.reader_thread.join(timeout=3)


# --- Clase Recognizer ---
class Recognizer:
    """
    Consume audio del pipeline y lo envia a Vosk.
    """

    def __init__(self, model_path=MODEL_PATH, vad_threshold=VAD_THRESHOLD,
                 silence_timeout=SILENCE_TIMEOUT, verbose=False):
        self.model_path = model_path
        self.vad_threshold = vad_threshold
        self.silence_timeout = silence_timeout
        self.verbose = verbose
        self.model = None
        self.rec = None
        self.running = False
        self.historial = []
        self.ultimo_tiempo_voz = 0
        self.frase_activa = False

    def load_model(self):
        """Carga el modelo Vosk."""
        print(f"  [Vosk] Cargando modelo '{self.model_path}'...")
        try:
            self.model = Model(self.model_path)
            self.rec = KaldiRecognizer(self.model, VOSK_SAMPLERATE)
            print("  [Vosk] Modelo cargado")
            return True
        except Exception as e:
            print(f"  [Vosk] ERROR: {e}")
            return False

    def process(self, audio_source):
        """Bucle principal de reconocimiento."""
        self.running = True
        print("  [Vosk] Escuchando...")

        while self.running:
            audio = audio_source.read(timeout=0.5)
            if audio is None:
                continue

            audio_np = np.frombuffer(audio, dtype=np.int16)
            energia = rms(audio_np)
            max_val_audio = max_val(audio_np)

            if self.verbose:
                clip_pct = clipping_percent(audio_np)
                print(f"\r  RMS: {energia:6.1f}  Max: {max_val_audio:6d}  Clip: {clip_pct:5.2f}%  ",
                      end="", flush=True)

            hay_voz = energia > self.vad_threshold

            if hay_voz:
                self.ultimo_tiempo_voz = time.time()
                self.frase_activa = True
            elif self.frase_activa and (time.time() - self.ultimo_tiempo_voz > self.silence_timeout):
                self._fin_frase()
                self.frase_activa = False

            if self.rec.AcceptWaveform(audio):
                resultado = json.loads(self.rec.Result())
                texto = resultado.get("text", "").strip()
                if texto:
                    print(f"\r  [parcial] {texto}", end="", flush=True)
            else:
                parcial = json.loads(self.rec.PartialResult()).get("partial", "")
                if parcial:
                    print(f"\r  ... {parcial}", end="", flush=True)

    def _fin_frase(self):
        """Imprime frase completa al detectar silencio."""
        resultado = json.loads(self.rec.FinalResult())
        texto = resultado.get("text", "").strip()
        if texto:
            self.historial.append(texto)
            print(f"\n  >>> {texto}")
        self.rec.Reset()

    def stop(self):
        self.running = False

    def get_historial(self):
        return self.historial


# --- Clase Teleprompter ---
class Teleprompter:
    """Orquesta los componentes principales."""

    def __init__(self, gain=-24, vosk_model=MODEL_PATH, verbose=False, test_duration=None):
        self.gain = gain
        self.vosk_model = vosk_model
        self.verbose = verbose
        self.test_duration = test_duration
        self.pipeline = None
        self.recognizer = None

    def start(self):
        print("=" * 55)
        print("  TELEPROMPTER PARA SORDOS - v3")
        print("=" * 55)
        print()

        self.pipeline = AudioPipeline(gain=self.gain)
        if not self.pipeline.start():
            return False

        self.recognizer = Recognizer(
            model_path=self.vosk_model,
            verbose=self.verbose
        )
        if not self.recognizer.load_model():
            return False

        print()
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
            self.recognizer.process(self.pipeline)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        print("\n\n  Deteniendo...")
        if self.recognizer:
            self.recognizer.stop()
        if self.pipeline:
            self.pipeline.stop()

        historial = self.recognizer.get_historial() if self.recognizer else []
        if historial:
            print("\n  Resumen:")
            for texto in historial:
                print(f"    - {texto}")


# --- Signal Handler ---
def signal_handler(signum, frame):
    raise KeyboardInterrupt


# --- Main ---
def main():
    parser = argparse.ArgumentParser(description="Teleprompter v3 - Reconocimiento de voz para sordos")
    parser.add_argument('--gain', type=float, default=-24,
                        help='Atenuacion de sox en dB (default: -24)')
    parser.add_argument('--vosk-model', type=str, default=MODEL_PATH,
                        help='Ruta al modelo Vosk (default: modelo)')
    parser.add_argument('--verbose', action='store_true',
                        help='Imprimir RMS y Max del audio procesado')
    parser.add_argument('--test', type=int, metavar='SEGUNDOS',
                        help='Modo test: ejecutar por N segundos y salir')

    args = parser.parse_args()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    tp = Teleprompter(
        gain=args.gain,
        vosk_model=args.vosk_model,
        verbose=args.verbose,
        test_duration=args.test
    )

    if not tp.start():
        print("ERROR: No se pudo iniciar el sistema")
        sys.exit(1)

    tp.run()


if __name__ == "__main__":
    main()