"""Small helpers for answer rules shared by the domain specifications."""

from __future__ import annotations

from jevbench.datagen.spec import UNKNOWN, known, mentioned


def fact(name):
    """Rule: the fact's value, or UNKNOWN when the text does not convey it."""
    return lambda f, m: known(f, m, name)


def test(name, pred):
    """Rule: pred(value), or UNKNOWN when the text does not convey the value."""
    return lambda f, m: (lambda v: UNKNOWN if v == UNKNOWN else pred(v))(known(f, m, name))


def said(f, m, name) -> bool:
    """'Does the text say X?': a speech act that is not said is a no."""
    return bool(mentioned(m, name) and f.get(name))


def kind_is(fact_name, *values):
    """applies=: the question is asked only for these values of the core fact."""
    return lambda f: f[fact_name] in values
