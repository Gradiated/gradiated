import math
import os
import threading
import time


class EnergyEstimator:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.updated_at = clock()
        self.sampled_at = None
        self.power = None
        self.active = 0
        self.integral = 0.0
        self.epoch = 0
        self.started = False

    def _advance(self, now):
        if self.power is None or self.sampled_at is None or now - self.sampled_at > 2:
            self.epoch += 1
        elif self.active:
            self.integral += self.power * max(0, now - self.updated_at) / self.active
        self.updated_at = now

    def sample(self, power):
        with self.lock:
            now = self.clock()
            self._advance(now)
            self.power = power if power is not None and math.isfinite(power) and power >= 0 else None
            self.sampled_at = now

    def begin(self):
        with self.lock:
            self._advance(self.clock())
            self.active += 1
            return self.integral, self.epoch

    def finish(self, ticket):
        with self.lock:
            self._advance(self.clock())
            self.active -= 1
            initial, epoch = ticket
            if epoch != self.epoch:
                return None
            value = self.integral - initial
            return value if math.isfinite(value) and value >= 0 else None

    def start(self):
        with self.lock:
            if self.started:
                return
            self.started = True
        try:
            threading.Thread(target=self._sample_forever, daemon=True, name='gpu-energy').start()
        except Exception:
            pass

    def _sample_forever(self):
        try:
            import pynvml

            devices = os.environ.get('NVIDIA_VISIBLE_DEVICES', '').split(',')
            # Never charge a request for unassigned GPUs elsewhere on the host.
            if not devices or len(set(devices)) != len(devices) or any(not d.startswith('GPU-') for d in devices):
                return
            pynvml.nvmlInit()
            handles = [pynvml.nvmlDeviceGetHandleByUUID(device) for device in devices]
        except Exception:
            return

        while True:
            try:
                power = sum(pynvml.nvmlDeviceGetPowerUsage(handle) for handle in handles) / 1000
                self.sample(power)
            except Exception:
                self.sample(None)
            time.sleep(.25)
