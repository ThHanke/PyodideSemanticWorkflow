"""
Sum two or more QUDT QuantityValues.

Input entities are discovered via prov:used on the activity, filtered to those
that also carry p-plan:correspondsToVariable (i.e. are run-level p-plan:Entity
instances for input variables).

Output: Single QUDT QuantityValue with the sum and shared unit.
"""

import hashlib

from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, RDFS, XSD

# Standard vocabularies
PROV    = Namespace("http://www.w3.org/ns/prov#")
PPLAN   = Namespace("http://purl.org/net/p-plan#")
QUDT    = Namespace("http://qudt.org/schema/qudt/")
UNIT    = Namespace("http://qudt.org/vocab/unit/")
OA      = Namespace("http://www.w3.org/ns/oa#")
DCTERMS = Namespace("http://purl.org/dc/terms/")


# ---------------------------------------------------------------------------
# IRI helpers
# ---------------------------------------------------------------------------

def data_ns_from_activity(activity_iri: str) -> str:
    """Derive the data namespace from the activity IRI.

    The activity IRI is already in the correct default namespace
    (e.g. http://example.com/SumRun_123), so we strip the local name
    to get the base namespace for all output IRIs.
    """
    iri = str(activity_iri)
    idx = max(iri.rfind('#'), iri.rfind('/'))
    return iri[:idx + 1] if idx >= 0 else iri + '/'


def create_execution_hash(activity_iri: str, *input_iris: str) -> str:
    """Deterministic hash from activity IRI + input IRIs (order-independent)."""
    sorted_inputs = sorted(str(iri) for iri in input_iris)
    combined = str(activity_iri) + ''.join(sorted_inputs)
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()[:16]


def local_name(iri) -> str:
    """Extract the local name from an IRI (after the last # or /)."""
    s = str(iri)
    idx = max(s.rfind('#'), s.rfind('/'))
    return s[idx + 1:] if idx >= 0 else s


def create_output_iri(data_ns: str, prefix: str, execution_hash: str) -> URIRef:
    """Create a data-namespace IRI for an output entity (used for error annotations)."""
    return URIRef(f"{data_ns}{prefix}_{execution_hash}")


def activity_output_iri(activity_iri: str, out_var) -> URIRef:
    """Derive the output entity IRI from the activity IRI + P-Plan output variable.

    Matches the IRI the app creates during instantiation:
        activityIri + '_' + localname(outputVariable)
    e.g. http://example.com/SumRun_1234_SumOutput
    """
    return URIRef(f"{activity_iri}_{local_name(out_var)}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def cleanup_previous_result(g: Graph, result_iri: URIRef) -> int:
    """Remove all triples for a previous result entity (idempotent re-runs)."""
    triples = list(g.triples((result_iri, None, None))) + \
              list(g.triples((None, None, result_iri)))
    for t in triples:
        g.remove(t)
    return len(triples)


def _new_output_graph() -> Graph:
    """Create a fresh output graph with standard prefix bindings."""
    out = Graph()
    out.bind("prov",    PROV)
    out.bind("p-plan",  PPLAN)
    out.bind("qudt",    QUDT)
    out.bind("unit",    UNIT)
    out.bind("oa",      OA)
    out.bind("dcterms", DCTERMS)
    return out


def _add_error(out: Graph, activity, message: str, code: str = None,
               data_ns: str = "http://example.com/",
               execution_hash: str = "unknown",
               target=None) -> None:
    """Record an error as a Web Annotation (W3C OA).

    oa:hasTarget  → the entity the error is about (defaults to activity).
    prov:wasGeneratedBy → always the activity.
    Message and code are placed directly on the annotation IRI (no blank node body).
    """
    ann_iri = create_output_iri(data_ns, "errorAnn", execution_hash)
    effective_target = target if target is not None else activity

    out.add((ann_iri, RDF.type,        OA.Annotation))
    out.add((ann_iri, OA.motivatedBy,  OA.assessing))
    out.add((ann_iri, RDFS.label,      Literal(message, datatype=XSD.string)))
    out.add((ann_iri, RDF.value,       Literal(message, datatype=XSD.string)))

    if effective_target is not None:
        out.add((ann_iri, OA.hasTarget, effective_target))
    if activity is not None:
        out.add((ann_iri, PROV.wasGeneratedBy, activity))

    if code is not None:
        out.add((ann_iri, DCTERMS.identifier, Literal(code, datatype=XSD.string)))


# ---------------------------------------------------------------------------
# Dynamic input resolution
# ---------------------------------------------------------------------------

def _get_var_label(g: Graph, entity) -> str:
    """Return the rdfs:label of the p-plan:Variable this entity corresponds to."""
    var = g.value(entity, PPLAN.correspondsToVariable)
    if var is None:
        return ""
    label = g.value(var, RDFS.label)
    return str(label) if label is not None else ""


def resolve_missing_entity_inputs(g: Graph, activity: URIRef) -> tuple:
    """Prompt the user for any QuantityValue inputs that lack qudt:numericValue.

    Discovers input entities via prov:used + p-plan:correspondsToVariable,
    checks each for qudt:numericValue, and if missing queries the graph for
    existing QuantityValue instances the user can select from a dropdown.

    Selected entity data (numericValue, unit) is copied to the empty
    placeholder so downstream computation reads it normally.

    Returns (errors, output_triples) where:
      - errors: list of error message strings (empty = all resolved OK)
      - output_triples: list of (s, p, o) provenance triples to add to
        the output graph
    """
    # Collect input entities that correspond to a template variable
    # and are typed as qudt:QuantityValue
    inputs = [
        entity for entity in g.objects(activity, PROV.used)
        if (entity, PPLAN.correspondsToVariable, None) in g
        and (entity, RDF.type, QUDT.QuantityValue) in g
    ]

    errors = []
    output_triples = []

    for entity in inputs:
        # Skip entities that already have a numeric value
        if g.value(entity, QUDT.numericValue) is not None:
            continue

        # Build the set of entities to exclude from candidates:
        # 1. All entities prov:used by this activity that have
        #    p-plan:correspondsToVariable (the activity's own input
        #    variable instances — includes filled placeholders on re-run)
        own_inputs = set(
            e for e in g.objects(activity, PROV.used)
            if (e, PPLAN.correspondsToVariable, None) in g
        )

        # 2. Entities prov:wasGeneratedBy this activity (previous outputs)
        own_outputs = set(g.subjects(PROV.wasGeneratedBy, activity))

        exclude = own_inputs | own_outputs

        # Query graph for all qudt:QuantityValue instances with a numericValue
        candidates = []
        for qv in g.subjects(RDF.type, QUDT.QuantityValue):
            if qv in exclude:
                continue
            num = g.value(qv, QUDT.numericValue)
            if num is None:
                continue
            candidates.append(qv)

        if not candidates:
            errors.append(
                "No QuantityValue instances found in graph. Load data first."
            )
            return errors, output_triples

        # Build dropdown options with human-readable labels
        options = []
        for qv in candidates:
            rdfs_label = g.value(qv, RDFS.label)
            num_val = g.value(qv, QUDT.numericValue)
            unit = g.value(qv, QUDT.unit)
            unit_label = g.value(unit, RDFS.label) if unit else None
            if unit_label is None and unit is not None:
                unit_label = local_name(unit)

            display = str(rdfs_label) if rdfs_label else local_name(qv)
            if num_val is not None:
                unit_str = f" {unit_label}" if unit_label else ""
                display = f"{display} ({num_val}{unit_str})"

            options.append({'label': display, 'value': str(qv)})

        var_label = _get_var_label(g, entity)
        prompt_label = var_label if var_label else "QuantityValue"

        try:
            selected_iri = request_input(  # noqa: F821 — injected at runtime
                f"Select {prompt_label}:", 'select', options=options
            )
        except Exception as exc:
            errors.append(
                f"Input prompt for '{prompt_label}' failed: {exc}"
            )
            continue

        if not selected_iri or not str(selected_iri).strip():
            errors.append(
                f"No value selected for '{prompt_label}'."
            )
            continue

        selected = URIRef(str(selected_iri).strip())

        # Copy numericValue and unit from selected entity to the placeholder
        num_val = g.value(selected, QUDT.numericValue)
        if num_val is not None:
            g.add((entity, QUDT.numericValue, num_val))
        unit_val = g.value(selected, QUDT.unit)
        if unit_val is not None:
            g.add((entity, QUDT.unit, unit_val))

        # Provenance: activity used the selected entity;
        # placeholder was derived from it
        output_triples.append((activity, PROV.used, selected))
        output_triples.append((entity, PROV.wasDerivedFrom, selected))

    return errors, output_triples


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(input_turtle: str, activity_iri: str) -> str:
    """
    Main entry point called by Pyodide runtime.

    Args:
        input_turtle: Input graph in Turtle format
        activity_iri: IRI of the prov:Activity being executed

    Returns:
        Output graph in Turtle format
    """
    data_ns = data_ns_from_activity(activity_iri)
    g = Graph()

    try:
        g.parse(data=input_turtle, format="turtle")
    except Exception as e:
        out = _new_output_graph()
        _add_error(out, activity=None,
                   message=f"Failed to parse input graph: {e}",
                   code="PARSE_ERROR",
                   data_ns=data_ns)
        return out.serialize(format="turtle")

    activity = URIRef(activity_iri)

    # Find input entities: things the activity prov:used that are p-plan:Entity
    # instances (i.e. carry p-plan:correspondsToVariable)
    inputs = [
        entity for entity in g.objects(activity, PROV.used)
        if (entity, PPLAN.correspondsToVariable, None) in g
        and (entity, RDF.type, QUDT.QuantityValue) in g
    ]

    execution_hash = create_execution_hash(activity_iri, *[str(qv) for qv in inputs])
    out = _new_output_graph()

    if len(inputs) < 2:
        _add_error(out, activity,
                   f"Expected at least 2 qudt:QuantityValue inputs linked via "
                   f"prov:used + p-plan:correspondsToVariable. Found {len(inputs)}.",
                   code="INPUT_TOO_FEW",
                   data_ns=data_ns,
                   execution_hash=execution_hash)
        return out.serialize(format="turtle")

    # Prompt for any missing entity inputs (QuantityValue without numericValue).
    # This modifies g in place — copies numericValue/unit from selected entities
    # to placeholders so the value extraction loop below reads them normally.
    input_errors, prov_triples = resolve_missing_entity_inputs(g, activity)
    if input_errors:
        missing_inp = next(
            (inp for inp in inputs if g.value(inp, QUDT.numericValue) is None),
            None
        )
        _add_error(out, activity,
                   "; ".join(input_errors),
                   code="INPUT_PROMPT_FAILED", data_ns=data_ns,
                   execution_hash=execution_hash, target=missing_inp)
        return out.serialize(format="turtle")

    # Add provenance triples from input resolution to output graph
    for s, p, o in prov_triples:
        out.add((s, p, o))

    values = []
    units = set()

    for qv in inputs:
        num = g.value(qv, QUDT.numericValue)
        unit = g.value(qv, QUDT.unit)

        if num is None:
            _add_error(out, activity, f"Input {qv} has no qudt:numericValue",
                       "MISSING_NUMERIC_VALUE", data_ns=data_ns,
                       execution_hash=execution_hash, target=qv)
            return out.serialize(format="turtle")

        try:
            values.append(float(num))
        except Exception:
            _add_error(out, activity, f"Input {qv} has non-numeric value {num}",
                       "NON_NUMERIC_VALUE", data_ns=data_ns,
                       execution_hash=execution_hash, target=qv)
            return out.serialize(format="turtle")

        if unit is not None:
            units.add(unit)

    if len(units) > 1:
        _add_error(out, activity,
                   "Inputs have different units: " + ", ".join(str(u) for u in units),
                   code="UNIT_MISMATCH", data_ns=data_ns,
                   execution_hash=execution_hash)
        return out.serialize(format="turtle")

    unit_iri = next(iter(units)) if units else UNIT.MilliM
    total = sum(values)

    # Find the template output variable this result corresponds to
    step = g.value(activity, PPLAN.correspondsToStep)
    out_var = g.value(predicate=PPLAN.isOutputVarOf, object=step) if step else None

    # Build result IRI — derived from activityIri + P-Plan output variable local name,
    # matching the placeholder the app created during workflow instantiation.
    if out_var:
        result_iri = activity_output_iri(activity_iri, out_var)
    else:
        result_iri = create_output_iri(data_ns, "sumResult", execution_hash)

    out.add((result_iri, RDF.type,                  QUDT.QuantityValue))
    out.add((result_iri, RDF.type,                  PROV.Entity))
    out.add((result_iri, RDF.type,                  PPLAN.Entity))
    out.add((result_iri, RDFS.label,                Literal(f"Sum of {len(values)} values")))
    out.add((result_iri, QUDT.numericValue,         Literal(total, datatype=XSD.decimal)))
    out.add((result_iri, QUDT.unit,                 unit_iri))
    out.add((result_iri, PROV.wasGeneratedBy,       activity))

    if out_var:
        out.add((result_iri, PPLAN.correspondsToVariable, out_var))

    for qv in inputs:
        out.add((result_iri, PROV.wasDerivedFrom, qv))

    return out.serialize(format="turtle")
