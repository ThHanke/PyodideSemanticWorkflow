# Use Case 1: Semantic Workflow Reuse

This guide is for developers who want to **use the workflow semantics** without the React Flow UI components. You only need the semantic definitions from `workflows/catalog.ttl`.

## Overview

The workflow catalog provides machine-readable definitions using W3C standards:
- **P-Plan** for workflow templates
- **PROV-O** for provenance
- **QUDT** for physical quantities
- **Schema.org** for discovery

## Quick Start

### 1. Load the Catalog

Using N3.js:

```javascript
import { Store, Parser } from 'n3';

const store = new Store();
const parser = new Parser();

// Load catalog
const catalogTtl = await fetch('workflows/catalog.ttl').then(r => r.text());
parser.parse(catalogTtl, (error, quad, prefixes) => {
  if (quad) store.addQuad(quad);
});
```

Using rdflib (Python):

```python
from rdflib import Graph

g = Graph()
g.parse('workflows/catalog.ttl', format='turtle')
```

### 2. Query for Workflow Templates

Find all available workflow templates:

```javascript
import { DataFactory } from 'n3';
const { namedNode } = DataFactory;

const P_PLAN_PLAN = namedNode('http://purl.org/net/p-plan#Plan');
const RDF_TYPE = namedNode('http://www.w3.org/1999/02/22-rdf-syntax-ns#type');

const templates = store.getQuads(null, RDF_TYPE, P_PLAN_PLAN);
templates.forEach(quad => {
  const templateURI = quad.subject.value;
  const label = store.getQuads(quad.subject, RDFS_LABEL, null)[0]?.object.value;
  console.log(`Template: ${label} (${templateURI})`);
});
```

SPARQL query:

```sparql
PREFIX p-plan: <http://purl.org/net/p-plan#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX schema: <https://schema.org/>

SELECT ?template ?label ?category ?description
WHERE {
    ?template a p-plan:Plan ;
              rdfs:label ?label ;
              schema:category ?category ;
              rdfs:comment ?description .
}
```

### 3. Discover Inputs and Outputs

For a specific template, find its inputs:

```javascript
const P_PLAN_IS_INPUT_VAR_OF = namedNode('http://purl.org/net/p-plan#isInputVarOf');
const SPW_EXPECTED_TYPE = namedNode('https://github.com/ThHanke/PyodideSemanticWorkflow#expectedType');

// Find the step
const steps = store.getQuads(null, P_PLAN_IS_STEP_OF_PLAN, templateURI);
const step = steps[0]?.subject;

// Find input variables
const inputs = store.getQuads(null, P_PLAN_IS_INPUT_VAR_OF, step);
inputs.forEach(quad => {
  const varURI = quad.subject;
  const label = store.getQuads(varURI, RDFS_LABEL, null)[0]?.object.value;
  const type = store.getQuads(varURI, SPW_EXPECTED_TYPE, null)[0]?.object.value;
  const required = store.getQuads(varURI, SPW_REQUIRED, null)[0]?.object.value;
  
  console.log(`Input: ${label}`);
  console.log(`  Type: ${type}`);
  console.log(`  Required: ${required}`);
});
```

### 4. Execute a Workflow

#### 4.1. Load the Python Implementation

```javascript
const SPW_SUM_CODE = namedNode('https://github.com/ThHanke/PyodideSemanticWorkflow#SumCode');
const PROV_AT_LOCATION = namedNode('http://www.w3.org/ns/prov#atLocation');

// Get code URL
const codeQuad = store.getQuads(SPW_SUM_CODE, PROV_AT_LOCATION, null)[0];
const codeURL = codeQuad.object.value;

// Fetch and load
const pythonCode = await fetch(codeURL).then(r => r.text());
```

#### 4.2. Execute with Pyodide

```javascript
// Initialize Pyodide
const pyodide = await loadPyodide();
await pyodide.loadPackage("micropip");
await pyodide.runPythonAsync(`
    import micropip
    await micropip.install("rdflib==7.0.0")
`);

// Create input graph
const inputGraph = `
@prefix qudt: <http://qudt.org/schema/qudt/> .
@prefix unit: <http://qudt.org/vocab/unit/> .
@prefix bfo: <https://example.org/bfo/> .

<urn:input1> a qudt:QuantityValue ;
    qudt:numericValue 2.0 ;
    qudt:unit unit:MilliM ;
    bfo:is_input_of <urn:activity> .

<urn:input2> a qudt:QuantityValue ;
    qudt:numericValue 3.0 ;
    qudt:unit unit:MilliM ;
    bfo:is_input_of <urn:activity> .
    
<urn:activity> a <http://www.w3.org/ns/prov#Activity> .
`;

// Load code and execute
pyodide.runPython(pythonCode);
const result = pyodide.runPython(`
run('''${inputGraph}''', 'urn:activity')
`);

console.log('Result:', result);
```

#### 4.3. Record Provenance

After execution, create a provenance record linking to the template:

```turtle
@prefix p-plan: <http://purl.org/net/p-plan#> .
@prefix prov: <http://www.w3.org/ns/prov#> .

:execution_001 a prov:Activity ;
    p-plan:correspondsToStep spw:SumStep ;
    prov:startedAtTime "2026-01-30T12:00:00Z"^^xsd:dateTime ;
    prov:endedAtTime "2026-01-30T12:00:01Z"^^xsd:dateTime ;
    prov:used :input1, :input2 .

:result a qudt:QuantityValue ;
    prov:wasGeneratedBy :execution_001 ;
    p-plan:correspondsToVariable spw:SumOutput .
```

## Integration Patterns

### Pattern 1: Workflow Validation

Validate input data against template specifications:

```javascript
function validateInput(inputData, templateVariable, store) {
  // Get expected type
  const expectedType = store.getQuads(
    templateVariable, 
    SPW_EXPECTED_TYPE, 
    null
  )[0]?.object;
  
  // Check if input matches type
  const actualType = store.getQuads(
    inputData,
    RDF_TYPE,
    null
  )[0]?.object;
  
  return expectedType.equals(actualType);
}
```

### Pattern 2: Dynamic Workflow Discovery

Find workflows that can process a specific data type:

```sparql
PREFIX p-plan: <http://purl.org/net/p-plan#>
PREFIX spw: <https://github.com/ThHanke/PyodideSemanticWorkflow#>
PREFIX qudt: <http://qudt.org/schema/qudt/>

SELECT ?template ?label WHERE {
    ?template a p-plan:Plan ;
              rdfs:label ?label .
    ?variable p-plan:isVariableOfPlan ?template ;
              p-plan:isInputVarOf ?step ;
              spw:expectedType qudt:QuantityValue .
}
```

### Pattern 3: Workflow Composition

Chain workflows by matching output types to input types:

```javascript
function canConnect(outputVariable, inputVariable, store) {
  const outType = store.getQuads(outputVariable, SPW_EXPECTED_TYPE, null)[0]?.object;
  const inType = store.getQuads(inputVariable, SPW_EXPECTED_TYPE, null)[0]?.object;
  
  return outType && inType && outType.equals(inType);
}
```

## Benefits

✅ **Standards-based** - Pure P-Plan/PROV-O, works with any RDF tool  
✅ **Framework-agnostic** - No UI dependencies  
✅ **Interoperable** - Exchange workflows with other systems  
✅ **Queryable** - SPARQL over workflow definitions  
✅ **Provenance-aware** - Track execution history  

## Next Steps

- See `examples/sum-execution.ttl` for complete execution examples
- See `docs/creating-workflows.md` to add your own workflows
- Explore SPARQL queries in `examples/README.md`
