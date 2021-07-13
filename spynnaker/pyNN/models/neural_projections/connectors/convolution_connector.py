# Copyright (c) The University of Sussex, Garibaldi Pineda Garcia,
# James Turner, James Knight and Thomas Nowotny
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

import numpy
from spinn_utilities.overrides import overrides
from spinn_front_end_common.utilities.constants import (
    BYTES_PER_WORD, BYTES_PER_SHORT)
from pyNN.random import RandomDistribution
from spynnaker.pyNN.exceptions import SynapticConfigurationException
from .abstract_connector import AbstractConnector
from .abstract_generate_connector_on_machine import (
    AbstractGenerateConnectorOnMachine, PARAM_TYPE_KERNEL,
    PARAM_TYPE_CONSTANT_ID, ConnectorIDs)
from data_specification.enums.data_type import DataType
from collections.abc import Iterable
from spinn_front_end_common.utilities.exceptions import ConfigurationException
from spynnaker.pyNN.utilities.utility_calls import get_n_bits

N_KERNEL_PARAMS = 8


def shape2word(sw, sh):
    return numpy.uint32(
        ((numpy.uint32(sh) & 0xFFFF) << 16) | (numpy.uint32(sw) & 0xFFFF))


class ConvolutionConnector(AbstractGenerateConnectorOnMachine):
    """
    Where the pre- and post-synaptic populations are considered as a 2D\
    array. Connect every post(row, col) neuron to many pre(row, col, kernel)\
    through a (kernel) set of weights and/or delays.

    .. admonition:: TODO

        Should these include `allow_self_connections` and `with_replacement`?

        TODO: ONLY AVERAGE POOLING IS ALLOWED AT THIS POINT!
    """

    __slots__ = [
        "__kernel_weights",
        "__strides",
        "__padding_shape",
        "__pool_shape",
        "__pool_stride"
    ]

    def __init__(self, kernel_weights, kernel_shape=None, strides=None,
                 padding=None, pool_shape=None, pool_stride=None, safe=True,
                 verbose=False, callback=None):
        """
        :param kernel_weights:
            The synaptic strengths, shared by neurons in the post population.
            Can be:
                * single value: kernel_shape must be provided;
                                the same value will be used for all weights
                * simple list: kernel_shape must be provided; the list must
                               be sized shape width * height
                * 2D list: If kernel_shape is provided, it must match
                * numpy.ndarray: As above for simple or 2D list
                * RandomDistribution: kernel_shape must be provided; weights
                                      will be drawn from the distribution
        :type kernel_weights:
            int or list or 2D-list or numpy.ndarray or RandomDistribution
        :param kernel_shape:
            The shape of the kernel if it cannot be determined from
            kernel_weights. If a single value is provided, a square kernel will
            be assumed.  If two values are provided, it will be assumed to be
            (n_rows, n_columns)
        :type kernel_shape: int or tuple(int,int)
        :param strides:
            Spatial sampling frequency, jumps between the post neurons.
            This matches the meaning of standard ML packages.  If a single
            value is provided, the same stride will be used for rows and
            columns.  If two values are provided it will be assumed to be
            (stride_rows, stride_columns)
        :type strides: int or tuple(int, int)
        :param padding:
            How many 'extra pixels' around the pre population will be added,
            only zero-valued pixels are currently supported.  If a single
            value is provided, the same padding will be used for rows and
            columns.  If two values are provided it will be assumed to be
            (padding_rows, padding_columns).  If True, automatic padding will
            be used based on the kernel shape.  If False or None, no padding
            will be used.
        :type padding: bool or int or tuple(int, int) or None
        :param pool_shape:
            Area of pooling, only average pooling is supported (and seems to
            make sense). If a single value is provided, the pooling area will
            be square.  If two values are provided it will be assumed to be
            (pooling_rows, pooling_columns).
        :type pool_shape: int or tuple(int, int)
        :param pool_stride:
            Jumps between pooling regions. If a single value is provided, the
            same stride will be used for rows and columns.  If two values are
            provided it will be assumed to be (stride_rows, stride_columns)
        :type pool_stride: int or tuple(int, int)
        :param bool safe: (ignored)
        :param bool verbose: (ignored)
        :param callable callback: (ignored)
        """
        super(ConvolutionConnector, self).__init__(
            safe=safe, callback=callback, verbose=verbose)

        self.__decode_kernel(kernel_weights, kernel_shape)
        self.__decode_padding(padding)

        if strides is None:
            strides = (1, 1)
        self.__strides = self.__to_2d_shape(strides, "strides")
        self.__pool_shape = self.__to_2d_shape(pool_shape, "pool_shape")
        self.__pool_stride = self.__to_2d_shape(pool_stride, "pool_stride")

    def __get_kernel_shape(self, shape):
        if shape is None:
            raise SynapticConfigurationException(
                "kernel_shape must be provided")
        if numpy.isscalar(shape):
            return (shape, shape)
        if isinstance(shape, tuple) and len(shape) == 2:
            return shape
        raise SynapticConfigurationException(f"Unknown kernel_shape: {shape}")

    def __decode_kernel(self, w, shape):
        if isinstance(w, int) or isinstance(w, float):
            shape = self.__get_kernel_shape(shape)
            self.__kernel_weights = numpy.full(shape, w)
        elif isinstance(w, Iterable):
            if all(isinstance(lst, Iterable) for lst in w):
                # 2D list
                if not all(len(lst) == len(w[0]) for lst in w):
                    raise SynapticConfigurationException(
                        "kernel_weights must be a 2D array with every row the"
                        " same length")
                self.__kernel_weights = numpy.array(w)
            else:
                # 1D list
                shape = self.__get_kernel_shape(shape)
                self.__kernel_weights = numpy.array(w).reshape(shape)
        elif isinstance(w, RandomDistribution):
            shape = self.__get_kernel_shape(shape)
            self.__kernel_weights = numpy.array(
                w.next(numpy.prod(shape))).reshape(shape)
        else:
            raise SynapticConfigurationException(
                f"Unknown combination of kernel_weights ({w}) and"
                f" kernel_shape ({shape})")

    @staticmethod
    def __to_2d_shape(shape, param_name):
        if shape is None:
            return None
        if numpy.isscalar(shape):
            return numpy.array([shape, shape], dtype='int')
        elif len(shape) == 1:
            return numpy.array([shape[0], 1], dtype='int')
        elif len(shape) == 2:
            return numpy.array(shape, dtype='int')
        raise SynapticConfigurationException(
            f"{param_name} must be an int or a tuple(int, int)")

    def __decode_padding(self, padding):
        if isinstance(padding, (int, Iterable)):
            self.__padding_shape = self.__to_2d_shape(padding, "padding")
        elif padding is None or padding is False:
            self.__padding_shape = numpy.zeros(2, dtype="int")
        elif padding:
            self.__padding_shape = self.__kernel_weights.shape // 2
        else:
            raise SynapticConfigurationException(
                f"Unrecognized padding {padding}")

    def get_post_shape(self, shape):
        """ Get the shape of the post image given the pre-image shape
        """
        shape = numpy.array(shape)
        if self.__pool_shape is not None:
            post_pool_shape = shape - (self.__pool_shape - 1)
            shape = (post_pool_shape // self.__pool_stride) + 1

        kernel_shape = numpy.array(self.__kernel_weights.shape)
        post_shape = (shape - (kernel_shape - 1) +
                      (2 * self.__padding_shape))

        return numpy.clip(
            post_shape // self.__strides, 1, numpy.inf).astype('int')

    @overrides(AbstractConnector.validate_connection)
    def validate_connection(self, application_edge, synapse_info):
        pre = application_edge.pre_vertex
        post = application_edge.post_vertex
        if len(pre.atoms_shape) != 2 or len(post.atoms_shape) != 2:
            raise ConfigurationException(
                "The ConvolutionConnector only works where the Populations"
                " of a Projection are both 2D.  Please ensure that the"
                " Populations uses a Grid2D structure.")
        expected_post_shape = tuple(self.get_post_shape(pre.atoms_shape))
        if expected_post_shape != post.atoms_shape:
            raise ConfigurationException(
                f"With a source population with shape {pre.atoms_shape}, "
                "for a Convolution connector with the given parameters, "
                "the post-population must have a shape "
                f"{expected_post_shape}")

    @overrides(AbstractConnector.get_delay_minimum)
    def get_delay_minimum(self, synapse_info):
        # All delays are 1 timestep
        return 1

    @overrides(AbstractConnector.get_delay_maximum)
    def get_delay_maximum(self, synapse_info):
        # All delays are 1 timestep
        return 1

    @overrides(AbstractConnector.get_n_connections_from_pre_vertex_maximum)
    def get_n_connections_from_pre_vertex_maximum(
            self, post_vertex_slice, synapse_info, min_delay=None,
            max_delay=None):
        w, h = self.__kernel_weights.shape
        return numpy.clip(w * h, 0, post_vertex_slice.n_atoms)

    @overrides(AbstractConnector.get_n_connections_to_post_vertex_maximum)
    def get_n_connections_to_post_vertex_maximum(self, synapse_info):
        w, h = self.__kernel_weights.shape
        return numpy.clip(w * h, 0, synapse_info.n_pre_neurons)

    @overrides(AbstractConnector.get_weight_maximum)
    def get_weight_maximum(self, synapse_info):
        return numpy.amax(self.__kernel_weights)

    @overrides(AbstractConnector.create_synaptic_block)
    def create_synaptic_block(
            self, pre_slices, post_slices, pre_vertex_slice, post_vertex_slice,
            synapse_type, synapse_info):

        # TODO: Make this work on host
        block = numpy.zeros(0, dtype=self.NUMPY_SYNAPSES_DTYPE)
        block['weight'] = 0
        block['delay'] = 1

        return block

    @overrides(AbstractGenerateConnectorOnMachine.generate_on_machine)
    def generate_on_machine(self, weights, delays):
        # TODO: Decide this based on other info
        return False

    @overrides(AbstractGenerateConnectorOnMachine.gen_delays_id)
    def gen_delays_id(self, delays):
        # Delays are always 1
        return PARAM_TYPE_CONSTANT_ID

    @overrides(
        AbstractGenerateConnectorOnMachine.gen_delay_params_size_in_bytes)
    def gen_delay_params_size_in_bytes(self, delays):
        # Delay is always 1 time step
        return BYTES_PER_WORD

    @overrides(AbstractGenerateConnectorOnMachine.gen_delay_params)
    def gen_delay_params(self, delays, pre_vertex_slice, post_vertex_slice):
        # Delay is always 1 time step
        return numpy.array(
                [DataType.S1615.encode_as_int(1)], dtype=numpy.uint32)

    @overrides(AbstractGenerateConnectorOnMachine.gen_weights_id)
    def gen_weights_id(self, weights):
        # Weights are always a kernel
        return PARAM_TYPE_KERNEL

    @overrides(
        AbstractGenerateConnectorOnMachine.gen_weight_params_size_in_bytes)
    def gen_weight_params_size_in_bytes(self, weights):
        # Weights are always a kernel
        return ((N_KERNEL_PARAMS + 1 + self.__kernel_weights.size) *
                BYTES_PER_WORD)

    @overrides(AbstractGenerateConnectorOnMachine.gen_weights_params)
    def gen_weights_params(self, weights, pre_vertex_slice, post_vertex_slice):
        properties = self.__get_kernel_properties(machine_edge)
        properties.append(post_vertex_slice.lo_atom)
        data = numpy.array(properties, dtype="uint32")
        values = DataType.S1615.encode_as_numpy_int_array(
            self.__kernel_weights)
        return numpy.concatenate((data, values.flatten()))

    @property
    @overrides(AbstractGenerateConnectorOnMachine.gen_connector_id)
    def gen_connector_id(self):
        return ConnectorIDs.KERNEL_CONNECTOR.value

    @overrides(AbstractGenerateConnectorOnMachine.gen_connector_params)
    def gen_connector_params(
            self, pre_slices, post_slices, pre_vertex_slice, post_vertex_slice,
            synapse_type, synapse_info):
        return numpy.array(
            self.__get_kernel_properties(machine_edge), dtype="uint32")

    @property
    @overrides(
        AbstractGenerateConnectorOnMachine.gen_connector_params_size_in_bytes)
    def gen_connector_params_size_in_bytes(self):
        return N_KERNEL_PARAMS * BYTES_PER_WORD

    def __get_kernel_properties(self, machine_edge):
        pre_app_vertex = machine_edge.pre_vertex.app_vertex
        post_app_vertex = machine_edge.post_vertex.app_vertex
        pre_shape = pre_app_vertex.atoms_shape
        post_shape = post_app_vertex.atoms_shape
        kernel_shape = self.__kernel_weights.shape
        return [
            shape2word(*pre_shape),
            shape2word(*pre_shape),
            shape2word(*post_shape),
            shape2word(0, 0),
            shape2word(0, 0),
            shape2word(1, 1),
            shape2word(*self.__strides),
            shape2word(*kernel_shape)
        ]

    @overrides(AbstractConnector.could_connect)
    def could_connect(self, _synapse_info, _pre_slice, _post_slice):
        pre_slice_x = _pre_slice.get_slice(0)
        pre_slice_y = _pre_slice.get_slice(1)
        post_slice_x = _post_slice.get_slice(0)
        post_slice_y = _post_slice.get_slice(1)

        # Get ranges allowed in post
        min_x = post_slice_x.start - self._hlf_k_w
        max_x = (post_slice_x.stop + self._hlf_k_w) - 1
        min_y = post_slice_y.start - self._hlf_k_h
        max_y = (post_slice_y.stop + self._hlf_k_h) - 1

        # Get pre-coordinates as post-coordinates
        pre_x_min, pre_y_min, pre_x_max, pre_y_max = self.__pre_as_post(
            [[pre_slice_x.start, pre_slice_y.start],
             [pre_slice_x.stop - 1, pre_slice_y.stop - 1]])

        # No part of the pre square overlaps the post-square, don't connect
        if (pre_x_max < min_x or pre_x_min > max_x or
                pre_y_max < min_y or pre_y_min > max_y):
            return False

        # Otherwise, they do
        return True

    def __pre_as_post(self, pre_coords):
        """ Write pre coords as post coords.

        :param Iterable pre_coords: An iterable of (x, y) coordinates
        :rtype: numpy.ndarray
        """
        coords = numpy.array(pre_coords)
        if self.__pool_stride is not None:
            coords //= self.__pool_stride

        kernel_shape = numpy.array(self.__kernel_weights.shape)
        coords = coords - kernel_shape // 2 + self.__padding_shape
        coords //= self.__strides
        return coords

    @property
    def local_only_n_bytes(self):
        return (
            (2 * BYTES_PER_WORD) +
            (12 * BYTES_PER_SHORT) +
            BYTES_PER_WORD +
            (self.__kernel_weights.size * BYTES_PER_WORD))

    def write_local_only_data(
            self, spec, edge, r_info, synapse_info, weight_scales):
        # Get info about things
        pre_start = edge.pre_vertex.vertex_slice.start
        pre_shape = edge.pre_vertex.vertex_slice.shape
        kernel_shape = self.__kernel_weights.shape
        ps_x, ps_y = 1, 1
        if self.__pool_stride is not None:
            ps_x, ps_y = self.__pool_stride

        # Write source key info
        spec.write_value(r_info.first_key)
        spec.write_value(r_info.first_mask)

        # Write the column and row mask and shifts to extract the column and
        # row from the incoming spike
        n_bits_col = get_n_bits(pre_shape[0])
        col_mask = (1 << n_bits_col) - 1
        n_bits_row = get_n_bits(pre_shape[1])
        row_mask = ((1 << n_bits_row) - 1) << n_bits_col
        spec.write_value(col_mask, dtype=DataType.UINT32)
        spec.write_value(0)
        spec.write_value(row_mask, dtype=DataType.UINT32)
        spec.write_value(n_bits_col)

        # Write remaining connector details
        spec.write_value(pre_start[0], dtype=DataType.INT16)
        spec.write_value(pre_start[1], dtype=DataType.INT16)
        spec.write_value(pre_shape[0], dtype=DataType.INT16)
        spec.write_value(pre_shape[1], dtype=DataType.INT16)
        spec.write_value(kernel_shape[0], dtype=DataType.INT16)
        spec.write_value(kernel_shape[1], dtype=DataType.INT16)
        spec.write_value(self.__padding_shape[0], dtype=DataType.INT16)
        spec.write_value(self.__padding_shape[1], dtype=DataType.INT16)
        spec.write_value(self.__recip(self.__strides[0]), dtype=DataType.INT16)
        spec.write_value(self.__recip(self.__strides[1]), dtype=DataType.INT16)
        spec.write_value(self.__recip(ps_x), dtype=DataType.INT16)
        spec.write_value(self.__recip(ps_y), dtype=DataType.INT16)
        spec.write_value(synapse_info.synapse_type, dtype=DataType.UINT32)
        spec.write_array(DataType.S1615.encode_as_numpy_int_array(
            self.__kernel_weights.flatten() *
            weight_scales[synapse_info.synapse_type]))

    def __recip(self, v):
        """ Compute the reciprocal of a number as an signed 1-bit integer,
            14-bit fractional fixed point number, encoded in an integer
        """
        return int(round((1 / v) * (1 << 14)))
