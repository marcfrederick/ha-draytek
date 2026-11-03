"""Data update coordinator for the DrayTek integration."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import DraytekClient, DraytekData, DraytekError
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

COUNTER32_MAX = 2**32

# sysUpTime is converted to a boot timestamp; ignore jitter below this
BOOT_TIME_TOLERANCE = timedelta(seconds=60)

type DraytekConfigEntry = ConfigEntry[DraytekCoordinator]


@dataclass
class InterfaceRates:
    """Throughput of an interface in bit/s, derived from octet counters."""

    rx: float | None = None
    tx: float | None = None


@dataclass
class _CounterSample:
    in_octets: int | None
    out_octets: int | None
    timestamp: float


def _rate(previous: int | None, current: int | None, seconds: float) -> float | None:
    if previous is None or current is None or seconds <= 0:
        return None
    delta = current - previous
    if delta < 0:
        # Counter32 wrapped around
        delta += COUNTER32_MAX
    return delta * 8 / seconds


@dataclass
class DraytekState:
    """Router data plus values derived across polls."""

    data: DraytekData
    boot_time: datetime | None
    rates: dict[int, InterfaceRates] = field(default_factory=dict)


class DraytekCoordinator(DataUpdateCoordinator[DraytekState]):
    """Poll the router via SNMP."""

    config_entry: DraytekConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: DraytekConfigEntry, client: DraytekClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self._samples: dict[int, _CounterSample] = {}

    async def _async_update_data(self) -> DraytekState:
        try:
            data = await self.client.async_get_data()
        except DraytekError as err:
            raise UpdateFailed(f"Error communicating with router: {err}") from err

        now = time.monotonic()
        rates: dict[int, InterfaceRates] = {}
        for index, iface in data.interfaces.items():
            if (prev := self._samples.get(index)) is not None:
                elapsed = now - prev.timestamp
                rates[index] = InterfaceRates(
                    rx=_rate(prev.in_octets, iface.in_octets, elapsed),
                    tx=_rate(prev.out_octets, iface.out_octets, elapsed),
                )
            self._samples[index] = _CounterSample(
                iface.in_octets, iface.out_octets, now
            )

        return DraytekState(data=data, boot_time=self._boot_time(data), rates=rates)

    def _boot_time(self, data: DraytekData) -> datetime | None:
        if data.uptime_seconds is None:
            return None
        boot_time = dt_util.utcnow() - timedelta(seconds=data.uptime_seconds)
        previous = self.data.boot_time if self.data else None
        if previous is not None and abs(boot_time - previous) < BOOT_TIME_TOLERANCE:
            return previous
        return boot_time.replace(microsecond=0)
