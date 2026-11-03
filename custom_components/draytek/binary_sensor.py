"""Binary sensor platform for the DrayTek integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DraytekConfigEntry
from .entity import DraytekInterfaceEntity

PARALLEL_UPDATES = 0

LINK_DESCRIPTION = BinarySensorEntityDescription(
    key="link",
    translation_key="interface_link",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DraytekConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up DrayTek binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        DraytekLinkBinarySensor(coordinator, LINK_DESCRIPTION, interface)
        for interface in coordinator.data.data.interfaces.values()
    )


class DraytekLinkBinarySensor(DraytekInterfaceEntity, BinarySensorEntity):
    """Operational status of an interface (e.g. DSL sync)."""

    @property
    def is_on(self) -> bool | None:
        """Return true if the interface is up."""
        if (interface := self.interface) is None:
            return None
        return interface.oper_up
