"""Base entity for the DrayTek integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import InterfaceData
from .const import DOMAIN
from .coordinator import DraytekCoordinator


class DraytekEntity(CoordinatorEntity[DraytekCoordinator]):
    """An entity belonging to the router device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DraytekCoordinator,
        description: EntityDescription,
        unique_id_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        entry = coordinator.config_entry
        data = coordinator.data.data
        self._attr_unique_id = f"{entry.unique_id}_{unique_id_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            connections=(
                {(CONNECTION_NETWORK_MAC, format_mac(data.mac))} if data.mac else set()
            ),
            manufacturer="DrayTek",
            model=data.model,
            name=entry.title,
            sw_version=data.firmware,
            configuration_url=f"http://{entry.data[CONF_HOST]}",
        )


class DraytekInterfaceEntity(DraytekEntity):
    """An entity for a single network interface of the router."""

    def __init__(
        self,
        coordinator: DraytekCoordinator,
        description: EntityDescription,
        interface: InterfaceData,
    ) -> None:
        super().__init__(
            coordinator, description, f"if{interface.index}_{description.key}"
        )
        self._index = interface.index
        is_dsl = interface.index == coordinator.data.data.dsl_index
        self._attr_translation_placeholders = {
            "interface": "DSL" if is_dsl else interface.descr
        }
        # Only enable entities of interfaces that are in use
        self._attr_entity_registry_enabled_default = interface.admin_up

    @property
    def interface(self) -> InterfaceData | None:
        """Return the current data of this interface."""
        return self.coordinator.data.data.interfaces.get(self._index)

    @property
    def available(self) -> bool:
        """Return if the interface is still reported by the router."""
        return super().available and self.interface is not None
