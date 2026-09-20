import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

from dese.constants import BUTTON_WIDTH, INPUT_WIDTH, PAD, WIDE_WRAP_LENGTH
from dese.core.model import has_quality_reading_entity
from dese.core.validation import ENUM_PROPERTY_TYPE
from dese.engine.event_log import export_event_log_to_csv, summarize_event_log
from dese.engine.flow_object_generation import schedule_flow_object_generation
from dese.engine.process_supply import schedule_process_supply_replenishment
from dese.engine.event_loop import run_simulation
from dese.engine.simulation_model import ModelValidationError, build_simulation_model
from dese.engine.simulation_request import (
    SimulationRequestValidationError,
    build_simulation_request,
)
from dese.engine.simulation_state import build_simulation_state
from dese.utils import measure_column_width, validate_number


class SimulationPage(ttk.Frame):
    """Lets the user configure and start a Simulation run. Reachable only
    once the active model passes validation — see
    DESEApp.update_simulation_button_state."""

    def __init__(
        self,
        parent,
        schema,
        model_data,
        simulation_state=None,
        simulation_request_field_values=None,
        on_simulation_state_changed=None,
        on_field_changed=None,
    ):
        super().__init__(parent)
        self.schema = schema
        self.model_data = model_data
        self.simulation_request_entries = {}
        self.simulation_state = simulation_state
        self.simulation_request_field_values = simulation_request_field_values or {}
        self.on_simulation_state_changed = on_simulation_state_changed
        self.on_field_changed = on_field_changed
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
        self.update_results_tab()

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

            remembered_value = self.simulation_request_field_values.get(field_name)

            if field_schema["type"] == ENUM_PROPERTY_TYPE:
                control_strategy_variable = tk.StringVar(
                    value=remembered_value or field_schema["values"][0]
                )
                entry = ttk.Combobox(
                    self.settings_frame,
                    textvariable=control_strategy_variable,
                    values=field_schema["values"],
                    state="readonly",
                    width=INPUT_WIDTH,
                )
                entry.variable = control_strategy_variable
                entry.bind(
                    "<<ComboboxSelected>>",
                    lambda event, field_name=field_name, entry=entry: self.commit_field(
                        field_name, entry
                    ),
                )
            else:
                validate_command = (self.register(validate_number), "%P")
                entry = ttk.Entry(
                    self.settings_frame,
                    width=INPUT_WIDTH,
                    validate="key",
                    validatecommand=validate_command,
                )

                if remembered_value is not None:
                    entry.insert(0, remembered_value)

                entry.bind(
                    "<FocusOut>",
                    lambda event, field_name=field_name, entry=entry: self.commit_field(
                        field_name, entry
                    ),
                )
                entry.bind(
                    "<Return>",
                    lambda event, field_name=field_name, entry=entry: self.commit_field(
                        field_name, entry
                    ),
                )

            entry.grid(row=row, column=1, sticky="w")

            unit_label = ttk.Label(self.settings_frame, text=field_schema.get("unit", ""))
            unit_label.grid(row=row, column=2, sticky="w")

            self.simulation_request_entries[field_name] = entry
            row += 1

        # Display widget:
        self.settings_frame.grid(row=0, column=0, sticky="new")

    def commit_field(self, field_name, entry):
        if self.on_field_changed is not None:
            self.on_field_changed(field_name, entry.get())

    def update_results_tab(self):
        # Rebuilt every time a run finishes (or on first display, when
        # there's nothing yet) -- clear whatever was there before.
        for widget in self.results_tab.winfo_children():
            widget.destroy()

        # Grid:
        self.results_tab.rowconfigure(0, weight=1)
        self.results_tab.columnconfigure(0, weight=1)

        if self.simulation_state is None:
            no_results_label = ttk.Label(
                self.results_tab, text="No results yet — run a simulation to see results here."
            )
            no_results_label.grid(row=0, column=0, sticky="nw", padx=PAD, pady=PAD)
            return

        summary_frame = ttk.LabelFrame(self.results_tab, text="Run Summary", padding=PAD)
        summary_frame.grid(row=0, column=0, sticky="new", padx=PAD, pady=PAD)
        summary_frame.columnconfigure(1, weight=1)

        request = self.simulation_state.simulation_request
        request_fields = self.schema.get_simulation_request_schema()["properties"]

        row = 0

        for field_name, field_schema in request_fields.items():
            label = ttk.Label(summary_frame, text=field_name.replace("_", " ").title())
            label.grid(row=row, column=0, sticky="w")

            value_text = f"{getattr(request, field_name)} {field_schema.get('unit', '')}".strip()
            value_label = ttk.Label(summary_frame, text=value_text)
            value_label.grid(row=row, column=1, sticky="w", padx=(PAD, 0))
            row += 1

        simulated_time_label = ttk.Label(summary_frame, text="Simulated Time Reached")
        simulated_time_label.grid(row=row, column=0, sticky="w")
        simulated_time_value = ttk.Label(summary_frame, text=f"{self.simulation_state.clock} s")
        simulated_time_value.grid(row=row, column=1, sticky="w", padx=(PAD, 0))
        row += 1

        if not has_quality_reading_entity(self.model_data, self.schema):
            no_inspection_label = ttk.Label(
                summary_frame,
                text=(
                    "No Inspection Entity in this model — defective Flow Objects are not "
                    "filtered out, they continue through the rest of the process."
                ),
                wraplength=WIDE_WRAP_LENGTH,
            )
            no_inspection_label.grid(row=row, column=0, columnspan=2, sticky="w")
            row += 1

        separator = ttk.Separator(summary_frame, orient="horizontal")
        separator.grid(row=row, column=0, columnspan=2, sticky="ew", pady=PAD)
        row += 1

        # Generic (event_type -> count) breakdown -- a new event_type
        # introduced later shows up automatically here, no code change.
        event_counts = summarize_event_log(self.simulation_state)

        for event_type, count in event_counts.items():
            label = ttk.Label(summary_frame, text=event_type.replace("_", " ").title())
            label.grid(row=row, column=0, sticky="w")
            value_label = ttk.Label(summary_frame, text=str(count))
            value_label.grid(row=row, column=1, sticky="w", padx=(PAD, 0))
            row += 1

        export_button = ttk.Button(
            self.results_tab,
            text="Export CSV",
            width=BUTTON_WIDTH,
            command=self.export_csv,
        )
        export_button.grid(row=1, column=0, sticky="se", padx=PAD, pady=PAD)

    def export_csv(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="event_log.csv",
            title="Export Event Log",
        )

        if not file_path:
            return

        export_event_log_to_csv(self.simulation_state, file_path)
        messagebox.showinfo("Export Event Log", f"Event log exported to {file_path}.")

    def start_simulation(self):
        fields = self.schema.get_simulation_request_schema()["properties"]
        values_by_field_name = {}

        for field_name, field_schema in fields.items():
            raw_value = self.simulation_request_entries[field_name].get()
            # Don't rely solely on FocusOut having already fired for every
            # field by the time this runs (e.g. editing a field and then
            # clicking Start Simulation without focus ever fully leaving it).
            self.commit_field(field_name, self.simulation_request_entries[field_name])

            if field_schema["type"] == ENUM_PROPERTY_TYPE:
                values_by_field_name[field_name] = raw_value
            else:
                try:
                    values_by_field_name[field_name] = float(raw_value)
                except ValueError:
                    values_by_field_name[field_name] = None

        try:
            simulation_request = build_simulation_request(
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
            return

        try:
            simulation_model = build_simulation_model(self.model_data, self.schema)
        except ModelValidationError as error:
            messagebox.showerror(
                "Model error",
                "\n".join(issue["message"] for issue in error.issues),
            )
            return

        simulation_state = build_simulation_state(simulation_model, simulation_request)
        schedule_flow_object_generation(simulation_state)
        schedule_process_supply_replenishment(simulation_state)
        run_simulation(simulation_state)

        self.simulation_state = simulation_state
        self.update_results_tab()
        self.notebook.select(self.results_tab)

        if self.on_simulation_state_changed is not None:
            self.on_simulation_state_changed(simulation_state)
