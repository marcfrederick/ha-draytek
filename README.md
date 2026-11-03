# DrayTek

Home Assistant integration that reads metrics from DrayTek routers (tested
with a Vigor166) over SNMP v2c.

## Installation

### HACS

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=marcfrederick&repository=ha-draytek&category=integration)

1. Click the button above, or in HACS open the menu, choose **Custom repositories**,
   and add `https://github.com/marcfrederick/ha-draytek` with type **Integration**.
2. Download **DrayTek** and restart Home Assistant.

### Manual

Copy `custom_components/draytek/` to `<config_dir>/custom_components/draytek/`
and restart Home Assistant.

## Configuration

1. Enable SNMP on the router (System Maintenance > SNMP) and set a read community.
2. In Home Assistant, go to **Settings > Devices & services > Add integration > DrayTek**
   and enter the router's host, community and port.

[![Open your Home Assistant instance and start setting up DrayTek.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=draytek)

## Entities

| Entity | Source |
| --- | --- |
| CPU load, memory usage | `hrProcessorLoad`, DrayTek MIB `7367.3.7` |
| Last restart | `sysUpTime` |
| DSL downstream/upstream rate | VDSL2-LINE-MIB `xdsl2ChStatusActDataRate` |
| DSL attainable rate, SNR margin, attenuation | ADSL-LINE-MIB |
| Per-interface received/sent bytes, receive/transmit rate, link | IF-MIB `ifTable` |

Interface entities are only enabled by default for interfaces that are
administratively up. The router only exposes 32-bit counters, so the
byte counters wrap at 4 GiB; they use the `total_increasing` state class,
which keeps long-term statistics correct across wraps.
