import shutil
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from dese.constants import BUTTON_WIDTH, PAD_FRAME_IN, PAD_FRAME_OUT, PAD_WIDGET
from dese.paths import TEMPLATE_DIR


class StartPage(ttk.Frame):
    def __init__(self, parent, activate_model_callback, select_model_callback):
        super().__init__(parent, padding=PAD_FRAME_IN)
        self.selected_model_path = None
        self.new_model_path = None
        self.activate_model_callback = activate_model_callback
        self.select_model_callback = select_model_callback
        self.create_widgets()

    # ----------------------------
    # METHODS
    # ----------------------------

    def edit_model(self):
        if self.selected_model_path is None:
            messagebox.showwarning("No model selected", "Please select a model first.")
            return

        self.activate_model_callback(self.selected_model_path)

    def continue_new_model(self):
        if self.new_model_path is None:
            messagebox.showwarning("No model created", "Please create a model first.")
            return

        self.activate_model_callback(self.new_model_path)

    def open_model_button_clicked(self):
        file_path = filedialog.askopenfilename(
            title="Open Existing Model",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if file_path:
            model_path = Path(file_path)
            self.selected_model_path = model_path
            self.file_name_label.config(text=model_path.name)
            self.select_model_callback(model_path)

    def create_new_model(self):
        template_path = TEMPLATE_DIR / "empty_model.json"
        save_path = filedialog.asksaveasfilename(
            title="Create New Model",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )

        if save_path:
            save_path = Path(save_path)
            shutil.copy(template_path, save_path)
            self.new_model_path = save_path
            self.created_model_label.config(text=save_path.name)

    # ----------------------------
    # START PAGE
    # ----------------------------

    def create_widgets(self):

        # ----------------------------
        # Welcome
        # ----------------------------

        # Grid:
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)
        self.rowconfigure(3, weight=1)
        self.rowconfigure(4, weight=1)
        self.columnconfigure(0, weight=1)

        # Child widgets:
        self.title_label = ttk.Label(
            self, text="Discrete Event Simulation Engine", font=("Arial", 16, "bold")
        )
        self.subtitle_label = ttk.Label(
            self,
            text="Design systems freely without predefined workflows and explore emergent behavior through simulation.",
            wraplength=400,
            justify="center",
        )
        self.separator = ttk.Separator(self, orient="horizontal")

        # Display child widgets:
        self.title_label.grid(
            row=0, column=0, sticky="n", padx=PAD_WIDGET, pady=PAD_WIDGET
        )
        self.subtitle_label.grid(row=1, column=0, padx=PAD_WIDGET, pady=PAD_WIDGET)
        self.separator.grid(row=2, column=0, sticky="ew")

        # ----------------------------
        # Open Existing Model Frame
        # ----------------------------

        # Frame widget:
        self.open_frame = ttk.LabelFrame(
            self,
            text="Open Existing Model",
            style="DESE.Section.TLabelframe",
            padding=PAD_FRAME_IN,
        )

        # Grid:
        self.open_frame.rowconfigure(0, weight=1)
        self.open_frame.rowconfigure(1, weight=1)
        self.open_frame.rowconfigure(2, weight=1)
        self.open_frame.columnconfigure(0, weight=1)
        self.open_frame.columnconfigure(1, weight=1)

        # Child widgets:
        self.open_frame_subtitle = ttk.Label(
            self.open_frame, text="Load and edit an existing simulation model."
        )
        self.selected_file_label = ttk.Label(self.open_frame, text="Selected file:")
        self.file_name_label = ttk.Label(self.open_frame, text="No file selected")
        self.open_button = ttk.Button(
            self.open_frame,
            text="Open",
            width=BUTTON_WIDTH,
            command=self.open_model_button_clicked,
        )
        self.edit_button = ttk.Button(
            self.open_frame, text="Edit", width=BUTTON_WIDTH, command=self.edit_model
        )

        # Display frame widget:
        self.open_frame.grid(
            row=3, column=0, sticky="ew", padx=PAD_FRAME_OUT, pady=PAD_FRAME_OUT
        )

        # Display child widgets:
        self.open_frame_subtitle.grid(
            row=0, column=0, columnspan=2, sticky="w", padx=PAD_WIDGET, pady=PAD_WIDGET
        )
        self.selected_file_label.grid(
            row=1, column=0, sticky="w", padx=PAD_WIDGET, pady=PAD_WIDGET
        )
        self.file_name_label.grid(
            row=2, column=0, sticky="w", padx=PAD_WIDGET, pady=PAD_WIDGET
        )
        self.open_button.grid(
            row=1, column=1, sticky="e", padx=PAD_WIDGET, pady=PAD_WIDGET
        )
        self.edit_button.grid(
            row=2, column=1, sticky="e", padx=PAD_WIDGET, pady=PAD_WIDGET
        )

        # ----------------------------
        # Create New Model Frame
        # ----------------------------

        # Frame widget:
        self.new_frame = ttk.LabelFrame(
            self,
            text="Create New Model",
            style="DESE.Section.TLabelframe",
            padding=PAD_FRAME_IN,
        )

        # Grid:
        self.new_frame.rowconfigure(0, weight=1)
        self.new_frame.rowconfigure(1, weight=1)
        self.new_frame.rowconfigure(2, weight=1)
        self.new_frame.columnconfigure(0, weight=1)
        self.new_frame.columnconfigure(1, weight=1)

        # Child widgets:
        self.new_frame_subtitle = ttk.Label(
            self.new_frame,
            text="Create a new simulation model from scratch. Define entities, relationships and rules to build your simulation model.",
            wraplength=400,
            justify="left",
        )
        self.created_model_title_label = ttk.Label(
            self.new_frame, text="Created model:"
        )
        self.created_model_label = ttk.Label(self.new_frame, text="No model created")
        self.create_button = ttk.Button(
            self.new_frame,
            text="Create",
            width=BUTTON_WIDTH,
            command=self.create_new_model,
        )
        self.continue_button = ttk.Button(
            self.new_frame,
            text="Continue",
            width=BUTTON_WIDTH,
            command=self.continue_new_model,
        )

        # Display frame widget:
        self.new_frame.grid(
            row=4, column=0, sticky="ew", padx=PAD_FRAME_OUT, pady=PAD_FRAME_OUT
        )

        # Display child widgets:
        self.new_frame_subtitle.grid(
            row=0, column=0, columnspan=2, sticky="w", padx=PAD_WIDGET, pady=PAD_WIDGET
        )
        self.created_model_title_label.grid(
            row=1, column=0, sticky="w", padx=PAD_WIDGET, pady=PAD_WIDGET
        )
        self.created_model_label.grid(
            row=2, column=0, sticky="w", padx=PAD_WIDGET, pady=PAD_WIDGET
        )
        self.create_button.grid(
            row=1, column=1, sticky="e", padx=PAD_WIDGET, pady=PAD_WIDGET
        )
        self.continue_button.grid(
            row=2, column=1, sticky="e", padx=PAD_WIDGET, pady=PAD_WIDGET
        )
