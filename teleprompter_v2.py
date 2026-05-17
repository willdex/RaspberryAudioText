#!/usr/bin/env python3
"""
Teleprompter V2 - Sistema de reconocimiento de voz para sordos by WillWick  Github willdex
Optimizado para Raspberry Pi 3 + Vosk offline
"""

import os
import sys
import queue
import json
import logging
from datetime import datetime
import sounddevice as sd
from vosk import Model, KaldiRecognizer
import pygame

# ============================================================
# CONFIGURACIÓN - EDITAR SEGÚN TU HARDWARE
# ============================================================
CONFIG = {
    "audio_device": None,  # None = auto-detectar, o "hw:1,0" para M6
    "model_path": "modelo",
    "max_words_display": 25,
    "font_size": 90,
    "color_fondo": (0, 0, 0),
    "color_texto": (255, 255, 0),
    "log_file": "/home/jose/proyecto_voz/teleprompter.log",
}

# Palabras comunes mal reconocidas (ampliar según necesidad)
REEMPLAZOS = {
    " a ": " ha ",
    " a ": " él ",
    " y ": " él ",
    " lo ": " el ",
    " de ": " de ",
    " que ": " que ",
    " se ": " ce ",
    " te ": " ti ",
    " me ": " mi ",
    " nos ": " nos ",
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(CONFIG["log_file"]),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ============================================================
# CLASE PRINCIPAL
# ============================================================
class Recognizer:
    def __init__(self):
        self.q = queue.Queue()
        self.historial = []
        self.partial_text = ""
        self.running = True
        
    def setup_audio(self):
        if CONFIG["audio_device"]:
            device = CONFIG["audio_device"]
        else:
            devices = sd.query_devices()
            mic = next((d for d in devices if d['max_input_channels'] > 0), None)
            if not mic:
                raise RuntimeError("No se encontró micrófono")
            device = mic['name']
            log.info(f"Auto-detectado micrófono: {device}")
        
        info = sd.query_devices(device, 'input')
        self.sample_rate = int(info['default_samplerate'])
        log.info(f"Dispositivo: {device} @ {self.sample_rate} Hz")
        
        return device
    
    def load_model(self):
        log.info(f"Cargando modelo desde: {CONFIG['model_path']}")
        model = Model(CONFIG["model_path"])
        rec = KaldiRecognizer(model, self.sample_rate)
        log.info("Modelo cargado exitosamente")
        return rec
    
    def audio_callback(self, indata, frames, time, status):
        if status:
            log.warning(f"Audio status: {status}")
        self.q.put(bytes(indata))
    
    def aplicar_reemplazos(self, texto):
        texto_corrigido = texto
        for incorrecto, correcto in REEMPLAZOS.items():
            texto_corrigido = texto_corrigido.replace(incorrecto, correcto)
        return texto_corrigido
    
    def procesar_resultado(self, rec, pygame, pantalla, fuente, info_pantalla):
        while self.running:
            try:
                data = self.q.get(timeout=1)
                
                if rec.AcceptWaveform(data):
                    resultado = json.loads(rec.Result())
                    texto = resultado.get("text", "").strip()
                    
                    if texto:
                        texto = self.aplicar_reemplazos(texto)
                        palabras = texto.split()
                        self.historial.extend(palabras)
                        log.info(f"Reconocido: {texto}")
                        self.actualizar_pantalla(pygame, pantalla, fuente, info_pantalla, "")
                
                else:
                    parcial = json.loads(rec.PartialResult())
                    texto_parcial = parcial.get("partial", "")
                    if texto_parcial != self.partial_text:
                        self.partial_text = texto_parcial
                        self.actualizar_pantalla(pygame, pantalla, fuente, info_pantalla, texto_parcial)
                        
            except queue.Empty:
                continue
            except Exception as e:
                log.error(f"Error en procesamiento: {e}")
    
    def actualizar_pantalla(self, pygame, pantalla, fuente, info_pantalla, partial):
        superficie = pantalla
        
        if len(self.historial) > CONFIG["max_words_display"]:
            self.historial = self.historial[-CONFIG["max_words_display"]:]
        
        texto_confirmado = " ".join(self.historial)
        texto_completo = texto_confirmado + (" " + partial if partial else "")
        
        superficie.fill(CONFIG["color_fondo"])
        
        ancho_max = info_pantalla.current_w - 100
        palabras_lista = texto_completo.split()
        lineas = []
        linea_actual = ""
        
        for palabra in palabras_lista:
            test_linea = linea_actual + palabra + " "
            if fuente.size(test_linea)[0] < ancho_max:
                linea_actual = test_linea
            else:
                if linea_actual:
                    lineas.append(linea_actual.strip())
                linea_actual = palabra + " "
        
        if linea_actual.strip():
            lineas.append(linea_actual.strip())
        
        y = 50
        for linea in lineas[-8:]:
            img = fuente.render(linea, True, CONFIG["color_texto"])
            superficie.blit(img, (50, y))
            y += 120
        
        pygame.display.update()
    
    def iniciar(self, pygame, pantalla, info_pantalla, fuente):
        device = self.setup_audio()
        rec = self.load_model()
        
        log.info(f"Iniciando reconocimiento en {device}")
        
        with sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=8000,
            device=device,
            dtype='int16',
            channels=1,
            callback=self.audio_callback
        ):
            log.info("Sistema listo. Habla al micrófono (Ctrl+C para detener)")
            self.procesar_resultado(rec, pygame, pantalla, fuente, info_pantalla)

# ============================================================
# MAIN
# ============================================================
def main():
    try:
        os.environ["SDL_NOMOUSE"] = "1"
        pygame.init()
        
        drivers = ['kmsdrm', 'fbcon', 'directfb']
        driver_ok = False
        
        for driver in drivers:
            os.environ["SDL_VIDEODRIVER"] = driver
            try:
                pygame.display.init()
                log.info(f"Driver de video: {driver}")
                driver_ok = True
                break
            except pygame.error as e:
                log.warning(f"Driver {driver} no disponible: {e}")
                continue
        
        if not driver_ok:
            log.error("No se pudo inicializar ningún driver de video")
            sys.exit(1)
        
        info = pygame.display.Info()
        pantalla = pygame.display.set_mode(
            (info.current_w, info.current_h),
            pygame.FULLSCREEN
        )
        
        fuente = pygame.font.Font(None, CONFIG["font_size"])
        
        recognizer = Recognizer()
        recognizer.iniciar(pygame, pantalla, info, fuente)
        
    except KeyboardInterrupt:
        log.info("Detenido por el usuario")
    except Exception as e:
        log.critical(f"Error fatal: {e}", exc_info=True)
    finally:
        pygame.quit()

if __name__ == "__main__":
    main()
EOF