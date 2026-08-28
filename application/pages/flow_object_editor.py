import tkinter as tk
from tkinter import ttk

from dese.constants import PAD_FRAME_IN, PAD_WIDGET


class FlowObjectEditor:
    def __init__(self, parent):
        self.window = tk.Toplevel(parent)
        self.window.title("Flow Objects")
        self.window.geometry("900x600")

        # Grid:
        self.window.rowconfigure(0, weight=1)
        self.window.columnconfigure(0, weight=1)

        self.create_widgets()

    # ==========================
    # Methods
    # ==========================

    def add_flow_object(self):
        flow_object_name = f"Flow Object {self.flow_object_listbox.size() + 1}"

        self.flow_object_listbox.insert(tk.END, flow_object_name)
        self.flow_object_listbox.selection_clear(0, tk.END)
        self.flow_object_listbox.selection_set(tk.END)

    def delete_flow_object(self):
        selected_index = self.flow_object_listbox.curselection()

        if not selected_index:
            return

        self.flow_object_listbox.delete(selected_index[0])

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

        # Display widgets:
        self.right_frame.grid(row=0, column=1, sticky="nsew")
