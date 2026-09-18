from tkinter import ttk


class SimulationPage(ttk.Frame):
    """Placeholder for the future Simulation Engine's UI entry point.
    Reachable only once the active model passes validation — see
    DESEApp.update_simulation_button_state."""

    def __init__(self, parent):
        super().__init__(parent)
        self.create_widgets()

    def create_widgets(self):
        self.placeholder_label = ttk.Label(self, text="Simulation — coming soon.")
        self.placeholder_label.grid(row=0, column=0)
