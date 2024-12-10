import logging
import struct
from datetime import datetime, UTC
from typing import NamedTuple, Self


_LOGGER = logging.getLogger("dries007_p1.config_flow")


PACKET_FORMAT = '=BBBIIIIIHHHHHHHHHHHHHHIBHBB'
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)
assert PACKET_SIZE == 60, "Packet length does not match firmware."


class Packet(NamedTuple):
    # These values are not yet scaled!
    pre0: int
    pre1: int
    pre2: int
    timestamp: int
    meter_delivered_t1: int             # .001
    meter_delivered_t2: int             # .001
    meter_injected_t1: int              # .001
    meter_injected_t2: int              # .001
    sum_power_delivered: int            # .001
    sum_power_injected: int             # .001
    power_per_phase_delivered_1: int    # .001
    power_per_phase_delivered_2: int    # .001
    power_per_phase_delivered_3: int    # .001
    power_per_phase_injected_1: int     # .001
    power_per_phase_injected_2: int     # .001
    power_per_phase_injected_3: int     # .001
    voltage_per_phase_1: int            # .1
    voltage_per_phase_2: int            # .1
    voltage_per_phase_3: int            # .1
    current_per_phase_1: int            # .01
    current_per_phase_2: int            # .01
    current_per_phase_3: int            # .01
    gas_volume: int                     # .001
    tariff: int
    checksum: int  # Broken, ignored.
    post0: int
    post1: int
    updated: datetime

    def is_sane_followup(self, pp: Self | None) -> bool:
        """
        Check if this packet is sane followup to the passed previous packet (pp).
        Only the "total" values are checked because they mess up the statistics if they are wrong.
        A momentary blip in the other measurements is less annoying to deal with.
        """

        assert self.pre0 == 0x42, "Bad prefix byte 0"
        assert self.pre1 == 0xAA, "Bad prefix byte 1"
        assert self.pre2 == 0xFF, "Bad prefix byte 2"
        assert self.post0 == 0x55, "Bad postfix byte 0"
        assert self.post1 == 0xAA, "Bad postfix byte 1"
        assert self.timestamp < 0x8000_0000, f"Error packet with code {self.timestamp - 0x8000_0000}"
        assert self.tariff == 1 or self.tariff == 2, "Tariff must be 1 or 2."
        assert 190_0 < self.voltage_per_phase_1 < 270_0, "Voltage P1 out of bounds of normal."
        assert 190_0 < self.voltage_per_phase_2 < 270_0, "Voltage P2 out of bounds of normal."
        assert 190_0 < self.voltage_per_phase_3 < 270_0, "Voltage P3 out of bounds of normal."

        if pp is None:
            _LOGGER.info("Previous packet was None, accepting.")
            return True

        dg = self.gas_volume - pp.gas_volume
        ddt1 = self.meter_delivered_t1 - pp.meter_delivered_t1
        ddt2 = self.meter_delivered_t2 - pp.meter_delivered_t2
        dit1 = self.meter_injected_t1 - pp.meter_injected_t1
        dit2 = self.meter_injected_t2 - pp.meter_injected_t2

        _LOGGER.debug("dGas=%d dDt1=%d dDt2=%d dIt1=%d dIt2=%d @ %s", dg, ddt1, ddt2, dit1, dit2, self.updated)
        # 10m³ max delta on gas
        # 10kWh max delta on energy meters
        return all(-10_000 <= x < 10_000 for x in (dg, ddt1, ddt2, dit1, dit2))

    @classmethod
    def load(cls, packet) -> Self:
        return cls(*struct.unpack(PACKET_FORMAT, packet), updated=datetime.now(UTC))


def _main():
    import rich.traceback
    from rich.logging import RichHandler

    rich.traceback.install()
    logging.basicConfig(level=logging.DEBUG, format="%(message)s", datefmt="[%X]", handlers=[RichHandler(rich_tracebacks=True, tracebacks_width=160, tracebacks_code_width=156, tracebacks_show_locals=True)])
    prev = None
    while True:
        inp = input("Packet as hex? ").strip()
        # noinspection PyBroadException
        try:
            packet = Packet.load(bytes.fromhex(inp))
            _LOGGER.info("Success: %r", packet)
            sane = packet.is_sane_followup(prev)
            _LOGGER.info("Sane followup: %r", sane)
            prev = packet
        except KeyboardInterrupt:
            raise
        except Exception:
            _LOGGER.exception("Error parsing packet.")


if __name__ == '__main__':
    _main()
