import random
from dataclasses import dataclass, field

from dese.core.model import get_processing_duration_property, holds_flow_object_queue


@dataclass
class FlowObjectInstance:
    id: str
    flow_object_type: str
    created_at: float
    quality: str
    current_entity_id: str


@dataclass
class EntityState:
    # slots is fixed-size, one entry per unit of the Entity's own "capacity"
    # -- only for Entities that do timed processing (Processing/Inspection/
    # Transport; see get_processing_duration_property), empty [] otherwise
    # (Storage/Process Supply/Process Sink don't have "slots" in this sense).
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
    busy_count: int = 0
    waiting_entity_ids: list = field(default_factory=list)


@dataclass
class SimulationState:
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


def build_entity_state(entity, domain_only_model_data, schema):
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
        if "initial_quantity" in entity.get("properties", {})
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
    )
