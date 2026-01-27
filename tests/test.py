# tests/test.py

import pathlib
import pytest


def test_sum_mm_node(selenium_standalone, web_server_main):
    """Test sum_mm.py with Pyodide in Node.js runtime."""
    
    root = pathlib.Path(__file__).resolve().parents[1]
    sum_mm_path = root / "sum_mm.py"
    ttl_path = root / "sum_semantic_graph.ttl"
    result_path = root / "result.ttl"
    
    assert sum_mm_path.exists(), f"sum_mm.py not found: {sum_mm_path}"
    assert ttl_path.exists(), f"Input TTL file not found: {ttl_path}"
    
    print("Installing rdflib via micropip...")
    selenium_standalone.run_js("""
        await pyodide.loadPackage("micropip");
        await pyodide.runPythonAsync(`
            import micropip
            await micropip.install("rdflib==7.0.0")
        `);
    """)
    
    print("Loading sum_mm.py from filesystem...")
    sum_mm_code = sum_mm_path.read_text(encoding="utf-8")
    input_ttl = ttl_path.read_text(encoding="utf-8")
    
    # Escaping für JavaScript String
    sum_mm_escaped = sum_mm_code.replace('\\', '\\\\').replace('`', '\\`').replace('${', '\\${')
    input_ttl_escaped = input_ttl.replace('\\', '\\\\').replace('`', '\\`').replace('${', '\\${')
    
    print("Running sum_mm.py...")
    result_ttl = selenium_standalone.run_js(f"""
        const sumMmCode = `{sum_mm_escaped}`;
        const inputTtl = `{input_ttl_escaped}`;
        
        const result = await pyodide.runPythonAsync(`

# Definiere die Funktion

${{sumMmCode.split('# Pyodide / Node contract')[0]}}

# Führe aus

result = run('''${{inputTtl}}''')
result
        `);
        
        return result;
    """)
    
    # Speichere das Ergebnis
    print(f"Saving result to {result_path}...")
    result_path.write_text(result_ttl, encoding="utf-8")
    
    # Validiere Ergebnis
    print("Validating results...")
    from rdflib import Graph, Namespace
    from rdflib.namespace import RDF

    g = Graph()
    g.parse(data=result_ttl, format="turtle")

    QUDT = Namespace("http://qudt.org/schema/qudt/")
    UNIT = Namespace("http://qudt.org/vocab/unit/")

    qvs = list(g.subjects(RDF.type, QUDT.QuantityValue))
    print(f"Found {len(qvs)} QuantityValues")
    assert len(qvs) >= 3, f"Expected at least 3 QuantityValues, found {len(qvs)}"

    found_sum = False
    for qv in qvs:
        val = g.value(qv, QUDT.numericValue)
        unit = g.value(qv, QUDT.unit)
        if val is None:
            continue
        try:
            f = float(val)
            print(f"  QV: value={f}, unit={unit}")
            if f == 5.0 and unit == UNIT.MilliM:
                found_sum = True
        except Exception:
            continue

    assert found_sum, "No sum QuantityValue with value 5.0 MilliM found"
    print(f"✓ Test passed! Result saved to {result_path.name}")