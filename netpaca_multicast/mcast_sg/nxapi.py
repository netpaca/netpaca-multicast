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

# -----------------------------------------------------------------------------
# System Imports
# -----------------------------------------------------------------------------

from typing import Optional, List
import re

# -----------------------------------------------------------------------------
# Public Imports
# -----------------------------------------------------------------------------

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

    metrics = [
        _make_metric(timestamp, xml_sg_rec)
        for xml_sg_rec in res[0].output.xpath(".//ROW_one_route")
    ]

    return metrics


# -----------------------------------------------------------------------------
#
#                            PRIVATE FUNCTIONS
#
# -----------------------------------------------------------------------------

_re_extracto_S_G = re.compile(r"\((?P<S>.+)/\d+, (?P<G>.+)/\d+\)").match


def _make_metric(ts, xml_sg_rec) -> Metric:
    mo = _re_extracto_S_G(xml_sg_rec.findtext("mcast-addrs"))

    status = _form_sg_status(xml_sg_rec)
    mcast_s, mcast_g = mo.group("S"), mo.group("G")
    oif_list = xml_sg_rec.xpath("TABLE_oif/ROW_oif/oif-name/text()")

    return mcast_sg.McastSGStatus(
        tags={
            "S": mcast_s,
            "G": mcast_g,
            "rpf_if_name": xml_sg_rec.findtext("route-iif"),
            "oif_count": str(len(oif_list)),
            "oif_list": ",".join(oif_list),
        },
        ts=ts,
        value=status,
    )


def _form_sg_status(xml_sg_rec) -> int:

    if xml_sg_rec.findtext("pending") == "true":
        return 2

    # if the rate of the counters are 0, then this is an inactive flow
    return 1 if xml_sg_rec.findtext("stats-rate-buf").startswith("0.000 ") else 0
