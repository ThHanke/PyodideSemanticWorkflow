# Use Case 2: Full React Flow UI Integration

This guide is for developers building **visual workflow editors** using React Flow and semantic workflow definitions.

## Overview

You'll use both:
- `workflows/catalog.ttl` - Semantic workflow definitions
- `workflows/catalog-ui.ttl` - Optional UI styling and React Flow metadata

The UI metadata uses web standards (CSS properties) and minimal custom properties for React Flow integration.

## Quick Start

### 1. Setup N3 Store

```javascript
import { Store, Parser } from 'n3';

async function loadCatalogs() {
  const store = new Store();
  const parser = new Parser();
  
  // Load semantic catalog
  const catalogTtl = await fetch('workflows/catalog.ttl').then(r => r.text());
  await new Promise((resolve) => {
    parser.parse(catalogTtl, (error, quad) => {
      if (quad) store.addQuad(quad);
      else resolve();
    });
  });
  
  // Load UI metadata
  const uiTtl = await fetch('workflows/catalog-ui.ttl').then(r => r.text());
  const uiParser = new Parser();
  await new Promise((resolve) => {
    uiParser.parse(uiTtl, (error, quad) => {
      if (quad) store.addQuad(quad);
      else resolve();
    });
  });
  
  return store;
}
```

### 2. Create React Hook

```javascript
import { useState, useEffect } from 'react';
import { DataFactory } from 'n3';

const { namedNode } = DataFactory;

export function useWorkflowCatalog() {
  const [templates, setTemplates] = useState([]);
  const [store, setStore] = useState(null);
  
  useEffect(() => {
    loadCatalogs().then(s => {
      setStore(s);
      
      // Query for templates
      const P_PLAN_PLAN = namedNode('http://purl.org/net/p-plan#Plan');
      const RDF_TYPE = namedNode('http://www.w3.org/1999/02/22-rdf-syntax-ns#type');
      
      const templateQuads = s.getQuads(null, RDF_TYPE, P_PLAN_PLAN);
      
      const templateData = templateQuads.map(quad => 
        createTemplateData(quad.subject, s)
      );
      
      setTemplates(templateData);
    });
  }, []);
  
  return { templates, store };
}

function createTemplateData(templateURI, store) {
  const RDFS_LABEL = namedNode('http://www.w3.org/2000/01/rdf-schema#label');
  const RDFS_COMMENT = namedNode('http://www.w3.org/2000/01/rdf-schema#comment');
  const SCHEMA_CATEGORY = namedNode('https://schema.org/category');
  const SCHEMA_IMAGE = namedNode('https://schema.org/image');
  
  // CSS properties
  const CSS_BG = namedNode('https://www.w3.org/TR/CSS/#background-color');
  const CSS_BORDER = namedNode('https://www.w3.org/TR/CSS/#border-color');
  
  // SPW properties
  const SPW_NODE_TYPE = namedNode('https://github.com/ThHanke/PyodideSemanticWorkflow#nodeType');
  const SPW_WIDTH = namedNode('https://github.com/ThHanke/PyodideSemanticWorkflow#defaultWidth');
  const SPW_HEIGHT = namedNode('https://github.com/ThHanke/PyodideSemanticWorkflow#defaultHeight');
  
  return {
    id: templateURI.value,
    label: store.getQuads(templateURI, RDFS_LABEL, null)[0]?.object.value,
    description: store.getQuads(templateURI, RDFS_COMMENT, null)[0]?.object.value,
    category: store.getQuads(templateURI, SCHEMA_CATEGORY, null)[0]?.object.value,
    icon: store.getQuads(templateURI, SCHEMA_IMAGE, null)[0]?.object.value,
    
    // React Flow properties
    type: store.getQuads(templateURI, SPW_NODE_TYPE, null)[0]?.object.value || 'default',
    
    // Styling from CSS properties
    style: {
      backgroundColor: store.getQuads(templateURI, CSS_BG, null)[0]?.object.value,
      borderColor: store.getQuads(templateURI, CSS_BORDER, null)[0]?.object.value,
      width: store.getQuads(templateURI, SPW_WIDTH, null)[0]?.object.value + 'px',
      height: store.getQuads(templateURI, SPW_HEIGHT, null)[0]?.object.value + 'px',
    }
  };
}
```

### 3. Create Workflow Palette Component

```jsx
import { useWorkflowCatalog } from './useWorkflowCatalog';

function WorkflowPalette() {
  const { templates } = useWorkflowCatalog();
  
  const onDragStart = (event, template) => {
    event.dataTransfer.setData('application/reactflow', JSON.stringify(template));
    event.dataTransfer.effectAllowed = 'move';
  };
  
  return (
    <div className="workflow-palette">
      <h3>Workflow Templates</h3>
      {templates.map(template => (
        <div
          key={template.id}
          className="palette-item"
          draggable
          onDragStart={(e) => onDragStart(e, template)}
          style={template.style}
        >
          {template.icon && (
            <img 
              src={template.icon} 
              alt={template.label}
              style={{ width: 24, height: 24 }}
            />
          )}
          <span>{template.label}</span>
          <small>{template.description}</small>
        </div>
      ))}
    </div>
  );
}
```

### 4. Create Custom React Flow Node

```jsx
import { Handle, Position } from 'reactflow';

function SemanticWorkflowNode({ data }) {
  return (
    <div className="semantic-workflow-node" style={data.style}>
      <Handle 
        type="target" 
        position={Position.Left} 
        style={{ background: '#555' }}
      />
      
      <div className="node-content">
        {data.icon && <img src={data.icon} alt="" />}
        <strong>{data.label}</strong>
        <small>{data.description}</small>
      </div>
      
      <Handle 
        type="source" 
        position={Position.Right} 
        style={{ background: '#555' }}
      />
    </div>
  );
}
```

### 5. Integrate with React Flow

```jsx
import ReactFlow, { 
  ReactFlowProvider, 
  useNodesState, 
  useEdgesState 
} from 'reactflow';
import 'reactflow/dist/style.css';

const nodeTypes = {
  'semantic-workflow': SemanticWorkflowNode,
};

function WorkflowEditor() {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const { store } = useWorkflowCatalog();
  
  const onDrop = (event) => {
    event.preventDefault();
    
    const templateData = JSON.parse(
      event.dataTransfer.getData('application/reactflow')
    );
    
    const position = {
      x: event.clientX,
      y: event.clientY,
    };
    
    const newNode = {
      id: `node_${Date.now()}`,
      type: templateData.type,
      position,
      data: templateData,
    };
    
    setNodes((nds) => nds.concat(newNode));
  };
  
  const onDragOver = (event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  };
  
  return (
    <div style={{ height: '100vh', display: 'flex' }}>
      <WorkflowPalette />
      
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onDrop={onDrop}
        onDragOver={onDragOver}
        nodeTypes={nodeTypes}
        fitView
      >
        {/* Add Controls, Background, MiniMap as needed */}
      </ReactFlow>
    </div>
  );
}

export default function App() {
  return (
    <ReactFlowProvider>
      <WorkflowEditor />
    </ReactFlowProvider>
  );
}
```

## Advanced Features

### Type-Safe Connections

Validate connections based on semantic types:

```javascript
import { useCallback } from 'react';

function WorkflowEditor() {
  // ... existing code ...
  
  const isValidConnection = useCallback((connection, store) => {
    const sourceNode = nodes.find(n => n.id === connection.source);
    const targetNode = nodes.find(n => n.id === connection.target);
    
    // Get template URIs
    const sourceTemplate = namedNode(sourceNode.data.id);
    const targetTemplate = namedNode(targetNode.data.id);
    
    // Find output variable of source
    const sourceStep = store.getQuads(null, P_PLAN_IS_STEP_OF_PLAN, sourceTemplate)[0]?.subject;
    const sourceOutput = store.getQuads(null, P_PLAN_IS_OUTPUT_VAR_OF, sourceStep)[0]?.subject;
    const sourceType = store.getQuads(sourceOutput, SPW_EXPECTED_TYPE, null)[0]?.object;
    
    // Find input variable of target
    const targetStep = store.getQuads(null, P_PLAN_IS_STEP_OF_PLAN, targetTemplate)[0]?.subject;
    const targetInput = store.getQuads(null, P_PLAN_IS_INPUT_VAR_OF, targetStep)[0]?.subject;
    const targetType = store.getQuads(targetInput, SPW_EXPECTED_TYPE, null)[0]?.object;
    
    // Types must match
    return sourceType && targetType && sourceType.equals(targetType);
  }, [nodes, store]);
  
  return (
    <ReactFlow
      // ... other props ...
      isValidConnection={isValidConnection}
    />
  );
}
```

### Execute Workflow Graph

```javascript
async function executeWorkflow(nodes, edges, store) {
  // Topological sort to determine execution order
  const sorted = topologicalSort(nodes, edges);
  
  // Execute each node in order
  const results = {};
  
  for (const node of sorted) {
    const templateURI = namedNode(node.data.id);
    
    // Get Python code
    const step = store.getQuads(null, P_PLAN_IS_STEP_OF_PLAN, templateURI)[0]?.subject;
    const codeEntity = store.getQuads(step, PROV_USED, null)[0]?.object;
    const codeURL = store.getQuads(codeEntity, PROV_AT_LOCATION, null)[0]?.object.value;
    
    // Get inputs from connected edges
    const inputs = edges
      .filter(e => e.target === node.id)
      .map(e => results[e.source]);
    
    // Execute
    const result = await executePyodideWorkflow(codeURL, inputs);
    results[node.id] = result;
  }
  
  return results;
}
```

## Styling

All styling uses standard CSS properties from the catalog-ui.ttl file. These map directly to React inline styles:

```javascript
// CSS properties from RDF → React styles (no transformation needed!)
style: {
  backgroundColor: cssBackgroundColor,
  borderColor: cssBorderColor,
  borderWidth: cssBorderWidth,
  borderRadius: cssBorderRadius,
  // ... etc
}
```

## Benefits

✅ **Visual workflow editor** - Drag-and-drop interface  
✅ **Type-safe connections** - Semantic validation  
✅ **Standards-based styling** - CSS properties  
✅ **Automatic UI generation** - From RDF metadata  
✅ **Full provenance tracking** - PROV-O integration  

## Next Steps

- See example React Flow integration in `examples/`
- Add custom node types for specialized workflows
- Implement SHACL validation (future enhancement)
