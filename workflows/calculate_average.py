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

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

# Standard vocabularies
PROV    = Namespace("http://www.w3.org/ns/prov#")
PPLAN   = Namespace("http://purl.org/net/p-plan#")
QUDT    = Namespace("http://qudt.org/schema/qudt/")
UNIT    = Namespace("http://qudt.org/vocab/unit/")
OA      = Namespace("http://www.w3.org/ns/oa#")
DCTERMS = Namespace("http://purl.org/dc/terms/")
SCHEMA  = Namespace("https://schema.org/")


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
    e.g. http://example.com/AverageRun_1234_AverageOutput
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
    out.bind("schema",  SCHEMA)
    return out


def _add_error(out: Graph, activity, message: str, code: str = None,
               data_ns: str = "http://example.com/",
               execution_hash: str = "unknown") -> None:
    """Record an error as a Web Annotation (W3C OA) targeting the activity.

    Message and code are placed directly on the annotation IRI (no blank node body)
    so the canvas can display them without blank-node noise.
    """
    ann_iri = create_output_iri(data_ns, "errorAnn", execution_hash)

    out.add((ann_iri, RDF.type,        OA.Annotation))
    out.add((ann_iri, OA.motivatedBy,  OA.assessing))
    out.add((ann_iri, RDFS.label,      Literal(message, datatype=XSD.string)))
    out.add((ann_iri, RDF.value,       Literal(message, datatype=XSD.string)))

    if activity is not None:
        out.add((ann_iri, OA.hasTarget,        activity))
        out.add((ann_iri, PROV.wasGeneratedBy, activity))

    if code is not None:
        out.add((ann_iri, DCTERMS.identifier, Literal(code, datatype=XSD.string)))


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
        out = _new_output_graph()
        _add_error(out, activity=None,
                   message=f"Failed to parse input graph: {e}",
                   code="PARSE_ERROR", data_ns=data_ns)
        return out.serialize(format="turtle")

    activity = URIRef(activity_iri)

    step    = g.value(activity, PPLAN.correspondsToStep)
    out_var = g.value(predicate=PPLAN.isOutputVarOf, object=step) if step else None

    # Find the input collection:
    # one prov:Collection entity linked via prov:used that carries p-plan:correspondsToVariable
    input_collections = [
        entity for entity in g.objects(activity, PROV.used)
        if (entity, RDF.type, PROV.Collection) in g
        and (entity, PPLAN.correspondsToVariable, None) in g
    ]

    execution_hash = create_execution_hash(activity_iri,
                                           *[str(c) for c in input_collections])
    out = _new_output_graph()

    if len(input_collections) < 1:
        _add_error(
            out, activity,
            "Expected 1 prov:Collection input via prov:used + "
            "p-plan:correspondsToVariable. Found "
            f"{len(input_collections)}.",
            code="INPUT_TOO_FEW", data_ns=data_ns,
            execution_hash=execution_hash,
        )
        return out.serialize(format="turtle")

    collection = input_collections[0]
    members = list(g.objects(collection, PROV.hadMember))

    if len(members) == 0:
        _add_error(out, activity,
                   "Collection has no members (prov:hadMember).",
                   code="EMPTY_COLLECTION", data_ns=data_ns,
                   execution_hash=execution_hash)
        return out.serialize(format="turtle")

    values = []
    units  = set()

    for member in members:
        num_value = g.value(member, QUDT.numericValue) or g.value(member, RDF.value)

        if num_value is None:
            _add_error(out, activity,
                       f"Member {member} has no qudt:numericValue or rdf:value.",
                       "MISSING_NUMERIC_VALUE", data_ns=data_ns,
                       execution_hash=execution_hash)
            return out.serialize(format="turtle")

        try:
            values.append(float(num_value))
        except Exception:
            _add_error(out, activity,
                       f"Member {member} has non-numeric value {num_value}.",
                       "NON_NUMERIC_VALUE", data_ns=data_ns,
                       execution_hash=execution_hash)
            return out.serialize(format="turtle")

        unit = g.value(member, QUDT.unit)
        if unit is not None:
            units.add(unit)

    if len(units) > 1:
        _add_error(out, activity,
                   "Collection members have different units: " +
                   ", ".join(str(u) for u in units),
                   code="UNIT_MISMATCH", data_ns=data_ns,
                   execution_hash=execution_hash)
        return out.serialize(format="turtle")

    unit_iri = next(iter(units)) if units else g.value(collection, QUDT.unit)

    try:
        average = statistics.mean(values)
    except Exception as e:
        _add_error(out, activity, f"Failed to calculate mean: {e}",
                   code="CALCULATION_ERROR", data_ns=data_ns,
                   execution_hash=execution_hash)
        return out.serialize(format="turtle")

    # Build result IRI — derived from activityIri + P-Plan output variable local name,
    # matching the placeholder the app created during workflow instantiation.
    if out_var:
        result_iri = activity_output_iri(activity_iri, out_var)
    else:
        result_iri = create_output_iri(data_ns, "averageResult", execution_hash)

    out.add((result_iri, RDF.type,          QUDT.QuantityValue))
    out.add((result_iri, RDF.type,          PROV.Entity))
    out.add((result_iri, RDF.type,          PPLAN.Entity))
    out.add((result_iri, RDFS.label,        Literal(f"Average of {len(values)} values")))
    out.add((result_iri, QUDT.numericValue, Literal(average, datatype=XSD.decimal)))

    if unit_iri:
        out.add((result_iri, QUDT.unit, unit_iri))

    out.add((result_iri, PROV.wasGeneratedBy, activity))
    out.add((result_iri, PROV.wasDerivedFrom, collection))
    for member in members:
        out.add((result_iri, PROV.wasDerivedFrom, member))

    if out_var:
        out.add((result_iri, PPLAN.correspondsToVariable, out_var))

    # Calculation metadata using Schema.org and Dublin Core
    out.add((result_iri, DCTERMS.description, Literal("arithmetic mean")))
    out.add((result_iri, SCHEMA.minValue,     Literal(min(values), datatype=XSD.decimal)))
    out.add((result_iri, SCHEMA.maxValue,     Literal(max(values), datatype=XSD.decimal)))

    return out.serialize(format="turtle")
