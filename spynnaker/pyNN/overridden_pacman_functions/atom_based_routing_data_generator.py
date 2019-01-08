import math

from spinn_front_end_common.interface.interface_functions import \
    ChipIOBufExtractor
from spinn_front_end_common.utilities.exceptions import SpinnFrontEndException

from spinn_utilities.progress_bar import ProgressBar

from spinnman.model import ExecutableTargets
from spinnman.model.enums import CPUState

from spynnaker.pyNN.models.abstract_models.\
    abstract_uses_population_table_and_synapses import \
    AbstractUsesPopulationTableAndSynapses

import struct
import logging

from spynnaker.pyNN.utilities import constants

logger = logging.getLogger(__name__)


class SpynnakerAtomBasedRoutingDataGenerator(object):
    """ Executes bitfield and routing table entries for atom based routing
    """

    __slots__ = ()

    # the sdram tag being used here
    _SDRAM_TAG = 2

    # flag which states that the binary finished cleanly.
    _SUCCESS = 0

    # the number of bytes needed to read the user2 register
    _USER_2_BYTES = 4

    # master pop, synaptic matrix, bitfield base addresses
    _N_ELEMENTS_PER_REGION_ELEMENT = 5

    # structs for performance requirements.
    _ONE_WORDS = struct.Struct("<I")
    _FOUR_WORDS = struct.Struct("<IIII")

    # binary name
    _BIT_FIELD_EXPANDER_APLX = "bit_field_expander.aplx"

    def __call__(
            self, placements, app_graph, executable_finder,
            provenance_file_path, machine, transceiver, graph_mapper):
        """ loads and runs the bit field generator on chip

        :param placements: placements
        :param app_graph: the app graph
        :param executable_finder: the executable finder
        :param provenance_file_path: the path to where provenance data items\
                                     is written
        :param machine: the SpiNNMachine instance
        :param transceiver: the SpiNNMan instance
        :param graph_mapper: mapper between application an machine graphs.
        :rtype: None
        """

        # progress bar
        progress = ProgressBar(
            len(app_graph.vertices) + 2,
            "Running bitfield generation on chip")

        # get data
        data_address, expander_cores = self._calculate_core_data(
            app_graph, graph_mapper, transceiver, placements, machine,
            progress, executable_finder)

        # load data
        bit_field_app_id = self._allocate_sdram_and_fill_in(
            data_address, transceiver)
        progress.update(1)

        # run app
        self._run_app(
            expander_cores, bit_field_app_id, transceiver,
            provenance_file_path, executable_finder)

        # read in bit fields for debugging purposes
        self._read_back_bit_fields(
            app_graph, graph_mapper, transceiver, placements, data_address)

        # update progress bar
        progress.end()

    def _read_back_bit_fields(
            self, app_graph, graph_mapper, transceiver, placements,
            data_address):
        for app_vertex in app_graph.vertices:
            if isinstance(app_vertex, AbstractUsesPopulationTableAndSynapses):
                machine_verts = graph_mapper.get_machine_vertices(app_vertex)
                for machine_vertex in machine_verts:
                    placement = \
                        placements.get_placement_of_vertex(machine_vertex)
                    bit_field_address = app_vertex.bit_field_base_address(
                        transceiver, placement)
                    n_bit_field_entries = struct.unpack(
                        "<I", transceiver.read_memory(
                            placement.x, placement.y, bit_field_address, 4))[0]
                    reading_address = bit_field_address + 4
                    for bit_field_index in range(0, n_bit_field_entries):
                        master_pop_key = struct.unpack(
                            "<I", transceiver.read_memory(
                                placement.x, placement.y, reading_address,
                                4))[0]
                        reading_address += 4
                        n_words_to_read = struct.unpack(
                            "<I", transceiver.read_memory(
                                placement.x, placement.y, reading_address,
                                4))[0]
                        reading_address += 4
                        bit_field = struct.unpack(
                            "<{}I".format(n_words_to_read),
                            transceiver.read_memory(
                                placement.x, placement.y, reading_address,
                                n_words_to_read *
                                constants.WORD_TO_BYTE_MULTIPLIER))
                        reading_address += (
                            n_words_to_read * constants.WORD_TO_BYTE_MULTIPLIER)
                        n_neurons = n_words_to_read * 32
                        for neuron_id in range(0, n_neurons):
                            print \
                                "for key {} neuron id {} has bit {} set".format(
                                    master_pop_key, neuron_id,
                                    self._bit_for_neuron_id(bit_field,
                                                            neuron_id))

    @staticmethod
    def _bit_for_neuron_id(bit_field, neuron_id):
        word_id = int(math.floor(neuron_id // 32))
        bit_in_word = neuron_id % 32
        flag = (bit_field[word_id] >> bit_in_word) & 1
        return flag

    def _calculate_core_data(
            self, app_graph, graph_mapper, transceiver, placements, machine,
            progress, executable_finder):
        """ gets the data needed for the bit field expander for the machine

        :param app_graph: app graph
        :param graph_mapper: graph mapper between app graph and machine graph
        :param transceiver: SpiNNMan instance
        :param placements: placements
        :param machine: SpiNNMachine instance
        :param progress: progress bar
        :param executable_finder: where to find the executable
        :return: data and expander cores
        """

        # storage for the data addresses needed for the bitfield
        data_address = dict()

        # cores to place bitfield expander
        expander_cores = ExecutableTargets()

        # bit field expander executable file path
        bit_field_expander_path = executable_finder.get_executable_path(
            self._BIT_FIELD_EXPANDER_APLX)

        # locate verts which can have a synaptic matrix to begin with
        for app_vertex in progress.over(app_graph.vertices, False):
            if isinstance(app_vertex, AbstractUsesPopulationTableAndSynapses):
                machine_verts = graph_mapper.get_machine_vertices(app_vertex)
                for machine_vertex in machine_verts:
                    placement = \
                        placements.get_placement_of_vertex(machine_vertex)

                    # check if the chip being considered already.
                    if (placement.x, placement.y) not in data_address:
                        data_address[(placement.x, placement.y)] = list()
                        expander_cores.add_processor(
                            bit_field_expander_path, placement.x, placement.y,
                            machine.get_chip_at(placement.x, placement.y).
                            get_first_none_monitor_processor().processor_id)

                    # add the extra data
                    data_address[(placement.x, placement.y)].append(
                        (app_vertex.master_pop_table_base_address(
                            transceiver, placement),
                         app_vertex.synaptic_matrix_base_address(
                             transceiver, placement),
                         app_vertex.bit_field_base_address(
                             transceiver, placement),
                         app_vertex.direct_matrix_base_address(
                            transceiver, placement)))

                    print "placement {}:{}:{} \n\n master table {:8x}, " \
                          "\n synaptic_matrix {:8x}, \n bitfield {:8x} , " \
                          "\n direct matrix {:8x}".format(
                        placement.x, placement.y, placement.p,
                        app_vertex.master_pop_table_base_address(
                            transceiver, placement),
                        app_vertex.synaptic_matrix_base_address(
                            transceiver, placement),
                        app_vertex.bit_field_base_address(
                            transceiver, placement),
                        app_vertex.direct_matrix_base_address(
                            transceiver, placement))

        return data_address, expander_cores

    def _allocate_sdram_and_fill_in(self, data_address, transceiver):
        """ loads the app data for the bitfield generation

        :param data_address: the data base addresses for the cores in question
        :param transceiver: SpiNNMan instance
        :return: the bitfield app id
        """

        # new app id for the bitfield expander
        bit_field_generator_app_id = transceiver.app_id_tracker.get_new_id()
        for (chip_x, chip_y) in data_address.keys():
            regions = data_address[(chip_x, chip_y)]
            base_address = transceiver.malloc_sdram(
                chip_x, chip_y,
                (len(regions) * self._N_ELEMENTS_PER_REGION_ELEMENT *
                 constants.WORD_TO_BYTE_MULTIPLIER),
                bit_field_generator_app_id, self._SDRAM_TAG)
            transceiver.write_memory(
                chip_x, chip_y, base_address, self._generate_data(regions))
        return bit_field_generator_app_id

    def _generate_data(self, regions):
        """ generates the chips worth of data for regions to bitfield

        :param regions: list of tuples of master pop, synaptic matrix
        :return: data in byte array format for a given chip's bit field \
                 generator
        """
        data = b''
        data += self._ONE_WORDS.pack(len(regions))
        for (master_pop_base_address, synaptic_matrix_base_address,
             bit_field_base_address, direct_matrix_base_address) in regions:
            data += self._FOUR_WORDS.pack(
                master_pop_base_address, synaptic_matrix_base_address,
                bit_field_base_address, direct_matrix_base_address)
        return bytearray(data)

    def _run_app(
            self, executable_cores, bit_field_app_id, transceiver,
            provenance_file_path, executable_finder):
        """ executes the app

        :param executable_cores: the cores to run the bit field expander on
        :param bit_field_app_id: the appid for the bit field expander
        :param transceiver: the SpiNNMan instance
        :param provenance_file_path: the path for where provenance data is\
        stored
        :param executable_finder: finder for executable paths
        :rtype: None
        """

        # load the bitfield expander executable
        transceiver.execute_application(executable_cores, bit_field_app_id)
        # Wait for the executable to finish
        succeeded = False
        try:
            transceiver.wait_for_cores_to_be_in_state(
                executable_cores.all_core_subsets, bit_field_app_id,
                [CPUState.FINISHED])
            succeeded = True
        finally:
            # get the debug data
            if not succeeded:
                self._handle_failure(
                    executable_cores, transceiver, provenance_file_path,
                    bit_field_app_id, executable_finder)

        # Check if any cores have not completed successfully
        self._check_for_success(
            executable_cores, transceiver, provenance_file_path,
            bit_field_app_id, executable_finder)

        iobuf_reader = ChipIOBufExtractor()
        iobuf_reader(
            transceiver, executable_cores, executable_finder,
            provenance_file_path)


        # stop anything that's associated with the compressor binary
        transceiver.stop_application(bit_field_app_id)
        transceiver.app_id_tracker.free_id(bit_field_app_id)

    def _check_for_success(
            self, executable_targets, transceiver, provenance_file_path,
            compressor_app_id, executable_finder):
        """ Goes through the cores checking for cores that have failed to\
            expand the bitfield to the core

        :param executable_targets: cores to load bitfield on
        :param transceiver: SpiNNMan instance
        :param provenance_file_path: path to provenance folder
        :param compressor_app_id: the app id for the compressor c code
        :param executable_finder: exeuctable path finder
        :rtype: None
        """

        for core_subset in executable_targets.all_core_subsets:
            x = core_subset.x
            y = core_subset.y
            for p in core_subset.processor_ids:
                # Read the result from USER0 register
                user_2_base_address = \
                    transceiver.get_user_2_register_address_from_core(p)
                result = struct.unpack(
                    "<I", transceiver.read_memory(
                        x, y, user_2_base_address, self._USER_2_BYTES))[0]

                # The result is 0 if success, otherwise failure
                if result != self._SUCCESS:
                    self._handle_failure(
                        executable_targets, transceiver, provenance_file_path,
                        compressor_app_id, executable_finder)

                    raise SpinnFrontEndException(
                        "The bit field expander on {}, {} failed to complete"
                        .format(x, y))

    @staticmethod
    def _handle_failure(
            executable_targets, transceiver, provenance_file_path,
            compressor_app_id, executable_finder):
        """handles the state where some cores have failed.

        :param executable_targets: cores which are running the bitfield \
        expander
        :param transceiver: SpiNNMan instance
        :param provenance_file_path: provenance file path
        :param executable_finder: executable finder
        :rtype: None
        """
        logger.info("bit field expander has failed")
        iobuf_extractor = ChipIOBufExtractor()
        io_errors, io_warnings = iobuf_extractor(
            transceiver, executable_targets, executable_finder,
            provenance_file_path)
        for warning in io_warnings:
            logger.warning(warning)
        for error in io_errors:
            logger.error(error)
        transceiver.stop_application(compressor_app_id)
        transceiver.app_id_tracker.free_id(compressor_app_id)
