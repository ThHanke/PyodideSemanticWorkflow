"""
Calculate the average of a collection of QUDT QuantityValues.

This workflow step calculates the arithmetic mean of values from a PROV Collection,
preserving units if they are attached to the values.

Input: PROV Collection containing QUDT QuantityValues or numeric literals
Output: Single QUDT QuantityValue with the average and unit (if applicable)
"""

import hashlib
import statistics
from typing import List, Optional

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

# Standard vocabularies
PROV = Namespace("http://www.w3.org/ns/prov#")
QUDT = Namespace("http://qudt.org/schema/qudt/")
UNIT = Namespace("http://qudt.org/vocab/unit/")
OA = Namespace("http://www.w3.org/ns/oa#")
P_PLAN = Namespace("http://purl.org/net/p-plan#")

# Domain vocabulary
EX = Namespace("https://github.com/ThHanke/PyodideSemanticWorkflow/")
BFO = Namespace("https://example.org/bfo/")


def create_execution_hash(activity_iri: str, *input_iris: str) -> str:
    """Create a deterministic hash from activity IRI and input IRIs."""
    sorted_inputs = sorted(str(iri) for iri in input_iris)
    combined = str(activity_iri) + "".join(sorted_inputs)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]


def create_deterministic_iri(prefix: str, execution_hash: str) -> URIRef:
    """Create a deterministic IRI using a prefix and shared execution hash."""
    return URIRef(f"#{prefix}_{execution_hash}")


def cleanup_previous_result(g: Graph, result_iri: URIRef) -> int:
    """Remove all triples related to a previous result entity from the graph."""
    triples_to_remove = []
    for s, p, o in g.triples((result_iri, None, None)):
        triples_to_remove.append((s, p, o))
    for s, p, o in g.triples((None, None, result_iri)):
        triples_to_remove.append((s, p, o))
    for triple in triples_to_remove:
        g.remove(triple)
    return len(triples_to_remove)


def _add_error(
    g: Graph, activity, message: str, code: str = None, execution_hash: str = "unknown"
) -> None:
    """Add an error as a Web Annotation with deterministic IRI."""
    ann_iri = create_deterministic_iri("errorAnn", execution_hash)
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


def run(input_turtle: str, activity_iri: str) -> str:
    """
    Main entry point called by Pyodide runtime.
    
    Args:
        input_turtle: Input graph in Turtle format
        activity_iri: IRI of the prov:Activity being executed
        
    Returns:
        Output graph in Turtle format with calculated average
    """
    g = Graph()
    
    # Parse input graph
    try:
        g.parse(data=input_turtle, format="turtle")
    except Exception as e:
        g = Graph()
        g.bind("prov", PROV)
        g.bind("oa", OA)
        g.bind("ex", EX)
        _add_error(
            g,
            activity=None,
            message=f"Failed to parse input graph: {e}",
            code="PARSE_ERROR",
        )
        return g.serialize(format="turtle")
    
    # Bind prefixes
    g.bind("prov", PROV)
    g.bind("qudt", QUDT)
    g.bind("unit", UNIT)
    g.bind("p-plan", P_PLAN)
    g.bind("bfo", BFO)
    g.bind("oa", OA)
    g.bind("ex", EX)
    
    activity = URIRef(activity_iri)
    
    # Find input collection using prov:used
    # Filter to only collections that correspond to input variables
    all_used = list(g.objects(activity, PROV.used))
    inputs = [
        entity for entity in all_used
        if (entity, RDF.type, PROV.Collection) in g
        and (entity, P_PLAN.correspondsToVariable, None) in g
    ]
    
    execution_hash = create_execution_hash(activity_iri, *[str(inp) for inp in inputs])
    
    if len(inputs) < 1:
        _add_error(
            g,
            activity=activity,
            message=f"Expected 1 PROV Collection as input. Found {len(inputs)}",
            code="INPUT_TOO_FEW",
            execution_hash=execution_hash,
        )
        return g.serialize(format="turtle")
    
    collection = inputs[0]
    
    # Get all members of the collection
    members = list(g.objects(collection, PROV.hadMember))
    
    if len(members) == 0:
        _add_error(
            g,
            activity=activity,
            message="Collection has no members (prov:hadMember)",
            code="EMPTY_COLLECTION",
            execution_hash=execution_hash,
        )
        return g.serialize(format="turtle")
    
    # Extract numeric values and units
    values = []
    units = set()
    
    for member in members:
        # Try to get as QuantityValue first
        num_value = g.value(member, QUDT.numericValue)
        
        if num_value is None:
            # Try to get as simple rdf:value
            num_value = g.value(member, RDF.value)
        
        if num_value is None:
            _add_error(
                g,
                activity,
                f"Member {member} has no qudt:numericValue or rdf:value",
                "MISSING_NUMERIC_VALUE",
                execution_hash=execution_hash,
            )
            return g.serialize(format="turtle")
        
        try:
            values.append(float(num_value))
        except Exception:
            _add_error(
                g,
                activity,
                f"Member {member} has non-numeric value {num_value}",
                "NON_NUMERIC_VALUE",
                execution_hash=execution_hash,
            )
            return g.serialize(format="turtle")
        
        # Get unit if present
        unit = g.value(member, QUDT.unit)
        if unit is not None:
            units.add(unit)
    
    # Check for unit consistency
    if len(units) > 1:
        _add_error(
            g,
            activity,
            "Collection members have different units: " + ", ".join(str(u) for u in units),
            code="UNIT_MISMATCH",
            execution_hash=execution_hash,
        )
        return g.serialize(format="turtle")
    
    # Get unit from collection if not found on members
    unit_iri = next(iter(units)) if units else g.value(collection, QUDT.unit)
    
    # Calculate average
    try:
        average = statistics.mean(values)
    except Exception as e:
        _add_error(
            g,
            activity,
            f"Failed to calculate mean: {e}",
            code="CALCULATION_ERROR",
            execution_hash=execution_hash,
        )
        return g.serialize(format="turtle")
    
    # Create result IRI using shared execution hash
    result_qv = create_deterministic_iri("averageResult", execution_hash)
    
    # Clean up any previous result with this IRI from the graph
    removed_count = cleanup_previous_result(g, result_qv)
    if removed_count > 0:
        print(f"[INFO] Removed {removed_count} triples from previous result {result_qv}")
    
    # Add the fresh result
    g.add((result_qv, RDF.type, QUDT.QuantityValue))
    g.add((result_qv, RDF.type, PROV.Entity))
    g.add((result_qv, QUDT.numericValue, Literal(average, datatype=XSD.decimal)))
    
    if unit_iri:
        g.add((result_qv, QUDT.unit, unit_iri))
    
    g.add((result_qv, PROV.wasGeneratedBy, activity))
    g.add((result_qv, PROV.wasDerivedFrom, collection))
    
    # Add metadata about the calculation
    g.add((result_qv, RDFS.label, Literal(f"Average of {len(values)} values")))
    g.add((result_qv, EX.valueCount, Literal(len(values), datatype=XSD.integer)))
    g.add((result_qv, EX.calculationMethod, Literal("arithmetic mean")))
    
    # Also add min/max for context
    g.add((result_qv, EX.minValue, Literal(min(values), datatype=XSD.decimal)))
    g.add((result_qv, EX.maxValue, Literal(max(values), datatype=XSD.decimal)))
    
    return g.serialize(format="turtle")
