"""Platform for P1 Logger sensor integration."""
from abc import ABC, abstractmethod
from datetime import datetime, UTC
from typing import Any, Generic, TypeVar

from homeassistant.core import callback, HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfElectricCurrent, UnitOfElectricPotential, UnitOfEnergy, UnitOfPower, UnitOfTime, UnitOfVolume

from .const import DOMAIN
from . import P1LoggerConfigEntry
from .p1logger import P1Logger


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: P1LoggerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    p1logger = config_entry.runtime_data
    entities = [
        P1SensorEntityTimestamp(p1logger),
        P1SensorEntityEnergy(p1logger, 'Meter delivered t1'),
        P1SensorEntityEnergy(p1logger, 'Meter delivered t2'),
        P1SensorEntityEnergy(p1logger, 'Meter injected t1'),
        P1SensorEntityEnergy(p1logger, 'Meter injected t2'),
        P1SensorEntityPower(p1logger, 'Sum power delivered'),
        P1SensorEntityPower(p1logger, 'Sum power injected'),
        P1SensorEntityPower(p1logger, 'Power per phase delivered 1'),
        P1SensorEntityPower(p1logger, 'Power per phase delivered 2'),
        P1SensorEntityPower(p1logger, 'Power per phase delivered 3'),
        P1SensorEntityPower(p1logger, 'Power per phase injected 1'),
        P1SensorEntityPower(p1logger, 'Power per phase injected 2'),
        P1SensorEntityPower(p1logger, 'Power per phase injected 3'),
        P1SensorEntityVoltage(p1logger, 'Voltage per phase 1'),
        P1SensorEntityVoltage(p1logger, 'Voltage per phase 2'),
        P1SensorEntityVoltage(p1logger, 'Voltage per phase 3'),
        P1SensorEntityCurrent(p1logger, 'Current per phase 1'),
        P1SensorEntityCurrent(p1logger, 'Current per phase 2'),
        P1SensorEntityCurrent(p1logger, 'Current per phase 3'),
        P1SensorEntityGas(p1logger, 'Gas volume'),
        P1SensorEntityTariff(p1logger, 'Tariff'),
        P1SensorEntityUpdate(p1logger),
    ]
    async_add_entities(entities)
    p1logger.start_listening()



_DataT = TypeVar("_DataT")


class P1SensorEntity(SensorEntity, Generic[_DataT], ABC):
    should_poll = False

    def __init__(self, p1logger: P1Logger, name: str) -> None:
        self._p1logger = p1logger
        self._p1_packet_attribute = name.lower().replace(' ', '_')
        self._attr_name = name
        self._attr_unique_id = f"{self._p1logger.device_id}_{self._p1_packet_attribute}"

    @property
    def device_info(self):
        """Return information to link this entity with the correct device."""
        return {"identifiers": {(DOMAIN, self._p1logger.device_id)}}

    @property
    def available(self) -> bool:
        return self._p1logger.packet is not None

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.available:
            return self.transform(getattr(self._p1logger.packet, self._p1_packet_attribute))

    async def async_added_to_hass(self):
        """Run when this Entity has been added to HA."""
        self._p1logger.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self):
        """Entity being removed from hass."""
        self._p1logger.remove_callback(self.async_write_ha_state)

    @abstractmethod
    def transform(self, inp: int) -> _DataT:
        raise NotImplementedError("Implement this method.")


class P1SensorEntityTimestamp(P1SensorEntity[datetime]):
    state_class = None
    device_class = SensorDeviceClass.TIMESTAMP
    native_unit_of_measurement = None

    def __init__(self, p1logger):
        super().__init__(p1logger, "Timestamp")

    def transform(self, inp: int):
        # Offset is 2000-01-01 00:00:00
        return datetime.fromtimestamp(946684800 + inp, tz=UTC)


class P1SensorEntityUpdate(P1SensorEntity[datetime]):
    # The "update" entity serves as the "device" by setting a device info name value.
    state_class = None
    device_class = SensorDeviceClass.TIMESTAMP
    native_unit_of_measurement = None

    def __init__(self, p1logger):
        super().__init__(p1logger, "Updated")

    @property
    def device_info(self):
        di = super().device_info
        di["name"] = self._p1logger.device_name
        return di

    def transform(self, inp: datetime):
        return inp


class P1SensorEntityEnergy(P1SensorEntity[float]):
    state_class = SensorStateClass.TOTAL_INCREASING
    device_class = SensorDeviceClass.ENERGY
    native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def transform(self, inp: int) -> float:
        return inp * 0.001


class P1SensorEntityPower(P1SensorEntity[float]):
    state_class = SensorStateClass.MEASUREMENT
    device_class = SensorDeviceClass.POWER
    native_unit_of_measurement = UnitOfPower.KILO_WATT

    def transform(self, inp: int) -> float:
        return inp * 0.001


class P1SensorEntityVoltage(P1SensorEntity[float]):
    state_class = SensorStateClass.MEASUREMENT
    device_class = SensorDeviceClass.VOLTAGE
    native_unit_of_measurement = UnitOfElectricPotential.VOLT

    def transform(self, inp: int) -> float:
        return inp * 0.1


class P1SensorEntityCurrent(P1SensorEntity[float]):
    state_class = SensorStateClass.MEASUREMENT
    device_class = SensorDeviceClass.CURRENT
    native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

    def transform(self, inp: int) -> float:
        return inp * 0.01


class P1SensorEntityGas(P1SensorEntity[float]):
    state_class = SensorStateClass.TOTAL_INCREASING
    device_class = SensorDeviceClass.GAS
    native_unit_of_measurement = UnitOfVolume.CUBIC_METERS

    def transform(self, inp: int) -> float:
        return inp * 0.001

class P1SensorEntityTariff(P1SensorEntity[str]):
    state_class = None
    device_class = SensorDeviceClass.ENUM
    native_unit_of_measurement = None

    options = ["1", "2"]

    def transform(self, inp: int) -> str:
        return str(inp)
