# SPW Ontology

The **Semantic Python Workflow (SPW)** ontology extends [P-Plan](http://purl.org/net/p-plan) and [PROV-O](https://www.w3.org/TR/prov-o/) with minimal properties specific to Python-based workflows executed in Pyodide.

## Design Philosophy

SPW follows the principle of **minimal extension**: only properties that are truly specific to this domain are defined. Wherever possible, existing standards are used:

- **P-Plan** for workflow template structure
- **PROV-O** for provenance and execution
- **Schema.org** for discovery and description
- **QUDT** for quantities and units
- **CSS properties** for styling

## Namespace

```turtle
@prefix spw: <https://github.com/ThHanke/PyodideSemanticWorkflow#> .
```

## Classes

### spw:WorkflowCategory
Groups related workflow templates for organization and filtering.

**Example:**
```turtle
spw:MathematicsCategory a spw:WorkflowCategory ;
    rdfs:label "Mathematics" .
```

## Properties

### Semantic Properties

#### spw:expectedType
- **Domain:** `p-plan:Variable`
- **Range:** `rdfs:Class`
- **Purpose:** Specifies the RDF type expected for a variable's value
- **Example:**
  ```turtle
  spw:SumInput1 spw:expectedType qudt:QuantityValue .
  ```

#### spw:required
- **Domain:** `p-plan:Variable`
- **Range:** `xsd:boolean`
- **Purpose:** Indicates whether a variable is required or optional
- **Example:**
  ```turtle
  spw:SumInput1 spw:required true .
  ```

#### spw:packageManager
- **Domain:** `prov:Entity`
- **Range:** `xsd:string`
- **Purpose:** Specifies which package manager to use (pip, micropip, etc.)
- **Example:**
  ```turtle
  spw:SumRequirements spw:packageManager "pip" .
  ```

### React Flow UI Properties

These properties are optional and only used when generating React Flow UIs (Use Case 2).

#### spw:nodeType
- **Domain:** `p-plan:Plan`
- **Range:** `xsd:string`
- **Purpose:** Maps to React Flow's `nodeType` property
- **Example:**
  ```turtle
  spw:SumTemplate spw:nodeType "semantic-workflow" .
  ```

#### spw:defaultWidth, spw:defaultHeight
- **Domain:** `p-plan:Plan`
- **Range:** `xsd:string` (pixel values)
- **Purpose:** Default dimensions for the node
- **Example:**
  ```turtle
  spw:SumTemplate
      spw:defaultWidth "200" ;
      spw:defaultHeight "80" .
  ```

#### spw:inputHandlePosition, spw:outputHandlePosition
- **Domain:** `p-plan:Plan`
- **Range:** `xsd:string` (left, right, top, bottom)
- **Purpose:** Position of connection handles
- **Example:**
  ```turtle
  spw:SumTemplate
      spw:inputHandlePosition "left" ;
      spw:outputHandlePosition "right" .
  ```

#### spw:handleStyle
- **Domain:** `p-plan:Plan`
- **Range:** `xsd:string` (smooth, step, straight)
- **Purpose:** Style of connection lines
- **Example:**
  ```turtle
  spw:SumTemplate spw:handleStyle "smooth" .
  ```

## Usage

### Use Case 1: Semantic-Only
Import only the semantic properties you need. UI properties can be ignored.

```turtle
@prefix spw: <https://github.com/ThHanke/PyodideSemanticWorkflow#> .

spw:MyVariable
    spw:expectedType qudt:QuantityValue ;
    spw:required true .
```

### Use Case 2: Full UI Integration
Use all properties including React Flow-specific ones.

```turtle
spw:MyTemplate
    # Semantic
    spw:required true ;
    # UI
    spw:nodeType "custom" ;
    spw:defaultWidth "200" .
```

## Related Ontologies

- [P-Plan](http://purl.org/net/p-plan) - Workflow templates
- [PROV-O](https://www.w3.org/TR/prov-o/) - Provenance
- [QUDT](http://www.qudt.org/) - Quantities and units
- [Schema.org](https://schema.org/) - Discovery metadata
