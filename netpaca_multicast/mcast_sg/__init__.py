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
This file contains the network monitoring collector for Multicast S,G health
check.
"""

from typing import Optional
from pydantic.dataclasses import dataclass
from pydantic import conint, Field

from nwkatk_netmon import Metric
from nwkatk_netmon.collectors import CollectorType, CollectorConfigModel
from nwkatk_netmon.config_model import CollectorModel  # noqa

__all__ = [
    'MCastSGCollectorConfig'
]

# -----------------------------------------------------------------------------
#
#                              Collector Config
# -----------------------------------------------------------------------------
# Define the collector configuraiton options that the User can set in their
# configuration file.
# -----------------------------------------------------------------------------


class MCastSGCollectorConfig(CollectorConfigModel):
    """ no additional config options at this time"""
    pass

# -----------------------------------------------------------------------------
#
#                              Metrics
#
# -----------------------------------------------------------------------------
# This section defines the Metric types supported by the IF DOM collector
# -----------------------------------------------------------------------------


# the status values will be encoded in the metric to mean
# 0 = S,G flow active (has OIF),
# 1 = S,G flow not active
# 2 = S,G flow not not available

_McastSGStatusValue = conint(ge=0, le=2)


@dataclass
class McastSGStatus(Metric):
    value: _McastSGStatusValue
    name: str = "mcast_sg_status"


# -----------------------------------------------------------------------------
#
#                              Collector Definition
#
# -----------------------------------------------------------------------------


class McastSGCollector(CollectorType):
    """
    This class defines the Interface DOM Collector specification.  This class is
    "registered" with the "nwka_netmon.collectors" entry_point group via the
    `setup.py` file.  As a result of this registration, a User of the
    nwka-netmon tool can setup their configuration file with the "use"
    statement.

    Examples (Configuration File)
    -----------------------------
    [collectors.ifdom]
        use = "nwka_netmon.collectors:ifdom"

    """

    name = "mcast-sg"
    description = """
Used to collect the state of multicast (S,G) flows
"""

    metrics = [
        McastSGStatus
    ]


# create an "alias" variable so that the device specific collector packages
# can register their start functions.

register = McastSGCollector.start.register

