import os
import logging

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    logging.warning("pygame no disponible, display deshabilitado")

from config import FONT_SIZE, MAX_WORDS_DISPLAY, COLOR_FONDO, COLOR_TEXTO

log = logging.getLogger(__name__)


class Display:
    def __init__(self):
        self.surface = None
        self.font = None
        self.info_pantalla = None
        self.running = False

    def init(self):
        if not PYGAME_AVAILABLE:
            log.warning("pygame no disponible")
            return False
        os.environ["SDL_NOMOUSE"] = "1"
        pygame.init()
        drivers = ['kmsdrm', 'fbcon', 'directfb']
        driver_ok = False
        for driver in drivers:
            os.environ["SDL_VIDEODRIVER"] = driver
            try:
                pygame.display.init()
                log.info(f"Driver video: {driver}")
                driver_ok = True
                break
            except pygame.error:
                continue
        if not driver_ok:
            log.error("No se pudo inicializar driver de video")
            return False
        self.info_pantalla = pygame.display.Info()
        self.surface = pygame.display.set_mode(
            (self.info_pantalla.current_w, self.info_pantalla.current_h),
            pygame.FULLSCREEN
        )
        self.font = pygame.font.Font(None, FONT_SIZE)
        self.running = True
        log.info("Display HDMI inicializado")
        return True

    def update(self, palabras_confirmadas, texto_parcial=""):
        if not PYGAME_AVAILABLE or not self.running:
            return
        self.surface.fill(COLOR_FONDO)
        texto_completo = " ".join(palabras_confirmadas)
        if texto_parcial:
            texto_completo += " " + texto_parcial
        palabras = texto_completo.split()
        if len(palabras) > MAX_WORDS_DISPLAY:
            palabras = palabras[-MAX_WORDS_DISPLAY:]
        texto_mostrar = " ".join(palabras)
        ancho_max = self.info_pantalla.current_w - 100
        lineas = []
        linea_actual = ""
        for palabra in palabras:
            test_linea = linea_actual + palabra + " "
            if self.font.size(test_linea)[0] < ancho_max:
                linea_actual = test_linea
            else:
                if linea_actual.strip():
                    lineas.append(linea_actual.strip())
                linea_actual = palabra + " "
        if linea_actual.strip():
            lineas.append(linea_actual.strip())
        y = 50
        for linea in lineas[-8:]:
            img = self.font.render(linea, True, COLOR_TEXTO)
            self.surface.blit(img, (50, y))
            y += 120
        pygame.display.update()

    def close(self):
        if PYGAME_AVAILABLE:
            pygame.quit()