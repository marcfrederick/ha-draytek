"""SNMP client for DrayTek routers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    bulk_walk_cmd,
    get_cmd,
)
from pysnmp.proto.rfc1905 import EndOfMibView, NoSuchInstance, NoSuchObject

# SNMPv2-MIB / HOST-RESOURCES-MIB
OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"
OID_SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
OID_SYS_NAME = "1.3.6.1.2.1.1.5.0"
OID_CPU_LOAD = "1.3.6.1.2.1.25.3.3.1.2.0"

# DrayTek enterprise MIB
OID_MODEL = "1.3.6.1.4.1.7367.3.1.0"
OID_FIRMWARE = "1.3.6.1.4.1.7367.3.2.0"
OID_MEMORY_USAGE = "1.3.6.1.4.1.7367.3.7.0"
OID_MAC = "1.3.6.1.4.1.7367.3.8.0"

# IF-MIB ifTable and its columns
OID_IF_TABLE = "1.3.6.1.2.1.2.2.1"
IF_DESCR = 2
IF_TYPE = 3
IF_SPEED = 5
IF_ADMIN_STATUS = 7
IF_OPER_STATUS = 8
IF_IN_OCTETS = 10
IF_OUT_OCTETS = 16

# ifType values of DSL interfaces: adsl(94), vdsl(97), vdsl2(251)
DSL_IF_TYPES = {94, 97, 251}

# ADSL-LINE-MIB ATU-C (exchange side) and ATU-R (router side) current status
# tables. DrayTek firmware deviates from the MIB: the ATU-C table holds the
# downstream values and the ATU-R table the upstream values, matching the
# "Near End"/"Far End" columns of the web UI's DSL status page.
OID_ATUC_CURR = "1.3.6.1.2.1.10.94.1.1.2.1"
OID_ATUR_CURR = "1.3.6.1.2.1.10.94.1.1.3.1"
CURR_SNR_MARGIN = 4
CURR_ATTENUATION = 5
CURR_ATTAINABLE_RATE = 8

# VDSL2-LINE-MIB xdsl2ChStatusActDataRate, indexed by ifIndex.unit where
# unit is xtuc(1) for downstream and xtur(2) for upstream
OID_XDSL2_ACT_DATA_RATE = "1.3.6.1.2.1.10.251.1.2.2.1.2"

TIMEOUT = 5
RETRIES = 2
MAX_REPETITIONS = 50


class DraytekError(Exception):
    """Raised when the router cannot be queried."""


@dataclass
class InterfaceData:
    """Status and counters of a single network interface."""

    index: int
    descr: str
    if_type: int | None
    speed: int | None
    admin_up: bool
    oper_up: bool
    in_octets: int | None
    out_octets: int | None


@dataclass
class DslData:
    """DSL line statistics."""

    downstream_rate: int | None = None
    upstream_rate: int | None = None
    downstream_attainable_rate: int | None = None
    upstream_attainable_rate: int | None = None
    downstream_snr_margin: float | None = None
    upstream_snr_margin: float | None = None
    downstream_attenuation: float | None = None
    upstream_attenuation: float | None = None


@dataclass
class DraytekData:
    """A snapshot of all values read from the router."""

    sys_descr: str
    sys_name: str | None
    model: str | None
    firmware: str | None
    mac: str | None
    uptime_seconds: float | None
    cpu_load: int | None
    memory_usage: int | None
    interfaces: dict[int, InterfaceData] = field(default_factory=dict)
    dsl_index: int | None = None
    dsl: DslData | None = None


def _value(val: Any) -> Any:
    """Convert a pysnmp value to a Python value, or None if missing."""
    if val is None or isinstance(val, (NoSuchInstance, NoSuchObject, EndOfMibView)):
        return None
    if hasattr(val, "asOctets"):
        return val.asOctets().rstrip(b"\x00").decode(errors="replace").strip()
    try:
        return int(val)
    except (TypeError, ValueError):
        return str(val)


def _int(val: Any) -> int | None:
    return val if isinstance(val, int) else None


def _str(val: Any) -> str | None:
    return val if isinstance(val, str) and val else None


class DraytekClient:
    """Read metrics from a DrayTek router via SNMP v2c."""

    def __init__(
        self, engine: SnmpEngine, host: str, port: int, community: str
    ) -> None:
        self._engine = engine
        self._host = host
        self._port = port
        # Vigor 165/166 firmware only supports SNMP v1/v2c
        self._auth = CommunityData(community, mpModel=1)
        self._target: UdpTransportTarget | None = None

    async def _get_target(self) -> UdpTransportTarget:
        if self._target is None:
            try:
                self._target = await UdpTransportTarget.create(
                    (self._host, self._port), timeout=TIMEOUT, retries=RETRIES
                )
            except Exception as err:
                raise DraytekError(f"Cannot resolve {self._host}: {err}") from err
        return self._target

    async def _get(self, oids: list[str]) -> dict[str, Any]:
        """Fetch a list of OIDs, returning missing ones as None."""
        target = await self._get_target()
        error_indication, error_status, _, var_binds = await get_cmd(
            self._engine,
            self._auth,
            target,
            ContextData(),
            *(ObjectType(ObjectIdentity(oid)) for oid in oids),
            lookupMib=False,
        )
        if error_indication:
            raise DraytekError(str(error_indication))
        if error_status:
            raise DraytekError(error_status.prettyPrint())
        return {str(oid): _value(val) for oid, val in var_binds}

    async def _walk(self, base_oid: str) -> dict[str, Any]:
        """Walk a subtree, returning values keyed by the OID suffix."""
        target = await self._get_target()
        result: dict[str, Any] = {}
        async for error_indication, error_status, _, var_binds in bulk_walk_cmd(
            self._engine,
            self._auth,
            target,
            ContextData(),
            0,
            MAX_REPETITIONS,
            ObjectType(ObjectIdentity(base_oid)),
            lexicographicMode=False,
            lookupMib=False,
        ):
            if error_indication:
                raise DraytekError(str(error_indication))
            if error_status:
                raise DraytekError(error_status.prettyPrint())
            for oid, val in var_binds:
                result[str(oid).removeprefix(f"{base_oid}.")] = _value(val)
        return result

    async def _get_interfaces(self) -> dict[int, InterfaceData]:
        columns: dict[int, dict[int, Any]] = {}
        for suffix, val in (await self._walk(OID_IF_TABLE)).items():
            column, _, index = suffix.partition(".")
            columns.setdefault(int(index), {})[int(column)] = val

        return {
            index: InterfaceData(
                index=index,
                descr=_str(cols.get(IF_DESCR)) or f"Interface {index}",
                if_type=_int(cols.get(IF_TYPE)),
                speed=_int(cols.get(IF_SPEED)),
                admin_up=cols.get(IF_ADMIN_STATUS) == 1,
                oper_up=cols.get(IF_OPER_STATUS) == 1,
                in_octets=_int(cols.get(IF_IN_OCTETS)),
                out_octets=_int(cols.get(IF_OUT_OCTETS)),
            )
            for index, cols in sorted(columns.items())
        }

    async def async_get_data(self) -> DraytekData:
        """Read all metrics from the router."""
        interfaces = await self._get_interfaces()
        dsl_index = next(
            (i.index for i in interfaces.values() if i.if_type in DSL_IF_TYPES),
            None,
        )

        oids = [
            OID_SYS_DESCR,
            OID_SYS_UPTIME,
            OID_SYS_NAME,
            OID_CPU_LOAD,
            OID_MODEL,
            OID_FIRMWARE,
            OID_MEMORY_USAGE,
            OID_MAC,
        ]
        if dsl_index is not None:
            dsl_oids = {
                "downstream_rate": f"{OID_XDSL2_ACT_DATA_RATE}.{dsl_index}.1",
                "upstream_rate": f"{OID_XDSL2_ACT_DATA_RATE}.{dsl_index}.2",
                "downstream_attainable_rate": f"{OID_ATUC_CURR}.{CURR_ATTAINABLE_RATE}.{dsl_index}",
                "upstream_attainable_rate": f"{OID_ATUR_CURR}.{CURR_ATTAINABLE_RATE}.{dsl_index}",
                "downstream_snr_margin": f"{OID_ATUC_CURR}.{CURR_SNR_MARGIN}.{dsl_index}",
                "upstream_snr_margin": f"{OID_ATUR_CURR}.{CURR_SNR_MARGIN}.{dsl_index}",
                "downstream_attenuation": f"{OID_ATUC_CURR}.{CURR_ATTENUATION}.{dsl_index}",
                "upstream_attenuation": f"{OID_ATUR_CURR}.{CURR_ATTENUATION}.{dsl_index}",
            }
            oids.extend(dsl_oids.values())

        values = await self._get(oids)
        if (sys_descr := _str(values.get(OID_SYS_DESCR))) is None:
            raise DraytekError("Router did not return sysDescr")

        dsl = None
        if dsl_index is not None:
            # ADSL-LINE-MIB defines SNR margin and attenuation in 0.1 dB, but
            # DrayTek firmware reports them in whole dB.
            dsl = DslData(
                **{key: _int(values.get(oid)) for key, oid in dsl_oids.items()}
            )

        uptime_ticks = _int(values.get(OID_SYS_UPTIME))
        return DraytekData(
            sys_descr=sys_descr,
            sys_name=_str(values.get(OID_SYS_NAME)),
            model=_str(values.get(OID_MODEL)),
            firmware=_str(values.get(OID_FIRMWARE)),
            mac=_str(values.get(OID_MAC)),
            uptime_seconds=uptime_ticks / 100 if uptime_ticks is not None else None,
            cpu_load=_int(values.get(OID_CPU_LOAD)),
            memory_usage=_int(values.get(OID_MEMORY_USAGE)),
            interfaces=interfaces,
            dsl_index=dsl_index,
            dsl=dsl,
        )
