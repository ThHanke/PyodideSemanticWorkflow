from rdflib import Graph, Namespace, URIRef, BNode, Literal
from rdflib.namespace import RDF, XSD
import uuid

# Standard vocabularies
PROV = Namespace("http://www.w3.org/ns/prov#")
QUDT = Namespace("http://qudt.org/schema/qudt/")
UNIT = Namespace("http://qudt.org/vocab/unit/")
OA   = Namespace("http://www.w3.org/ns/oa#")

# Domain vocabulary
EX   = Namespace("https://github.com/ThHanke/PyodideSemanticWorkflow/")
BFO  = Namespace("https://example.org/bfo/")

# ---------------------------------------------------------------------------
# PROV context injected by pyodide-run.js
# ---------------------------------------------------------------------------

try:
    ACTIVITY_IRI = URIRef(__PROV_ACTIVITY_ID__)
except Exception:
    ACTIVITY_IRI = None

try:
    AGENT_IRI = URIRef(__PROV_AGENT_ID__)
except Exception:
    AGENT_IRI = None

try:
    PLAN_IRI = URIRef(__PROV_PLAN__)
except Exception:
    PLAN_IRI = None


def _add_error(g: Graph, activity, message: str, code: str | None = None) -> None:
    """Add an error as a Web Annotation."""
    ann_iri = URIRef(f"#errorAnn_{uuid.uuid4().hex}")
    body = BNode()

    g.bind("prov", PROV)
    g.bind("oa", OA)
    g.bind("ex", EX)

    g.add((ann_iri, RDF.type, OA.Annotation))
    g.add((ann_iri, OA.motivatedBy, EX.errorReporting))
    g.add((ann_iri, OA.hasBody, body))

    if activity is not None:
        g.add((ann_iri, OA.hasTarget, activity))
        g.add((ann_iri, PROV.wasGeneratedBy, activity))

    g.add((body, RDF.type, OA.TextualBody))
    g.add((body, RDF.value, Literal(message, datatype=XSD.string)))

    if code is not None:
        g.add((body, EX.errorCode, Literal(code, datatype=XSD.string)))


def _ensure_prov_context(g: Graph, activity):
    """Ensure Activity, Agent, and Plan exist and are linked."""
    if activity is not None:
        g.add((activity, RDF.type, PROV.Activity))

        if AGENT_IRI is not None:
            g.add((AGENT_IRI, RDF.type, PROV.Agent))
            g.add((activity, PROV.wasAssociatedWith, AGENT_IRI))

        if PLAN_IRI is not None:
            g.add((PLAN_IRI, RDF.type, PROV.Plan))
            g.add((activity, PROV.used, PLAN_IRI))


def run(graph_ttl: str) -> str:
    g = Graph()

    try:
        g.parse(data=graph_ttl, format="turtle")
    except Exception as e:
        g = Graph()
        g.bind("prov", PROV)
        g.bind("oa", OA)
        g.bind("ex", EX)
        _add_error(
            g,
            activity=None,
            message=f"Failed to parse input graph: {e}",
            code="PARSE_ERROR"
        )
        result = g.serialize(format="turtle")
        return result

    # Bind prefixes
    g.bind("prov", PROV)
    g.bind("qudt", QUDT)
    g.bind("unit", UNIT)
    g.bind("bfo", BFO)
    g.bind("oa", OA)
    g.bind("ex", EX)

    # 1) Determine the activity
    activity = next(g.subjects(RDF.type, PROV.Activity), None)

    if activity is None and ACTIVITY_IRI is not None:
        activity = ACTIVITY_IRI
        g.add((activity, RDF.type, PROV.Activity))

    if activity is None:
        _add_error(
            g,
            activity=None,
            message="No prov:Activity found or provided",
            code="NO_ACTIVITY"
        )
        result = g.serialize(format="turtle")
        return result

    _ensure_prov_context(g, activity)

    # 2) Find inputs
    inputs = [
        qv for qv in g.subjects(BFO.is_input_of, activity)
        if (qv, RDF.type, QUDT.QuantityValue) in g
    ]

    if len(inputs) < 2:
        _add_error(
            g,
            activity=activity,
            message="Expected at least two qudt:QuantityValue inputs linked via bfo:is_input_of",
            code="INPUT_TOO_FEW"
        )
        result = g.serialize(format="turtle")
        return result

    # 3) Read numeric values
    values = []
    units = set()

    for qv in inputs:
        num = g.value(qv, QUDT.numericValue)
        unit = g.value(qv, QUDT.unit)

        if num is None:
            _add_error(g, activity, f"Input {qv} has no qudt:numericValue", "MISSING_NUMERIC_VALUE")
            return g.serialize(format="turtle")

        try:
            values.append(float(num))
        except Exception:
            _add_error(g, activity, f"Input {qv} has non-numeric value {num}", "NON_NUMERIC_VALUE")
            return g.serialize(format="turtle")

        if unit is not None:
            units.add(unit)

    if len(units) > 1:
        _add_error(
            g,
            activity,
            "Inputs have different units: " + ", ".join(str(u) for u in units),
            "UNIT_MISMATCH"
        )
        return g.serialize(format="turtle")

    unit_iri = next(iter(units)) if units else UNIT.MilliM

    # 4) Compute
    total = sum(values)

    # 5) Create result
    result_qv = URIRef(f"#sumResult_{uuid.uuid4().hex}")
    g.add((result_qv, RDF.type, QUDT.QuantityValue))
    g.add((result_qv, QUDT.numericValue, Literal(total, datatype=XSD.decimal)))
    g.add((result_qv, QUDT.unit, unit_iri))
    g.add((result_qv, PROV.wasGeneratedBy, activity))

    for qv in inputs:
        g.add((result_qv, PROV.wasDerivedFrom, qv))

    result = g.serialize(format="turtle")
    return result


# ---------------------------------------------------------------------------
# Pyodide / Node contract
# ---------------------------------------------------------------------------

# This is what pyodide-run.js looks for
result_ttl = run(__INPUT_GRAPH_TTL__) if "__INPUT_GRAPH_TTL__" in globals() else None


if __name__ == "__main__":
    import sys
    input_ttl = sys.stdin.read()
    print(run(input_ttl))
