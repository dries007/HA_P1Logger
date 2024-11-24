import asyncio
import logging
import struct
from datetime import datetime, UTC
from typing import Callable, NamedTuple, Self

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import callback, HomeAssistant

import serial_asyncio_fast as serial_asyncio
from serial import SerialException


_LOGGER = logging.getLogger(DOMAIN).getChild("config_flow")

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
        assert 190_0 < self.voltage_per_phase_1 < 270_0
        assert 190_0 < self.voltage_per_phase_2 < 270_0
        assert 190_0 < self.voltage_per_phase_3 < 270_0

        if pp is None:
            return True

        return (
            # 10m³ max increase on gas
            0 <= self.gas_volume - pp.gas_volume < 10_000
            # 10kWh max increase on energy meters
            and 0 <= self.meter_delivered_t1 - pp.meter_delivered_t1 < 10_000
            and 0 <= self.meter_delivered_t2 - pp.meter_delivered_t2 < 10_000
            and 0 <= self.meter_injected_t1 - pp.meter_injected_t1 < 10_000
            and 0 <= self.meter_injected_t2 - pp.meter_injected_t2 < 10_000
        )



class P1Logger:
    def __init__(self, hass: HomeAssistant, serial_port: str) -> None:
        self.device_name = "P1 Logger"
        self.device_id = "p1"
        self._hass = hass
        self._serial_port = serial_port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._callbacks = set()
        self._task = None
        self.packet: Packet | None = None

    async def connect(self):
        try:
            self._reader, self._writer = await serial_asyncio.open_serial_connection(
                url=self._serial_port,
                baudrate=1200,
                bytesize=serial_asyncio.serial.EIGHTBITS,
                parity=serial_asyncio.serial.PARITY_NONE,
                stopbits=serial_asyncio.serial.STOPBITS_ONE,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
        except SerialException:
            _LOGGER.exception("Unable to connect to the serial device %s.", self._serial_port)
            raise

    async def disconnect(self):
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()

    def register_callback(self, cb: Callable[[], None]) -> None:
        self._callbacks.add(cb)

    def remove_callback(self, cb: Callable[[], None]) -> None:
        self._callbacks.discard(cb)

    @callback
    def _stop(self, event):
        self._task.cancel()

    def start_listening(self):
        self._task = self._hass.loop.create_task(self.serial_read())
        self._hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._stop)

    # noinspection PyBroadException
    async def serial_read(self):
        _LOGGER.info('Starting serial read loop...')
        previous_packet: Packet | None = None
        attempts = 0
        fail_len = 0
        fail_parse = 0
        fail_insane = 0

        while True:
            try:
                try:
                    _LOGGER.info('Connecting to serial port %s...', self._serial_port)
                    await self.connect()
                except SerialException:
                    await asyncio.sleep(5)
                    continue

                consecutive_fails = 0
                while True:
                    if consecutive_fails > 10:
                        _LOGGER.error('Too many consecutive failures. Restarting...')
                        await asyncio.sleep(1)
                        break

                    raw = await self._reader.readuntil(b'\x55\xAA')
                    _LOGGER.debug(f'Raw input: {raw.hex()}')
                    start = raw.rfind(b'\x42\xAA\xFF')
                    if start == -1:
                        _LOGGER.error(f"Skipping packet due to missing prefix: {raw.hex()}")
                        continue
                    attempts += 1
                    packet = raw[start:]
                    if len(packet) != PACKET_SIZE:
                        consecutive_fails += 1
                        fail_len += 1
                        _LOGGER.error(f"Bad packet, length wrong. Occurred in {fail_len} of {attempts} packets. Got {len(packet)} instead of {PACKET_SIZE}: {packet.hex()}")
                        continue
                    try:
                        parsed = Packet(*struct.unpack(PACKET_FORMAT, packet), updated=datetime.now(UTC))

                        if not parsed.is_sane_followup(previous_packet):
                            consecutive_fails += 1
                            fail_insane += 1
                            _LOGGER.error(f"Bad packet, insane values. Occurred in {fail_insane} of {attempts} packets  Hex: {packet.hex()}", exc_info=True)
                            continue

                    except Exception:
                        consecutive_fails += 1
                        fail_parse += 1
                        _LOGGER.error(f"Bad packet, parsing failed. Occurred in {fail_parse} of {attempts} packets. Hex: {packet.hex()}", exc_info=True)
                        continue

                    _LOGGER.debug("Success: %r", parsed)

                    consecutive_fails = 0
                    previous_packet = self.packet
                    self.packet = parsed

                    for cb in self._callbacks:
                        cb()

            except Exception:
                _LOGGER.error("Something went wrong. Retrying.", exc_info=True)


