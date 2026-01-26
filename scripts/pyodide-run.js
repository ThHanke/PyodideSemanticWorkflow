// Node runner that loads Pyodide via the npm package, executes a Python example file,
// and writes out PROV-O semantic artifacts for CI.
//
// Usage: node scripts/pyodide-run.js example.py [fail_on_missing]

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

    // PROV context (passed from CI env or defaulted)
    const PROV_ACTIVITY_ID = process.env.PROV_ACTIVITY_ID || 'ci:pyodide-activity';
    const PROV_AGENT_ID = process.env.PROV_AGENT_ID || 'ci:github-actions';
    const PROV_PLAN = process.env.PROV_PLAN || 'sum_semantic_graph.ttl';

    // dynamic import for CommonJS
    const { loadPyodide } = await import('pyodide');

    console.log('Loading Pyodide (Node WASM runtime)…');
    const pyodide = await loadPyodide();
    console.log('Pyodide loaded.');

    // Inject PROV metadata into Python globals
    pyodide.globals.set('__PROV_ACTIVITY_ID__', PROV_ACTIVITY_ID);
    pyodide.globals.set('__PROV_AGENT_ID__', PROV_AGENT_ID);
    pyodide.globals.set('__PROV_PLAN__', PROV_PLAN);

    console.log('Running Python workflow:', abs);
    await pyodide.runPythonAsync(code);

    let wroteResult = false;

    // Preferred: Turtle (PROV graph)
    try {
      const ttl = pyodide.globals.get('result_ttl');
      if (ttl) {
        const text = typeof ttl.toJs === 'function' ? ttl.toJs() : String(ttl);
        fs.writeFileSync('pyodide-semantic-result.ttl', text, 'utf8');
        wroteResult = true;
      }
    } catch {}

    // JSON fallback
    try {
      const obj = pyodide.globals.get('result_obj');
      if (obj) {
        const jsObj = typeof obj.toJs === 'function' ? obj.toJs() : obj;
        fs.writeFileSync(
          'pyodide-semantic-result.json',
          JSON.stringify(jsObj, null, 2),
          'utf8'
        );
        wroteResult = true;
      }
    } catch {}

    // Raw fallback
    try {
      const raw = pyodide.globals.get('__SEMANTIC_WORKFLOW_RESULT__');
      if (raw) {
        const jsRaw = typeof raw.toJs === 'function' ? raw.toJs() : String(raw);
        fs.writeFileSync('pyodide-semantic-result.raw.txt', jsRaw, 'utf8');
        wroteResult = true;
      }
    } catch {}

    // Ensure PROV activity is materialized
    if (!fs.existsSync('sum_semantic_graph.ttl')) {
      fs.writeFileSync(
        'sum_semantic_graph.ttl',
        `
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix ci: <https://github.com/${process.env.GITHUB_REPOSITORY || 'ci'}/> .

ci:activity a prov:Activity ;
  prov:wasAssociatedWith ci:agent ;
  prov:used ci:plan .

ci:agent a prov:Agent .
ci:plan a prov:Plan .
`.trim() + '\n',
        'utf8'
      );
    }

    fs.writeFileSync(
      'run-pyodide.log',
      wroteResult
        ? 'Semantic result produced\n'
        : 'No semantic result found\n',
      'utf8'
    );

    if (!wroteResult && failOnMissing) {
      console.error('Failing: no semantic result produced.');
      process.exit(3);
    }

    process.exit(0);
  } catch (err) {
    console.error('Error running Pyodide workflow:', err);
    fs.writeFileSync('run-pyodide.log', `Error: ${String(err)}\n`);
    process.exit(4);
  }
})();
