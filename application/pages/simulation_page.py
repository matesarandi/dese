import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

from dese.constants import BUTTON_WIDTH, INPUT_WIDTH, PAD, WIDE_WRAP_LENGTH
from dese.core.validation import ENUM_PROPERTY_TYPE
from dese.engine.simulation_request import (
    SimulationRequestValidationError,
    build_simulation_request,
)
from dese.utils import measure_column_width, validate_number


class SimulationPage(ttk.Frame):
    """Lets the user configure and start a Simulation run. Reachable only
    once the active model passes validation — see
    DESEApp.update_simulation_button_state."""

    def __init__(self, parent, schema):
        super().__init__(parent)
        self.schema = schema
        self.simulation_request_entries = {}
        self.create_widgets()

    def create_widgets(self):
        # Grid:
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        # Notebook
        # ==========================

        self.notebook = ttk.Notebook(self, padding=0)

        self.settings_tab = ttk.Frame(self.notebook)
        self.results_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.settings_tab, text="Settings")
        self.notebook.add(self.results_tab, text="Results")

        self.notebook.grid(row=0, column=0, sticky="nsew")

        self.create_settings_tab()
        self.create_results_tab()

        # Button Frame
        # ==========================
        # Shared across every tab, so it lives below the notebook rather
        # than inside one tab's content — same layout as the Model Editor's
        # Save/Show Issues button row below its own notebook.

        self.button_frame = ttk.Frame(self, padding=PAD)

        # Grid:
        self.button_frame.columnconfigure(0, weight=1)

        # Display widget:
        self.button_frame.grid(row=1, column=0, sticky="ew")

        self.start_simulation_button = ttk.Button(
            self.button_frame,
            text="Start Simulation",
            width=BUTTON_WIDTH,
            command=self.start_simulation,
        )
        self.start_simulation_button.grid(row=0, column=0, sticky="e")

    def create_settings_tab(self):
        # Grid:
        self.settings_tab.columnconfigure(0, weight=1)

        self.settings_frame = ttk.LabelFrame(self.settings_tab, padding=PAD)

        fields = self.schema.get_simulation_request_schema()["properties"]

        # A fixed column 0 width (the longest field label here) keeps the
        # entry/unit columns justified at the same x position on every row —
        # same approach as RulesTabMixin.render_rule_property_form. The
        # trailing column 3 is an empty spacer that absorbs any extra width,
        # so the label/entry/unit columns stay packed together on the left.
        default_font = tkfont.nametofont("TkDefaultFont")
        label_column_width = measure_column_width(
            [field_name.replace("_", " ").title() for field_name in fields], default_font
        )
        self.settings_frame.columnconfigure(0, minsize=label_column_width)
        self.settings_frame.columnconfigure(3, weight=1)

        row = 0

        for field_name, field_schema in fields.items():
            if row > 0:
                separator = ttk.Separator(self.settings_frame, orient="horizontal")
                separator.grid(row=row, column=0, columnspan=4, sticky="ew")
                row += 1

            description_label = ttk.Label(
                self.settings_frame,
                text=field_schema["description"],
                wraplength=WIDE_WRAP_LENGTH,
            )
            description_label.grid(row=row, column=0, columnspan=4, sticky="w")
            row += 1

            field_label = ttk.Label(
                self.settings_frame, text=field_name.replace("_", " ").title()
            )
            field_label.grid(row=row, column=0, sticky="w")

            if field_schema["type"] == ENUM_PROPERTY_TYPE:
                control_strategy_variable = tk.StringVar(value=field_schema["values"][0])
                entry = ttk.Combobox(
                    self.settings_frame,
                    textvariable=control_strategy_variable,
                    values=field_schema["values"],
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

            unit_label = ttk.Label(self.settings_frame, text=field_schema.get("unit", ""))
            unit_label.grid(row=row, column=2, sticky="w")

            self.simulation_request_entries[field_name] = entry
            row += 1

        # Display widget:
        self.settings_frame.grid(row=0, column=0, sticky="new")

    def create_results_tab(self):
        # Grid:
        self.results_tab.columnconfigure(0, weight=1)

        self.no_results_label = ttk.Label(
            self.results_tab, text="No results yet — run a simulation to see results here."
        )
        self.no_results_label.grid(row=0, column=0, sticky="w")

    def start_simulation(self):
        fields = self.schema.get_simulation_request_schema()["properties"]
        values_by_field_name = {}

        for field_name, field_schema in fields.items():
            raw_value = self.simulation_request_entries[field_name].get()

            if field_schema["type"] == ENUM_PROPERTY_TYPE:
                values_by_field_name[field_name] = raw_value
            else:
                try:
                    values_by_field_name[field_name] = float(raw_value)
                except ValueError:
                    values_by_field_name[field_name] = None

        try:
            build_simulation_request(
                values_by_field_name["run_duration"],
                values_by_field_name["replications"],
                values_by_field_name["random_seed"],
                values_by_field_name["control_strategy"],
                self.schema,
            )
        except SimulationRequestValidationError as error:
            messagebox.showerror(
                "Simulation Request error",
                "\n".join(issue["message"] for issue in error.issues),
            )
