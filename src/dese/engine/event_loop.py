"""The core discrete-event loop: a heapq-based priority queue of
(time, sequence, event_type, data) tuples, and the single `run_simulation`
driver that pops and dispatches them in order until the run duration is
reached. Every other engine module schedules its own events here and
registers its own handlers in `EVENT_HANDLERS` -- this module has no
domain knowledge of what any event type actually does.
"""
import heapq

from dese.constants import SECONDS_PER_HOUR

# Populated by each behavior layer (Flow Object generation, Processing,
# Failure/Maintenance, ...) as its own handlers are added -- run_simulation
# itself never needs to change when a new event type is introduced.
EVENT_HANDLERS = {}


def schedule_event(state, time, event_type, data=None):
    """Queues an event to fire at ``time``.

    Args:
        state: The mutable SimulationState.
        time: Simulated clock time (seconds) at which the event should fire.
        event_type: Key into ``EVENT_HANDLERS`` identifying which handler
            runs when this event is dispatched.
        data: Optional dict of event-specific payload, passed through
            unchanged to the handler.
    """
    # The sequence number is the tie-breaker for same-time events, so heapq
    # never needs to compare two events' own (non-orderable) data dicts.
    state.event_sequence_counter += 1
    heapq.heappush(
        state.event_queue,
        (time, state.event_sequence_counter, event_type, data or {}),
    )


def run_simulation(state):
    """Runs the event loop until the queue empties or the run duration elapses.

    Pops the earliest-scheduled event, advances ``state.clock`` to its time,
    and dispatches it to the handler registered in ``EVENT_HANDLERS`` under
    its ``event_type`` -- repeating until either no events remain or the
    next event's time exceeds the request's configured run duration.

    Args:
        state: The mutable SimulationState to run; mutated in place (its
            ``event_log`` ends up holding the full run's history).

    Returns:
        The same ``state`` object, for convenient chaining.
    """
    run_duration_seconds = state.simulation_request.run_duration * SECONDS_PER_HOUR

    while state.event_queue:
        time, _sequence, event_type, data = state.event_queue[0]

        if time > run_duration_seconds:
            break

        heapq.heappop(state.event_queue)
        state.clock = time

        EVENT_HANDLERS[event_type](state, data)

    return state
