import asyncio
import logging
from typing import Callable

import serial_asyncio_fast as serial_asyncio
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import callback, HomeAssistant
from serial import SerialException

from .const import DOMAIN
from .packet import Packet, PACKET_SIZE

_LOGGER = logging.getLogger(DOMAIN).getChild("p1logger")




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
        attempts = 0
        fail_len = 0
        fail_parse = 0
        fail_insane = 0

        while True:
            previous_packet: Packet | None = None
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
                        parsed = Packet.load(packet)

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


