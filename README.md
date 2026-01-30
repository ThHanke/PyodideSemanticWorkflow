# PyodideSemanticWorkflow

**Semantic workflow definitions for browser-based Python data processing using Pyodide.**

This repository provides semantically-enriched workflow templates that can be executed in-browser via Pyodide (WebAssembly Python), enabling interactive data processing and workflow composition without backend servers.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Key Features

- **Standards-Based** - Uses W3C standards (P-Plan, PROV-O, Schema.org)
- **Framework-Agnostic** - Semantic definitions work with any RDF tool
- **Two Integration Modes** - Semantic-only OR full React Flow UI
- **Browser-Native** - Runs entirely in-browser via Pyodide (no backend)
- **Provenance-Aware** - Complete execution tracking using PROV-O
- **Type-Safe** - Semantic type checking (QUDT quantities)
- **Extensible** - Easy to add new workflow templates

## Quick Start

### Use Case 1: Semantic Workflow Definitions Only

Load workflow templates and execute them programmatically:

```javascript
import { Store, Parser } from 'n3';

// Load workflow catalog
const store = new Store();
const parser = new Parser();
const catalogTtl = await fetch('workflows/catalog.ttl').then(r => r.text());
parser.parse(catalogTtl, (error, quad) => {
  if (quad) store.addQuad(quad);
});

// Query for available templates
const templates = store.getQuads(null, RDF.type, P_PLAN.Plan);
```

**See:** [Use Case 1 Documentation](docs/USE_CASE_1.md)

### Use Case 2: React Flow UI Integration

Build visual workflow editors with drag-and-drop:

```jsx
import { useWorkflowCatalog } from './hooks/useWorkflowCatalog';

function WorkflowEditor() {
  const { templates } = useWorkflowCatalog();
  
  return (
    <ReactFlow>
      {/* Drag-drop workflow templates from catalog */}
    </ReactFlow>
  );
}
```

**See:** [Use Case 2 Documentation](docs/USE_CASE_2.md)

## Architecture

### Layered Ontology Approach

```text
                                     
   Your Application (React Flow)     
                                     |
   SPW Ontology (minimal custom)       -> Workflow-specific properties
                                     |
   CSS Properties (web standards)      -> Styling
                                     |
   Schema.org + QUDT (discovery)       -> Metadata & types
                                     |
   P-Plan (workflow templates)         -> Template structure
                                     |
   PROV-O (provenance)                 -> W3C provenance standard
                                     
```

### File Structure

```text
PyodideSemanticWorkflow/
   workflows/
      catalog.ttl              # Semantic workflow templates (Use Case 1 & 2)
      catalog-ui.ttl           # Optional UI metadata (Use Case 2 only)
      sum.py                   # Python implementation (Pyodide)
      requirements.txt         # Python dependencies
   ontology/
      spw.ttl                  # SPW vocabulary definition
      README.md                # Ontology documentation
   examples/
      sum-execution.ttl        # Example execution with provenance
      README.md                # Example documentation
   docs/
      USE_CASE_1.md           # Semantic-only integration guide
      USE_CASE_2.md           # React Flow UI integration guide
      creating-workflows.md    # How to add new workflows (TODO)
   tests/
       test.py                  # Pyodide execution tests
```

## Workflow Templates

The catalog currently includes:

### 1. **Sum QUDT Quantities**
Sums two or more QUDT QuantityValue instances with compatible units.
- **Inputs:** 2+ QuantityValues (same unit)
- **Output:** Sum as QuantityValue
- **Category:** Mathematics

### 2. **Multiply QUDT Quantities**
Multiplies two QUDT QuantityValue instances with unit algebra.
- **Inputs:** 2 QuantityValues
- **Output:** Product with derived unit (e.g., m × m = m²)
- **Category:** Mathematics

### 3. **Convert QUDT Units**
Converts a QuantityValue to a different compatible unit.
- **Inputs:** 1 QuantityValue, 1 target Unit
- **Output:** Converted QuantityValue
- **Category:** Units

## Standards Used

### Core Ontologies
- **[P-Plan](http://purl.org/net/p-plan)** - Workflow template structure
- **[PROV-O](https://www.w3.org/TR/prov-o/)** - Provenance and execution tracking
- **[QUDT](http://www.qudt.org/)** - Physical quantities, units, dimensions
- **[Schema.org](https://schema.org/)** - Discovery and description metadata

### UI Integration
- **CSS Properties** - Standard web styling (from W3C WebRef)
- **SPW Ontology** - Minimal custom properties for React Flow

## Example: Template Definition

From `workflows/catalog.ttl`:

```turtle
spw:SumTemplate a p-plan:Plan, prov:Plan ;
    rdfs:label "Sum QUDT Quantities"@en ;
    schema:category "Mathematics" ;
    dcterms:license <https://spdx.org/licenses/MIT> .

spw:SumStep a p-plan:Step ;
    p-plan:isStepOfPlan spw:SumTemplate ;
    prov:used spw:SumCode .

spw:SumInput1 a p-plan:Variable ;
    p-plan:isVariableOfPlan spw:SumTemplate ;
    p-plan:isInputVarOf spw:SumStep ;
    spw:expectedType qudt:QuantityValue ;
    spw:required true .
```

## Example: Execution Instance

From `examples/sum-execution.ttl`:

```turtle
# Concrete execution linking back to template
spw:SumRun_1 a prov:Activity ;
    p-plan:correspondsToStep spw:SumStep ;
    prov:used spw:inputLength1, spw:inputLength2 ;
    prov:startedAtTime "2026-01-30T10:45:00Z"^^xsd:dateTime .

# Result with full provenance
<#sumResult_abc123> a qudt:QuantityValue ;
    qudt:numericValue 5.0 ;
    prov:wasGeneratedBy spw:SumRun_1 ;
    prov:wasDerivedFrom spw:inputLength1, spw:inputLength2 .
```

## Installation & Setup

### For Use Case 1 (Semantic Only)

```bash
# Clone repository
git clone https://github.com/ThHanke/PyodideSemanticWorkflow.git

# Install N3.js or rdflib
npm install n3
# or
pip install rdflib
```

Load the catalog and start querying (see [Use Case 1 docs](docs/USE_CASE_1.md)).

### For Use Case 2 (React Flow UI)

```bash
# Install dependencies
npm install n3 reactflow react react-dom

# Load both catalogs
import catalog from './workflows/catalog.ttl';
import catalogUI from './workflows/catalog-ui.ttl';
```

Build your workflow editor (see [Use Case 2 docs](docs/USE_CASE_2.md)).

## SPARQL Queries

Find workflows by category:

```sparql
PREFIX p-plan: <http://purl.org/net/p-plan#>
PREFIX schema: <https://schema.org/>

SELECT ?template ?label WHERE {
    ?template a p-plan:Plan ;
              rdfs:label ?label ;
              schema:category "Mathematics" .
}
```

Find all executions of a template:

```sparql
PREFIX p-plan: <http://purl.org/net/p-plan#>
PREFIX prov: <http://www.w3.org/ns/prov#>

SELECT ?execution ?startTime WHERE {
    ?execution p-plan:correspondsToStep spw:SumStep ;
               prov:startedAtTime ?startTime .
}
```

Trace provenance chain:

```sparql
PREFIX prov: <http://www.w3.org/ns/prov#>

SELECT ?input WHERE {
    <#result_abc123> prov:wasDerivedFrom ?input .
}
```

## Development

### Adding New Workflows

1. Create Python implementation in `workflows/`
2. Add template definition to `workflows/catalog.ttl`
3. (Optional) Add UI metadata to `workflows/catalog-ui.ttl`
4. Create example execution in `examples/`
5. Update tests

See [Creating Workflows Guide](docs/creating-workflows.md) (coming soon).

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-pyodide

# Run tests
pytest tests/
```

## Project Goals

1. **Interoperability** - Enable workflow exchange between systems using W3C standards
2. **Provenance** - Track complete execution history for reproducibility
3. **Browser-Native** - No backend required, runs entirely client-side
4. **Developer-Friendly** - Both semantic-only and UI integration paths
5. **Standards-Compliant** - Minimal custom vocabulary, maximum reuse

## Related Projects

- [Pyodide](https://pyodide.org/) - Python compiled to WebAssembly
- [React Flow](https://reactflow.dev/) - Visual workflow builder for React
- [N3.js](https://github.com/rdfjs/N3.js) - RDF library for JavaScript
- [rdflib](https://github.com/RDFLib/rdflib) - RDF library for Python

## Contributing

Contributions welcome! Areas of interest:
- Additional workflow templates (data processing, ML, etc.)
- SHACL validation shapes
- Improved React Flow components
- Documentation improvements
- Test coverage

## License

MIT License - see [LICENSE](LICENSE) file.

## Citation

If you use this in research, please cite:

```bibtex
@software{pyodide_semantic_workflow,
  author = {Hanke, Thomas},
  title = {PyodideSemanticWorkflow: Semantic Workflow Definitions for Browser-Based Python Processing},
  year = {2026},
  url = {https://github.com/ThHanke/PyodideSemanticWorkflow}
}
```

## Acknowledgments

Built with:
- **P-Plan** ontology by Daniel Garijo and Yolanda Gil
- **PROV-O** W3C provenance ontology
- **QUDT** quantities, units, dimensions, and types ontology
- **Pyodide** project for WebAssembly Python

## Contact

- GitHub: [@ThHanke](https://github.com/ThHanke)
- Repository: [PyodideSemanticWorkflow](https://github.com/ThHanke/PyodideSemanticWorkflow)
