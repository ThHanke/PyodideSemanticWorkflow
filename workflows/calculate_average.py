"""
Calculate the average of a collection of QUDT QuantityValues.

Follows the P-Plan + PROV-O two-level model:

  Template level (spw: namespace, stays in urn:vg:workflows):
    spw:AverageStep  a p-plan:Step
    spw:CollectionIn a p-plan:Variable  ; p-plan:isInputVarOf  spw:AverageStep
    spw:AverageOut   a p-plan:Variable  ; p-plan:isOutputVarOf spw:AverageStep

  Run level (default namespace, lives in urn:vg:data):
    :AverageRun_123  a prov:Activity, p-plan:Activity
        p-plan:correspondsToStep  spw:AverageStep
        prov:hadPlan              spw:AveragePlan
        prov:used                 :CollectionIn_123      (run entity for collection)
        prov:used                 spw:AverageCode        (resource, template IRI ok)
        prov:wasAssociatedWith    spw:PyodideEngine

    :CollectionIn_123  a prov:Collection, prov:Entity, p-plan:Entity
        p-plan:correspondsToVariable  spw:CollectionIn
        prov:hadMember  ... (members added by user before execution)

    :averageResult_abc  a qudt:QuantityValue, prov:Entity, p-plan:Entity
        p-plan:correspondsToVariable  spw:AverageOut
        prov:wasGeneratedBy           :AverageRun_123
        prov:wasDerivedFrom           :CollectionIn_123
                                      (+ individual members for fine-grained provenance)

Input:  The full urn:vg:data graph as Turtle.
Output: Turtle with new result triples to merge back into urn:vg:data.
"""

import hashlib
import statistics

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

# Standard vocabularies
PROV   = Namespace("http://www.w3.org/ns/prov#")
PPLAN  = Namespace("http://purl.org/net/p-plan#")
QUDT   = Namespace("http://qudt.org/schema/qudt/")
UNIT   = Namespace("http://qudt.org/vocab/unit/")
OA     = Namespace("http://www.w3.org/ns/oa#")
SPW    = Namespace("https://thhanke.github.io/PyodideSemanticWorkflow#")


# ---------------------------------------------------------------------------
# IRI helpers
# ---------------------------------------------------------------------------

def data_ns_from_activity(activity_iri: str) -> str:
    """Derive the data namespace from the activity IRI.

    The activity IRI is already in the correct default namespace
    (e.g. http://example.com/AverageRun_123), so strip the local name
    to get the base for all output IRIs.
    """
    iri = str(activity_iri)
    idx = max(iri.rfind('#'), iri.rfind('/'))
    return iri[:idx + 1] if idx >= 0 else iri + '/'


def create_execution_hash(activity_iri: str, *input_iris: str) -> str:
    """Deterministic hash from activity IRI + input IRIs (order-independent)."""
    sorted_inputs = sorted(str(iri) for iri in input_iris)
    combined = str(activity_iri) + ''.join(sorted_inputs)
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()[:16]


def create_output_iri(data_ns: str, prefix: str, execution_hash: str) -> URIRef:
    """Create a data-namespace IRI for an output entity."""
    return URIRef(f"{data_ns}{prefix}_{execution_hash}")


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
    """Record an error as a Web Annotation with a data-namespace IRI."""
    ann_iri = create_output_iri(data_ns, "errorAnn", execution_hash)
    body = BNode()

    g.bind("prov", PROV)
    g.bind("oa",   OA)
    g.bind("spw",  SPW)

    g.add((ann_iri, RDF.type,           OA.Annotation))
    g.add((ann_iri, OA.motivatedBy,     SPW.errorReporting))
    g.add((ann_iri, OA.hasBody,         body))

    if activity is not None:
        g.add((ann_iri, OA.hasTarget,        activity))
        g.add((ann_iri, PROV.wasGeneratedBy, activity))

    g.add((body, RDF.type,  OA.TextualBody))
    g.add((body, RDF.value, Literal(message, datatype=XSD.string)))
    if code is not None:
        g.add((body, SPW.errorCode, Literal(code, datatype=XSD.string)))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(input_turtle: str, activity_iri: str) -> str:
    """
    Main entry point called by the Pyodide runtime.

    Args:
        input_turtle: Full urn:vg:data graph as Turtle
        activity_iri: IRI of the prov:Activity being executed (default namespace)

    Returns:
        Turtle with new result triples to merge back into urn:vg:data
    """
    data_ns = data_ns_from_activity(activity_iri)
    g = Graph()

    try:
        g.parse(data=input_turtle, format="turtle")
    except Exception as e:
        g = Graph()
        _add_error(g, activity=None,
                   message=f"Failed to parse input graph: {e}",
                   code="PARSE_ERROR", data_ns=data_ns)
        return g.serialize(format="turtle")

    g.bind("prov",   PROV)
    g.bind("p-plan", PPLAN)
    g.bind("qudt",   QUDT)
    g.bind("unit",   UNIT)
    g.bind("oa",     OA)
    g.bind("spw",    SPW)

    activity = URIRef(activity_iri)

    # Ensure the activity is typed as p-plan:Activity in the output
    g.add((activity, RDF.type, PPLAN.Activity))

    # Resolve template step, plan and output variable via p-plan links
    step    = g.value(activity, PPLAN.correspondsToStep)
    out_var = g.value(predicate=PPLAN.isOutputVarOf, object=step) if step else None

    # -----------------------------------------------------------------------
    # Find the input collection
    # Expected: one prov:Collection entity linked via prov:used that also
    # carries p-plan:correspondsToVariable (run-level p-plan:Entity).
    # -----------------------------------------------------------------------
    input_collections = [
        entity for entity in g.objects(activity, PROV.used)
        if (entity, RDF.type, PROV.Collection) in g
        and (entity, PPLAN.correspondsToVariable, None) in g
    ]

    execution_hash = create_execution_hash(activity_iri,
                                           *[str(c) for c in input_collections])

    if len(input_collections) < 1:
        _add_error(
            g, activity,
            "Expected 1 prov:Collection input via prov:used + "
            "p-plan:correspondsToVariable. Found "
            f"{len(input_collections)}.",
            code="INPUT_TOO_FEW", data_ns=data_ns,
            execution_hash=execution_hash,
        )
        return g.serialize(format="turtle")

    collection = input_collections[0]

    # Ensure the collection is typed as p-plan:Entity (it is a run-level entity)
    g.add((collection, RDF.type, PPLAN.Entity))

    members = list(g.objects(collection, PROV.hadMember))

    if len(members) == 0:
        _add_error(g, activity,
                   "Collection has no members (prov:hadMember).",
                   code="EMPTY_COLLECTION", data_ns=data_ns,
                   execution_hash=execution_hash)
        return g.serialize(format="turtle")

    # -----------------------------------------------------------------------
    # Extract numeric values and unit
    # -----------------------------------------------------------------------
    values = []
    units  = set()

    for member in members:
        num_value = g.value(member, QUDT.numericValue) or g.value(member, RDF.value)

        if num_value is None:
            _add_error(g, activity,
                       f"Member {member} has no qudt:numericValue or rdf:value.",
                       "MISSING_NUMERIC_VALUE", data_ns=data_ns,
                       execution_hash=execution_hash)
            return g.serialize(format="turtle")

        try:
            values.append(float(num_value))
        except Exception:
            _add_error(g, activity,
                       f"Member {member} has non-numeric value {num_value}.",
                       "NON_NUMERIC_VALUE", data_ns=data_ns,
                       execution_hash=execution_hash)
            return g.serialize(format="turtle")

        unit = g.value(member, QUDT.unit)
        if unit is not None:
            units.add(unit)

    if len(units) > 1:
        _add_error(g, activity,
                   "Collection members have different units: " +
                   ", ".join(str(u) for u in units),
                   code="UNIT_MISMATCH", data_ns=data_ns,
                   execution_hash=execution_hash)
        return g.serialize(format="turtle")

    unit_iri = next(iter(units)) if units else g.value(collection, QUDT.unit)

    # -----------------------------------------------------------------------
    # Calculate average
    # -----------------------------------------------------------------------
    try:
        average = statistics.mean(values)
    except Exception as e:
        _add_error(g, activity, f"Failed to calculate mean: {e}",
                   code="CALCULATION_ERROR", data_ns=data_ns,
                   execution_hash=execution_hash)
        return g.serialize(format="turtle")

    # -----------------------------------------------------------------------
    # Build result entity in the data namespace
    # -----------------------------------------------------------------------
    result_iri = create_output_iri(data_ns, "averageResult", execution_hash)
    cleanup_previous_result(g, result_iri)

    # Types: domain type + prov:Entity + p-plan:Entity (run-level entity)
    g.add((result_iri, RDF.type, QUDT.QuantityValue))
    g.add((result_iri, RDF.type, PROV.Entity))
    g.add((result_iri, RDF.type, PPLAN.Entity))

    g.add((result_iri, RDFS.label,        Literal(f"Average of {len(values)} values")))
    g.add((result_iri, QUDT.numericValue, Literal(average, datatype=XSD.decimal)))

    if unit_iri:
        g.add((result_iri, QUDT.unit, unit_iri))

    # Provenance links
    g.add((result_iri, PROV.wasGeneratedBy, activity))
    g.add((result_iri, PROV.wasDerivedFrom, collection))   # coarse-grained
    for member in members:                                  # fine-grained
        g.add((result_iri, PROV.wasDerivedFrom, member))

    # Link back to template variable (run ↔ template bridge)
    if out_var:
        g.add((result_iri, PPLAN.correspondsToVariable, out_var))

    # Calculation metadata
    g.add((result_iri, SPW.valueCount,        Literal(len(values), datatype=XSD.integer)))
    g.add((result_iri, SPW.calculationMethod, Literal("arithmetic mean")))
    g.add((result_iri, SPW.minValue,          Literal(min(values), datatype=XSD.decimal)))
    g.add((result_iri, SPW.maxValue,          Literal(max(values), datatype=XSD.decimal)))

    return g.serialize(format="turtle")
