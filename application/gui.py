import tkinter as tk
from tkinter import messagebox, ttk

from dese.application.pages.model_editor_page import ModelEditorPage
from dese.application.pages.start_page import StartPage
from dese.constants import INPUT_WIDTH, PAD_WIDGET
from dese.core.schema_loader import SchemaLoader
from dese.paths import SCHEMA_DIR
from dese.styles import configure_styles


class DESEApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.schema = SchemaLoader(SCHEMA_DIR / "schema.json")
        self.model_changed = False
        self.editing_model_path = None
        self.selected_model_path = None
        self.create_window()
        self.create_menu()
        self.create_navigation()
        self.create_widgets()
        self.show_start_page()

    # ----------------------------
    # METHODS
    # ----------------------------

    def update_domain_selector(self):
        domain = self.model_editor_page.model_data["domain"]

        if domain:
            self.domain_combobox.set(domain)

    def show_domain_selector(self):
        self.domain_label.grid(row=0, column=5, padx=PAD_WIDGET, pady=PAD_WIDGET)
        self.domain_combobox.grid(row=0, column=6, padx=PAD_WIDGET, pady=PAD_WIDGET)

    def hide_domain_selector(self):
        self.domain_label.grid_remove()
        self.domain_combobox.grid_remove()

    def update_domain(self):
        selected_domain = self.domain_combobox.get()

        if not selected_domain:
            return

        if not hasattr(self, "model_editor_page"):
            return

        self.model_editor_page.update_domain(selected_domain)

    def activate_model(self, model_path):
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
        if self.editing_model_path is None:
            return
        self.show_model_editor_page()

    def save_model(self):
        if hasattr(self, "model_editor_page"):
            self.model_editor_page.save_model()

    def select_model(self, model_path):
        self.selected_model_path = model_path

    def set_model_changed(self, changed):
        self.model_changed = changed

        if changed:
            self.unsaved_label.config(text="⏺")
        else:
            self.unsaved_label.config(text="")

    def create_window(self):
        # Window:
        self.geometry("500x500")
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
        # Window:
        self.geometry("500x500")
        self.resizable(False, False)

        # Hide domain selector:
        self.hide_domain_selector()

        # Clear page:
        self.clear_page()

        # Widgets:
        self.start_page = StartPage(
            self.container, self.activate_model, self.select_model
        )

        # Display widgets:
        self.start_page.grid(row=0, column=0, sticky="nsew")

    def open_start_page(self):
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
        # Window:
        self.geometry("1100x750")
        self.resizable(False, False)

        # Show domain selector:
        self.show_domain_selector()

        # Clear page:
        self.clear_page()

        # Widgets:
        self.model_editor_page = ModelEditorPage(
            self.container, self.editing_model_path, self.schema, self.set_model_changed
        )

        # Update domain selector:
        self.update_domain_selector()

        # Display widgets:
        self.model_editor_page.grid(row=0, column=0, sticky="nsew")

    def create_menu(self):

        # ----------------------------
        # Menu Bar
        # ----------------------------

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

        # ----------------------------
        # Navigation Bar
        # ----------------------------

        # Widgets:
        self.navigation_frame = ttk.Frame(self)
        self.start_button = ttk.Button(
            self.navigation_frame, text="Start", command=self.open_start_page
        )
        self.model_editor_button = ttk.Button(
            self.navigation_frame,
            text="Model Editor",
            command=self.open_model_editor,
            state="disabled",
        )
        self.model_file_label = ttk.Label(self.navigation_frame, text="")
        self.unsaved_label = ttk.Label(self.navigation_frame, text="")
        self.domain_label = ttk.Label(self.navigation_frame, text="Domain:")
        self.domain_combobox = ttk.Combobox(
            self.navigation_frame,
            state="readonly",
            values=self.schema.get_domains(),
            width=INPUT_WIDTH,
        )

        # Event binding:
        self.domain_combobox.bind(
            "<<ComboboxSelected>>", lambda event: self.update_domain()
        )

        # Display widgets:
        self.navigation_frame.grid(row=0, column=0, sticky="ew")
        self.start_button.grid(row=0, column=0, padx=PAD_WIDGET, pady=PAD_WIDGET)
        self.model_editor_button.grid(row=0, column=1, padx=PAD_WIDGET, pady=PAD_WIDGET)
        self.model_file_label.grid(row=0, column=2, padx=PAD_WIDGET, pady=PAD_WIDGET)
        self.unsaved_label.grid(row=0, column=3, padx=PAD_WIDGET, pady=PAD_WIDGET)

        # Grid:
        self.navigation_frame.columnconfigure(4, weight=1)

        # Display domain selector:
        self.domain_label.grid(row=0, column=5, padx=PAD_WIDGET, pady=PAD_WIDGET)
        self.domain_combobox.grid(row=0, column=6, padx=PAD_WIDGET, pady=PAD_WIDGET)

    # ----------------------------
    # MAIN CONTAINER
    # ----------------------------

    def create_widgets(self):

        # ----------------------------
        # Container
        # ----------------------------

        # Widgets:
        self.container = ttk.Frame(self)

        # Grid:
        self.container.rowconfigure(0, weight=1)
        self.container.columnconfigure(0, weight=1)

        # Display widgets:
        self.container.grid(row=1, column=0, sticky="nsew")


# ----------------------------
# MAIN LOOP
# ----------------------------

if __name__ == "__main__":
    app = DESEApp()
    app.mainloop()
