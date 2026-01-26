from rdflib import Graph, Namespace, URIRef, BNode, Literal
from rdflib.namespace import RDF, XSD
import uuid

# Standard vocabularies

PROV = Namespace("http://www.w3.org/ns/prov#")
QUDT = Namespace("http://qudt.org/schema/qudt/")
UNIT = Namespace("http://qudt.org/vocab/unit/")
OA   = Namespace("http://www.w3.org/ns/oa#")

# Your domain vocabulary for error semantics

EX   = Namespace("https://github.com/ThHanke/PyodideSemanticWorkflow/")

# This must match the predicate used in your graph for "is input of"

# Adjust the namespace/IRI to your actual BFO IRI if needed.

BFO  = Namespace("https://example.org/bfo/")


def _add_error(g: Graph, activity, message: str, code: str | None = None) -> None:
    """
    Add an error as a Web Annotation to the graph.

    - activity: prov:Activity or None
    - message: human-readable error message
    - code: optional machine-readable error code

    Pattern:
      - an oa:Annotation (#errorAnn_...)
      - oa:hasTarget = activity (if known)
      - oa:hasBody = oa:TextualBody blank node with rdf:value and optional ex:errorCode
      - prov:wasGeneratedBy = activity (if known)
      - oa:motivatedBy = ex:errorReporting

    """
    # Annotation IRI as relative fragment
    ann_iri = URIRef(f"#errorAnn_{uuid.uuid4().hex}")
    body = BNode()

    # Ensure prefixes exist (idempotent)
    g.bind("prov", PROV)
    g.bind("oa", OA)
    g.bind("ex", EX)

    # Define motivation and errorCode term usage (no schema triples here, just use them)
    g.add((ann_iri, RDF.type, OA.Annotation))
    g.add((ann_iri, OA.motivatedBy, EX.errorReporting))
    g.add((ann_iri, OA.hasBody, body))

    if activity is not None:
        g.add((ann_iri, OA.hasTarget, activity))
        g.add((ann_iri, PROV.wasGeneratedBy, activity))

    # Body as TextualBody with message and optional code
    g.add((body, RDF.type, OA.TextualBody))
    g.add((body, RDF.value, Literal(message, datatype=XSD.string)))

    if code is not None:
        g.add((body, EX.errorCode, Literal(code, datatype=XSD.string)))


def run(graph_ttl: str) -> str:
    """
    Generic entry point for the Pyodide node.

    - graph_ttl: RDF graph in Turtle syntax (string)
    - returns: updated graph (Turtle)

    Behaviour:
      - parses the input graph
      - finds the first prov:Activity
      - finds all qudt:QuantityValue that are bfo:is_input_of that activity
      - if OK:
          - sums their qudt:numericValue
          - creates a new qudt:QuantityValue with relative IRI (#sumResult_...)
          - links result with prov:wasGeneratedBy and prov:wasDerivedFrom
      - on semantic error:
          - adds an oa:Annotation (#errorAnn_...) with a TextualBody
          - does NOT raise; always returns a graph

    """
    g = Graph()
    try:
        g.parse(data=graph_ttl, format="turtle")
    except Exception as e:
        # Cannot even parse: return a new graph with a pure error annotation (no activity)
        g = Graph()
        g.bind("prov", PROV)
        g.bind("qudt", QUDT)
        g.bind("unit", UNIT)
        g.bind("bfo", BFO)
        g.bind("oa", OA)
        g.bind("ex", EX)
        _add_error(
            g,
            activity=None,
            message=f"Failed to parse input graph: {e}",
            code="PARSE_ERROR"
        )
        return g.serialize(format="turtle")

    # Bind prefixes for nicer output (optional)
    g.bind("prov", PROV)
    g.bind("qudt", QUDT)
    g.bind("unit", UNIT)
    g.bind("bfo", BFO)
    g.bind("oa", OA)
    g.bind("ex", EX)

    # 1) Find the activity to execute
    activity = next(g.subjects(RDF.type, PROV.Activity), None)
    if activity is None:
        _add_error(
            g,
            activity=None,
            message="No prov:Activity found in graph",
            code="NO_ACTIVITY"
        )
        return g.serialize(format="turtle")

    # 2) Find all QUDT QuantityValues that are inputs to this activity
    inputs = []
    for qv in g.subjects(BFO.is_input_of, activity):
        if (qv, RDF.type, QUDT.QuantityValue) in g:
            inputs.append(qv)

    if len(inputs) < 2:
        _add_error(
            g,
            activity=activity,
            message="Expected at least two qudt:QuantityValue inputs linked via bfo:is_input_of",
            code="INPUT_TOO_FEW"
        )
        return g.serialize(format="turtle")

    # 3) Read numeric values and units
    values = []
    units = set()

    for qv in inputs:
        num = g.value(qv, QUDT.numericValue)
        unit = g.value(qv, QUDT.unit)

        if num is None:
            _add_error(
                g,
                activity=activity,
                message=f"Input {qv} has no qudt:numericValue",
                code="MISSING_NUMERIC_VALUE"
            )
            return g.serialize(format="turtle")

        try:
            values.append(float(num))
        except Exception:
            _add_error(
                g,
                activity=activity,
                message=f"Input {qv} has a non-numeric qudt:numericValue: {num}",
                code="NON_NUMERIC_VALUE"
            )
            return g.serialize(format="turtle")

        if unit is not None:
            units.add(unit)

    if len(units) > 1:
        _add_error(
            g,
            activity=activity,
            message="Inputs have different units: " + ", ".join(str(u) for u in units),
            code="UNIT_MISMATCH"
        )
        return g.serialize(format="turtle")

    # If no unit was specified, default to millimeter; otherwise reuse the single unit
    if units:
        unit_iri = next(iter(units))
    else:
        unit_iri = UNIT.MilliM

    # 4) Compute the sum
    total = sum(values)

    # 5) Create a new result QuantityValue with a relative IRI fragment
    result_qv = URIRef(f"#sumResult_{uuid.uuid4().hex}")

    g.add((result_qv, RDF.type, QUDT.QuantityValue))
    g.add((result_qv, QUDT.numericValue, Literal(total, datatype=XSD.decimal)))
    g.add((result_qv, QUDT.unit, unit_iri))

    # Link back via PROV
    g.add((result_qv, PROV.wasGeneratedBy, activity))
    for qv in inputs:
        g.add((result_qv, PROV.wasDerivedFrom, qv))

    return g.serialize(format="turtle")


if __name__ == "__main__":
    import sys
    input_ttl = sys.stdin.read()
    print(run(input_ttl))