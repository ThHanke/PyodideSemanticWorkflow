# Activity Generation Rules from P-Plan Templates

This document describes the rules for programmatically generating PROV-O Activity instances from P-Plan workflow templates.

**⚠️ IMPORTANT**: For workflows with multiple steps, also see [Generic Activity Generation](GENERIC_ACTIVITY_GENERATION.md) which provides template-agnostic derivation rules that work for ANY workflow.

## Architecture Overview

```
TEMPLATE (Design Time)          EXECUTION (Runtime)
├─ p-plan:Plan                  ├─ prov:Activity
├─ p-plan:Step                  │   ├─ prov:hadPlan → Plan
├─ p-plan:Variable              │   ├─ p-plan:correspondsToStep → Step
└─ prov:used (on Step)          │   ├─ prov:used → [Resources + Data]
                                │   └─ prov:wasAssociatedWith → Agent
                                └─ prov:Entity (concrete data)
                                    └─ p-plan:correspondsToVariable → Variable
```

## Rule Set for Activity Generation

### Rule 1: Create Activity Linked to Plan

**Input:** A p-plan:Plan/Step to execute
**Output:** A prov:Activity

```sparql
# Template Query
SELECT ?plan ?step WHERE {
    ?step p-plan:isStepOfPlan ?plan .
    FILTER(?step = spw:SumStep)
}

# Generate Activity
?newActivity a prov:Activity ;
    prov:hadPlan ?plan ;                    # Link to the Plan
    p-plan:correspondsToStep ?step ;        # Link to the Step
```

**Example:**
```turtle
spw:SumRun_1 a prov:Activity ;
    prov:hadPlan spw:SumTemplate ;
    p-plan:correspondsToStep spw:SumStep .
```

---

### Rule 2: Inherit Step Resources (Code & Dependencies)

**Input:** The Step being executed
**Output:** Resources that the Activity uses

```sparql
# Template Query: What does this Step use?
SELECT ?resource WHERE {
    spw:SumStep prov:used ?resource .
}
# Returns: spw:SumCode, spw:SumRequirements

# Generate Activity usage statements
?newActivity prov:used ?resource .
```

**Example:**
```turtle
# From catalog.ttl (Template):
spw:SumStep prov:used spw:SumCode, spw:SumRequirements .

# Generates (Execution):
spw:SumRun_1 prov:used spw:SumCode, spw:SumRequirements .
```

**Rationale:** The Step declares what implementation resources are needed. The Activity inherits these declarations because it's executing that Step.

---

### Rule 3: Add Concrete Input Data

**Input:** User-provided data + template variables
**Output:** Concrete entities with `prov:used` links

```sparql
# Template Query: What inputs are required?
SELECT ?var WHERE {
    ?var p-plan:isInputVarOf spw:SumStep .
}
# Returns: spw:SumInput1, spw:SumInput2

# For each required variable, user must provide concrete data:
?concreteData a qudt:QuantityValue, prov:Entity ;
    p-plan:correspondsToVariable ?var ;     # Links back to template
    qudt:numericValue ?value ;
    qudt:unit ?unit .

# Activity uses the concrete data:
?newActivity prov:used ?concreteData .
```

**Example:**
```turtle
# User provides:
spw:inputLength1 a qudt:QuantityValue, prov:Entity ;
    qudt:numericValue "2.0"^^xsd:decimal ;
    qudt:unit unit:MilliM ;
    p-plan:correspondsToVariable spw:SumInput1 .  # Maps to template

# Generates:
spw:SumRun_1 prov:used spw:inputLength1 .
```

---

### Rule 4: Associate with Execution Agent

**Input:** The Step's declared agent
**Output:** Agent association in Activity

```sparql
# Template Query: What agent executes this?
SELECT ?agent WHERE {
    spw:SumStep prov:wasAssociatedWith ?agent .
}
# Returns: spw:PyodideEngine

# Generate Activity association
?newActivity prov:wasAssociatedWith ?agent .
```

**Example:**
```turtle
spw:SumRun_1 prov:wasAssociatedWith spw:PyodideEngine .
```

---

### Rule 5: Generate Output Entities

**Input:** Step execution results + template output variables
**Output:** Concrete result entities

```sparql
# Template Query: What outputs are expected?
SELECT ?var WHERE {
    ?var p-plan:isOutputVarOf spw:SumStep .
}
# Returns: spw:SumOutput

# Generate result entity:
?result a qudt:QuantityValue, prov:Entity ;
    p-plan:correspondsToVariable ?var ;      # Maps to template
    prov:wasGeneratedBy ?newActivity ;       # Created by this execution
    prov:wasDerivedFrom ?input1, ?input2 ;   # Derived from these inputs
    qudt:numericValue ?computedValue ;
    qudt:unit ?computedUnit .
```

**Example:**
```turtle
<#sumResult_c22ad6de4d807f4b> a qudt:QuantityValue, prov:Entity ;
    p-plan:correspondsToVariable spw:SumOutput ;
    prov:wasGeneratedBy spw:SumRun_1 ;
    prov:wasDerivedFrom spw:inputLength1, spw:inputLength2 ;
    qudt:numericValue "5.0"^^xsd:decimal ;
    qudt:unit unit:MilliM .
```

---

## Complete Generation Algorithm

### Pseudocode

```python
def generate_activity_from_template(plan_uri, step_uri, user_inputs, execution_id):
    """
    Generate a PROV-O Activity instance from a P-Plan template.
    
    Args:
        plan_uri: URI of the p-plan:Plan to execute
        step_uri: URI of the p-plan:Step to execute
        user_inputs: Dict mapping variable URIs to concrete data
        execution_id: Unique ID for this execution
    
    Returns:
        RDF graph containing the Activity and its entities
    """
    g = Graph()
    
    # 1. Create Activity with plan/step links
    activity = URIRef(f"{plan_uri}Run_{execution_id}")
    g.add((activity, RDF.type, PROV.Activity))
    g.add((activity, PROV.hadPlan, plan_uri))
    g.add((activity, P_PLAN.correspondsToStep, step_uri))
    
    # 2. Inherit resources from Step (Rule 2)
    for resource in template_graph.objects(step_uri, PROV.used):
        g.add((activity, PROV.used, resource))
    
    # 3. Add concrete input data (Rule 3)
    for var_uri, concrete_data in user_inputs.items():
        data_uri = URIRef(f"input_{execution_id}_{var_uri.fragment}")
        g.add((data_uri, RDF.type, QUDT.QuantityValue))
        g.add((data_uri, RDF.type, PROV.Entity))
        g.add((data_uri, P_PLAN.correspondsToVariable, var_uri))
        g.add((data_uri, QUDT.numericValue, concrete_data['value']))
        g.add((data_uri, QUDT.unit, concrete_data['unit']))
        g.add((activity, PROV.used, data_uri))
    
    # 4. Associate with agent (Rule 4)
    agent = template_graph.value(step_uri, PROV.wasAssociatedWith)
    if agent:
        g.add((activity, PROV.wasAssociatedWith, agent))
    
    # 5. Execute and generate output (Rule 5)
    result_value = execute_step_logic(step_uri, user_inputs)
    
    output_var = template_graph.value(
        None, P_PLAN.isOutputVarOf, step_uri
    )
    result_uri = URIRef(f"result_{execution_id}")
    g.add((result_uri, RDF.type, QUDT.QuantityValue))
    g.add((result_uri, RDF.type, PROV.Entity))
    g.add((result_uri, P_PLAN.correspondsToVariable, output_var))
    g.add((result_uri, PROV.wasGeneratedBy, activity))
    g.add((result_uri, QUDT.numericValue, result_value['value']))
    g.add((result_uri, QUDT.unit, result_value['unit']))
    
    # Link output to inputs via wasDerivedFrom
    for input_uri in user_inputs.keys():
        g.add((result_uri, PROV.wasDerivedFrom, input_uri))
    
    # Add timestamps
    g.add((activity, PROV.startedAtTime, Literal(start_time, datatype=XSD.dateTime)))
    g.add((activity, PROV.endedAtTime, Literal(end_time, datatype=XSD.dateTime)))
    
    return g
```

---

## SPARQL Query for Complete Generation

This single query extracts all information needed from the template:

```sparql
PREFIX p-plan: <http://purl.org/net/p-plan#>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX spw: <https://thhanke.github.io/PyodideSemanticWorkflow#>

# Get all information needed to instantiate SumTemplate
SELECT 
    ?plan 
    ?step 
    ?resource          # Code & dependencies to inherit
    ?agent             # Execution agent
    ?inputVar          # Required input variables
    ?outputVar         # Expected output variables
WHERE {
    # Plan and Step
    BIND(spw:SumTemplate AS ?plan)
    ?step p-plan:isStepOfPlan ?plan .
    
    # Resources the Step uses (Code, Requirements)
    OPTIONAL { ?step prov:used ?resource }
    
    # Agent that executes the Step
    OPTIONAL { ?step prov:wasAssociatedWith ?agent }
    
    # Input variables (what user must provide)
    OPTIONAL {
        ?inputVar p-plan:isInputVarOf ?step .
    }
    
    # Output variables (what will be generated)
    OPTIONAL {
        ?outputVar p-plan:isOutputVarOf ?step .
    }
}

# Results for spw:SumTemplate:
# ?resource      → spw:SumCode, spw:SumRequirements
# ?agent         → spw:PyodideEngine
# ?inputVar      → spw:SumInput1, spw:SumInput2
# ?outputVar     → spw:SumOutput
```

---

## Validation Rules

Before generating an Activity, validate:

1. **All required inputs provided:**
   ```sparql
   SELECT ?var WHERE {
       ?var p-plan:isInputVarOf ?step ;
            spw:required true .
       FILTER NOT EXISTS {
           ?data p-plan:correspondsToVariable ?var .
       }
   }
   # Should return empty result (all required vars have data)
   ```

2. **Input types match expectations:**
   ```sparql
   SELECT ?var ?expectedType ?actualType WHERE {
       ?var spw:expectedType ?expectedType .
       ?data p-plan:correspondsToVariable ?var ;
             rdf:type ?actualType .
       FILTER(?expectedType != ?actualType)
   }
   # Should return empty result (types match)
   ```

---

## Example: Complete Sum Execution Generation

### Input Configuration
```json
{
  "template": "spw:SumTemplate",
  "step": "spw:SumStep",
  "executionId": "2026-01-30_001",
  "inputs": {
    "spw:SumInput1": {
      "value": 2.0,
      "unit": "unit:MilliM"
    },
    "spw:SumInput2": {
      "value": 3.0,
      "unit": "unit:MilliM"
    }
  }
}
```

### Generated RDF
```turtle
# Activity (Rules 1, 2, 4)
spw:SumRun_2026-01-30_001 a prov:Activity ;
    prov:hadPlan spw:SumTemplate ;
    p-plan:correspondsToStep spw:SumStep ;
    prov:used spw:SumCode, spw:SumRequirements ;    # Inherited from Step
    prov:used spw:input_001_1, spw:input_001_2 ;    # Concrete data
    prov:wasAssociatedWith spw:PyodideEngine ;
    prov:startedAtTime "2026-01-30T16:10:00Z"^^xsd:dateTime ;
    prov:endedAtTime "2026-01-30T16:10:01Z"^^xsd:dateTime .

# Input Data (Rule 3)
spw:input_001_1 a qudt:QuantityValue, prov:Entity ;
    p-plan:correspondsToVariable spw:SumInput1 ;
    qudt:numericValue "2.0"^^xsd:decimal ;
    qudt:unit unit:MilliM .

spw:input_001_2 a qudt:QuantityValue, prov:Entity ;
    p-plan:correspondsToVariable spw:SumInput2 ;
    qudt:numericValue "3.0"^^xsd:decimal ;
    qudt:unit unit:MilliM .

# Output (Rule 5)
spw:result_001 a qudt:QuantityValue, prov:Entity ;
    p-plan:correspondsToVariable spw:SumOutput ;
    prov:wasGeneratedBy spw:SumRun_2026-01-30_001 ;
    prov:wasDerivedFrom spw:input_001_1, spw:input_001_2 ;
    qudt:numericValue "5.0"^^xsd:decimal ;
    qudt:unit unit:MilliM .
```

---

## Key Insight: The Pattern

**The generation rule is simple:**

```
Activity.prov:used = 
    Step.prov:used                    // Inherit Step resources
    + ConcreteData.correspondsTo(     // Plus user-provided OR intermediate data
        Variable.isInputVarOf(Step)   //   for each input variable
      )
```

**In words:** 
- The Activity uses everything the Step uses (code, dependencies)
- PLUS the concrete data that corresponds to the Step's input variables
  - If the variable is ALSO an output of another step: use intermediate data
  - If the variable is ONLY an input: user provides concrete data

This is why we put `prov:used` on the Step in `catalog.ttl` - it declares what gets inherited by all Activities executing that Step!

### Multi-Step Data Flow

For workflows with multiple steps, data flows automatically when a variable is BOTH an output and an input:

```turtle
# In template (catalog.ttl):
?intermediateVar p-plan:isOutputVarOf ?stepA ;
                 p-plan:isInputVarOf ?stepB .

# In execution:
?entityFromA prov:wasGeneratedBy ?activityA ;
             p-plan:correspondsToVariable ?intermediateVar .

?activityB prov:used ?entityFromA ;
           prov:wasInformedBy ?activityA .
```

**See [Generic Activity Generation](GENERIC_ACTIVITY_GENERATION.md) for complete details on multi-step workflows.**

---

## Implementation Example

See the complete two-level example in:
- **Template:** `workflows/catalog.ttl` (lines 53-97)
- **Execution:** `sum_semantic_graph.ttl` (lines 166-200)

The execution was generated following these exact rules.
