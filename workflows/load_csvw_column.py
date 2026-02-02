"""
Load a column from CSVW (CSV on the Web) metadata.

This workflow step loads a column from a CSV file described by CSVW metadata,
extracting values along with their units if defined in the metadata.

Input: URI of a CSVW column from tableSchema
Output: Array of QUDT QuantityValues (if units present) or literals
"""

import hashlib
import json
from typing import Any, Dict, List, Optional

import requests
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

# Standard vocabularies
PROV = Namespace("http://www.w3.org/ns/prov#")
QUDT = Namespace("http://qudt.org/schema/qudt/")
UNIT = Namespace("http://qudt.org/vocab/unit/")
OA = Namespace("http://www.w3.org/ns/oa#")
CSVW = Namespace("http://www.w3.org/ns/csvw#")
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


def parse_csvw_metadata(metadata_uri: str) -> Dict[str, Any]:
    """
    Fetch and parse CSVW metadata from a URI.
    
    Args:
        metadata_uri: URI of the CSVW metadata JSON file
        
    Returns:
        Parsed JSON metadata as dictionary
    """
    response = requests.get(metadata_uri)
    response.raise_for_status()
    return response.json()


def map_csvw_unit_to_qudt(csvw_unit: Optional[str]) -> Optional[URIRef]:
    """
    Map CSVW unit notation to QUDT unit URI.
    
    This is a simple mapping - in production you'd want a comprehensive lookup table.
    """
    if not csvw_unit:
        return None
    
    # Simple unit mappings
    unit_map = {
        "mm": UNIT.MilliM,
        "millimeter": UNIT.MilliM,
        "m": UNIT.M,
        "meter": UNIT.M,
        "cm": UNIT.CentiM,
        "centimeter": UNIT.CentiM,
        "kg": UNIT.KiloGM,
        "kilogram": UNIT.KiloGM,
        "g": UNIT.GM,
        "gram": UNIT.GM,
        "s": UNIT.SEC,
        "second": UNIT.SEC,
        "°C": UNIT.DEG_C,
        "celsius": UNIT.DEG_C,
        "K": UNIT.K,
        "kelvin": UNIT.K,
    }
    
    return unit_map.get(csvw_unit.lower(), None)


def load_column_from_csvw(
    metadata_uri: str, column_name: str
) -> tuple[List[Any], Optional[URIRef], Optional[str]]:
    """
    Load a column from a CSV file using CSVW metadata.
    
    Args:
        metadata_uri: URI of the CSVW metadata file
        column_name: Name of the column to load
        
    Returns:
        Tuple of (values, unit_uri, column_title)
    """
    metadata = parse_csvw_metadata(metadata_uri)
    
    # Find the table (assume first table if multiple)
    tables = metadata.get("tables", [metadata])
    if not tables:
        raise ValueError("No tables found in CSVW metadata")
    
    table = tables[0] if isinstance(tables, list) else tables
    
    # Get CSV URL
    csv_url = table.get("url")
    if not csv_url:
        raise ValueError("No CSV URL found in metadata")
    
    # If relative URL, make it absolute based on metadata URI
    if not csv_url.startswith("http"):
        base_url = "/".join(metadata_uri.split("/")[:-1])
        csv_url = f"{base_url}/{csv_url}"
    
    # Find column schema
    table_schema = table.get("tableSchema", {})
    columns = table_schema.get("columns", [])
    
    column_schema = None
    column_index = None
    
    for idx, col in enumerate(columns):
        if col.get("name") == column_name or col.get("titles") == column_name:
            column_schema = col
            column_index = idx
            break
    
    if column_schema is None:
        raise ValueError(f"Column '{column_name}' not found in metadata")
    
    # Extract unit information
    unit_str = column_schema.get("dc:unit") or column_schema.get("unit")
    unit_uri = map_csvw_unit_to_qudt(unit_str)
    
    column_title = column_schema.get("titles", column_name)
    if isinstance(column_title, list):
        column_title = column_title[0]
    
    # Load CSV data
    csv_response = requests.get(csv_url)
    csv_response.raise_for_status()
    
    # Parse CSV (simple implementation - assumes comma delimiter)
    lines = csv_response.text.strip().split("\n")
    
    # Skip header row
    data_lines = lines[1:]
    
    # Extract column values
    values = []
    for line in data_lines:
        fields = line.split(",")
        if column_index < len(fields):
            value_str = fields[column_index].strip().strip('"')
            try:
                # Try to parse as number
                value = float(value_str)
                values.append(value)
            except ValueError:
                # Keep as string if not numeric
                values.append(value_str)
    
    return values, unit_uri, column_title


def run(input_turtle: str, activity_iri: str) -> str:
    """
    Main entry point called by Pyodide runtime.
    
    Args:
        input_turtle: Input graph in Turtle format
        activity_iri: IRI of the prov:Activity being executed
        
    Returns:
        Output graph in Turtle format with loaded column data
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
    g.bind("csvw", CSVW)
    g.bind("p-plan", P_PLAN)
    g.bind("bfo", BFO)
    g.bind("oa", OA)
    g.bind("ex", EX)
    
    activity = URIRef(activity_iri)
    
    # Find inputs using bfo:is_input_of
    # Input 1: CSVW metadata URI (as literal)
    # Input 2: Column name (as literal)
    inputs = list(g.subjects(BFO.is_input_of, activity))
    
    execution_hash = create_execution_hash(activity_iri, *[str(inp) for inp in inputs])
    
    if len(inputs) < 2:
        _add_error(
            g,
            activity=activity,
            message=f"Expected 2 inputs (metadata URI, column name). Found {len(inputs)}",
            code="INPUT_TOO_FEW",
            execution_hash=execution_hash,
        )
        return g.serialize(format="turtle")
    
    # Extract metadata URI and column name from inputs
    metadata_uri = None
    column_name = None
    
    for inp in inputs:
        # Check what type of input this is by checking correspondsToVariable
        var = g.value(inp, P_PLAN.correspondsToVariable)
        var_label = str(g.value(var, RDFS.label)) if var else ""
        
        value = g.value(inp, RDF.value)
        
        if "metadata" in var_label.lower() or "uri" in var_label.lower():
            metadata_uri = str(value)
        elif "column" in var_label.lower():
            column_name = str(value)
    
    if not metadata_uri or not column_name:
        _add_error(
            g,
            activity=activity,
            message=f"Could not determine metadata URI or column name from inputs",
            code="MISSING_INPUT",
            execution_hash=execution_hash,
        )
        return g.serialize(format="turtle")
    
    # Load column from CSVW
    try:
        values, unit_uri, column_title = load_column_from_csvw(metadata_uri, column_name)
    except Exception as e:
        _add_error(
            g,
            activity=activity,
            message=f"Failed to load column from CSVW: {e}",
            code="CSVW_LOAD_ERROR",
            execution_hash=execution_hash,
        )
        return g.serialize(format="turtle")
    
    # Create result - an RDF Collection (list) of QuantityValues or literals
    result_collection = create_deterministic_iri("columnData", execution_hash)
    
    # Clean up any previous result
    removed_count = cleanup_previous_result(g, result_collection)
    if removed_count > 0:
        print(f"[INFO] Removed {removed_count} triples from previous result {result_collection}")
    
    # Add result metadata
    g.add((result_collection, RDF.type, PROV.Entity))
    g.add((result_collection, RDF.type, PROV.Collection))
    g.add((result_collection, RDFS.label, Literal(f"Column data: {column_title}")))
    g.add((result_collection, PROV.wasGeneratedBy, activity))
    
    for inp in inputs:
        g.add((result_collection, PROV.wasDerivedFrom, inp))
    
    # Create individual QuantityValues or literals for each value
    for idx, value in enumerate(values):
        value_iri = create_deterministic_iri(f"value{idx}", execution_hash)
        
        if isinstance(value, (int, float)) and unit_uri:
            # Create as QuantityValue with unit
            g.add((value_iri, RDF.type, QUDT.QuantityValue))
            g.add((value_iri, RDF.type, PROV.Entity))
            g.add((value_iri, QUDT.numericValue, Literal(value, datatype=XSD.decimal)))
            g.add((value_iri, QUDT.unit, unit_uri))
        else:
            # Create as simple entity with value
            g.add((value_iri, RDF.type, PROV.Entity))
            if isinstance(value, (int, float)):
                g.add((value_iri, RDF.value, Literal(value, datatype=XSD.decimal)))
            else:
                g.add((value_iri, RDF.value, Literal(value, datatype=XSD.string)))
        
        # Link to collection
        g.add((result_collection, PROV.hadMember, value_iri))
    
    # Add metadata about the loaded column
    if unit_uri:
        g.add((result_collection, QUDT.unit, unit_uri))
    g.add((result_collection, EX.sourceColumn, Literal(column_name)))
    g.add((result_collection, EX.columnTitle, Literal(column_title)))
    g.add((result_collection, EX.valueCount, Literal(len(values), datatype=XSD.integer)))
    
    return g.serialize(format="turtle")
