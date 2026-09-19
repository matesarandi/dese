from dataclasses import dataclass

from dese.constants import VALID_CONTROL_STRATEGIES

# Single source of truth for the Simulation page's form: label, description
# and (where relevant) unit for each SimulationRequest field, mirroring how
# schema.json describes model properties for the Model Editor's forms.
SIMULATION_REQUEST_FIELDS = {
    "run_duration": {
        "label": "Run Duration",
        "description": "Total simulated time to run.",
        "unit": "h",
    },
    "replications": {
        "label": "Replications",
        "description": "Number of independent runs to average results over.",
    },
    "random_seed": {
        "label": "Random Seed",
        "description": "Seed for the random number generator, for reproducible results.",
    },
    "control_strategy": {
        "label": "Control Strategy",
        "description": "How Processing Entities receive Flow Objects: Push or Pull.",
    },
}


class SimulationRequestValidationError(Exception):
    def __init__(self, issues):
        self.issues = issues
        super().__init__(f"Cannot build a Simulation Request: {len(issues)} validation issue(s).")


@dataclass
class SimulationRequest:
    run_duration: float
    replications: int
    random_seed: int
    control_strategy: str


def validate_simulation_request(run_duration, replications, random_seed, control_strategy):
    issues = []

    if run_duration is None or run_duration <= 0:
        issues.append({"severity": "error", "message": "Run duration must be a positive number."})

    if replications is None or replications < 1:
        issues.append({"severity": "error", "message": "Replications must be at least 1."})

    if random_seed is None:
        issues.append({"severity": "error", "message": "Random seed is required."})

    if control_strategy not in VALID_CONTROL_STRATEGIES:
        issues.append(
            {
                "severity": "error",
                "message": f"Control strategy must be one of {VALID_CONTROL_STRATEGIES}.",
            }
        )

    return issues


def build_simulation_request(run_duration, replications, random_seed, control_strategy):
    issues = validate_simulation_request(run_duration, replications, random_seed, control_strategy)

    if issues:
        raise SimulationRequestValidationError(issues)

    return SimulationRequest(
        run_duration=run_duration,
        replications=replications,
        random_seed=random_seed,
        control_strategy=control_strategy,
    )
