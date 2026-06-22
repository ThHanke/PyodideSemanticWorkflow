"""
Load a column from CSVW (CSV on the Web) metadata already present in the graph.

This workflow step queries the graph for csvw:TableGroup and csvw:Column entities
(loaded from CSVW JSON-LD metadata), presents select dropdowns for the user to
choose a data source and column, then fetches and parses the CSV data.

Input:  CSVW metadata must already be loaded in the graph as RDF triples.
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
from typing import Optional

import requests
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

import spw_input

# Standard vocabularies
PROV  = Namespace("http://www.w3.org/ns/prov#")
PPLAN = Namespace("http://purl.org/net/p-plan#")
QUDT  = Namespace("http://qudt.org/schema/qudt/")
UNIT  = Namespace("http://qudt.org/vocab/unit/")
OA      = Namespace("http://www.w3.org/ns/oa#")
CSVW    = Namespace("http://www.w3.org/ns/csvw#")
DCTERMS = Namespace("http://purl.org/dc/terms/")
SCHEMA  = Namespace("https://schema.org/")
DC      = Namespace("http://purl.org/dc/elements/1.1/")


# ---------------------------------------------------------------------------
# IRI helpers
# ---------------------------------------------------------------------------

def data_ns_from_activity(activity_iri: str) -> str:
    iri = str(activity_iri)
    idx = max(iri.rfind('#'), iri.rfind('/'))
    return iri[:idx + 1] if idx >= 0 else iri + '/'


def create_execution_hash(activity_iri: str, *input_iris: str) -> str:
    sorted_inputs = sorted(str(iri) for iri in input_iris)
    combined = str(activity_iri) + ''.join(sorted_inputs)
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()[:16]


def local_name(iri) -> str:
    s = str(iri)
    idx = max(s.rfind('#'), s.rfind('/'))
    return s[idx + 1:] if idx >= 0 else s


def create_output_iri(data_ns: str, prefix: str, execution_hash: str) -> URIRef:
    return URIRef(f"{data_ns}{prefix}_{execution_hash}")


def activity_output_iri(activity_iri: str, out_var) -> URIRef:
    return URIRef(f"{activity_iri}_{local_name(out_var)}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def cleanup_previous_result(g: Graph, result_iri: URIRef) -> int:
    triples = list(g.triples((result_iri, None, None))) + \
              list(g.triples((None, None, result_iri)))
    for t in triples:
        g.remove(t)
    return len(triples)


def _new_output_graph() -> Graph:
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
               execution_hash: str = "unknown",
               target=None) -> None:
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


def map_csvw_unit_to_qudt(csvw_unit: Optional[str]) -> Optional[URIRef]:
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


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(input_turtle: str, activity_iri: str) -> str:
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

    inputs = [
        entity for entity in g.objects(activity, PROV.used)
        if (entity, PPLAN.correspondsToVariable, None) in g
    ]

    execution_hash = create_execution_hash(activity_iri, *[str(inp) for inp in inputs])
    out = _new_output_graph()
    prov_triples = []

    if len(inputs) < 2:
        _add_error(out, activity,
                   f"Expected 2 inputs (metadata source, column name). Found {len(inputs)}.",
                   code="INPUT_TOO_FEW", data_ns=data_ns,
                   execution_hash=execution_hash)
        return out.serialize(format="turtle")

    # Identify placeholder entities by variable label
    metadata_placeholder = None
    column_placeholder = None
    for inp in inputs:
        var = g.value(inp, PPLAN.correspondsToVariable)
        var_label = str(g.value(var, RDFS.label)).lower() if var else ""
        if "metadata" in var_label or "uri" in var_label:
            metadata_placeholder = inp
        elif "column" in var_label:
            column_placeholder = inp

    # -----------------------------------------------------------------------
    # Phase 1: Resolve TableGroup via graph query + select dropdown
    # -----------------------------------------------------------------------
    table_groups = list(g.subjects(RDF.type, CSVW.TableGroup))

    if not table_groups:
        _add_error(out, activity,
                   "No csvw:TableGroup found in graph. Load CSVW metadata first.",
                   code="NO_TABLE_GROUPS", data_ns=data_ns,
                   execution_hash=execution_hash, target=metadata_placeholder)
        return out.serialize(format="turtle")

    if len(table_groups) == 1:
        selected_tg = table_groups[0]
    else:
        tg_options = []
        for tg in table_groups:
            label = g.value(tg, RDFS.label)
            if label is None:
                label = local_name(tg)
            tg_options.append({'label': str(label), 'value': str(tg)})

        try:
            selected_tg_iri = spw_input.prompt_select("data source", tg_options)
            selected_tg = URIRef(selected_tg_iri)
        except spw_input.InputCancelled as exc:
            _add_error(out, activity, str(exc),
                       code="INPUT_CANCELLED", data_ns=data_ns,
                       execution_hash=execution_hash, target=metadata_placeholder)
            return out.serialize(format="turtle")
        except spw_input.InputFailed as exc:
            _add_error(out, activity, str(exc),
                       code="INPUT_PROMPT_FAILED", data_ns=data_ns,
                       execution_hash=execution_hash, target=metadata_placeholder)
            return out.serialize(format="turtle")

    # Write selected TableGroup IRI to metadata placeholder for downstream compatibility
    if metadata_placeholder is not None:
        g.add((metadata_placeholder, RDF.value, Literal(str(selected_tg))))

    prov_triples.extend(
        spw_input.make_provenance(activity, metadata_placeholder, selected_tg)
        if metadata_placeholder else [(activity, PROV.used, selected_tg)]
    )

    # -----------------------------------------------------------------------
    # Phase 2: Traverse TableGroup → table → schema → columns → select
    # -----------------------------------------------------------------------
    columns = []
    tables = list(g.objects(selected_tg, CSVW.table))

    for table in tables:
        schema = g.value(table, CSVW.tableSchema)
        if schema is None:
            continue
        for col in g.objects(schema, CSVW.column):
            col_name = g.value(col, CSVW.name)
            col_title = g.value(col, CSVW.title)
            display = str(col_title) if col_title else (str(col_name) if col_name else local_name(col))
            columns.append({
                'column': col,
                'name': str(col_name) if col_name else None,
                'display': display,
                'table': table,
            })

    if not columns:
        _add_error(out, activity,
                   "No csvw:Column found in selected data source. Check CSVW metadata structure.",
                   code="NO_COLUMNS", data_ns=data_ns,
                   execution_hash=execution_hash, target=column_placeholder)
        return out.serialize(format="turtle")

    if len(columns) == 1:
        selected_col = columns[0]
    else:
        col_options = [
            {'label': c['display'], 'value': str(i)}
            for i, c in enumerate(columns)
        ]

        try:
            selected_idx = spw_input.prompt_select("column", col_options)
            selected_col = columns[int(selected_idx)]
        except spw_input.InputCancelled as exc:
            _add_error(out, activity, str(exc),
                       code="INPUT_CANCELLED", data_ns=data_ns,
                       execution_hash=execution_hash, target=column_placeholder)
            return out.serialize(format="turtle")
        except spw_input.InputFailed as exc:
            _add_error(out, activity, str(exc),
                       code="INPUT_PROMPT_FAILED", data_ns=data_ns,
                       execution_hash=execution_hash, target=column_placeholder)
            return out.serialize(format="turtle")

    column_name = selected_col['name']
    column_entity = selected_col['column']
    table_entity = selected_col['table']

    if not column_name:
        _add_error(out, activity,
                   "Selected column has no csvw:name. Cannot match CSV header.",
                   code="NO_COLUMN_NAME", data_ns=data_ns,
                   execution_hash=execution_hash, target=column_placeholder)
        return out.serialize(format="turtle")

    # Write selected column name to placeholder
    if column_placeholder is not None:
        g.add((column_placeholder, RDF.value, Literal(column_name)))

    # -----------------------------------------------------------------------
    # Derive CSV URL and unit from graph
    # -----------------------------------------------------------------------
    csv_url_node = g.value(table_entity, CSVW.url)
    if csv_url_node is None:
        _add_error(out, activity,
                   "No csvw:url found on table. Cannot fetch CSV data.",
                   code="NO_CSV_URL", data_ns=data_ns,
                   execution_hash=execution_hash)
        return out.serialize(format="turtle")
    csv_url = str(csv_url_node)

    # Try qudt:unit on column entity first, then dc:unit string for fallback mapping
    unit_uri = None
    qudt_unit = g.value(column_entity, QUDT.unit)
    if qudt_unit is not None:
        unit_uri = qudt_unit
    else:
        dc_unit = g.value(column_entity, DC.unit)
        if dc_unit is not None:
            unit_uri = map_csvw_unit_to_qudt(str(dc_unit))

    # Detect delimiter from table dialect if present
    dialect = g.value(table_entity, CSVW.dialect)
    delimiter = ","
    if dialect is not None:
        delim_val = g.value(dialect, CSVW.delimiter)
        if delim_val is not None:
            delimiter = str(delim_val)

    # -----------------------------------------------------------------------
    # Fetch CSV and extract column
    # -----------------------------------------------------------------------
    try:
        csv_response = requests.get(csv_url)
        csv_response.raise_for_status()
    except Exception as e:
        _add_error(out, activity,
                   f"Failed to fetch CSV data from {csv_url}: {e}",
                   code="CSV_FETCH_ERROR", data_ns=data_ns,
                   execution_hash=execution_hash)
        return out.serialize(format="turtle")

    lines = csv_response.text.strip().split("\n")
    if len(lines) < 2:
        _add_error(out, activity,
                   "CSV file has no data rows.",
                   code="EMPTY_CSV", data_ns=data_ns,
                   execution_hash=execution_hash)
        return out.serialize(format="turtle")

    header = [h.strip().strip('"') for h in lines[0].split(delimiter)]
    try:
        column_index = header.index(column_name)
    except ValueError:
        _add_error(out, activity,
                   f"Column '{column_name}' not found in CSV header: {header}",
                   code="COLUMN_NOT_FOUND", data_ns=data_ns,
                   execution_hash=execution_hash)
        return out.serialize(format="turtle")

    values = []
    for line in lines[1:]:
        fields = line.split(delimiter)
        if column_index < len(fields):
            value_str = fields[column_index].strip().strip('"')
            try:
                values.append(float(value_str))
            except ValueError:
                values.append(value_str)

    if len(values) == 0:
        _add_error(out, activity,
                   f"Column '{column_name}' loaded but contains no values.",
                   code="EMPTY_COLUMN", data_ns=data_ns,
                   execution_hash=execution_hash)
        return out.serialize(format="turtle")

    # -----------------------------------------------------------------------
    # Build output collection
    # -----------------------------------------------------------------------
    if out_var:
        result_iri = activity_output_iri(activity_iri, out_var)
    else:
        result_iri = create_output_iri(data_ns, "columnData", execution_hash)

    out.add((result_iri, RDF.type, PROV.Collection))
    out.add((result_iri, RDF.type, PROV.Entity))
    out.add((result_iri, RDF.type, PPLAN.Entity))
    out.add((result_iri, RDFS.label, Literal(f"Column data: {selected_col['display']}")))
    out.add((result_iri, PROV.wasGeneratedBy, activity))
    for inp in inputs:
        out.add((result_iri, PROV.wasDerivedFrom, inp))

    if out_var:
        out.add((result_iri, PPLAN.correspondsToVariable, out_var))

    if unit_uri:
        out.add((result_iri, QUDT.unit, unit_uri))
    out.add((result_iri, DCTERMS.source, Literal(column_name)))
    out.add((result_iri, SCHEMA.numberOfItems, Literal(len(values), datatype=XSD.integer)))

    # Add provenance triples from input resolution
    for s, p, o in prov_triples:
        out.add((s, p, o))

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
