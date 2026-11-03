"""Sensor platform for the DrayTek integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS,
    EntityCategory,
    UnitOfDataRate,
    UnitOfInformation,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import DslData, InterfaceData
from .coordinator import (
    DraytekConfigEntry,
    DraytekCoordinator,
    DraytekState,
    InterfaceRates,
)
from .entity import DraytekEntity, DraytekInterfaceEntity

PARALLEL_UPDATES = 0

type StateType = int | float | datetime | None


@dataclass(frozen=True, kw_only=True)
class DraytekSensorEntityDescription(SensorEntityDescription):
    """Describes a router-level sensor."""

    value_fn: Callable[[DraytekState], StateType]


@dataclass(frozen=True, kw_only=True)
class DraytekDslSensorEntityDescription(SensorEntityDescription):
    """Describes a DSL line sensor."""

    value_fn: Callable[[DslData], StateType]


@dataclass(frozen=True, kw_only=True)
class DraytekInterfaceSensorEntityDescription(SensorEntityDescription):
    """Describes a per-interface sensor."""

    value_fn: Callable[[InterfaceData, InterfaceRates | None], StateType]


SENSORS: tuple[DraytekSensorEntityDescription, ...] = (
    DraytekSensorEntityDescription(
        key="last_restart",
        translation_key="last_restart",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.boot_time,
    ),
    DraytekSensorEntityDescription(
        key="cpu_load",
        translation_key="cpu_load",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.data.cpu_load,
    ),
    DraytekSensorEntityDescription(
        key="memory_usage",
        translation_key="memory_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.data.memory_usage,
    ),
)


def _data_rate(
    key: str, value_fn: Callable[[DslData], StateType]
) -> DraytekDslSensorEntityDescription:
    return DraytekDslSensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=value_fn,
    )


def _decibels(
    key: str, value_fn: Callable[[DslData], StateType]
) -> DraytekDslSensorEntityDescription:
    return DraytekDslSensorEntityDescription(
        key=key,
        translation_key=key,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=value_fn,
    )


DSL_SENSORS: tuple[DraytekDslSensorEntityDescription, ...] = (
    _data_rate("dsl_downstream_rate", lambda dsl: dsl.downstream_rate),
    _data_rate("dsl_upstream_rate", lambda dsl: dsl.upstream_rate),
    _data_rate(
        "dsl_downstream_attainable_rate", lambda dsl: dsl.downstream_attainable_rate
    ),
    _data_rate(
        "dsl_upstream_attainable_rate", lambda dsl: dsl.upstream_attainable_rate
    ),
    _decibels("dsl_downstream_snr_margin", lambda dsl: dsl.downstream_snr_margin),
    _decibels("dsl_upstream_snr_margin", lambda dsl: dsl.upstream_snr_margin),
    _decibels("dsl_downstream_attenuation", lambda dsl: dsl.downstream_attenuation),
    _decibels("dsl_upstream_attenuation", lambda dsl: dsl.upstream_attenuation),
)


INTERFACE_SENSORS: tuple[DraytekInterfaceSensorEntityDescription, ...] = (
    DraytekInterfaceSensorEntityDescription(
        key="received",
        translation_key="interface_received",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda iface, _: iface.in_octets,
    ),
    DraytekInterfaceSensorEntityDescription(
        key="sent",
        translation_key="interface_sent",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda iface, _: iface.out_octets,
    ),
    DraytekInterfaceSensorEntityDescription(
        key="rx_rate",
        translation_key="interface_rx_rate",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda _, rates: rates.rx if rates else None,
    ),
    DraytekInterfaceSensorEntityDescription(
        key="tx_rate",
        translation_key="interface_tx_rate",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda _, rates: rates.tx if rates else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DraytekConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up DrayTek sensors."""
    coordinator = entry.runtime_data
    data = coordinator.data.data

    entities: list[SensorEntity] = [
        DraytekSensor(coordinator, description) for description in SENSORS
    ]
    if data.dsl is not None:
        entities.extend(
            DraytekDslSensor(coordinator, description) for description in DSL_SENSORS
        )
    entities.extend(
        DraytekInterfaceSensor(coordinator, description, interface)
        for interface in data.interfaces.values()
        for description in INTERFACE_SENSORS
    )
    async_add_entities(entities)


class DraytekSensor(DraytekEntity, SensorEntity):
    """A router-level sensor."""

    entity_description: DraytekSensorEntityDescription

    def __init__(
        self,
        coordinator: DraytekCoordinator,
        description: DraytekSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, description, description.key)

    @property
    def native_value(self) -> StateType:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)


class DraytekDslSensor(DraytekEntity, SensorEntity):
    """A DSL line sensor."""

    entity_description: DraytekDslSensorEntityDescription

    def __init__(
        self,
        coordinator: DraytekCoordinator,
        description: DraytekDslSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, description, description.key)

    @property
    def available(self) -> bool:
        """Return if DSL data is available."""
        return super().available and self.coordinator.data.data.dsl is not None

    @property
    def native_value(self) -> StateType:
        """Return the sensor value."""
        dsl = self.coordinator.data.data.dsl
        return self.entity_description.value_fn(dsl) if dsl else None


class DraytekInterfaceSensor(DraytekInterfaceEntity, SensorEntity):
    """A per-interface sensor."""

    entity_description: DraytekInterfaceSensorEntityDescription

    @property
    def native_value(self) -> StateType:
        """Return the sensor value."""
        if (interface := self.interface) is None:
            return None
        return self.entity_description.value_fn(
            interface, self.coordinator.data.rates.get(self._index)
        )
