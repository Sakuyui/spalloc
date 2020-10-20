# Copyright (c) 2017-2020 The University of Manchester
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from six import add_metaclass
from spinn_utilities.abstract_base import AbstractBase, abstractmethod

SYNAPSE_EXPANDER_APLX = "synapse_expander.aplx"


@add_metaclass(AbstractBase)
class AbstractSynapseExpandable(object):
    """ Indicates a class (most likely a MachineVertex) that has may need to
        run the SYNAPSE_EXPANDER aplx

        Cores that do not use the synapse_manager should not implement this
        api even though their app vertex may hold a synapse_manager

        Note: This is NOT implemented by the DelayExtensionMachineVertex
        which needs a different expander aplx
    """

    __slots__ = ()

    @abstractmethod
    def gen_on_machine(self):

        """
        True if the synapses of a the slice of this vertex should be generated
        on the machine.

        Note: The typical implementation for this method will be to ask the
        app_vertex's synapse_manager
        """

    @abstractmethod
    def read_generated_connection_holders(self, transceiver, placement):
        """ Fill in the connection holders


        Note: The typical implementation for this method will be to ask the
        app_vertex's synapse_manager

        :param Transceiver transceiver: How the data is to be read
        :param Placement placement: Where the data is on the machine
        """
        self.__synapse_manager.read_generated_connection_holders(
            transceiver, placement)
