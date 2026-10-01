DESE documentation
==================

DESE (Discrete Event Simulation Engine) is a learning project: a schema-driven
discrete-event simulation tool with a Tkinter GUI. Build a process model
(entities, relationships, routing rules), run a simulation against it, and
export the resulting event log as CSV.

This is a beginner portfolio project, built AI-assisted with Claude Code --
as much a way to consolidate what was learned from books and tools into one
real, working thing as it is a demo piece. The simulation core (the event
loop, routing, retry/fairness logic under ``dese.engine``) is AI-generated,
SimPy-like logic rather than a hand-designed algorithm -- see the project's
README for the full disclosure. Directing that collaboration -- the
schema-driven GUI/data-model design, the project's structure, and the
iterative debugging that came with it -- was the author's own effort.

This site is generated from the docstrings in ``src/dese`` -- every module,
class and function listed under *API Reference* links back to its own page.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   api/modules

