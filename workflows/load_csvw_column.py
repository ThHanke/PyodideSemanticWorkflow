"""
Load a column from CSVW (CSV on the Web) metadata.

This workflow step loads a column from a CSV file described by CSVW metadata,
extracting values along with their units if defined in the metadata.

Input:  URI of a CSVW metadata JSON file + column name string
Output: prov:Collection of qudt:QuantityValues (if units present) or plain entities

Follows the P-Plan + PROV-O two-level model:

  Template level (spw: namespace, stays in urn:vg:workflows):
    spw:LoadCSVWColumnStep  a p-plan:Step
    spw:CSVWMetadataURI     a p-plan:Variable ; p-plan:isInputVarOf  spw:LoadCSVWColumnStep
    spw:CSVWColumnName      a p-plan:Variable ; p-plan:isInputVarOf  spw:LoadCSVWColumnStep
    spw:LoadedColumnData    a p-plan:Variable ; p-plan:isOutputVarOf spw:LoadCSVWColumnStep

  Run level (default namespace, lives in urn:vg:data):
    :LoadRun_123  a prov:Activity, p-plan:Activity
        p-plan:correspondsToStep  spw:LoadCSVWColumnStep
        prov:used                 :MetadataURI_123, :ColumnName_123, spw:LoadCSVWColumnCode

    :columnData_abc  a prov:Collection, prov:Entity, p-plan:Entity
        p-plan:correspondsToVariable  spw:LoadedColumnData
        prov:wasGeneratedBy           :LoadRun_123
        prov:hadMember                :value0_abc, :value1_abc, ...
"""

import hashlib
import json
from typing import Any, Dict, List, Optional

import requests
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

# Standard vocabularies
PROV  = Namespace("http://www.w3.org/ns/prov#")
PPLAN = Namespace("http://purl.org/net/p-plan#")
QUDT  = Namespace("http://qudt.org/schema/qudt/")
UNIT  = Namespace("http://qudt.org/vocab/unit/")
OA      = Namespace("http://www.w3.org/ns/oa#")
CSVW    = Namespace("http://www.w3.org/ns/csvw#")
DCTERMS = Namespace("http://purl.org/dc/terms/")
SCHEMA  = Namespace("https://schema.org/")


# ---------------------------------------------------------------------------
# IRI helpers
# ---------------------------------------------------------------------------

def data_ns_from_activity(activity_iri: str) -> str:
    """Derive the data namespace from the activity IRI.

    The activity IRI is already in the correct default namespace
    (e.g. http://example.com/LoadRun_123), so strip the local name
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
    e.g. http://example.com/LoadRun_1234_LoadedColumnData
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
    out.bind("csvw",    CSVW)
    out.bind("oa",      OA)
    out.bind("dcterms", DCTERMS)
    out.bind("schema",  SCHEMA)
    return out


def _add_error(out: Graph, activity, message: str, code: str = None,
               data_ns: str = "http://example.com/",
               execution_hash: str = "unknown") -> None:
    """Record an error as a Web Annotation with a data-namespace IRI."""
    ann_iri = create_output_iri(data_ns, "errorAnn", execution_hash)
    body = BNode()

    out.add((ann_iri, RDF.type,        OA.Annotation))
    out.add((ann_iri, OA.motivatedBy,  OA.assessing))
    out.add((ann_iri, OA.hasBody,      body))

    if activity is not None:
        out.add((ann_iri, OA.hasTarget,        activity))
        out.add((ann_iri, PROV.wasGeneratedBy, activity))

    out.add((body, RDF.type,  OA.TextualBody))
    out.add((body, RDF.value, Literal(message, datatype=XSD.string)))
    if code is not None:
        out.add((body, DCTERMS.identifier, Literal(code, datatype=XSD.string)))


# ---------------------------------------------------------------------------
# CSVW loading
# ---------------------------------------------------------------------------

def parse_csvw_metadata(metadata_uri: str) -> Dict[str, Any]:
    """Fetch and parse CSVW metadata from a URI."""
    response = requests.get(metadata_uri)
    response.raise_for_status()
    return response.json()


def map_csvw_unit_to_qudt(csvw_unit: Optional[str]) -> Optional[URIRef]:
    """Map CSVW unit notation to QUDT unit URI."""
    if not csvw_unit:
        return None
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
) -> tuple:
    """
    Load a column from a CSV file using CSVW metadata.

    Returns:
        (values, unit_uri, column_title, delimiter)
    """
    metadata = parse_csvw_metadata(metadata_uri)

    tables = metadata.get("tables", [metadata])
    table = tables[0] if isinstance(tables, list) else tables

    csv_url = table.get("url")
    if not csv_url:
        raise ValueError("No CSV URL found in metadata")

    if not csv_url.startswith("http"):
        base_url = "/".join(metadata_uri.split("/")[:-1])
        csv_url = f"{base_url}/{csv_url}"

    # Detect delimiter from metadata (default comma)
    dialect = table.get("dialect", {})
    delimiter = dialect.get("delimiter", ",")

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

    unit_str = column_schema.get("dc:unit") or column_schema.get("unit")
    unit_uri = map_csvw_unit_to_qudt(unit_str)

    column_title = column_schema.get("titles", column_name)
    if isinstance(column_title, list):
        column_title = column_title[0]

    csv_response = requests.get(csv_url)
    csv_response.raise_for_status()

    lines = csv_response.text.strip().split("\n")
    values = []
    for line in lines[1:]:  # skip header
        fields = line.split(delimiter)
        if column_index < len(fields):
            value_str = fields[column_index].strip().strip('"')
            try:
                values.append(float(value_str))
            except ValueError:
                values.append(value_str)

    return values, unit_uri, column_title


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
        Output graph in Turtle format with loaded column data
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

    # Resolve template step and output variable
    step    = g.value(activity, PPLAN.correspondsToStep)
    out_var = g.value(predicate=PPLAN.isOutputVarOf, object=step) if step else None

    # Find input data entities (those with p-plan:correspondsToVariable, not code/requirements)
    inputs = [
        entity for entity in g.objects(activity, PROV.used)
        if (entity, PPLAN.correspondsToVariable, None) in g
    ]

    execution_hash = create_execution_hash(activity_iri, *[str(inp) for inp in inputs])
    out = _new_output_graph()

    if len(inputs) < 2:
        _add_error(out, activity,
                   f"Expected 2 inputs (metadata URI, column name). Found {len(inputs)}.",
                   code="INPUT_TOO_FEW", data_ns=data_ns,
                   execution_hash=execution_hash)
        return out.serialize(format="turtle")

    # Identify which input is metadata URI and which is column name
    # by inspecting the template variable label
    metadata_uri = None
    column_name = None

    for inp in inputs:
        var = g.value(inp, PPLAN.correspondsToVariable)
        var_label = str(g.value(var, RDFS.label)).lower() if var else ""
        value = g.value(inp, RDF.value)
        if value is None:
            continue
        if "metadata" in var_label or "uri" in var_label:
            metadata_uri = str(value)
        elif "column" in var_label:
            column_name = str(value)

    if not metadata_uri or not column_name:
        _add_error(out, activity,
                   "Could not resolve metadata URI or column name from inputs. "
                   "Check that input variables have rdfs:label containing 'metadata'/'uri' "
                   "and 'column' respectively.",
                   code="MISSING_INPUT", data_ns=data_ns,
                   execution_hash=execution_hash)
        return out.serialize(format="turtle")

    # Load column from CSVW
    try:
        values, unit_uri, column_title = load_column_from_csvw(metadata_uri, column_name)
    except Exception as e:
        _add_error(out, activity,
                   f"Failed to load column from CSVW: {e}",
                   code="CSVW_LOAD_ERROR", data_ns=data_ns,
                   execution_hash=execution_hash)
        return out.serialize(format="turtle")

    if len(values) == 0:
        _add_error(out, activity,
                   f"Column '{column_name}' loaded but contains no values.",
                   code="EMPTY_COLUMN", data_ns=data_ns,
                   execution_hash=execution_hash)
        return out.serialize(format="turtle")

    # Build result IRI — derived from activityIri + P-Plan output variable local name,
    # matching the placeholder the app created during workflow instantiation.
    if out_var:
        result_iri = activity_output_iri(activity_iri, out_var)
    else:
        result_iri = create_output_iri(data_ns, "columnData", execution_hash)

    # Types: prov:Collection + prov:Entity + p-plan:Entity (run-level)
    out.add((result_iri, RDF.type, PROV.Collection))
    out.add((result_iri, RDF.type, PROV.Entity))
    out.add((result_iri, RDF.type, PPLAN.Entity))
    out.add((result_iri, RDFS.label, Literal(f"Column data: {column_title}")))
    out.add((result_iri, PROV.wasGeneratedBy, activity))
    for inp in inputs:
        out.add((result_iri, PROV.wasDerivedFrom, inp))

    # Link to template output variable so downstream steps can find this collection
    if out_var:
        out.add((result_iri, PPLAN.correspondsToVariable, out_var))

    # Collection metadata — standard vocabularies only
    if unit_uri:
        out.add((result_iri, QUDT.unit,            unit_uri))
    out.add((result_iri, DCTERMS.source,           Literal(column_name)))   # source column name
    out.add((result_iri, SCHEMA.numberOfItems,     Literal(len(values), datatype=XSD.integer)))

    # Create individual QuantityValues or plain entities for each row value
    for idx, value in enumerate(values):
        value_iri = create_output_iri(data_ns, f"value{idx}", execution_hash)
        out.add((value_iri, RDF.type, PROV.Entity))

        if isinstance(value, float) and unit_uri:
            out.add((value_iri, RDF.type,            QUDT.QuantityValue))
            out.add((value_iri, QUDT.numericValue,   Literal(value, datatype=XSD.decimal)))
            out.add((value_iri, QUDT.unit,           unit_uri))
        elif isinstance(value, float):
            out.add((value_iri, RDF.value, Literal(value, datatype=XSD.decimal)))
        else:
            out.add((value_iri, RDF.value, Literal(str(value), datatype=XSD.string)))

        out.add((result_iri, PROV.hadMember, value_iri))

    return out.serialize(format="turtle")
