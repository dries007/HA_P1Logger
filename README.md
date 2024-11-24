# Home Assistant P1 Logger

Home Assistant custom component for taking in (custom) Smart Meter P1 port communications.

If your installation is within cable reach of your smart meter, I recommend you use the official [DSMR Slimme Meter](https://www.home-assistant.io/integrations/dsmr/) integration.

I made this specifically because my meter is in the basement. I had to use a very low bandwidth serial link, so I'm sending over a limited subset of the parsed data.

## Hardware

The hardware I use for this project is a DIY circuit board based on the HC-12 SI4463 wireless UART modules.

I used some microcontrollers I had lying around (ATMega128A) to parse the P1 telegrams into a compact binary format with CRC and send it over the highest gain/lowest bandwidth connection possible.
This together with the use of a directional antenna was needed to receive the signal reliably trough 3 floors of concrete with in-floor heating.

On the receiving end, a simple USB-TTY cable is used, directly attached to a HC-12. 

The HC-12 mode is set to FU4 mode, with baud rate of 1200bps. This limits data to "60 bytes or less", at intervals of "no less than 2 seconds". This mode setting is done manually via AT commands, since it only needs to be done once.

If you would like schematics or code of this hardware, let me know. I even have some circuit boards left, I will ship them at cost if you would like to build your own.

Related repo: https://github.com/dries007/P1logger

## Software

This is an addon for Home Assistant in the form of a custom component that can be installed via [HACS](https://hacs.xyz/).

The code is based on the official [DSMR](https://www.home-assistant.io/integrations/dsmr/) integration.

A single packet follows this struct, with Little Endian encoding and struct packing enabled:

| Type        | Name                      | Source                             | Value                                                    |
|-------------|---------------------------|------------------------------------|----------------------------------------------------------|
| `uint8[3]`  | pre                       | Magic numbers                      | 0x42, 0x42, 0xFF                                         |
| `unit32`    | timestamp                 | 0-0:1.0.0                          | Timestamp in seconds since 2000-01-01 00:00:00           |
| `unit32`    | meter_delivered_t1        | 1-0:1.8.1                          | Delivered meter reading for tariff 1 in Wh.              |
| `unit32`    | meter_delivered_t2        | 1-0:1.8.2                          | Delivered meter reading for tariff 2 in Wh.              |
| `unit32`    | meter_injected_t1         | 1-0:2.8.1                          | Injected meter reading for tariff 1 in Wh.               |
| `unit32`    | meter_injected_t2         | 1-0:2.8.2                          | Injected meter reading for tariff 2 in Wh.               |
| `uint16`    | sum_power_delivered       | 1-0:1.7.0                          | Sum "actual" power for all phases in W.                  |
| `uint16`    | sum_power_injected        | 1-0:2.7.0                          | Sum "actual" power for all phases in W.                  |
| `uint16[3]` | power_per_phase_delivered | 1-0:21.7.0, 1-0:41.7.0, 1-0:61.7.0 | Instantaneous "actual" power for every phase in W.       |
| `uint16[3]` | power_per_phase_injected  | 1-0:22.7.0, 1-0:42.7.0, 1-0:62.7.0 | Instantaneous "actual" power for every phase in W.       |
| `uint16[3]` | voltage_per_phase         | 1-0:32.7.0, 1-0:52.7.0, 1-0:72.7.0 | Instantaneous voltage for every phase in .1V.            |
| `uint16[3]` | current_per_phase         | 1-0:31.7.0, 1-0:51.7.0, 1-0:71.7.0 | Instantaneous "actual" power for every phase in .01A.    |
| `unit32 `   | gas_volume                | 0-1:24.2.3                         | Gas volume in 0.001m3.                                   |
| `uint8 `    | tariff                    | 0-0:96.14.0                        | Tariff currently in effect. (1/2 for normal/night in BE) |
| `uint16 `   | checksum                  | CRC16                              | Calculated over all of the previous bytes.               |
| `uint8[2]`  | post                      | Magic numbers                      | 0x55, 0xAA                                               |

String for Python's struct module: `<BBBIIIIIHHHHHHHHHHHHHHIBHBB`.

If a value is -1, it indicates the value was not present in the telegram. All normal numbers are positive, as delivered and injected are counted separately.

To communicate errors, the MSB of timestamp is set. Treat payload after timestamp as raw bytes to be discarded.
Timestamp codes:

+  `0xFFFF_FFFF`     Blank telegram send. Usually a bad sign.
+  `0x8000_0000`     No telegram received within expected timeframe. Optional.
+  `0x8000_0002`     CRC mismatch.

This addon exposes each of the previously mentioned fields as a sensor to Home Assistant except for `pre`, `post`, and `checksum`.
