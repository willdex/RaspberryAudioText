from config import CORRECCIONES


def normalizar_texto(texto):
    if not texto:
        return ""
    texto_lower = texto.lower().strip()
    for incorrecto, correcto in CORRECCIONES.items():
        texto_lower = texto_lower.replace(incorrecto, correcto)
    return texto_lower


def filtrar_palabras_basicas(palabra):
    if len(palabra) < 2:
        return False
    basicas = {'eh', 'ah', 'oh', 'uh', 'mm', 'hm', 'hn'}
    if palabra.lower() in basicas:
        return False
    return True