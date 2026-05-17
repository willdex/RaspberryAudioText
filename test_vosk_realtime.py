import json
import numpy as np
from scipy.signal import resample
import sounddevice as sd
from vosk import Model, KaldiRecognizer, SetLogLevel

SetLogLevel(-1)

SAMPLE_RATE_DEV = 44100
SAMPLE_RATE_VOSK = 16000
BLOCK_SIZE = 4410  # 100ms
MODEL_PATH = "modelo"

print("Cargando modelo Vosk...")
model = Model(MODEL_PATH)
rec = KaldiRecognizer(model, SAMPLE_RATE_VOSK)

chunk_count = [0]
sentences = []

def callback(indata, frames, time_info, status):
    chunk_44100 = indata[:, 0].astype(np.int16)
    num_out = int(len(chunk_44100) * SAMPLE_RATE_VOSK / SAMPLE_RATE_DEV)
    resampled = resample(chunk_44100.astype(np.float32), num_out)
    chunk_16000 = np.clip(resampled, -32768, 32767).astype(np.int16)

    if rec.AcceptWaveform(chunk_16000.tobytes()):
        result = json.loads(rec.Result())
        text = result.get('text', '').strip()
        if text and len(text) > 1:
            sentences.append(text)
            print(f"  [FRASE] {text}")
    else:
        partial = json.loads(rec.PartialResult())
        ptext = partial.get('partial', '').strip()
        if ptext and len(ptext) > 2:
            print(f"  ... {ptext}", end="", flush=True)

    chunk_count[0] += 1
    if chunk_count[0] % 10 == 0:
        energy = np.abs(chunk_44100).mean()
        print(f"  [{chunk_count[0]*0.1:.1f}s] energia={energy:.0f}")

device = None
for i, dev in enumerate(sd.query_devices()):
    if 'USB' in dev['name'] and dev['max_input_channels'] > 0:
        device = i
        break

print(f"\nMicrófono USB: dispositivo {device}")
print("HABLE AL MICROFONO - 15 segundos...\n")

stream = sd.InputStream(
    device=device, samplerate=SAMPLE_RATE_DEV,
    blocksize=BLOCK_SIZE, dtype='int16', channels=1,
    callback=callback
)

with stream:
    sd.sleep(15000)

final = json.loads(rec.FinalResult())
ftext = final.get('text', '').strip()
if ftext:
    sentences.append(ftext)

print(f"\n{'='*50}")
print(f"Frases reconocidas: {len(sentences)}")
for i, s in enumerate(sentences):
    print(f"  {i+1}. {s}")
print(f"{'='*50}")

if len(sentences) > 0:
    print("\nVosk funciona! El reconocimiento en tiempo real es consistente.")
else:
    print("\nSin resultados. Verificar microfono o acercarse mas al hablar.")