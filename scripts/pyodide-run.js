// scripts/pyodide-run.js
// Pyodide runner for OFFICIAL pyodide/pyodide-env Docker image

const fs = require("fs");
const path = require("path");

(async () => {
  try {
    const examplePath = process.argv[2] || "sum_mm.py";
    const failOnMissing = (process.argv[3] || "false") === "true";

    const abs = path.resolve(examplePath);
    if (!fs.existsSync(abs)) {
      console.error("Example Python file not found:", abs);
      process.exit(2);
    }

    const code = fs.readFileSync(abs, "utf8");

    // ------------------------------------------------------------------
    // IMPORTANT: load Pyodide from the container-provided path
    // ------------------------------------------------------------------
    const { loadPyodide } = await import(
      "file:///usr/share/pyodide/pyodide.mjs"
    );

    console.log("Loading Pyodide from /usr/share/pyodide …");

    const pyodide = await loadPyodide({
      indexURL: "/usr/share/pyodide"
    });

    console.log("Pyodide loaded.");

    // Inject PROV context
    pyodide.globals.set("__PROV_ACTIVITY_ID__", process.env.PROV_ACTIVITY_ID);
    pyodide.globals.set("__PROV_AGENT_ID__", process.env.PROV_AGENT_ID);
    pyodide.globals.set("__PROV_PLAN__", process.env.PROV_PLAN);

    console.log("Running Python workflow:", abs);
    await pyodide.runPythonAsync(code);

    let wroteResult = false;

    // Preferred: Turtle
    try {
      const ttl = pyodide.globals.get("result_ttl");
      if (ttl) {
        const text = typeof ttl.toJs === "function" ? ttl.toJs() : String(ttl);
        fs.writeFileSync("pyodide-semantic-result.ttl", text, "utf8");
        wroteResult = true;
      }
    } catch {}

    // JSON fallback
    try {
      const obj = pyodide.globals.get("result_obj");
      if (obj) {
        const jsObj = typeof obj.toJs === "function" ? obj.toJs() : obj;
        fs.writeFileSync(
          "pyodide-semantic-result.json",
          JSON.stringify(jsObj, null, 2),
          "utf8"
        );
        wroteResult = true;
      }
    } catch {}

    // Raw fallback
    try {
      const raw = pyodide.globals.get("__SEMANTIC_WORKFLOW_RESULT__");
      if (raw) {
        const jsRaw = typeof raw.toJs === "function" ? raw.toJs() : String(raw);
        fs.writeFileSync("pyodide-semantic-result.raw.txt", jsRaw, "utf8");
        wroteResult = true;
      }
    } catch {}

    fs.writeFileSync(
      "run-pyodide.log",
      wroteResult ? "Semantic result produced\n" : "No semantic result found\n",
      "utf8"
    );

    if (!wroteResult && failOnMissing) {
      console.error("Failing: no semantic result produced.");
      process.exit(3);
    }

    process.exit(0);
  } catch (err) {
    console.error("Error running Pyodide workflow:", err);
    fs.writeFileSync("run-pyodide.log", `Error: ${String(err)}\n`);
    process.exit(4);
  }
})();
