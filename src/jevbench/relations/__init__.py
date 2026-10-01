"""Relation plugins, one module per dimension. Importing this package registers all built-in relations.

    rep          REP  Representation consistency
    bat          BAT  Batch independence
    mea          MEA  Probability measure coherence
    log          LOG  Logical coherence
    cho          CHO  Choice-set coherence
    diagnostics  response fields (not scored)
    _shared      templates, probes and trial builders used by several dimensions
"""

from jevbench.relations import bat, cho, diagnostics, log, mea, rep  # noqa: F401
from jevbench import taxonomy
from jevbench.relations.base import REGISTRY, Context, Outcome, Relation, Trial, register

taxonomy.check_registry(REGISTRY)

__all__ = ["REGISTRY", "Context", "Outcome", "Relation", "Trial", "register"]
