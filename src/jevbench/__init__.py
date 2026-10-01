"""JevBench: metamorphic coherence tests for Jev-compatible typed decision models.

    import jevbench as jb

    model = jb.systemone("http://localhost:8000/v1/systemone", model="my-model")
    report = jb.evaluate(model)          # jevbench-mini, the reported suite
    print(report.table("group"))

See `jevbench.api` for the whole interface.
"""

__version__ = "0.1.0"

from jevbench.api import (  # noqa: E402 - the version must exist before the engine imports it
    AnswerFormatError,
    Case,
    ModelError,
    Report,
    check,
    compare,
    describe,
    estimate,
    evaluate,
    fake,
    from_callable,
    list_dimensions,
    list_groups,
    list_relations,
    load_cases,
    load_suite,
    radar,
    select_relations,
    systemone,
)
from jevbench.relations import register  # noqa: E402
from jevbench.suites import list_suites  # noqa: E402

__all__ = ["AnswerFormatError", "Case", "ModelError", "Report", "__version__", "check", "compare", "describe",
           "estimate", "evaluate", "fake", "from_callable", "list_dimensions", "list_groups", "list_relations",
           "list_suites", "load_cases", "load_suite", "radar", "register", "select_relations", "systemone"]
