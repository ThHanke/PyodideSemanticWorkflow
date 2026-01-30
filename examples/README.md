# Examples

This directory contains example workflow executions demonstrating how to use the workflow templates defined in `workflows/catalog.ttl`.

## Files

### sum-execution.ttl
A complete example showing:
- Concrete input data (two QUDT QuantityValues)
- Execution activity linking to the template
- Output result with full provenance chain
- Use of `p-plan:correspondsToStep` and `p-plan:correspondsToVariable` to link execution to template

## Key Concepts

### Template vs Execution

**Template Level** (in `workflows/catalog.ttl`):
```turtle
# Abstract definition - what kind of inputs are needed
spw:SumInput1 a p-plan:Variable ;
    p-plan:isVariableOfPlan spw:SumTemplate ;
    spw:expectedType qudt:QuantityValue .
```

**Execution Level** (in `sum-execution.ttl`):
```turtle
# Concrete data - actual values used in a specific run
spw:inputLength1 a qudt:QuantityValue ;
    qudt:numericValue "2.0"^^xsd:decimal ;
    p-plan:correspondsToVariable spw:SumInput1 .
```

### Provenance Queries

With this structure, you can query:

**Find all executions of a template:**
```sparql
SELECT ?execution ?startTime WHERE {
    ?execution p-plan:correspondsToStep spw:SumStep ;
               prov:startedAtTime ?startTime .
}
```

**Find what a result was derived from:**
```sparql
SELECT ?input WHERE {
    <#sumResult_c22ad6de4d807f4b> prov:wasDerivedFrom ?input .
}
```

**Find which template was used:**
```sparql
SELECT ?template WHERE {
    ?execution prov:wasGeneratedBy <#sumResult_c22ad6de4d807f4b> .
    ?execution p-plan:correspondsToStep ?step .
    ?step p-plan:isStepOfPlan ?template .
}
```

## Creating Your Own Execution Instance

1. Start with your template from `workflows/catalog.ttl`
2. Create concrete input entities (e.g., `qudt:QuantityValue`)
3. Link inputs to template variables using `p-plan:correspondsToVariable`
4. Create an activity linking to the template step using `p-plan:correspondsToStep`
5. Link the activity to inputs using `prov:used`
6. Generate output entity
7. Link output to activity using `prov:wasGeneratedBy`
8. Link output to inputs using `prov:wasDerivedFrom`

Example template:
```turtle
# Create concrete inputs
:myInput1 a qudt:QuantityValue ;
    qudt:numericValue 10.0 ;
    p-plan:correspondsToVariable spw:SumInput1 .

# Create execution
:myExecution a prov:Activity ;
    p-plan:correspondsToStep spw:SumStep ;
    prov:used :myInput1, :myInput2 .

# Create output
:myOutput a qudt:QuantityValue ;
    prov:wasGeneratedBy :myExecution ;
    prov:wasDerivedFrom :myInput1, :myInput2 .
```
