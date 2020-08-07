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
#

"""
This file contains the Multicast S,G flow status collector for
Arista EOS.

References
----------
Flags:
    A - Learned via Anycast RP Router
    B - Learned via Border Router
    C - Learned from a DR via a register
    D - Joining SPT due to protocol
    E - Entry forwarding on the RPT
    H - Joining SPT due to policy
    I - SG Include Join alert rcvd
    J - Joining to the SPT
    K - Keepalive timer not running
    L - Source is attached
    M - Learned via MSDP
    N - May notify MSDP
    P - (*,G) Programmed in hardware
    R - RPT bit is set
    S - SPT bit is set
    T - Switching Incoming Interface
    W - Wildcard entry
    X - External component interest
    Z - Entry marked for deletion
"""

# -----------------------------------------------------------------------------
# System Imports
# -----------------------------------------------------------------------------

from typing import Optional, List, Tuple

# -----------------------------------------------------------------------------
# Public Imports
# -----------------------------------------------------------------------------

from nwkatk_netmon import Metric, MetricTimestamp
from nwkatk_netmon.collectors.executor import CollectorExecutor
from nwkatk_netmon.drivers.eapi import Device

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
#                     Register Arista Device to Colletor Type
#
# -----------------------------------------------------------------------------


@mcast_sg.register
async def start(
    device: Device, executor: CollectorExecutor, spec: mcast_sg.CollectorModel,
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
    device.log.info(f"{device.name}: Starting Arista EOS MC S,G flow status collector")

    executor.start(
        # required args
        spec=spec,
        coro=get_mcast_flow_metrics,
        device=device,
        # kwargs to collector coroutine:
        config=spec.config,
    )


# -----------------------------------------------------------------------------
#
#                             Collector Coroutine
#
# -----------------------------------------------------------------------------


async def get_mcast_flow_metrics(
    device: Device, timestamp: MetricTimestamp,
    config: mcast_sg.MCastSGCollectorConfig             # noqa - not used (yet)
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

    # Execute the required "show" commands to colelct the interface information
    # needed to produce the Metrics

    cli_res = await device.eapi.exec(['show ip mroute'])
    cli_sh_ip_mroute = cli_res[0]

    if not cli_sh_ip_mroute.ok:
        device.log.error(
            f"{device.name}: failed to collect MROUTE information: {cli_sh_ip_mroute.output}, skipping."
        )
        return

    metrics = [
        mcast_sg.McastSGStatus(
            ts=timestamp, value=_mcast_sg_status(mcast_flow=flow_data),
            tags={
                'S': mcast_S,
                'G': mcast_G,
                'flags': flow_data['routeFlags'],
                'rpf_if_name': flow_data['rpfInterface'],
                'oif_list': ','.join(flow_data['oifList'])
            }
        )
        for mcast_S, mcast_G, flow_data in _find_mcast_sg_flows(cli_sh_ip_mroute.output)
    ]

    return metrics


# -----------------------------------------------------------------------------
#
#                            PRIVATE FUNCTIONS
#
# -----------------------------------------------------------------------------

def _mcast_sg_status(mcast_flow):
    flags = mcast_flow['routeFlags']

    if flags.startswith('S'):
        return 0 if mcast_flow['oifList'] else 1

    if flags.startswith('J'):
        return 2

    return 1


def _find_mcast_sg_flows(cli_data) -> Tuple[str, str, dict]:
    """
    This generator will yield a tuple of S,G,data for each multicast.

    Parameters
    ----------
    cli_data: dict
        The dict result from the CLI show command

    Yields
    ------
    Tuple where first item is the multicast source (S) ipaddress, then the
    multicast group (G) ipaddress, then the dataset associated with the S,G flow
    in CLI dict form.
    """
    all_mc_gr_data = cli_data['groups']
    for mc_g_ip, mc_g_data in all_mc_gr_data.items():
        for mc_s_ip, mc_s_data in mc_g_data['groupSources'].items():
            if mc_s_ip != '0.0.0.0':
                yield mc_s_ip, mc_g_ip, mc_s_data
