from tkinter import ttk

# ----------------------------
# STYLE CONFIGURATION
# ----------------------------


def configure_styles():

    style = ttk.Style()

    style.configure("DESE.Section.TLabelframe", font=("TkDefaultFont", 12, "bold"))
    style.configure(
        "DESE.Section.TLabelframe.Label", font=("TkDefaultFont", 12, "bold")
    )
