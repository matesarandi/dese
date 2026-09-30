"""The application's entry point and top-level window (`DESEApp`): owns the
schema, the active model's file path, and the three-page navigation (Start
-> Model Editor -> Simulation). Run directly (``python -m dese.application.gui``)
to launch the app.
"""
import tkinter as tk
from tkinter import messagebox, ttk

from dese.application.pages.model_editor_page import ModelEditorPage
from dese.application.pages.simulation_page import SimulationPage
from dese.application.pages.start_page import StartPage
from dese.constants import (
    BUTTON_WIDTH,
    MODEL_EDITOR_WINDOW_SIZE,
    START_WINDOW_SIZE,
)
from dese.core.schema_loader import SchemaLoader
from dese.core.validation import validate_model as validate_model_data
from dese.paths import DEFAULT_SCHEMA_PATH
from dese.styles import configure_styles


class DESEApp(tk.Tk):
    """Top-level window: owns the schema, the active model path, and page routing
    between the Start page and the Model Editor page."""

    def __init__(self):
        super().__init__()
        self.schema = SchemaLoader(DEFAULT_SCHEMA_PATH)
        self.model_changed = False
        self.editing_model_path = None
        self.selected_model_path = None
        # SimulationPage is rebuilt from scratch every time it's shown (see
        # show_simulation_page) -- unlike ModelEditorPage, it has no file to
        # reload from, so its entered settings and last run's results would
        # otherwise be lost on every navigation away and back. Held here
        # instead, across rebuilds.
        self.simulation_state = None
        self.simulation_request_field_values = {}
        self.create_window()
        self.create_menu()
        self.create_navigation()
        self.create_widgets()
        self.show_start_page()

    # ==========================
    # Methods
    # ==========================

    def activate_model(self, model_path):
        """Makes ``model_path`` the active model and opens the Model Editor
        on it, prompting to save any unsaved changes to a DIFFERENT model
        first if one was already open."""
        if (
            self.editing_model_path is not None
            and self.model_changed
            and self.editing_model_path != model_path
        ):
            result = messagebox.askyesnocancel(
                "Unsaved changes",
                f"Save changes to {self.editing_model_path.name} before opening another model?",
            )

            if result is None:
                return

            if result:
                self.save_model()

        self.editing_model_path = model_path
        self.model_file_label.config(text=self.editing_model_path.name)
        self.model_changed = False
        self.unsaved_label.config(text="")
        self.model_editor_button.config(state="normal")
        self.show_model_editor_page()

    def open_model_editor(self):
        """Navigation-bar "Model Editor" button handler: shows the Model
        Editor for the currently active model, if any."""
        if self.editing_model_path is None:
            return

        self.show_model_editor_page()

    def save_model(self):
        """Delegates saving to the active Model Editor page, if one is open."""
        if hasattr(self, "model_editor_page"):
            self.model_editor_page.save_model()

    def select_model(self, model_path):
        """Records which model file is currently selected on the Start page
        (before it's actually opened)."""
        self.selected_model_path = model_path

    def set_model_changed(self, changed):
        """Callback passed to ModelEditorPage: updates the unsaved-changes
        indicator and re-evaluates whether the Simulation button should be
        enabled, whenever the model is edited."""
        self.model_changed = changed

        if changed:
            self.unsaved_label.config(text="⏺")

        else:
            self.unsaved_label.config(text="")

        self.update_simulation_button_state()

    def update_simulation_button_state(self):
        """Enables/disables the Simulation nav button based on whether the
        active model currently has zero validation issues.

        Re-checked on every edit (via set_model_changed) so the button
        reflects the model's current state, not just its state as of the
        last explicit Validate click.
        """
        if not hasattr(self, "model_editor_page") or self.model_editor_page.model_data is None:
            self.simulation_button.config(state="disabled")
            return

        issues = validate_model_data(self.model_editor_page.model_data, self.schema)
        self.simulation_button.config(state="normal" if not issues else "disabled")

    def create_window(self):
        # Window:
        self.geometry(START_WINDOW_SIZE)
        self.title("DESE")

        configure_styles()

        # Grid:
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

    def clear_page(self):
        for widget in self.container.winfo_children():
            widget.destroy()

    def show_start_page(self):
        """Tears down the current page and shows the Start page."""
        # Window:
        self.geometry(START_WINDOW_SIZE)
        self.resizable(False, False)

        # Clear page:
        self.clear_page()

        # Widgets:
        self.start_page = StartPage(
            self.container, self.schema, self.activate_model, self.select_model
        )

        # Display widgets:
        self.start_page.grid(row=0, column=0, sticky="nsew")

        self.simulation_button.config(state="disabled")

    def open_start_page(self):
        """Navigation-bar "Start" button handler: prompts to save unsaved
        changes, then shows the Start page."""
        if self.editing_model_path is not None and self.model_changed:
            result = messagebox.askyesnocancel(
                "Unsaved changes",
                f"Save changes to {self.editing_model_path.name} before returning to Start?",
            )

            if result is None:
                return

            if result:
                self.save_model()

        self.show_start_page()

    def show_model_editor_page(self):
        """Tears down the current page and shows the Model Editor for
        ``self.editing_model_path``, falling back to the Start page if
        loading it fails."""
        # Window:
        self.geometry(MODEL_EDITOR_WINDOW_SIZE)
        self.resizable(False, False)

        # Clear page:
        self.clear_page()

        # Widgets:
        self.model_editor_page = ModelEditorPage(
            self.container, self.editing_model_path, self.schema, self.set_model_changed
        )

        # Loading may fail (e.g. an incompatible schema version) — load_model
        # already showed an error dialog, so just fall back to the Start page
        # instead of displaying a half-built, empty Model Editor.
        if self.model_editor_page.model_data is None:
            self.show_start_page()
            return

        # Display widgets:
        self.model_editor_page.grid(row=0, column=0, sticky="nsew")

        self.update_simulation_button_state()

    def open_simulation_page(self):
        """Navigation-bar "Simulation" button handler: shows the Simulation
        page for the currently active model, if any."""
        if self.editing_model_path is None:
            return

        self.show_simulation_page()

    def show_simulation_page(self):
        """Tears down the current page and rebuilds the Simulation page,
        re-hydrating it from ``self.simulation_state``/
        ``self.simulation_request_field_values`` so a prior run's settings
        and results survive navigating away and back."""
        # Window:
        self.geometry(MODEL_EDITOR_WINDOW_SIZE)
        self.resizable(False, False)

        # Clear page:
        self.clear_page()

        # Widgets:
        self.simulation_page = SimulationPage(
            self.container,
            self.schema,
            self.model_editor_page.model_data,
            simulation_state=self.simulation_state,
            simulation_request_field_values=self.simulation_request_field_values,
            on_simulation_state_changed=self.set_simulation_state,
            on_field_changed=self.set_simulation_request_field_value,
        )

        # Display widgets:
        self.simulation_page.grid(row=0, column=0, sticky="nsew")

    def set_simulation_state(self, simulation_state):
        """Callback passed to SimulationPage: persists the last-run
        SimulationState here so it survives the page being rebuilt on navigation."""
        self.simulation_state = simulation_state

    def set_simulation_request_field_value(self, field_name, value):
        """Callback passed to SimulationPage: persists one run-parameter
        field's value here so it survives the page being rebuilt on navigation."""
        self.simulation_request_field_values[field_name] = value

    def create_menu(self):

        # Menu Bar
        # ==========================

        # Widgets:
        self.menu_bar = tk.Menu(self)
        self.file_menu = tk.Menu(self.menu_bar, tearoff=0)

        # Configuration:
        self.file_menu.add_command(label="Save", command=self.save_model)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Exit", command=self.destroy)
        self.menu_bar.add_cascade(label="File", menu=self.file_menu)
        self.config(menu=self.menu_bar)

    def create_navigation(self):

        # Navigation Bar
        # ==========================

        # Widgets:
        self.navigation_frame = ttk.Frame(self)
        self.start_button = ttk.Button(
            self.navigation_frame,
            width=BUTTON_WIDTH,
            text="Start",
            command=self.open_start_page,
        )
        self.model_editor_button = ttk.Button(
            self.navigation_frame,
            text="Model Editor",
            width=BUTTON_WIDTH,
            command=self.open_model_editor,
            state="disabled",
        )
        self.simulation_button = ttk.Button(
            self.navigation_frame,
            text="Simulation",
            width=BUTTON_WIDTH,
            command=self.open_simulation_page,
            state="disabled",
        )
        self.model_file_label = ttk.Label(self.navigation_frame, text="")
        self.unsaved_label = ttk.Label(self.navigation_frame, text="")

        # Display widgets:
        self.navigation_frame.grid(row=0, column=0, sticky="ew")
        self.start_button.grid(row=0, column=0)
        self.model_editor_button.grid(row=0, column=1)
        self.simulation_button.grid(row=0, column=2)
        self.model_file_label.grid(row=0, column=3)
        self.unsaved_label.grid(row=0, column=4)

        # Grid:
        self.navigation_frame.columnconfigure(5, weight=1)

    # ==========================
    # Main Container
    # ==========================

    def create_widgets(self):

        # Container
        # ==========================

        # Widgets:
        self.container = ttk.Frame(self)

        # Grid:
        self.container.rowconfigure(0, weight=1)
        self.container.columnconfigure(0, weight=1)

        # Display widgets:
        self.container.grid(row=1, column=0, sticky="nsew")


# ==========================
# Main Loop
# ==========================

if __name__ == "__main__":
    app = DESEApp()
    app.mainloop()
