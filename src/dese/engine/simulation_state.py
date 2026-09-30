"""SimulationState: the single mutable object a run threads through every
engine module -- the event queue, the clock, per-entity occupancy, and the
event log all live here. Built once per run by `build_simulation_state`,
which derives its per-entity shape (slots vs. a Storage queue vs. a Process
Supply quantity) purely from the schema-driven model, never from
hardcoded entity-type names.
"""
import random
from dataclasses import dataclass, field

from dese.core.model import (
    get_processing_duration_property,
    holds_flow_object_queue,
    is_supply_source,
)


@dataclass
class FlowObjectInstance:
    """One generated Flow Object's runtime state -- its identity, current
    quality, and where it currently is in the system."""

    id: str
    flow_object_type: str
    created_at: float
    quality: str
    current_entity_id: str
    # Set alongside quality="scrap" ("entity_failure" or "baseline_variation",
    # see maintenance.apply_wear_and_rules) so any later event involving this
    # instance can report WHY it's scrap, not just THAT it is -- avoids
    # needing to cross-reference the original flow_object_scrapped row.
    scrap_cause: str = None


@dataclass
class EntityState:
    """One Entity's runtime state: its derived status, its processing slots
    (if any), and its wear counter.
    """

    # slots is fixed-size, one entry per unit of the Entity's own "capacity"
    # -- only for Entities that do timed processing (Processing/Inspection;
    # see get_processing_duration_property), empty [] otherwise (Storage/
    # Process Supply/Process Sink don't have "slots" in this sense).
    # A slot's identity (its position in the list) stays stable across
    # occupants: {"flow_object_instance_id": None-or-id, "last_flow_object_type":
    # ..., "processing_started": bool} -- last_flow_object_type persists even
    # while the slot is empty, so the NEXT occupant's changeover_time can
    # still be compared against it (changeover is tracked per slot, not per
    # Entity, since capacity > 1 means independent parallel resources -- e.g.
    # separate robot arms). processing_started is False while an occupant is
    # seated but stalled waiting on Process Supply material -- see
    # processing.retry_stalled_slots, called on every replenishment. finished
    # is True once an occupant is done but couldn't move on (its target was
    # full) -- see processing.retry_upstream, called whenever a downstream
    # slot frees up, to un-block it without waiting for an unrelated event.
    status: str = "idle"
    slots: list = field(default_factory=list)
    cycles_since_maintenance: float = 0


@dataclass
class MaintenanceResourceState:
    """The shared, model-wide repair/maintenance resource's own occupancy:
    how many jobs are currently running, and who's queued for the next
    free slot (see maintenance.request_maintenance_resource)."""

    busy_count: int = 0
    waiting_entity_ids: list = field(default_factory=list)


@dataclass
class SimulationState:
    """Everything a single simulation run needs: the model being simulated,
    the request parameters, the event queue/clock, and every per-entity/
    per-Flow-Object piece of runtime state. One instance per run, built by
    `build_simulation_state` and mutated in place by every engine module
    for the run's duration.
    """

    simulation_model: object
    simulation_request: object
    clock: float
    event_queue: list
    event_sequence_counter: int
    random_generator: object
    flow_object_instances: dict
    order_storage: list
    entity_states: dict
    storage_states: dict
    process_supply_states: dict
    maintenance_resource_state: MaintenanceResourceState
    event_log: list
    # Separate from event_sequence_counter (the event QUEUE's own tie-
    # breaker) so the exported log's sequence column starts cleanly at 1,
    # independent of how many events happened to already be scheduled.
    log_sequence_counter: int = 0
    # A dedicated monotonic counter for Flow Object instance ids -- unlike
    # utils.generate_id (used for Entities/Relationships, where reusing the
    # lowest free number after a delete is the right, human-facing UX),
    # instance ids are never freed, so re-scanning from 1 on every single
    # generated instance would turn a long/high-volume run quadratic.
    flow_object_instance_counter: int = 0


def build_entity_state(entity, domain_only_model_data, schema):
    """Builds the initial EntityState for one Entity.

    Schema-driven, not type-name-driven: an Entity gets slots only if it
    has a processing-duration property (Processing/Inspection), regardless
    of its literal type name -- a Storage/Process Supply/Process Sink gets
    an empty, slot-less EntityState instead.

    Args:
        entity: The Entity dict from the model.
        domain_only_model_data: A ``{"domain": ...}``-only stand-in for the
            full model, sufficient for the schema lookups this needs.
        schema: The loaded SchemaLoader.

    Returns:
        EntityState: idle, with as many empty slots as the Entity's own
        ``capacity`` property, or none at all if it doesn't process.
    """
    duration_property = get_processing_duration_property(entity, domain_only_model_data, schema)

    if duration_property is None:
        return EntityState()

    capacity = int(entity["properties"]["capacity"])
    slots = [
        {
            "flow_object_instance_id": None,
            "last_flow_object_type": None,
            "processing_started": False,
            "finished": False,
        }
        for _ in range(capacity)
    ]

    return EntityState(slots=slots)


def build_simulation_state(simulation_model, simulation_request):
    """Builds a fresh SimulationState for one run, ready for
    ``event_loop.run_simulation``.

    Derives per-entity runtime state purely from the schema (slots for
    processing Entities via ``build_entity_state``, an empty FIFO queue for
    queue-holding Entities, an initial quantity for Process Supply sources)
    -- never from hardcoded entity-type names. Seeds ``random_generator``
    once, from ``simulation_request.random_seed``, for the whole run.

    Args:
        simulation_model: The built SimulationModel (schema + resolved
            entities/relationships/rules) to simulate.
        simulation_request: The run parameters (duration, seed, control
            strategy).

    Returns:
        SimulationState: clock at 0, empty event queue/log, ready to have
        generation/replenishment events scheduled onto it before running.
    """
    domain_only_model_data = {"domain": simulation_model.domain}

    entity_states = {
        entity_id: build_entity_state(entity, domain_only_model_data, simulation_model.schema)
        for entity_id, entity in simulation_model.entities_by_id.items()
    }

    storage_states = {
        entity_id: []
        for entity_id, entity in simulation_model.entities_by_id.items()
        if holds_flow_object_queue(entity, domain_only_model_data, simulation_model.schema)
    }

    process_supply_states = {
        entity_id: entity["properties"]["initial_quantity"]
        for entity_id, entity in simulation_model.entities_by_id.items()
        if is_supply_source(entity, domain_only_model_data, simulation_model.schema)
    }

    return SimulationState(
        simulation_model=simulation_model,
        simulation_request=simulation_request,
        clock=0,
        event_queue=[],
        event_sequence_counter=0,
        random_generator=random.Random(simulation_request.random_seed),
        flow_object_instances={},
        order_storage=[],
        entity_states=entity_states,
        storage_states=storage_states,
        process_supply_states=process_supply_states,
        maintenance_resource_state=MaintenanceResourceState(),
        event_log=[],
    )
