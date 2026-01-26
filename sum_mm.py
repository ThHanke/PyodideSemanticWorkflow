from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, XSD

EX   = Namespace("https://example.org/pyodide/sum-example/")
PROV = Namespace("http://www.w3.org/ns/prov#")
QUDT = Namespace("http://qudt.org/schema/qudt/")
UNIT = Namespace("http://qudt.org/vocab/unit/")
BFO  = Namespace("https://example.org/bfo/")

def run(graph_ttl: str) -> str:
    """
    Generic entry point for the Pyodide node.

    - graph_ttl: RDF graph in Turtle syntax (string)
    - returns: updated graph (Turtle) with the sum result added

    """
    g = Graph()
    g.parse(data=graph_ttl, format="turtle")

    # Bind prefixes for nicer output
    g.bind("ex", EX)
    g.bind("prov", PROV)
    g.bind("qudt", QUDT)
    g.bind("unit", UNIT)
    g.bind("bfo", BFO)

    # 1) Find the activity to execute
    #    For simplicity: take the first prov:Activity in the graph.
    activity = next(g.subjects(RDF.type, PROV.Activity), None)
    if activity is None:
        raise ValueError("No prov:Activity found in graph")

    # 2) Find all QUDT QuantityValues that are inputs to this activity
    inputs = []
    for qv in g.subjects(BFO.is_input_of, activity):
        if (qv, RDF.type, QUDT.QuantityValue) in g:
            inputs.append(qv)

    if len(inputs) < 2:
        raise ValueError("Expected at least two qudt:QuantityValue inputs")

    # 3) Read numeric values and units
    values = []
    units = set()

    for qv in inputs:
        num = g.value(qv, QUDT.numericValue)
        unit = g.value(qv, QUDT.unit)
        if num is None:
            raise ValueError(f"Input {qv} has no qudt:numericValue")
        values.append(float(num))
        if unit is not None:
            units.add(unit)

    if len(units) > 1:
        raise ValueError(f"Inputs have different units: {units}")

    # If no unit was specified, default to millimeter; otherwise reuse the single unit
    if units:
        unit_iri = list(units)[0]
    else:
        unit_iri = UNIT.MilliM

    # 4) Compute the sum
    total = sum(values)

    # 5) Create a new result QuantityValue
    #    Here we generate a simple IRI; in a real system, use a proper IRI strategy.
    result_qv = EX["sumResult_auto_1"]

    g.add((result_qv, RDF.type, QUDT.QuantityValue))
    g.add((result_qv, QUDT.numericValue, Literal(total, datatype=XSD.decimal)))
    g.add((result_qv, QUDT.unit, unit_iri))

    # Link back via PROV
    g.add((result_qv, PROV.wasGeneratedBy, activity))
    for qv in inputs:
        g.add((result_qv, PROV.wasDerivedFrom, qv))

    # 6) Return the updated graph as Turtle
    return g.serialize(format="turtle")

# If you want a quick local test (outside Pyodide), you can do:

if __name__ == "__main__":
    import sys
    input_ttl = sys.stdin.read()
    print(run(input_ttl))