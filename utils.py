import sys


def validate_number(value):
    if value == "":
        return True

    try:
        float(value)
        return True

    except ValueError:
        return False


def convert_property_value(value, property_type):
    if property_type == "number" and value != "":
        return float(value)

    return value


def generate_id(existing_ids, prefix):
    number = 1

    while f"{prefix}{number:03d}" in existing_ids:
        number += 1

    return f"{prefix}{number:03d}"


def bind_canvas_mousewheel(canvas):
    # A ttk.Scrollbar alone only scrolls while the cursor is over the
    # scrollbar itself. This binds the wheel/trackpad directly (and
    # recursively) on the canvas and everything currently inside it, so it
    # scrolls from anywhere over it (like a Treeview or a web page) —
    # without the bind_all()-on-<Enter>/<Leave> idiom, whose global
    # (application-wide) binding can outlive an unreliable <Leave> (e.g. one
    # that doesn't fire cleanly when the pointer crosses onto a child
    # widget) and then keep hijacking wheel input elsewhere.
    #
    # Call this again after rebuilding the canvas's content (destroying and
    # re-adding child widgets) — bind() replaces any previous handler on a
    # widget, so re-running this is safe and picks up the new children.
    #
    # tk.Canvas.yview_scroll(n, "units") is a no-op unless yscrollincrement
    # is set (it defaults to 0) — this is what actually makes each wheel
    # notch move the canvas by a real, fixed pixel amount. Kept small so the
    # scroll feels smooth/granular rather than jumping in big steps.
    canvas.configure(yscrollincrement=6)

    def on_mousewheel(event):
        if sys.platform == "darwin":
            canvas.yview_scroll(int(-1 * event.delta), "units")
        else:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def on_scroll_up(event):
        canvas.yview_scroll(-1, "units")

    def on_scroll_down(event):
        canvas.yview_scroll(1, "units")

    def bind_widget(widget):
        widget.bind("<MouseWheel>", on_mousewheel)
        widget.bind("<Button-4>", on_scroll_up)
        widget.bind("<Button-5>", on_scroll_down)

        for child in widget.winfo_children():
            bind_widget(child)

    bind_widget(canvas)
