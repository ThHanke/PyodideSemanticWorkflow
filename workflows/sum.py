"""
Sum two or more QUDT QuantityValues.

Input entities are discovered via prov:used on the activity, filtered to those
that also carry p-plan:correspondsToVariable (i.e. are run-level p-plan:Entity
instances for input variables).

Output: Single QUDT QuantityValue with the sum and shared unit.
"""

import hashlib

from rdflib import Graph, Namespace, URIRef, BNode, Literal
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


def _add_error(g: Graph, activity, message: str, code: str = None,
               data_ns: str = "http://example.com/",
               execution_hash: str = "unknown") -> None:
    """Record an error as a Web Annotation (W3C OA) targeting the activity."""
    ann_iri = create_output_iri(data_ns, "errorAnn", execution_hash)
    body = BNode()

    g.bind("oa",      OA)
    g.bind("dcterms", DCTERMS)
    g.bind("prov",    PROV)

    g.add((ann_iri, RDF.type,        OA.Annotation))
    g.add((ann_iri, OA.motivatedBy,  OA.assessing))
    g.add((ann_iri, OA.hasBody,      body))

    if activity is not None:
        g.add((ann_iri, OA.hasTarget,        activity))
        g.add((ann_iri, PROV.wasGeneratedBy, activity))

    g.add((body, RDF.type,             OA.TextualBody))
    g.add((body, RDF.value,            Literal(message, datatype=XSD.string)))
    if code is not None:
        g.add((body, DCTERMS.identifier, Literal(code, datatype=XSD.string)))


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
        g = Graph()
        _add_error(g, activity=None,
                   message=f"Failed to parse input graph: {e}",
                   code="PARSE_ERROR",
                   data_ns=data_ns)
        return g.serialize(format="turtle")

    g.bind("prov",    PROV)
    g.bind("p-plan",  PPLAN)
    g.bind("qudt",    QUDT)
    g.bind("unit",    UNIT)
    g.bind("oa",      OA)
    g.bind("dcterms", DCTERMS)

    activity = URIRef(activity_iri)

    # Find input entities: things the activity prov:used that are p-plan:Entity
    # instances (i.e. carry p-plan:correspondsToVariable)
    inputs = [
        entity for entity in g.objects(activity, PROV.used)
        if (entity, PPLAN.correspondsToVariable, None) in g
        and (entity, RDF.type, QUDT.QuantityValue) in g
    ]

    execution_hash = create_execution_hash(activity_iri, *[str(qv) for qv in inputs])

    if len(inputs) < 2:
        _add_error(g, activity,
                   f"Expected at least 2 qudt:QuantityValue inputs linked via "
                   f"prov:used + p-plan:correspondsToVariable. Found {len(inputs)}.",
                   code="INPUT_TOO_FEW",
                   data_ns=data_ns,
                   execution_hash=execution_hash)
        return g.serialize(format="turtle")

    values = []
    units = set()

    for qv in inputs:
        num = g.value(qv, QUDT.numericValue)
        unit = g.value(qv, QUDT.unit)

        if num is None:
            _add_error(g, activity, f"Input {qv} has no qudt:numericValue",
                       "MISSING_NUMERIC_VALUE", data_ns=data_ns,
                       execution_hash=execution_hash)
            return g.serialize(format="turtle")

        try:
            values.append(float(num))
        except Exception:
            _add_error(g, activity, f"Input {qv} has non-numeric value {num}",
                       "NON_NUMERIC_VALUE", data_ns=data_ns,
                       execution_hash=execution_hash)
            return g.serialize(format="turtle")

        if unit is not None:
            units.add(unit)

    if len(units) > 1:
        _add_error(g, activity,
                   "Inputs have different units: " + ", ".join(str(u) for u in units),
                   code="UNIT_MISMATCH", data_ns=data_ns,
                   execution_hash=execution_hash)
        return g.serialize(format="turtle")

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
    cleanup_previous_result(g, result_iri)

    g.add((result_iri, RDF.type,                  QUDT.QuantityValue))
    g.add((result_iri, RDF.type,                  PROV.Entity))
    g.add((result_iri, RDF.type,                  PPLAN.Entity))
    g.add((result_iri, RDFS.label,                Literal(f"Sum of {len(values)} values")))
    g.add((result_iri, QUDT.numericValue,         Literal(total, datatype=XSD.decimal)))
    g.add((result_iri, QUDT.unit,                 unit_iri))
    g.add((result_iri, PROV.wasGeneratedBy,       activity))

    if out_var:
        g.add((result_iri, PPLAN.correspondsToVariable, out_var))

    for qv in inputs:
        g.add((result_iri, PROV.wasDerivedFrom, qv))

    return g.serialize(format="turtle")
