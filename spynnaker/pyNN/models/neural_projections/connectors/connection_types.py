# Copyright (c) 2023 The University of Manchester
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Types (and related) that are useful for implementing connectors.
"""

import numpy
from numpy.typing import NDArray
from pyNN.random import RandomDistribution
import pyNN
from typing import Union
from typing_extensions import TypeAlias, TypeGuard
#: The type of weights and delays provided by
D: TypeAlias = Union[pyNN.random.RandomDistribution, int, float, str]
Weight_Delay_Types: TypeAlias = \
    Union[float, str, RandomDistribution, NDArray[numpy.float64]]


def is_scalar(value: Weight_Delay_Types) -> TypeGuard[Union[int, float]]:
    """
    Are the weights or delays a simple integer or float?
    """
    return numpy.isscalar(value)
