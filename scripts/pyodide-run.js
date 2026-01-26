// Node runner that loads Pyodide via the npm package, executes a Python example file,
// and writes out Turtle (or other) outputs to disk for CI artifacts.
//
// Usage: node scripts/pyodide-run.js examples/workflow.py [fail_on_missing]

const fs = require('fs');
const path = require('path');

(async () => {
  try {
    const examplePath = process.argv[2] || 'sum_mm.py';
    const failOnMissing = (process.argv[3] || 'false') === 'true';

    const abs = path.resolve(examplePath);
    if (!fs.existsSync(abs)) {
      console.error('Example Python file not found:', abs);
      process.exit(2);
    }

    const code = fs.readFileSync(abs, 'utf8');

    // dynamic import so this can run in CommonJS environment
    const { loadPyodide } = await import('pyodide');

    console.log('Loading Pyodide (this loads WASM + stdlib from the npm package)...');
    // IMPORTANT: do NOT set indexURL to the CDN when using the npm package in Node
    const pyodide = await loadPyodide();
    console.log('Pyodide loaded.');

    console.log('Running example Python code from', abs);
    await pyodide.runPythonAsync(code);

    // Prefer Turtle string
    try {
      const val = pyodide.globals.get('result_ttl');
      if (val !== undefined && val !== null) {
        const resultTtl = typeof val.toJs === 'function' ? val.toJs() : String(val);
        fs.writeFileSync('pyodide-semantic-result.ttl', resultTtl, 'utf8');
        console.log('Saved Turtle result to pyodide-semantic-result.ttl');
        fs.writeFileSync('run-pyodide.log', 'Saved Turtle result\n');
        process.exit(0);
      }
    } catch (e) {
      // ignore and continue
    }

    // JSON-serializable object
    try {
      const resultObj = pyodide.globals.get('result_obj');
      if (resultObj !== undefined && resultObj !== null) {
        const jsObj = typeof resultObj.toJs === 'function' ? resultObj.toJs() : resultObj;
        fs.writeFileSync('pyodide-semantic-result.json', JSON.stringify(jsObj, null, 2), 'utf8');
        console.log('Saved JSON result to pyodide-semantic-result.json');
        fs.writeFileSync('run-pyodide.log', 'Saved JSON result\n');
        process.exit(0);
      }
    } catch (e) {
      // ignore and continue
    }

    // Generic raw string
    try {
      const anyRes = pyodide.globals.get('__SEMANTIC_WORKFLOW_RESULT__');
      if (anyRes !== undefined && anyRes !== null) {
        const jsAny = typeof anyRes.toJs === 'function' ? anyRes.toJs() : String(anyRes);
        fs.writeFileSync('pyodide-semantic-result.raw.txt', String(jsAny), 'utf8');
        console.log('Saved raw result to pyodide-semantic-result.raw.txt');
        fs.writeFileSync('run-pyodide.log', 'Saved raw result\n');
        process.exit(0);
      }
    } catch (e) {
      // ignore
    }

    console.warn('No recognized result variable found in Python globals.');
    fs.writeFileSync('run-pyodide.log', 'No result found\n');
    if (failOnMissing) {
      console.error('Failing because fail_on_missing was requested and no result was produced.');
      process.exit(3);
    } else {
      process.exit(0);
    }
  } catch (err) {
    console.error('Error running Pyodide example:', err);
    fs.writeFileSync('run-pyodide.log', `Error: ${String(err)}\n`);
    process.exit(4);
  }
})();