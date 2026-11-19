"""RP2350 PIO frequency-deviation bench test; not a practical broadcast transmitter."""

import time
import rp2
from machine import Pin, freq

DEVIATION_HZ = 75_000


@rp2.asm_pio(set_init=rp2.PIO.OUT_LOW)
def rf_carrier():
    wrap_target()
    set(pins, 1)
    set(pins, 0)
    wrap()

class FMTransmitter:
    def __init__(self, pin_num):
        self.pin = Pin(pin_num, Pin.OUT)
        self.sm = None
        self.carrier_hz = 0

    def start(self, mhz):
        carrier_hz = int(mhz * 1_000_000)
        max_carrier_hz = freq() // 2 - DEVIATION_HZ
        if not DEVIATION_HZ < carrier_hz <= max_carrier_hz:
            raise ValueError(
                "Carrier must be above the deviation and at or below "
                "{:.3f} MHz for the current system clock.".format(
                    max_carrier_hz / 1_000_000
                )
            )

        if self.sm is not None:
            self.sm.active(0)

        self.carrier_hz = carrier_hz
        self.sm = rp2.StateMachine(
            0, rf_carrier, freq=self.carrier_hz * 2, set_base=self.pin
        )
        self.sm.active(1)

    def send_beep(self, tone_hz=650, duration=0.3):
        if self.sm is None:
            raise RuntimeError("Start the transmitter before sending a beep.")
        if not 1 <= tone_hz <= 500_000:
            raise ValueError("Tone frequency must be between 1 and 500000 Hz.")
        if duration <= 0:
            raise ValueError("Beep duration must be greater than zero.")

        half_period = int(500_000 / tone_hz)
        end = time.ticks_add(time.ticks_ms(), int(duration * 1000))

        while time.ticks_diff(end, time.ticks_ms()) > 0:
            self.sm.freq(int((self.carrier_hz + DEVIATION_HZ) * 2))
            time.sleep_us(half_period)
            self.sm.freq(int((self.carrier_hz - DEVIATION_HZ) * 2))
            time.sleep_us(half_period)

        self.sm.freq(int(self.carrier_hz * 2))

    def stop(self):
        if self.sm is not None:
            self.sm.active(0)
        self.pin.value(0)


tx = FMTransmitter(15)
max_mhz = (freq() // 2 - DEVIATION_HZ) / 1_000_000
min_mhz = DEVIATION_HZ / 1_000_000

print("PIO FM bench experiment only; not suitable for FM broadcasting.")
print("Keep the output lead short; do not connect an antenna.")
while True:
    try:
        user_input = input(
            "Carrier MHz ({:.3f}-{:.3f}) or 'q': ".format(min_mhz, max_mhz)
        ).strip().lower()

        if user_input == "q":
            tx.stop()
            print("Stopped.")
            break

        mhz = float(user_input)

        tx.start(mhz)
        print("Running a stepped FM test at {:.3f} MHz.".format(mhz))
        try:
            tx.send_beep()
        finally:
            tx.stop()
        print("Test finished. Enter another frequency.")

    except ValueError:
        print("Invalid input or unsupported carrier frequency.")
    except KeyboardInterrupt:
        tx.stop()
        print("\nStopped.")
        break