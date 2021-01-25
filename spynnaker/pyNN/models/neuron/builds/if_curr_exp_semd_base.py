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

from spynnaker.pyNN.models.defaults import default_initial_values
from spynnaker.pyNN.models.neuron.neuron_models import (
    NeuronModelLeakyIntegrateAndFire)
from spynnaker.pyNN.models.neuron import AbstractPyNNNeuronModelStandard
from spynnaker.pyNN.models.neuron.synapse_types import SynapseTypeSEMD
from spynnaker.pyNN.models.neuron.input_types import InputTypeCurrent
from spynnaker.pyNN.models.neuron.threshold_types import ThresholdTypeStatic


class IFCurrExpSEMDBase(AbstractPyNNNeuronModelStandard):
    """ Leaky integrate and fire neuron with an exponentially decaying\
        current input, where the excitatory input depends upon the inhibitory\
        input (see https://www.cit-ec.de/en/nbs/spiking-insect-vision)

    :param tau_m: :math:`\\tau_m`
    :type tau_m: Float, iterable of Floats, RandomDistribution or function
    :param cm: :math:`C_m`
    :type cm: Float, iterable of Floats, RandomDistribution or function
    :param v_rest: :math:`V_{rest}`
    :type v_rest: Float, iterable of Floats, RandomDistribution or function
    :param v_reset: :math:`V_{reset}`
    :type v_reset: Float, iterable of Floats, RandomDistribution or function
    :param v_thresh: :math:`V_{thresh}`
    :type v_thresh: Float, iterable of Floats, RandomDistribution or function
    :param tau_syn_E: :math:`\\tau^{syn}_{e_1}`
    :type tau_syn_E: Float, iterable of Floats, RandomDistribution or function
    :param tau_syn_E2: :math:`\\tau^{syn}_{e_2}`
    :type tau_syn E2: Float, iterable of Floats, RandomDistribution or function
    :param tau_syn_I: :math:`\\tau^{syn}_i`
    :type tau_syn_I: Float, iterable of Floats, RandomDistribution or function
    :param tau_refrac: :math:`\\tau_{refrac}`
    :type tau_refrac: Float, iterable of Floats, RandomDistribution or function
    :param i_offset: :math:`I_{offset}`
    :type i_offset: Float, iterable of Floats, RandomDistribution or function
    :param v: :math:`V_{init}`
    :type v: Float, iterable of Floats, RandomDistribution or function
    :param isyn_exc: :math:`I^{syn}_{e_1}`
    :type isyn_exc: Float, iterable of Floats, RandomDistribution or function
    :param isyn_exc2: :math:`I^{syn}_{e_2}`
    :type isyn_exc2: Float, iterable of Floats, RandomDistribution or function
    :param isyn_inh: :math:`I^{syn}_i`
    :type isyn_inh: Float, iterable of Floats, RandomDistribution or function
    :param multiplicator:
    :type multiplicator: Float, iterable of Floats, RandomDistribution \
                         or function
    :param exc2_old:
    :type exc2_old: Float, iterable of Floats, RandomDistribution or function
    :param scaling_factor:
    :type scaling_factor: Float, iterable of Floats, RandomDistribution \
                          or function
    """

    @default_initial_values({"v", "isyn_exc", "isyn_exc2", "isyn_inh",
                             "exc2_old"})
    def __init__(
            self, tau_m=20.0, cm=1.0, v_rest=-65.0, v_reset=-65.0,
            v_thresh=-50.0, tau_syn_E=5.0, tau_syn_E2=5.0, tau_syn_I=5.0,
            tau_refrac=0.1, i_offset=0.0, v=-65.0, isyn_exc=0.0,
            isyn_exc2=0.0, isyn_inh=0.0, multiplicator=0.0, exc2_old=0.0,
            scaling_factor=1.0):
        neuron_model = NeuronModelLeakyIntegrateAndFire(
            v, v_rest, tau_m, cm, i_offset, v_reset, tau_refrac)
        synapse_type = SynapseTypeSEMD(
            tau_syn_E, tau_syn_E2, tau_syn_I, isyn_exc, isyn_exc2, isyn_inh,
            multiplicator, exc2_old, scaling_factor)
        input_type = InputTypeCurrent()
        threshold_type = ThresholdTypeStatic(v_thresh)

        super(IFCurrExpSEMDBase, self).__init__(
            model_name="IF_curr_exp_SEMD", binary="IF_curr_exp_sEMD.aplx",
            neuron_model=neuron_model, input_type=input_type,
            synapse_type=synapse_type, threshold_type=threshold_type)
