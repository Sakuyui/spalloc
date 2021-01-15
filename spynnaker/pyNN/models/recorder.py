# Copyright (c) 2017-2019 The University of Manchester
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
from datetime import datetime
import logging
import numpy
from six import string_types
from six.moves import xrange
import neo
import quantities
from spinn_utilities import logger_utils
from spinn_utilities.log import FormatAdapter
from spinn_utilities.ordered_set import OrderedSet
from spinn_front_end_common.utilities.exceptions import ConfigurationException
from spinn_front_end_common.utilities.globals_variables import get_simulator
from spynnaker.pyNN.models.common import (
    AbstractSpikeRecordable, AbstractNeuronRecordable)
from spynnaker.pyNN.utilities.constants import (
    SPIKES, MEMBRANE_POTENTIAL, GSYN_EXCIT, GSYN_INHIB)
from spynnaker.pyNN.exceptions import InvalidParameterType
from spynnaker.pyNN.utilities.data_cache import DataCache

logger = FormatAdapter(logging.getLogger(__name__))
_DEFAULT_UNITS = {
    SPIKES: "spikes",
    MEMBRANE_POTENTIAL: "mV",
    GSYN_EXCIT: "uS",
    GSYN_INHIB: "uS"}


class RecordingCommon(object):
    """ Object to hold recording behaviour.
    """
    # pylint: disable=protected-access

    # DO NOT DEFINE SLOTS! Multiple inheritance problems otherwise.
    # __slots__ = [
    #     "_data_cache",
    #     "__population",
    #     "_recording_start_time",
    #     "__write_to_files_indicators"]

    def __init__(self, population):
        """
        :param PyNNPopulationCommon population: the population to record for
        """
        self.__population = population

        # file flags, allows separate files for the recorded variables
        self.__write_to_files_indicators = {
            'spikes': None,
            'gsyn_exc': None,
            'gsyn_inh': None,
            'v': None}
        self._recording_start_time = get_simulator().t
        self._data_cache = {}

    @property
    def _population(self):
        return self.__population

    @property
    def _write_to_files_indicators(self):
        return self.__write_to_files_indicators

    def _record(self, variable, sampling_interval=None, to_file=None,
                indexes=None):
        """ Tell the vertex to record data.

        :param str variable: the variable to record, valued variables to\
            record are: 'gsyn_exc', 'gsyn_inh', 'v', 'spikes'
        :param int sampling_interval: the interval to record them
        :param indexes: List of indexes to record or None for all
        :type indexes: list(int) or None
        :return: None
        """

        get_simulator().verify_not_running()
        # tell vertex its recording
        if variable == "spikes":
            if not isinstance(self.__population._vertex,
                              AbstractSpikeRecordable):
                raise Exception("This population does not support the "
                                "recording of spikes!")
            self.__population._vertex.set_recording_spikes(
                sampling_interval=sampling_interval, indexes=indexes)
        elif variable == "all":
            raise Exception("Illegal call with all")
        else:
            if not isinstance(self.__population._vertex,
                              AbstractNeuronRecordable):
                raise Exception("This population does not support the "
                                "recording of {}!".format(variable))
            self.__population._vertex.set_recording(
                variable, sampling_interval=sampling_interval, indexes=indexes)

        # update file writer
        self.__write_to_files_indicators[variable] = to_file

        if variable == "gsyn_exc":
            if not self.__population._vertex.conductance_based:
                logger_utils.warn_once(
                    logger, "You are trying to record the excitatory "
                    "conductance from a model which does not use conductance "
                    "input. You will receive current measurements instead.")
        elif variable == "gsyn_inh":
            if not self.__population._vertex.conductance_based:
                logger_utils.warn_once(
                    logger, "You are trying to record the inhibitory "
                    "conductance from a model which does not use conductance "
                    "input. You will receive current measurements instead.")

    def _get_recorded_pynn7(self, variable):
        """ Get recorded data in PyNN 0.7 format. Must not be spikes.
        """
        (data, ids, sampling_interval) = self._get_recorded_matrix(variable)
        n_machine_time_steps = len(data)
        n_neurons = len(ids)
        column_length = n_machine_time_steps * n_neurons
        times = [i * sampling_interval
                 for i in xrange(0, n_machine_time_steps)]
        return numpy.column_stack((
                numpy.repeat(ids, n_machine_time_steps, 0),
                numpy.tile(times, n_neurons),
                numpy.transpose(data).reshape(column_length)))

    def _get_recorded_matrix(self, variable):
        """ Perform safety checks and get the recorded data from the vertex\
            in matrix format.

        :param str variable:
            the variable name to read. supported variable names are:
            'gsyn_exc', 'gsyn_inh', 'v'
        :return: data, indexes, sampling_interval
        :rtype: tuple(~numpy.ndarray, list(int), float)
        """
        data = None
        sim = get_simulator()

        get_simulator().verify_not_running()

        # check that we're in a state to get voltages
        if not isinstance(
                self.__population._vertex, AbstractNeuronRecordable):
            raise ConfigurationException(
                "This population has not got the capability to record {}"
                .format(variable))

        if not self.__population._vertex.is_recording(variable):
            raise ConfigurationException(
                "This population has not been set to record {}"
                .format(variable))

        if not sim.has_ran:
            logger.warning(
                "The simulation has not yet run, therefore {} cannot"
                " be retrieved, hence the list will be empty".format(
                    variable))
            data = numpy.zeros((0, 3))
            indexes = []
            sampling_interval = self.__population._vertex.\
                get_neuron_sampling_interval(variable)
        elif sim.use_virtual_board:
            logger.warning(
                "The simulation is using a virtual machine and so has not"
                " truly ran, hence the list will be empty")
            data = numpy.zeros((0, 3))
            indexes = []
            sampling_interval = self.__population._vertex.\
                get_neuron_sampling_interval(variable)
        else:
            # assuming we got here, everything is ok, so we should go get the
            # data
            results = self.__population._vertex.get_data(
                variable, sim.no_machine_time_steps, sim.placements,
                sim.buffer_manager, sim.machine_time_step)
            (data, indexes, sampling_interval) = results

        return (data, indexes, sampling_interval)

    def _get_spikes(self):
        """ How to get spikes from a vertex.

        :return: the spikes from a vertex
        :rtype: ~numpy.ndarray
        """

        # check we're in a state where we can get spikes
        if not isinstance(self.__population._vertex, AbstractSpikeRecordable):
            raise ConfigurationException(
                "This population has not got the capability to record spikes")
        if not self.__population._vertex.is_recording_spikes():
            raise ConfigurationException(
                "This population has not been set to record spikes")

        sim = get_simulator()
        if not sim.has_ran:
            logger.warning(
                "The simulation has not yet run, therefore spikes cannot "
                "be retrieved, hence the list will be empty")
            return numpy.zeros((0, 2))

        if sim.use_virtual_board:
            logger.warning(
                "The simulation is using a virtual machine and so has not "
                "truly ran, hence the list will be empty")
            return numpy.zeros((0, 2))

        # assuming we got here, everything is OK, so we should go get the
        # spikes
        return self.__population._vertex.get_spikes(
            sim.placements, sim.buffer_manager, sim.machine_time_step)

    def _turn_off_all_recording(self, indexes=None):
        """ Turns off recording, is used by a pop saying `.record()`

        :rtype: None
        """
        # check for standard record which includes spikes
        if isinstance(self.__population._vertex, AbstractNeuronRecordable):
            variables = self.__population._vertex.get_recordable_variables()
            for variable in variables:
                self.__population._vertex.set_recording(
                    variable, new_state=False, indexes=indexes)

        # check for spikes
        if isinstance(self.__population._vertex, AbstractSpikeRecordable):
            self.__population._vertex.set_recording_spikes(
                new_state=False, indexes=indexes)

    def _extract_neo_block(self, variables, view_indexes, clear, annotations):
        """ Extracts block from the vertices and puts them into a Neo block

        :param variables: the variables to extract
        :param view_indexes: the indexes to be included in the view
        :param clear: if the variables should be cleared after reading
        :param annotations: annotations to put on the Neo block
        :return: The Neo block
        :rtype: ~neo.core.Block
        """

        block = neo.Block()

        for previous in range(0, get_simulator().segment_counter):
            self._append_previous_segment(
                block, previous, variables, view_indexes)

        # add to the segments the new block
        self._append_current_segment(block, variables, view_indexes, clear)

        # add fluff to the neo block
        block.name = self._population.label
        block.description = self._population.describe()
        # pylint: disable=no-member
        block.rec_datetime = block.segments[0].rec_datetime
        block.annotate(**self._metadata())
        if annotations:
            block.annotate(**annotations)
        return block

    def _get_units(self, variable):
        """ Get units with some safety code if the population has trouble

        :param str variable: name of the variable
        :return: type of the data
        :rtype: str
        """
        try:
            return self._population.find_units(variable)
        except Exception:
            logger.warning("Population: {} Does not support units for {}",
                           self._population.label, variable)
            if variable in _DEFAULT_UNITS:
                return _DEFAULT_UNITS[variable]
            raise

    def __spike_sampling_interval(self):
        """
        :rtype: float
        """
        return self._population._vertex.get_spikes_sampling_interval()

    def cache_data(self):
        """ Store data for later extraction
        """
        variables = self._get_all_recording_variables()
        if variables:
            segment_number = get_simulator().segment_counter
            logger.info("Caching data for segment {:d}", segment_number)

            data_cache = DataCache(
                label=self._population.label,
                description=self._population.describe(),
                segment_number=segment_number,
                recording_start_time=self._recording_start_time,
                t=get_simulator().t)

            for variable in variables:
                if variable == SPIKES:
                    data = self._get_spikes()
                    sampling_interval = self.__spike_sampling_interval()
                    indexes = None
                else:
                    results = self._get_recorded_matrix(variable)
                    (data, indexes, sampling_interval) = results
                data_cache.save_data(
                    variable=variable, data=data, indexes=indexes,
                    n_neurons=self._population.size,
                    units=self._get_units(variable),
                    sampling_interval=sampling_interval)
            self._data_cache[segment_number] = data_cache

    def _filter_recorded(self, filter_ids):
        record_ids = list()
        for neuron_id in range(0, len(filter_ids)):
            if filter_ids[neuron_id]:
                # add population first ID to ensure all atoms have a unique
                # identifier (PyNN enforcement)
                record_ids.append(neuron_id + self._population.first_id)
        return record_ids

    def _clean_variables(self, variables):
        """ Sorts out variables for processing usage

        :param variables: list of variables names, or 'all', or single.
        :type variables: str or list(str)
        :return: ordered set of variables' names.
        :rtype: iterable(str)
        """
        # if variable is a base string, plonk into a array for ease of
        # conversion
        if isinstance(variables, string_types):
            variables = [variables]

        # if all are needed to be extracted, extract each and plonk into the
        # neo block segment. ensures whatever was in variables stays in
        # variables, regardless of all
        if 'all' in variables:
            variables = OrderedSet(variables)
            variables.remove('all')
            variables.update(self._get_all_recording_variables())
        return variables

    def _append_current_segment(self, block, variables, view_indexes, clear):
        # build segment for the current data to be gathered in
        segment = neo.Segment(
            name="segment{}".format(get_simulator().segment_counter),
            description=self._population.describe(),
            rec_datetime=datetime.now())

        # sort out variables for using
        variables = self._clean_variables(variables)

        for variable in variables:
            if variable == SPIKES:
                sampling_interval = self.__spike_sampling_interval()
                self.read_in_spikes(
                    segment=segment,
                    spikes=self._get_spikes(),
                    t=get_simulator().get_current_time(),
                    n_neurons=self._population.size,
                    recording_start_time=self._recording_start_time,
                    sampling_interval=sampling_interval,
                    indexes=view_indexes,
                    label=self._population.label)
            else:
                (data, data_indexes, sampling_interval) = \
                    self._get_recorded_matrix(variable)
                self.read_in_signal(
                    segment=segment,
                    block=block,
                    signal_array=data,
                    data_indexes=data_indexes,
                    view_indexes=view_indexes,
                    variable=variable,
                    recording_start_time=self._recording_start_time,
                    sampling_interval=sampling_interval,
                    units=self._get_units(variable),
                    label=self._population.label)
        block.segments.append(segment)

        if clear:
            self._clear_recording(variables)

    def _append_previous_segment(
            self, block, segment_number, variables, view_indexes):
        if segment_number not in self._data_cache:
            logger.warning("No Data available for Segment {}", segment_number)
            segment = neo.Segment(
                name="segment{}".format(segment_number),
                description="Empty",
                rec_datetime=datetime.now())
            return segment

        data_cache = self._data_cache[segment_number]

        # sort out variables
        variables = self._clean_variables(variables)

        # build segment for the previous data to be gathered in
        segment = neo.Segment(
            name="segment{}".format(segment_number),
            description=data_cache.description,
            rec_datetime=data_cache.rec_datetime)

        for variable in variables:
            if variable not in data_cache.variables:
                logger.warning("No Data available for Segment {} variable {}",
                               segment_number, variable)
                continue
            variable_cache = data_cache.get_data(variable)
            if variable == SPIKES:
                self.read_in_spikes(
                    segment=segment,
                    spikes=variable_cache.data,
                    t=data_cache.t,
                    n_neurons=variable_cache.n_neurons,
                    recording_start_time=data_cache.recording_start_time,
                    sampling_interval=variable_cache.sampling_interval,
                    indexes=view_indexes,
                    label=data_cache.label)
            else:
                self.read_in_signal(
                    segment=segment,
                    block=block,
                    signal_array=variable_cache.data,
                    data_indexes=variable_cache.indexes,
                    view_indexes=view_indexes,
                    variable=variable,
                    recording_start_time=data_cache.recording_start_time,
                    sampling_interval=variable_cache.sampling_interval,
                    units=variable_cache.units,
                    label=data_cache.label)

        block.segments.append(segment)

    def _get_all_possible_recordable_variables(self):
        variables = OrderedSet()
        if isinstance(self._population._vertex, AbstractSpikeRecordable):
            variables.add(SPIKES)
        if isinstance(self._population._vertex, AbstractNeuronRecordable):
            variables.update(
                self._population._vertex.get_recordable_variables())
        return variables

    def _get_all_recording_variables(self):
        possibles = self._get_all_possible_recordable_variables()
        variables = OrderedSet()
        for possible in possibles:
            if possible == SPIKES:
                if isinstance(self._population._vertex,
                              AbstractSpikeRecordable) \
                        and self._population._vertex.is_recording_spikes():
                    variables.add(possible)
            elif isinstance(self._population._vertex,
                            AbstractNeuronRecordable) and \
                    self._population._vertex.is_recording(possible):
                variables.add(possible)
        return variables

    def _metadata(self):
        metadata = {
            'size': self._population.size,
            'first_index': 0,
            'last_index': self._population.size,
            'first_id': int(self._population.first_id),
            'last_id': int(self._population.last_id),
            'label': self._population.label,
            'simulator': get_simulator().name,
        }
        metadata.update(self._population._annotations)
        metadata['dt'] = get_simulator().dt
        metadata['mpi_processes'] = get_simulator().num_processes
        return metadata

    def _clear_recording(self, variables):
        sim = get_simulator()
        for variable in variables:
            if variable == SPIKES:
                self._population._vertex.clear_spike_recording(
                    sim.buffer_manager, sim.placements)
            elif variable == MEMBRANE_POTENTIAL:
                self._population._vertex.clear_recording(
                    variable, sim.buffer_manager, sim.placements)
            elif variable == GSYN_EXCIT:
                self._population._vertex.clear_recording(
                    variable, sim.buffer_manager, sim.placements)
            elif variable == GSYN_INHIB:
                self._population._vertex.clear_recording(
                    variable, sim.buffer_manager, sim.placements)
            else:
                raise InvalidParameterType(
                    "The variable {} is not a recordable value".format(
                        variable))

    def read_in_spikes(
            self, segment, spikes, t, n_neurons, recording_start_time,
            sampling_interval, indexes, label):
        """ Converts the data into SpikeTrains and saves them to the segment.

        :param ~neo.core.Segment segment: Segment to add spikes to
        :param ~numpy.ndarray spikes: Spike data in raw sPyNNaker format
        :param int t: last simulation time
        :param int n_neurons:
            total number of neurons including ones not recording
        :param int recording_start_time: time recording started
        :param int sampling_interval: how often a neuron is recorded
        :param str label: recording elements label
        """
        # pylint: disable=too-many-arguments
        # Safety check in case spikes are an empty list
        if len(spikes) == 0:
            spikes = numpy.empty(shape=(0, 2))

        t_stop = t * quantities.ms

        if indexes is None:
            indexes = xrange(n_neurons)
        for index in indexes:
            spiketrain = neo.SpikeTrain(
                times=spikes[spikes[:, 0] == index][:, 1],
                t_start=recording_start_time,
                t_stop=t_stop,
                units='ms',
                sampling_interval=sampling_interval,
                source_population=label,
                source_id=self._population.index_to_id(index),
                source_index=index)
            # get times per atom
            segment.spiketrains.append(spiketrain)

    def read_in_signal(
            self, segment, block, signal_array, data_indexes, view_indexes,
            variable, recording_start_time, sampling_interval, units, label):
        """ Reads in a data item that's not spikes (likely v, gsyn e, gsyn i)\
        and saves this data to the segment.

        :param ~neo.core.Segment segment: Segment to add data to
        :param ~neo.core.Block block: neo block
        :param ~numpy.ndarray signal_array: the raw signal data
        :param list(int) data_indexes: The indexes for the recorded data
        :param view_indexes: The indexes for which data should be returned.
            If None all data (view_index = data_indexes)
        :type view_indexes: list(int) or None
        :param str variable: the variable name
        :param recording_start_time: when recording started
        :type recording_start_time: float or int
        :param sampling_interval: how often a neuron is recorded
        :type sampling_interval: float or int
        :param units: the units of the recorded value
        :type units: quantities.quantity.Quantity or str
        :param str label: human readable label
        """
        # pylint: disable=too-many-arguments, no-member
        t_start = recording_start_time * quantities.ms
        sampling_period = sampling_interval * quantities.ms
        if view_indexes is None:
            if len(data_indexes) != self._population.size:
                msg = "Warning getting data on a whole population when " \
                      "selective recording is active will result in only " \
                      "the requested neurons being returned in numerical " \
                      "order and without repeats."
                logger_utils.warn_once(logger, msg)
            indexes = numpy.array(data_indexes)
        elif view_indexes == data_indexes:
            indexes = numpy.array(data_indexes)
        else:
            # keep just the view indexes in the data
            indexes = [i for i in view_indexes if i in data_indexes]
            # keep just data columns in the view
            map_indexes = [data_indexes.index(i) for i in indexes]
            signal_array = signal_array[:, map_indexes]

        ids = list(map(self._population.index_to_id, indexes))
        data_array = neo.AnalogSignal(
            signal_array,
            units=units,
            t_start=t_start,
            sampling_period=sampling_period,
            name=variable,
            source_population=label,
            source_ids=ids)
        channel_index = _get_channel_index(indexes, block)
        data_array.channel_index = channel_index
        data_array.shape = (data_array.shape[0], data_array.shape[1])
        segment.analogsignals.append(data_array)
        channel_index.analogsignals.append(data_array)


def _get_channel_index(ids, block):
    for channel_index in block.channel_indexes:
        if numpy.array_equal(channel_index.index, ids):
            return channel_index
    count = len(block.channel_indexes)
    channel_index = neo.ChannelIndex(
        name="Index {}".format(count), index=ids)
    block.channel_indexes.append(channel_index)
    return channel_index


def _convert_extracted_data_into_neo_expected_format(
        signal_array, indexes):
    """ Converts data between sPyNNaker format and Neo format

    :param ~numpy.ndarray signal_array: Draw data in sPyNNaker format
    :rtype: ~numpy.ndarray
    """
    processed_data = [
        signal_array[:, 2][signal_array[:, 0] == index]
        for index in indexes]
    processed_data = numpy.vstack(processed_data).T
    return processed_data
