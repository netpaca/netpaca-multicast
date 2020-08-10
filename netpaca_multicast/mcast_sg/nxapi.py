#  Copyright (C) 2020  Jeremy Schulman
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
This file contains the multicast S,G health collector for Cisco NX-OS
via NXAPI.  The flags must be collected using a CLI command that
is not supported by NXAPI in the v7.0 release.

References
----------
Cisco CLI Flags:

    device# show forwarding distribution multicast route
    Legend:
       C = Control Route
       D = Drop Route
       G = Local Group (directly connected receivers)
       O = Drop on RPF Fail
       P = Punt to supervisor
       L = SRC behind L3
       d = Decap Route

"""
# -----------------------------------------------------------------------------
# System Imports
# -----------------------------------------------------------------------------

from typing import Optional, List
import re

# -----------------------------------------------------------------------------
# Public Imports
# -----------------------------------------------------------------------------

from ttp import ttp
from netpaca import Metric, MetricTimestamp
from netpaca.collectors.executor import CollectorExecutor
from netpaca.drivers.nxapi import Device

# -----------------------------------------------------------------------------
# Private Imports
# -----------------------------------------------------------------------------

from netpaca_multicast import mcast_sg

# -----------------------------------------------------------------------------
# Exports (none)
# -----------------------------------------------------------------------------

__all__ = []

# -----------------------------------------------------------------------------
#
#                                 CODE BEGINS
#
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
#
#                     Register Cisco NX-OS Device to Colletor Type
#
# -----------------------------------------------------------------------------


@mcast_sg.register
async def start(
    device: Device, executor: CollectorExecutor, spec: mcast_sg,
):
    """
    The IF DOM collector start coroutine for Arista EOS devices.  The purpose of this
    coroutine is to start the collector task.  Nothing fancy.

    Parameters
    ----------
    device:
        The device driver instance for the Arista device

    executor:
        The netmon executor that is used to start one or more collector tasks.
        In this instance, there is only one collector task started per device.

    spec:
        The collector model instance that contains information about the
        collector; for example the collector configuration values.
    """
    device.log.info(f"{device.name}: Starting NX-OS NXAPI MC S,G flow status collector")

    # TODO: hardcoding API version for N9K v7.0 release.  Need to find a better
    #       way for accounting for these differences.
    device.nxapi.api.API_VER = "1.0"

    executor.start(
        # required args
        spec=spec,
        coro=get_mcast_flow_metrics,
        device=device,
        # kwargs to collector coroutine:
        config=spec.config,
    )


async def get_mcast_flow_metrics(
    device: Device,
    timestamp: MetricTimestamp,
    config: mcast_sg.MCastSGCollectorConfig,  # noqa - not used (yet)
) -> Optional[List[Metric]]:
    """
    This coroutine will be executed as a asyncio Task on a periodic basis, the
    purpose is to collect data from the device and return the list of Interface
    DOM metrics.

    Parameters
    ----------
    device:
        The Arisa EOS device driver instance for this device.

    timestamp: MetricTimestamp
        The timestamp now in milliseconds

    config:
        The collector configuration options

    Returns
    -------
    Option list of Metic items.
    """
    res = await device.nxapi.exec(["show ip mroute source-tree detail"])

    if not res[0].ok:
        # TODO: add reason for failure from response body to log message
        device.log.error(
            f"{device.name}: failed to collect MROUTE information, skipping."
        )
        return None

    xml_mroute_sgtree = res[0].output

    # the above CLI command does not provide the flags we need to check, so we
    # need to run another command:

    res = await device.nxapi.exec(
        [" show forwarding distribution multicast route"], ofmt="text"
    )
    if not res[0].ok:
        device.log.error(f"{device.name}: failed to collect FDMR")
        return None

    fdmr_data = _parse_show_fdmr(res[0].output)

    metrics = [
        _make_metric(timestamp, xml_sg_rec, fdmr_data)
        for xml_sg_rec in xml_mroute_sgtree.xpath(".//ROW_one_route")
    ]

    return metrics


# -----------------------------------------------------------------------------
#
#                            PRIVATE FUNCTIONS
#
# -----------------------------------------------------------------------------

_re_extracto_S_G = re.compile(r"\((?P<S>.+)/\d+, (?P<G>.+)/\d+\)").match


def _make_metric(ts, xml_sg_rec, fdmr_data) -> Metric:
    mo = _re_extracto_S_G(xml_sg_rec.findtext("mcast-addrs"))

    mcast_s, mcast_g = mo.group("S"), mo.group("G")
    mcast_flags = fdmr_data.get((mcast_s, mcast_g), "")
    status = _form_sg_status(xml_sg_rec, mcast_flags)
    oif_list = xml_sg_rec.xpath("TABLE_oif/ROW_oif/oif-name/text()")

    return mcast_sg.McastSGStatus(
        tags={
            "S": mcast_s,
            "G": mcast_g,
            "rpf_if_name": xml_sg_rec.findtext("route-iif"),
            "flags": mcast_flags,
            "oif_count": str(len(oif_list)),
            "oif_list": ",".join(oif_list),
        },
        ts=ts,
        value=status,
    )


def _form_sg_status(xml_sg_rec, flags) -> int:

    if xml_sg_rec.findtext("pending") == "true":
        return 2

    if "O" in flags or "D" in flags:
        return 2

    # if the rate of the counters are 0, then this is an inactive flow
    return 1 if xml_sg_rec.findtext("stats-rate-buf").startswith("0.000 ") else 0


# -----------------------------------------------------------------------------
#                     CLI Text Parser (TTP) for FDMR commmand
# -----------------------------------------------------------------------------

_CLI_FDMR_TEMPLATE = """
<group name="mc_flows">
  ({{ source_ipaddr | IP | _start_ }}/32, {{ group_ipaddr | IP }}/32), RPF Interface: {{ ignore }}, flags: {{ flags }}
</group>
"""


def _parse_show_fdmr(cli_text):
    parser = ttp(data=cli_text, template=_CLI_FDMR_TEMPLATE, log_level="none")

    parser.parse()
    if not (found := parser.result()[0]):
        return {}

    return {
        (rec["source_ipaddr"], rec["group_ipaddr"]): rec["flags"]
        for rec in found[0]["mc_flows"]
    }
