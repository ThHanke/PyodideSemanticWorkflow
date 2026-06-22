"""
Shared input resolution library for SPW workflow scripts.

Provides reusable functions for discovering candidate entities in the graph,
prompting users via select dropdowns, copying properties between entities,
and recording provenance. Used by workflow scripts that need dynamic input
resolution at runtime.

request_input() is injected by the Pyodide worker runtime — not imported.
"""

from rdflib import Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

PROV  = Namespace("http://www.w3.org/ns/prov#")
PPLAN = Namespace("http://purl.org/net/p-plan#")
QUDT  = Namespace("http://qudt.org/schema/qudt/")
UNIT  = Namespace("http://qudt.org/vocab/unit/")


class InputCancelled(Exception):
    pass


class InputFailed(Exception):
    pass


def get_var_label(g, entity) -> str:
    """Return rdfs:label of the p-plan:Variable this entity corresponds to."""
    var = g.value(entity, PPLAN.correspondsToVariable)
    if var is None:
        return ""
    label = g.value(var, RDFS.label)
    return str(label) if label is not None else ""


def find_candidates(g, activity, rdf_type, value_predicate=None):
    """Find graph instances of rdf_type, excluding the activity's own inputs/outputs.

    Self-filter: excludes entities prov:used by activity that have
    p-plan:correspondsToVariable (own input placeholders), and entities
    prov:wasGeneratedBy activity (own outputs).

    If value_predicate is given, only returns candidates that have a value
    for that predicate.
    """
    own_inputs = set(
        e for e in g.objects(activity, PROV.used)
        if (e, PPLAN.correspondsToVariable, None) in g
    )
    own_outputs = set(g.subjects(PROV.wasGeneratedBy, activity))
    exclude = own_inputs | own_outputs

    candidates = []
    for entity in g.subjects(RDF.type, rdf_type):
        if entity in exclude:
            continue
        if value_predicate is not None and g.value(entity, value_predicate) is None:
            continue
        candidates.append(entity)
    return candidates


def prompt_select(var_label, options):
    """Prompt user to select from options via request_input().

    Args:
        var_label: Human-readable label for the prompt.
        options: List of {label, value} dicts.

    Returns:
        The selected value string.

    Raises:
        InputCancelled: User cancelled the prompt.
        InputFailed: Prompt timed out or returned empty.
    """
    try:
        selected = request_input(  # noqa: F821 — injected at runtime
            f"Select {var_label}:", 'select', options=options
        )
    except Exception as exc:
        msg = str(exc)
        if 'cancel' in msg.lower():
            raise InputCancelled(f"Selection of '{var_label}' was cancelled.")
        raise InputFailed(f"Input prompt for '{var_label}' failed: {exc}")

    if not selected or not str(selected).strip():
        raise InputCancelled(f"No value selected for '{var_label}'.")

    return str(selected).strip()


def copy_properties(g, source, target, predicates):
    """Copy all values of each predicate from source to target in graph g."""
    for pred in predicates:
        for val in g.objects(source, pred):
            g.add((target, pred, val))


def make_provenance(activity, placeholder, selected):
    """Return provenance triples linking activity and placeholder to selected entity."""
    return [
        (activity, PROV.used, selected),
        (placeholder, PROV.wasDerivedFrom, selected),
    ]
