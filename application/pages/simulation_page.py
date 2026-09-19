import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

from dese.constants import BUTTON_WIDTH, INPUT_WIDTH, PAD, VALID_CONTROL_STRATEGIES
from dese.engine.simulation_request import (
    SIMULATION_REQUEST_FIELDS,
    SimulationRequestValidationError,
    build_simulation_request,
)
from dese.utils import measure_column_width, validate_number


class SimulationPage(ttk.Frame):
    """Lets the user configure and start a Simulation run. Reachable only
    once the active model passes validation — see
    DESEApp.update_simulation_button_state."""

    def __init__(self, parent):
        super().__init__(parent)
        self.simulation_request_entries = {}
        self.create_widgets()

    def create_widgets(self):
        self.settings_frame = ttk.LabelFrame(self, text="Simulation Settings")

        # A fixed column 0 width (the longest field label here) keeps the
        # entry/unit columns justified at the same x position on every row —
        # same approach as RulesTabMixin.render_rule_property_form. The
        # trailing column 3 is an empty spacer that absorbs any extra width,
        # so the label/entry/unit columns stay packed together on the left.
        default_font = tkfont.nametofont("TkDefaultFont")
        label_column_width = measure_column_width(
            [field["label"] for field in SIMULATION_REQUEST_FIELDS.values()], default_font
        )
        self.settings_frame.columnconfigure(0, minsize=label_column_width)
        self.settings_frame.columnconfigure(3, weight=1)

        row = 0

        for field_name, field in SIMULATION_REQUEST_FIELDS.items():
            if row > 0:
                separator = ttk.Separator(self.settings_frame, orient="horizontal")
                separator.grid(row=row, column=0, columnspan=4, sticky="ew")
                row += 1

            description_label = ttk.Label(self.settings_frame, text=field["description"])
            description_label.grid(row=row, column=0, columnspan=4, sticky="w")
            row += 1

            field_label = ttk.Label(self.settings_frame, text=field["label"])
            field_label.grid(row=row, column=0, sticky="w")

            if field_name == "control_strategy":
                control_strategy_variable = tk.StringVar(value=VALID_CONTROL_STRATEGIES[0])
                entry = ttk.Combobox(
                    self.settings_frame,
                    textvariable=control_strategy_variable,
                    values=VALID_CONTROL_STRATEGIES,
                    state="readonly",
                    width=INPUT_WIDTH,
                )
                entry.variable = control_strategy_variable
            else:
                validate_command = (self.register(validate_number), "%P")
                entry = ttk.Entry(
                    self.settings_frame,
                    width=INPUT_WIDTH,
                    validate="key",
                    validatecommand=validate_command,
                )

            entry.grid(row=row, column=1, sticky="w")

            unit_label = ttk.Label(self.settings_frame, text=field.get("unit", ""))
            unit_label.grid(row=row, column=2, sticky="w")

            self.simulation_request_entries[field_name] = entry
            row += 1

        self.start_simulation_button = ttk.Button(
            self,
            text="Start Simulation",
            width=BUTTON_WIDTH,
            command=self.start_simulation,
        )

        # Display widgets:
        self.settings_frame.grid(row=0, column=0, sticky="nsew", padx=PAD, pady=PAD)
        self.start_simulation_button.grid(row=1, column=0, sticky="e", padx=PAD, pady=PAD)

    def start_simulation(self):
        try:
            run_duration = float(self.simulation_request_entries["run_duration"].get())
        except ValueError:
            run_duration = None

        try:
            replications = int(self.simulation_request_entries["replications"].get())
        except ValueError:
            replications = None

        try:
            random_seed = int(self.simulation_request_entries["random_seed"].get())
        except ValueError:
            random_seed = None

        control_strategy = self.simulation_request_entries["control_strategy"].get()

        try:
            build_simulation_request(run_duration, replications, random_seed, control_strategy)
        except SimulationRequestValidationError as error:
            messagebox.showerror(
                "Simulation Request error",
                "\n".join(issue["message"] for issue in error.issues),
            )
