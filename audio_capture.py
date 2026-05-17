import queue
import logging
import sounddevice as sd

log = logging.getLogger(__name__)


class AudioCapture:
    def __init__(self, device, sample_rate, blocksize, channels=1):
        self.device = device
        self.sample_rate = sample_rate
        self.blocksize = blocksize
        self.channels = channels
        self.q = queue.Queue()
        self.running = False

    def _callback(self, indata, frames, time, status):
        if status:
            log.warning(f"Audio status: {status}")
        self.q.put(bytes(indata))

    def start(self):
        self.stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=self.blocksize,
            device=self.device,
            dtype='int16',
            channels=self.channels,
            callback=self._callback
        )
        self.running = True
        log.info(f"Audio started: {self.device} @ {self.sample_rate}Hz")

    def stop(self):
        self.running = False
        if hasattr(self, 'stream'):
            self.stream.close()

    def read(self):
        return self.q.get()