# Workflow Execution Examples

This directory contains example execution instances demonstrating how to use the workflow templates defined in `workflows/catalog.ttl`.

## Overview

Each example shows:
1. **Template Definition** - The abstract workflow plan with variables
2. **Concrete Data** - Real input values provided by the user
3. **Activity Instance** - The actual execution with provenance
4. **Results** - Generated outputs with full provenance chain

## Examples

### 1. Sum Execution (`sum-execution.ttl`)

A simple single-step workflow that sums two QUDT QuantityValues.

**Template:** `spw:SumTemplate`  
**Step:** `spw:SumStep`

**Input Data:**
- `spw:inputLength1`: 2.0 mm
- `spw:inputLength2`: 3.0 mm

**Output:**
- Sum: 5.0 mm

**Key Concepts Demonstrated:**
- Basic workflow execution pattern
- QUDT QuantityValue handling
- Unit preservation
- Provenance tracking with `prov:wasGeneratedBy` and `prov:wasDerivedFrom`

### 2. CSVW Column Average Execution (`csvw-average-execution.ttl`)

A two-step workflow demonstrating multi-step composition and data flow.

**Template:** `spw:CSVWAverageTemplate`  
**Steps:** `spw:LoadCSVWColumnStep` ’ `spw:CalculateAverageStep`

#### Step 1: Load Column from CSVW

**Input Data:**
- Metadata URI: `https://raw.githubusercontent.com/Mat-O-Lab/CSVToCSVW/refs/heads/main/examples/example-metadata.json`
- Column Name: `"temperature"`

**Output:**
- Collection of 5 temperature values (23.5°C, 24.1°C, 22.9°C, 23.8°C, 23.2°C)
- Each value is a `qudt:QuantityValue` with unit `unit:DEG_C`

#### Step 2: Calculate Average

**Input Data:**
- Collection from Step 1

**Output:**
- Average: 23.5°C
- Additional metadata: min (22.9°C), max (24.1°C), count (5)

**Key Concepts Demonstrated:**
- Multi-step workflow execution
- Data flow between steps using `prov:Collection`
- Activity chaining with `prov:wasInformedBy`
- CSVW metadata parsing
- Unit preservation through workflow steps
- Separate Python implementations with different requirements
- Complete provenance chain across multiple steps

## Supporting Files

### Example Data Files

#### `example-measurements.csv`
Sample CSV file with laboratory measurements:
- Sample ID
- Temperature (°C)
- Pressure (kPa)
- Volume (mL)

#### `example-measurements-metadata.json`
CSVW metadata describing the CSV structure:
- Column definitions
- Data types
- Units (using Dublin Core `dc:unit`)
- Column descriptions

This demonstrates the CSVW (CSV on the Web) standard for describing tabular data with semantic metadata.

## How to Read These Examples

### Template Level (Design Time)

From `workflows/catalog.ttl`:
```turtle
spw:CSVWAverageTemplate a p-plan:Plan ;
    rdfs:label "CSVW Column Average"@en .

spw:LoadCSVWColumnStep a p-plan:Step ;
    p-plan:isStepOfPlan spw:CSVWAverageTemplate .

spw:CSVWMetadataURI a p-plan:Variable ;
    p-plan:isInputVarOf spw:LoadCSVWColumnStep .
```

### Execution Level (Runtime)

From `csvw-average-execution.ttl`:
```turtle
spw:metadataURIInput a prov:Entity ;
    rdf:value "https://..."^^xsd:anyURI ;
    p-plan:correspondsToVariable spw:CSVWMetadataURI .

spw:LoadColumnRun_1 a prov:Activity ;
    p-plan:correspondsToStep spw:LoadCSVWColumnStep ;
    prov:used spw:metadataURIInput .
```

### The Link

The `p-plan:correspondsToVariable` and `p-plan:correspondsToStep` properties connect concrete execution instances back to their abstract template definitions.

## Provenance Queries

### Find all executions of a workflow
```sparql
PREFIX prov: <http://www.w3.org/ns/prov#>

SELECT ?activity ?startTime WHERE {
    ?activity prov:hadPlan spw:CSVWAverageTemplate ;
              prov:startedAtTime ?startTime .
}
```

### Trace data lineage
```sparql
PREFIX prov: <http://www.w3.org/ns/prov#>

SELECT ?intermediate ?input WHERE {
    <#averageTempResult> prov:wasDerivedFrom ?intermediate .
    ?intermediate prov:wasDerivedFrom ?input .
}
```

### Find what code was used
```sparql
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX schema: <https://schema.org/>

SELECT ?code ?location WHERE {
    ?activity prov:used ?code .
    ?code a schema:SoftwareSourceCode ;
          prov:atLocation ?location .
}
```

## Creating Your Own Examples

To create a new execution example:

1. **Choose a template** from `workflows/catalog.ttl`
2. **Identify required inputs** using the template's input variables
3. **Create concrete data** entities with `p-plan:correspondsToVariable` links
4. **Create the activity** with:
   - `prov:hadPlan` linking to template
   - `p-plan:correspondsToStep` linking to step
   - `prov:used` for code, requirements, and input data (inherited + concrete)
   - `prov:wasAssociatedWith` for the execution agent
5. **Generate outputs** with:
   - `prov:wasGeneratedBy` linking to activity
   - `prov:wasDerivedFrom` linking to inputs
   - `p-plan:correspondsToVariable` linking to template variable

## Multi-Step Workflow Pattern

For workflows with multiple steps:

1. Execute Step 1:
   - Create Activity 1
   - Generate Output 1

2. Execute Step 2:
   - Use Output 1 as input
   - Create Activity 2
   - Link with `prov:wasInformedBy` pointing to Activity 1
   - Generate final Output

The key is that **each step's output becomes the next step's input**, creating a complete provenance chain.

## Standards Used

- **P-Plan** - Workflow template structure
- **PROV-O** - Provenance and execution tracking
- **QUDT** - Quantities, units, dimensions
- **CSVW** - CSV metadata standard
- **BFO** - Basic Formal Ontology (for `is_input_of` relations)

## Further Reading

- [PROV-O Primer](https://www.w3.org/TR/prov-primer/)
- [P-Plan Ontology](http://purl.org/net/p-plan)
- [CSVW Primer](https://www.w3.org/TR/tabular-data-primer/)
- [Execution Generation Rules](../docs/EXECUTION_GENERATION_RULES.md)
