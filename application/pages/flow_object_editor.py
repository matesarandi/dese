import tkinter as tk
from tkinter import messagebox, ttk

from dese.constants import INPUT_WIDTH, PAD_FRAME_IN, PAD_WIDGET
from dese.utils import validate_number


class FlowObjectEditor:
    def __init__(self, parent, model_data, schema, model_changed_callback):
        self.window = tk.Toplevel(parent)
        self.window.title("Flow Objects")
        self.window.geometry("900x600")
        self.model_data = model_data
        self.schema = schema
        self.model_changed_callback = model_changed_callback

        # Grid:
        self.window.rowconfigure(0, weight=1)
        self.window.columnconfigure(0, weight=1)

        self.create_widgets()

    # ==========================
    # Methods
    # ==========================

    def is_flow_object_name_unique(self, flow_object, name):
        return all(
            other_flow_object is flow_object or other_flow_object["name"] != name
            for other_flow_object in self.model_data["flow_objects"]
        )

    def validate_flow_object_name(self, flow_object, name, variable):
        if not self.is_flow_object_name_unique(flow_object, name):
            messagebox.showwarning("Duplicate name", "Cannot use the same name.")

            variable.set(flow_object["name"])
            return False

        self.update_flow_object_property(flow_object, "name", name, "string")
        return True

    def add_flow_object(self):
        flow_object_schema = self.schema.get_flow_object_schema()

        flow_object = {}

        # Required properties:
        for property_name in flow_object_schema["required_properties"]:
            flow_object[property_name] = None

        number = 1

        while any(
            flow_object["name"] == f"Flow Object {number}"
            for flow_object in self.model_data["flow_objects"]
        ):
            number += 1

        flow_object["name"] = f"Flow Object {number}"

        # Properties:
        flow_object["properties"] = {}

        for property_name in flow_object_schema["properties"]:
            flow_object["properties"][property_name] = None

        self.model_data["flow_objects"].append(flow_object)

        self.model_changed_callback(True)

        self.flow_object_listbox.insert(tk.END, flow_object["name"])

        self.flow_object_listbox.selection_clear(0, tk.END)
        self.flow_object_listbox.selection_set(tk.END)

    def select_flow_object(self, event=None):
        selected_index = self.flow_object_listbox.curselection()

        if not selected_index:
            return

        flow_object = self.model_data["flow_objects"][selected_index[0]]

        self.display_flow_object_properties(flow_object)

    def update_flow_object_property(
        self, flow_object, property_name, value, property_type
    ):
        if property_type == "number" and value != "":
            value = float(value)

        flow_object[property_name] = value

        if property_name == "name":
            flow_object_index = next(
                index
                for index, item in enumerate(self.model_data["flow_objects"])
                if item is flow_object
            )

            self.flow_object_listbox.delete(flow_object_index)
            self.flow_object_listbox.insert(flow_object_index, flow_object["name"])
            self.flow_object_listbox.selection_set(flow_object_index)

        self.model_changed_callback(True)

    def get_processing_entities(self):
        return [
            entity
            for entity in self.model_data["entities"]
            if entity["type"] == "Processing"
        ]

    def get_processing_entity_names(self):
        return [entity["name"] for entity in self.get_processing_entities()]

    def get_processing_entity_id(self, entity_name):
        for entity in self.get_processing_entities():
            if entity["name"] == entity_name:
                return entity["id"]

    def display_flow_object_properties(self, flow_object):
        for widget in self.right_frame.winfo_children():
            widget.destroy()

        flow_object_schema = self.schema.get_flow_object_schema()

        row = 0

        # Required Properties
        # ==========================

        # Child widgets + display child widgets:

        for property_name, property_schema in flow_object_schema[
            "required_properties"
        ].items():
            ttk.Label(
                self.right_frame, text=property_name.replace("_", " ").title()
            ).grid(row=row, column=0, sticky="w", padx=PAD_WIDGET, pady=PAD_WIDGET)

            variable = tk.StringVar(value=str(flow_object[property_name] or ""))

            entry = ttk.Entry(
                self.right_frame, width=INPUT_WIDTH, textvariable=variable
            )

            entry.grid(row=row, column=1, sticky="ew", padx=PAD_WIDGET, pady=PAD_WIDGET)

            # Event binding:
            if property_name == "name":
                entry.bind(
                    "<FocusOut>",
                    lambda event, flow_object=flow_object, variable=variable: (
                        self.validate_flow_object_name(
                            flow_object, variable.get(), variable
                        )
                    ),
                )

                entry.bind(
                    "<Return>",
                    lambda event, flow_object=flow_object, variable=variable: (
                        self.validate_flow_object_name(
                            flow_object, variable.get(), variable
                        )
                    ),
                )

            else:
                variable.trace_add(
                    "write",
                    lambda *args, property_name=property_name, property_type=property_schema["type"], variable=variable: (
                        self.update_flow_object_property(
                            flow_object, property_name, variable.get(), property_type
                        )
                    ),
                )

            row += 1

        # Properties
        # ==========================

        # Child widgets + display child widgets:

        for property_name, property_description in flow_object_schema[
            "properties"
        ].items():
            if property_name == "entry_entity":
                entry = ttk.Combobox(
                    self.right_frame,
                    values=self.get_processing_entity_names(),
                    state="readonly",
                    width=INPUT_WIDTH,
                )

                # Event binding:
                entry.bind(
                    "<<ComboboxSelected>>",
                    lambda event, entry=entry, flow_object=flow_object: (
                        self.update_flow_object_property(
                            flow_object["properties"],
                            "entry_entity",
                            self.get_processing_entity_id(entry.get()),
                            "string",
                        )
                    ),
                )

                # Display current value:
                current_entity_id = flow_object["properties"].get("entry_entity")

                if current_entity_id:
                    for entity in self.get_processing_entities():
                        if entity["id"] == current_entity_id:
                            entry.set(entity["name"])
                            break

            ttk.Label(
                self.right_frame, text=property_name.replace("_", " ").title()
            ).grid(row=row, column=0, sticky="w", padx=PAD_WIDGET, pady=PAD_WIDGET)

            if property_name != "entry_entity":
                variable = tk.StringVar(
                    value=str(flow_object["properties"][property_name] or "")
                )

                if property_description["type"] == "number":
                    validate_command = (
                        self.window.register(self.validate_number),
                        "%P",
                    )

                    entry = ttk.Entry(
                        self.right_frame,
                        width=INPUT_WIDTH,
                        textvariable=variable,
                        validate="key",
                        validatecommand=validate_command,
                    )

                else:
                    entry = ttk.Entry(
                        self.right_frame, width=INPUT_WIDTH, textvariable=variable
                    )

                # Event binding:
                variable.trace_add(
                    "write",
                    lambda *args, property_name=property_name, property_type=property_description["type"], variable=variable: (
                        self.update_flow_object_property(
                            flow_object["properties"],
                            property_name,
                            variable.get(),
                            property_type,
                            variable,
                        )
                    ),
                )

            entry.grid(row=row, column=1, sticky="ew", padx=PAD_WIDGET, pady=PAD_WIDGET)

            row += 1

    def load_flow_objects(self):
        self.flow_object_listbox.delete(0, tk.END)

        for flow_object in self.model_data["flow_objects"]:
            self.flow_object_listbox.insert(tk.END, flow_object["name"])

    def delete_flow_object(self):
        selected_index = self.flow_object_listbox.curselection()

        if not selected_index:
            return

        del self.model_data["flow_objects"][selected_index[0]]
        self.flow_object_listbox.delete(selected_index[0])

        self.model_changed_callback(True)

    def create_widgets(self):

        # Main Frame
        # ==========================

        # Widgets:
        self.main_frame = ttk.Frame(self.window, padding=PAD_FRAME_IN)

        # Grid:
        self.main_frame.rowconfigure(0, weight=1)
        self.main_frame.columnconfigure(0, weight=0)
        self.main_frame.columnconfigure(1, weight=1)

        # Display widgets:
        self.main_frame.grid(row=0, column=0, sticky="nsew")

        # Left Frame
        # ==========================

        # Frame widget:
        self.left_frame = ttk.LabelFrame(
            self.main_frame,
            text="Flow Objects",
            style="DESE.Section.TLabelframe",
            padding=PAD_FRAME_IN,
        )

        # Grid:
        self.left_frame.rowconfigure(0, weight=1)
        self.left_frame.rowconfigure(1, weight=0)
        self.left_frame.columnconfigure(0, weight=1)

        # Child widgets:
        self.flow_object_listbox = tk.Listbox(self.left_frame)
        self.button_frame = ttk.Frame(self.left_frame)
        self.add_button = ttk.Button(
            self.button_frame, text="Add", command=self.add_flow_object
        )
        self.delete_button = ttk.Button(
            self.button_frame, text="Delete", command=self.delete_flow_object
        )

        # Event binding:
        self.flow_object_listbox.bind("<<ListboxSelect>>", self.select_flow_object)

        # Display frame widget:
        self.left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, PAD_FRAME_IN))

        # Display child widgets:
        self.flow_object_listbox.grid(
            row=0, column=0, sticky="nsew", padx=PAD_WIDGET, pady=PAD_WIDGET
        )
        self.button_frame.grid(
            row=1, column=0, sticky="ew", padx=PAD_WIDGET, pady=PAD_WIDGET
        )
        self.add_button.grid(row=0, column=0, padx=PAD_WIDGET, pady=PAD_WIDGET)
        self.delete_button.grid(row=0, column=1, padx=PAD_WIDGET, pady=PAD_WIDGET)

        # Right Frame
        # ==========================

        # Widgets:
        self.right_frame = ttk.LabelFrame(
            self.main_frame,
            text="Flow Object Properties",
            style="DESE.Section.TLabelframe",
            padding=PAD_FRAME_IN,
        )

        # Grid:
        self.right_frame.columnconfigure(1, weight=1)

        # Display widgets:
        self.right_frame.grid(row=0, column=1, sticky="nsew")

        # Load existing Flow Objects:
        self.load_flow_objects()
