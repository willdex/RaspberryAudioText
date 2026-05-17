"""
Configuración del Teleprompter para sordos
Optimizado para Raspberry Pi 3 + Vosk
"""

AUDIO_DEVICE = None
MODEL_PATH = "modelo"
SAMPLE_RATE = 44100
BLOCKSIZE = 16000

FONT_SIZE = 90
MAX_WORDS_DISPLAY = 25
COLOR_FONDO = (0, 0, 0)
COLOR_TEXTO = (255, 255, 0)

CORRECCIONES = {
    " a ": " ha ",
    " e l ": " el ",
    " d e ": " de ",
    " q u e ": " que ",
    " a l ": " al ",
    " e n ": " en ",
    " d e l ": " del ",
    " p o r ": " por ",
    " g r a c i a s ": " gracias ",
    " p o r f a v o r ": " por favor ",
    " b u e n o s d i a s ": " buenos dias ",
    " c o m o e s t a s ": " como estas ",
}

LOG_FILE = "teleprompter.log"
LOG_LEVEL = "INFO"