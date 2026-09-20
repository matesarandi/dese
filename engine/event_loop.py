import heapq

from dese.constants import SECONDS_PER_HOUR

# Populated by each behavior layer (Flow Object generation, Processing,
# Failure/Maintenance, ...) as its own handlers are added -- run_simulation
# itself never needs to change when a new event type is introduced.
EVENT_HANDLERS = {}


def schedule_event(state, time, event_type, data=None):
    # The sequence number is the tie-breaker for same-time events, so heapq
    # never needs to compare two events' own (non-orderable) data dicts.
    state.event_sequence_counter += 1
    heapq.heappush(
        state.event_queue,
        (time, state.event_sequence_counter, event_type, data or {}),
    )


def run_simulation(state):
    run_duration_seconds = state.simulation_request.run_duration * SECONDS_PER_HOUR

    while state.event_queue:
        time, _sequence, event_type, data = state.event_queue[0]

        if time > run_duration_seconds:
            break

        heapq.heappop(state.event_queue)
        state.clock = time

        EVENT_HANDLERS[event_type](state, data)

    return state
