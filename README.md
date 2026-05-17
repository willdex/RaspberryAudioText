# Vosk Teleprompter

Sistema de reconocimiento de voz en tiempo real para personas sordas.
Optimizado para Raspberry Pi 3 con Vosk offline.

## Requisitos

- Raspberry Pi 3 (1GB RAM)
- Raspberry Pi OS Lite
- Micrófono USB
- Display HDMI

## Instalación

```bash
git clone https://github.com/willdex/RaspberryAudioText.git
cd RaspberryAudioText
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Agregar modelo Vosk en español a carpeta ./modelo/
# Descargar de: https://alphacephei.com/vosk/models
# Modelo recomendado: vosk-model-small-es-0.3 (~45MB)

python3 teleprompter.py
```

## Configuración

Editar `config.py` para ajustar:
- Dispositivo de audio (AUDIO_DEVICE)
- Tasa de muestreo (SAMPLE_RATE)
- Bloques de audio (BLOCKSIZE)
- Colores del display
- Correcciones de texto

## Auto-inicio con systemd

```bash
sudo cp teleprompter.service /etc/systemd/system/
sudo systemctl enable teleprompter
sudo systemctl start teleprompter
sudo journalctl -u teleprompter -f  # Ver logs
```

## Estructura del proyecto

```
├── config.py           # Configuración
├── audio_capture.py    # Captura de audio
├── text_processing.py  # Procesamiento de texto
├── display.py          # Display HDMI
├── teleprompter.py     # Script principal
├── requirements.txt    # Dependencias
├── teleprompter.service # Servicio systemd
└── modelo/             # Carpeta del modelo Vosk
```

## Solución de problemas

### Input overflow
Aumentar BLOCKSIZE en config.py a 32000

### Error cargando modelo
Verificar que la carpeta ./modelo/ contenga los archivos del modelo Vosk

### Sin audio
Ejecutar: python3 -c "import sounddevice as sd; print(sd.query_devices())"
Verificar que el micrófono aparece en la lista

## Modelo recomendado

Para Raspberry Pi 3 con 1GB RAM, usar `vosk-model-small-es-0.3`:
- Tamaño: ~45MB
- WER aproximado: 15-20%
- Compatible con sample rate 44100Hz