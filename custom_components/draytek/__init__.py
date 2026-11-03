"""The DrayTek integration."""

from __future__ import annotations

from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.singleton import singleton
from pysnmp.hlapi.v3arch.asyncio import SnmpEngine
from pysnmp.hlapi.v3arch.asyncio.cmdgen import LCD
from pysnmp.smi import view

from .api import DraytekClient
from .const import CONF_COMMUNITY, DOMAIN
from .coordinator import DraytekConfigEntry, DraytekCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]


def _create_snmp_engine() -> SnmpEngine:
    """Create an SNMP engine with all MIB modules loaded.

    pysnmp otherwise loads MIB modules from disk lazily inside the event loop.
    """
    engine = SnmpEngine()
    mib_view_controller = view.MibViewController(
        engine.message_dispatcher.mib_instrum_controller.get_mib_builder()
    )
    engine.cache["mibViewController"] = mib_view_controller
    mib_view_controller.mibBuilder.load_modules()
    return engine


@singleton(f"{DOMAIN}_snmp_engine")
async def async_get_snmp_engine(hass: HomeAssistant) -> SnmpEngine:
    """Return the SNMP engine shared by all config entries."""
    engine = await hass.async_add_executor_job(_create_snmp_engine)

    @callback
    def _async_shutdown(event: Event) -> None:
        LCD.unconfigure(engine, None)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_shutdown)
    return engine


async def async_create_client(
    hass: HomeAssistant, host: str, port: int, community: str
) -> DraytekClient:
    """Create an SNMP client."""
    engine = await async_get_snmp_engine(hass)
    return DraytekClient(engine, host, port, community)


async def async_setup_entry(hass: HomeAssistant, entry: DraytekConfigEntry) -> bool:
    """Set up DrayTek from a config entry."""
    client = await async_create_client(
        hass,
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_COMMUNITY],
    )
    coordinator = DraytekCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DraytekConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
