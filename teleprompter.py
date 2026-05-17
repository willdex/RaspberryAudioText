#!/usr/bin/env python3
"""
Teleprompter para sordos - Sistema de reconocimiento de voz en tiempo real
Optimizado para Raspberry Pi 3 + Vosk offline

Uso: python3 teleprompter.py
"""

import sys
import os
import logging
import json
import threading

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("teleprompter.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import AUDIO_DEVICE, MODEL_PATH, SAMPLE_RATE, BLOCKSIZE, LOG_FILE, LOG_LEVEL
from audio_capture import AudioCapture
from text_processing import normalizar_texto, filtrar_palabras_basicas
from display import Display


class Recognizer:
    def __init__(self, model_path):
        log.info(f"Cargando modelo: {model_path}")
        from vosk import Model, KaldiRecognizer
        self.model = Model(model_path)
        self.rec = KaldiRecognizer(self.model, SAMPLE_RATE)
        log.info("Modelo cargado exitosamente")
        self.historial = []
        self.parcial = ""
        self.running = True

    def process(self, audio_capture, display):
        while self.running:
            try:
                data = audio_capture.read()
                if self.rec.AcceptWaveform(data):
                    result = json.loads(self.rec.Result())
                    texto = result.get("text", "").strip()
                    if texto:
                        texto_normalizado = normalizar_texto(texto)
                        if texto_normalizado:
                            palabras = texto_normalizado.split()
                            palabras_filtradas = [p for p in palabras if filtrar_palabras_basicas(p)]
                            self.historial.extend(palabras_filtradas)
                            if len(self.historial) > 50:
                                self.historial = self.historial[-50:]
                            log.info(f">>> {texto_normalizado}")
                            if display:
                                display.update(self.historial, "")
                else:
                    parcial = json.loads(self.rec.PartialResult()).get("partial", "")
                    if parcial and parcial != self.parcial:
                        self.parcial = parcial
                        if display:
                            display.update(self.historial, parcial)
            except Exception as e:
                log.error(f"Error en procesamiento: {e}")

    def stop(self):
        self.running = False


def detect_audio_device():
    import sounddevice as sd
    if AUDIO_DEVICE:
        return AUDIO_DEVICE
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        if d['max_input_channels'] > 0:
            log.info(f"Microfono encontrado: {d['name']} (hw:{i})")
            return i
    log.warning("No se encontro microfono, usando default")
    return None


def main():
    log.info("=== Teleprompter para sordos ===")
    device = detect_audio_device()
    audio = AudioCapture(device, SAMPLE_RATE, BLOCKSIZE)
    audio.start()
    display = Display()
    if display.init():
        log.info("Sistema listo con display HDMI")
    else:
        log.warning("Sin display - modo solo texto")
        display = None
    try:
        recognizer = Recognizer(MODEL_PATH)
    except Exception as e:
        log.error(f"No se pudo cargar el modelo: {e}")
        audio.stop()
        return 1
    processor = threading.Thread(target=recognizer.process, args=(audio, display), daemon=True)
    processor.start()
    log.info("Sistema listo. Habla al microfono (Ctrl+C para detener)")
    try:
        while processor.is_alive():
            import time
            time.sleep(0.5)
    except KeyboardInterrupt:
        log.info("Deteniendo sistema...")
    finally:
        recognizer.stop()
        audio.stop()
        if display:
            display.close()
        log.info("Sistema detenido")
    return 0


if __name__ == "__main__":
    sys.exit(main())