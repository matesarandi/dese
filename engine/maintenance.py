from dese.engine.event_log import get_entity_log_fields, log_event
from dese.engine.event_loop import EVENT_HANDLERS, schedule_event

# Each function ranks the waiting list by one criterion; dispatch_priority
# (a user-ordered list of these names) composes them into one sort key, most
# important first -- see build_dispatch_sort_key.
DISPATCH_PRIORITY_KEY_FUNCTIONS = {
    "unplanned_first": lambda entry: 0 if entry["request_type"] == "unplanned" else 1,
    "most_worn_first": lambda entry: -entry["cycles_since_maintenance"],
    "fifo": lambda entry: entry["arrival_sequence"],
}


def build_dispatch_sort_key(dispatch_priority):
    key_functions = [
        DISPATCH_PRIORITY_KEY_FUNCTIONS[criterion] for criterion in dispatch_priority
    ]

    def sort_key(entry):
        return tuple(key_function(entry) for key_function in key_functions)

    return sort_key


def request_maintenance_resource(state, entity_id, request_type):
    # request_type is "unplanned" (a Failure) or "planned" (proactive
    # Maintenance). Either way the whole Entity goes down -- one shared
    # cycles_since_maintenance/status per Entity, not per parallel slot (a
    # single machine, even with several parallel processing slots).
    entity_state = state.entity_states[entity_id]
    entity_state.status = "failed" if request_type == "unplanned" else "down"
    log_event(
        state,
        "entity_failed" if request_type == "unplanned" else "entity_maintenance_started",
        **get_entity_log_fields(state, entity_id),
        cycles_since_maintenance=entity_state.cycles_since_maintenance,
    )

    entry = {
        "entity_id": entity_id,
        "request_type": request_type,
        "cycles_since_maintenance": entity_state.cycles_since_maintenance,
        "arrival_sequence": state.event_sequence_counter,
    }

    resource_state = state.maintenance_resource_state
    capacity = state.simulation_model.maintenance_resource_rule["capacity"]

    if resource_state.busy_count < capacity:
        start_maintenance_resource_job(state, entry)
    else:
        resource_state.waiting_entity_ids.append(entry)


def start_maintenance_resource_job(state, entry):
    state.maintenance_resource_state.busy_count += 1

    entity_id = entry["entity_id"]
    rule_bundle = state.simulation_model.rules_by_entity_id[entity_id]

    if entry["request_type"] == "unplanned":
        duration = rule_bundle["failure"]["mean_repair_time"]
    else:
        duration = rule_bundle["maintenance"]["mean_maintenance_time"]

    schedule_event(state, state.clock + duration, "maintenance_resource_job_finished", entry)


def handle_maintenance_resource_job_finished(state, data):
    # Deferred import: breaks the mutual dependency with processing.py
    # (start_processing needs to refuse starting on a failed/down Entity,
    # and this handler needs to retry whatever was stalled once repaired).
    from dese.engine.processing import retry_stalled_slots

    entity_id = data["entity_id"]
    entity_state = state.entity_states[entity_id]
    resource_state = state.maintenance_resource_state

    entity_state.cycles_since_maintenance = 0
    # Silently clears failed/down to a sentinel (no update_entity_status/
    # logging here -- just enough for start_processing's own status check,
    # below via retry_stalled_slots, to not refuse). None rather than
    # "idle": retry_stalled_slots' own final update_entity_status call
    # (see its own comment) compares against WHATEVER this was set to, so
    # if the true outcome happens to also be "idle" (nothing to resume),
    # pre-setting "idle" here would make that look like no change at all --
    # silently swallowing a real failed/down -> idle transition. None never
    # equals a real computed status, so that comparison always logs
    # something, whatever the real outcome turns out to be. Calling
    # update_entity_status directly here (before retry_stalled_slots) would
    # have the OTHER problem -- logging a premature "blocked" for a
    # seated-but-not-yet-retried occupant that a few lines later turns out
    # to have been wrong, the same bug movement.enter_entity used to have.
    entity_state.status = None
    resource_state.busy_count -= 1
    log_event(
        state,
        "entity_repaired" if data["request_type"] == "unplanned" else "entity_maintenance_finished",
        **get_entity_log_fields(state, entity_id),
    )

    if resource_state.waiting_entity_ids:
        dispatch_priority = state.simulation_model.maintenance_resource_rule["dispatch_priority"]
        resource_state.waiting_entity_ids.sort(key=build_dispatch_sort_key(dispatch_priority))
        next_entry = resource_state.waiting_entity_ids.pop(0)
        start_maintenance_resource_job(state, next_entry)

    # retry_stalled_slots' own final update_entity_status call (see its
    # comment) determines and logs the real outcome against the None
    # sentinel above -- nothing further needed here.
    retry_stalled_slots(state, entity_id)


EVENT_HANDLERS["maintenance_resource_job_finished"] = handle_maintenance_resource_job_finished


WEAR_DEPENDENT_RULE_TYPES = ("failure", "maintenance", "baseline_scrap")


def apply_wear_and_rules(state, entity_id, instance_id):
    # Called once per completed cycle (see processing.handle_finish_processing).
    # No-op for Entities with none of Failure/Maintenance/BaselineScrap
    # configured -- an Entity can have any subset of these (independent
    # rule_eligibility flags), so the shared wear counter increments
    # whenever ANY of them is present, not just when Failure specifically is.
    rule_bundle = state.simulation_model.rules_by_entity_id.get(entity_id)

    if rule_bundle is None or not any(
        rule_type in rule_bundle for rule_type in WEAR_DEPENDENT_RULE_TYPES
    ):
        return

    entity_state = state.entity_states[entity_id]
    entity_state.cycles_since_maintenance += 1
    instance = state.flow_object_instances[instance_id]

    # Only rolls a NEW failure/maintenance incident if the Entity isn't
    # already down -- with capacity > 1 (independent parallel slots sharing
    # one physical Entity), a second slot can finish shortly after the first
    # one already failed it (its finish_processing was scheduled before the
    # failure and nothing cancels it). Without this guard, that second
    # finish independently rolls its own failure/maintenance check and can
    # request a SECOND, separate repair job for the same Entity -- doubling
    # up on the shared Maintenance Resource's capacity and logging two
    # entity_failed rows for what is really one incident on one machine.
    if entity_state.status not in ("failed", "down"):
        maintenance_rule = rule_bundle.get("maintenance")
        maintenance_triggered = (
            maintenance_rule is not None
            and entity_state.cycles_since_maintenance >= maintenance_rule["maintenance_interval"]
        )

        if maintenance_triggered:
            request_maintenance_resource(state, entity_id, "planned")
        else:
            failure_rule = rule_bundle.get("failure")

            if failure_rule is not None:
                failure_probability = min(
                    1,
                    failure_rule["base_failure_probability"]
                    + failure_rule["added_failure_probability_per_cycle"]
                    * entity_state.cycles_since_maintenance,
                )

                if state.random_generator.random() < failure_probability:
                    request_maintenance_resource(state, entity_id, "unplanned")

                    # The Entity broke down while actively working on this
                    # instance -- a direct consequence, distinct from
                    # BaselineScrap's own failure-independent roll below (which
                    # is skipped once this already applies). Not its own log
                    # event -- "becoming scrap" isn't a real-world event, just a
                    # state change that the next flow_object_exited/completed/
                    # routed row already shows (quality/cause come from
                    # get_flow_object_log_fields), same time, next sequence.
                    if instance.quality != "scrap":
                        instance.quality = "scrap"
                        instance.scrap_cause = "entity_failure"

    # Baseline Scrap affects the just-finished Flow Object's own quality --
    # independent of whether the Entity itself is about to go down for
    # Maintenance/Failure, so it's always checked, not skipped above (unless
    # entity_failure already scrapped this same instance this cycle).
    baseline_scrap_rule = rule_bundle.get("baseline_scrap")

    if baseline_scrap_rule is not None and instance.quality != "scrap":
        scrap_probability = min(
            1,
            baseline_scrap_rule["base_scrap_probability"]
            + baseline_scrap_rule["added_scrap_probability_per_cycle"]
            * entity_state.cycles_since_maintenance,
        )

        if state.random_generator.random() < scrap_probability:
            instance.quality = "scrap"
            instance.scrap_cause = "baseline_variation"
