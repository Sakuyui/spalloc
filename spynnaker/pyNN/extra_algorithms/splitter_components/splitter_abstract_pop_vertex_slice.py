# Copyright (c) 2020-2021 The University of Manchester
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
import os

from pacman.executor.injection_decorator import inject_items
from pacman.model.resources import ResourceContainer, ConstantSDRAM, \
    DTCMResource, CPUCyclesPerTickResource
from spinn_front_end_common.interface.partitioner_splitters.\
    abstract_splitters.abstract_splitter_slice import AbstractSplitterSlice
from spinn_front_end_common.interface.profiling import profile_utils
from spinn_front_end_common.utilities.constants import \
    SYSTEM_BYTES_REQUIREMENT, BYTES_PER_WORD
from spinn_utilities.overrides import overrides
from spynnaker.pyNN.exceptions import SpynnakerSplitterConfigurationException
from spynnaker.pyNN.extra_algorithms.splitter_components import (
    AbstractSpynnakerSplitterDelay)
from spynnaker.pyNN.models.neuron import (
    AbstractPopulationVertex, PopulationMachineVertex)
from spynnaker.pyNN.utilities import bit_field_utilities


class SplitterAbstractPopulationVertexSlice(
        AbstractSplitterSlice, AbstractSpynnakerSplitterDelay):
    """ handles the splitting of the AbstractPopulationVertex via slice logic.
    """

    __slots__ = []

    _NEURON_BASE_N_CPU_CYCLES_PER_NEURON = 22
    _NEURON_BASE_N_CPU_CYCLES = 10
    _C_MAIN_BASE_N_CPU_CYCLES = 0

    # TODO: Make sure these values are correct (particularly CPU cycles)
    _C_MAIN_BASE_DTCM_USAGE_IN_BYTES = 3 * BYTES_PER_WORD
    _C_MAIN_BASE_SDRAM_USAGE_IN_BYTES = 18 * BYTES_PER_WORD

    # TODO: Make sure these values are correct (particularly CPU cycles)
    _NEURON_BASE_DTCM_USAGE_IN_BYTES = 9 * BYTES_PER_WORD
    _NEURON_BASE_SDRAM_USAGE_IN_BYTES = 3 * BYTES_PER_WORD

    SPLITTER_NAME = "SplitterAbstractPopulationVertexSlice"

    INVALID_POP_ERROR_MESSAGE = (
        "The vertex {} cannot be supported by the "
        "SplitterAbstractPopulationVertexSlice as"
        " the only vertex supported by this splitter is a "
        "AbstractPopulationVertex. Please use the correct splitter for "
        "your vertex and try again.")

    def __init__(self):
        AbstractSplitterSlice.__init__(self, self.SPLITTER_NAME)
        AbstractSpynnakerSplitterDelay.__init__(self)

    @overrides(AbstractSplitterSlice.set_governed_app_vertex)
    def set_governed_app_vertex(self, app_vertex):
        AbstractSplitterSlice.set_governed_app_vertex(self, app_vertex)
        if not isinstance(app_vertex, AbstractPopulationVertex):
            raise SpynnakerSplitterConfigurationException(
                self.INVALID_POP_ERROR_MESSAGE.format(app_vertex))

    @overrides(AbstractSplitterSlice.create_machine_vertex)
    def create_machine_vertex(
            self, vertex_slice, resources, label, remaining_constraints):
        return PopulationMachineVertex(
            resources,
            self._governed_app_vertex.neuron_recorder.recorded_ids_by_slice(
                vertex_slice),
            label, remaining_constraints, self._governed_app_vertex,
            vertex_slice, self.__get_binary_file_name())

    @inject_items({
        "graph": "MemoryApplicationGraph",
        "machine_time_step": "MachineTimeStep"
    })
    @overrides(AbstractSplitterSlice.get_resources_used_by_atoms,
               additional_arguments={"graph", "machine_time_step"})
    def get_resources_used_by_atoms(
            self, vertex_slice, graph, machine_time_step):
        """ ger res for a APV

        :param vertex_slice: the slice
        :param graph: app graph
        :param machine_time_step: machine time step
        :rtype: ResourceContainer
        """
        variable_sdram = self.get_variable_sdram(vertex_slice)
        constant_sdram = self.constant_sdram(
            vertex_slice, graph, machine_time_step)

        # set resources required from this object
        container = ResourceContainer(
            sdram=variable_sdram + constant_sdram,
            dtcm=self.dtcm_cost(vertex_slice),
            cpu_cycles=self.cpu_cost(vertex_slice))

        # return the total resources.
        return container

    def get_variable_sdram(self, vertex_slice):
        return self._governed_app_vertex.neuron_recorder.\
            get_variable_sdram_usage(vertex_slice)

    def constant_sdram(self, vertex_slice,  graph, machine_time_step):
        sdram_requirement = (
            SYSTEM_BYTES_REQUIREMENT +
            self._governed_app_vertex.sdram_usage_for_neuron_params(
                vertex_slice) +
            self._governed_app_vertex.neuron_recorder.get_static_sdram_usage(
                vertex_slice) +
            PopulationMachineVertex.get_provenance_data_size(
                len(PopulationMachineVertex.EXTRA_PROVENANCE_DATA_ENTRIES)) +
            self._governed_app_vertex.synapse_manager.get_sdram_usage_in_bytes(
                vertex_slice, machine_time_step, graph,
                self._governed_app_vertex) +
            profile_utils.get_profile_region_size(
                self._governed_app_vertex.n_profile_samples) +
            bit_field_utilities.get_estimated_sdram_for_bit_field_region(
                graph, self._governed_app_vertex) +
            bit_field_utilities.get_estimated_sdram_for_key_region(
                graph, self._governed_app_vertex) +
            bit_field_utilities.exact_sdram_for_bit_field_builder_region())
        return ConstantSDRAM(sdram_requirement)

    def dtcm_cost(self, vertex_slice):
        return DTCMResource(
            self._governed_app_vertex.neuron_impl.get_dtcm_usage_in_bytes(
                vertex_slice.n_atoms) +
            self._governed_app_vertex.neuron_recorder.get_dtcm_usage_in_bytes(
                vertex_slice) +
            self._governed_app_vertex.synapse_manager.
            get_dtcm_usage_in_bytes())

    def cpu_cost(self, vertex_slice):
        return CPUCyclesPerTickResource(
            self._NEURON_BASE_N_CPU_CYCLES + self._C_MAIN_BASE_N_CPU_CYCLES +
            (self._NEURON_BASE_N_CPU_CYCLES_PER_NEURON *
             vertex_slice.n_atoms) +
            self._governed_app_vertex.neuron_recorder.get_n_cpu_cycles(
                vertex_slice.n_atoms) +
            self._governed_app_vertex.neuron_impl.get_n_cpu_cycles(
                vertex_slice.n_atoms) +
            self._governed_app_vertex.synapse_manager.get_n_cpu_cycles())

    def __get_binary_file_name(self):

        # Split binary name into title and extension
        binary_title, binary_extension = os.path.splitext(
            self._governed_app_vertex.neuron_impl.binary_name)

        # Reunite title and extension and return
        return (
            binary_title +
            self._governed_app_vertex.synapse_manager.
            vertex_executable_suffix + binary_extension)
