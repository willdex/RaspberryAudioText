# Proyecto Teleprompter para Sordos - Informe Técnico

## Hardware
- **Raspberry Pi 3 Model B** (1GB RAM)
- **Sistema Operativo:** Raspberry Pi OS Lite (32-bit, Debian Bullseye)
- **Conexión:** WiFi, SSH activo
- **Usuario:** jose
- **IP:** 192.168.1.110

## Repositorio
- **GitHub:** https://github.com/willdex/RaspberryAudioText
- Para clonar en Raspberry: `git clone https://github.com/willdex/RaspberryAudioText.git`
- Carpeta de trabajo: `/home/jose/RaspberryAudioText/`

## Micrófono
- **USB PnP Sound Device** (hw:2,0)
- Sample rate máximo: 44100 Hz (no soporta 16000 Hz directamente)

## Requerimiento del Cliente
- Sistema de reconocimiento de voz offline para personas sordas
- Debe usar **Vosk** (no otras alternativas como Whisper)
- Raspberry Pi 3 con limitaciones de hardware
- Mostrar texto reconocido en pantalla HDMI
- Para demo en feria

## Modelos Vosk Probados
1. **vosk-model-small-es-0.3** (~33MB) - Modelo de Android, estructura incompleta
2. **vosk-model-small-es-0.42** (~39MB) - Modelo correcto descargado de alphacephei.com
3. **Modelo grande completo (1.4GB)** - No funciona por falta de RAM

## Problema Principal
El micrófono captura audio correctamente (44100 Hz, max 32767), la conversión a 16kHz con ffmpeg funciona, pero el modelo Vosk reconoce texto de forma inconsistente.偶尔 reconoce algunas palabras ("hola cómo", "eh eh") pero a veces retorna vacío.

## Estado Actual de Archivos
```
/home/jose/RaspberryAudioText/
├── modelo/                    # Modelo vosk-model-small-es-0.42 (~39MB)
│   ├── am/
│   ├── conf/
│   ├── graph/
│   ├── ivector/
│   └── README
├── audio_capture.py
├── config.py
├── display.py
├── text_processing.py
├── teleprompter.py
├── requirements.txt
└── venv/
```

## Dependencias Instaladas en Raspberry
```bash
pip install sounddevice vosk pygame numpy
sudo apt install ffmpeg libopenblas0
```

## Solución Funcional (Actual)
El método que funciona: Graba audio a 44100Hz, convierte a 16kHz con ffmpeg, procesa con Vosk.

```python
import sounddevice as sd
import numpy as np
import wave
import json
import subprocess
from vosk import Model, KaldiRecognizer

model = Model("modelo")
rec = KaldiRecognizer(model, 16000)

audio_data = []
def callback(indata, frames, time, status):
    audio_data.append(indata.copy())

stream = sd.InputStream(samplerate=44100, blocksize=44100, device='hw:2,0', dtype='int16', channels=1, callback=callback)
with stream:
    sd.sleep(10000)

audio = np.concatenate(audio_data).astype(np.int16)

with wave.open('/tmp/test.wav', 'wb') as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(44100)
    wf.writeframes(audio.tobytes())

subprocess.run(['ffmpeg', '-y', '-i', '/tmp/test.wav', '-ar', '16000', '-ac', '1', '-b', '16', '/tmp/test_16k.wav'], capture_output=True)

with wave.open('/tmp/test_16k.wav', 'rb') as wf:
    audio_16 = wf.readframes(wf.getnframes())

rec.AcceptWaveform(audio_16)
result = json.loads(rec.FinalResult())
print(f"RESULTADO: '{result.get('text', '')}'")
```

## Verificaciones Realizadas

### Audio funciona (44100 Hz, max 32767):
```
Audio samples: 220500
Max value: 32767
Mean value: 27141.3
```

### Conversión ffmpeg funciona:
```
Audio 16k: 160000 bytes
16k sample rate: 16000
16k channels: 1
16k frames: 80000
```

### Modelo carga correctamente:
```
LOG (VoskAPI:ReadDataFiles():model.cc:213) Decoding params beam=11 max-active=4000 lattice-beam=4
Modelo cargado exitosamente
```

## Resultados de Reconocimiento
- **'hola cómo'** - Reconocido parcialmente (2 palabras de frase completa)
- **'eh eh eh'** - Reconocido cuando usuario habló "eh"
- **''** - Varios intentos retornaron vacío

## Soluciones Intentadas
1. Downsampling manual byte por byte - No funciona
2. Conversión con sox - Instalado pero no resuelve
3. Conversión con ffmpeg - Funciona técnicamente
4. Procesar chunk por chunk - Inconsistente
5. Modelo pequeño vs grande - Ambos mismo comportamiento

## Problema de Inconsistencia
El modelo funciona a veces pero no otras. Posibles causas:
1. Estado interno del reconocedor Vosk
2. Timing de audio (silencio al inicio/final)
3. Calidad del micrófono USB
4. Condiciones de memoria en Raspberry Pi 3

## Recomendación
Para resolver de forma consistente, se necesita:
1. Investigar por qué el reconocedor a veces retorna vacío
2. Implementar buffer circular con procesamiento en tiempo real
3. Agregar validación de audio antes de procesar
4. Posiblemente usar un modelo diferente o más pesado si la memoria lo permite

## Objetivo del Proyecto
Crear un sistema que:
1. Grabe audio del micrófono USB
2. Convierta a 16kHz (formato que Vosk espera)
3. Procese con Vosk para reconocimiento de voz en español
4. Muestre texto reconocido en pantalla HDMI
5. Funcione de forma consistente en Raspberry Pi 3 para demo de sordos

## Información del Sistema
```bash
# Estructura del proyecto en Raspberry
/home/jose/RaspberryAudioText/

# Modelo Vosk
/home/jose/RaspberryAudioText/modelo/

# Acceso SSH
ssh jose@192.168.1.110

# Clonar repo
git clone https://github.com/willdex/RaspberryAudioText.git
```

## Autores / Contacto
- Usuario Raspberry: jose
- Repo GitHub: https://github.com/willdex/RaspberryAudioText
- Fecha Informe: 17 Mayo 2026