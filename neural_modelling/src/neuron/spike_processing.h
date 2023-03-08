/*
 * Copyright (c) 2015 The University of Manchester
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

//! \file
//! \brief Spike processing API
#ifndef _SPIKE_PROCESSING_H_
#define _SPIKE_PROCESSING_H_

#include <common/neuron-typedefs.h>
#include <common/in_spikes.h>
#include <spin1_api.h>

//! Provenance for spike processing
struct spike_processing_provenance {
    //! A count of the times that the synaptic input circular buffers overflowed
    uint32_t n_input_buffer_overflows;
    //! The number of DMAs performed
    uint32_t n_dmas_complete;
    //! The number of spikes received and processed
    uint32_t n_spikes_processed;
    //! The number of rewirings performed.
    uint32_t n_rewires;
    //! The number of packets that were cleared at the end of timesteps
    uint32_t n_packets_dropped_from_lateness;
    //! The maximum size of the input buffer
    uint32_t max_filled_input_buffer_size;
};

//! \brief Initialise the spike processing system
//! \param[in] row_max_n_bytes: The maximum size of a synaptic row
//! \param[in] mc_packet_callback_priority:
//!     Multicast packet receive interrupt priority
//! \param[in] user_event_priority: User event interrupt priority
//! \param[in] incoming_spike_buffer_size: Size of buffer for receiving spikes
//! \param[in] clear_input_buffers_of_late_packets_init:
//!     Whether packets that are left at the end of a time step are wiped
//! \param[in] packets_per_timestep_region:
//!     The recording region to use for the packets per timestep
//! \return True if initialisation succeeded
bool spike_processing_initialise(
        size_t row_max_n_bytes, uint mc_packet_callback_priority,
        uint user_event_priority, uint incoming_spike_buffer_size,
        bool clear_input_buffers_of_late_packets_init,
        uint32_t packets_per_timestep_region);

//! \brief Get provenance data for Spike processing
//! \param[in] prov The structure to store the provenance data in
void spike_processing_store_provenance(struct spike_processing_provenance *prov);

//! \brief Set the number of times spike_processing has to attempt rewiring.
//! \param[in] number_of_rewires: The number of rewirings to perform
//! \return currently always true
bool spike_processing_do_rewiring(int number_of_rewires);

//! \brief clears the input buffer of packets
//! \param[in] time: The current timestep
void spike_processing_clear_input_buffer(timer_t time);

#endif // _SPIKE_PROCESSING_H_
