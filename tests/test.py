# tests/test.py

import pathlib
import pytest


@pytest.fixture(scope="module")
def pyodide_with_rdflib(selenium_module_scope):
    """Setup Pyodide with rdflib installed (runs once per test module)."""
    selenium = selenium_module_scope
    
    # Setze langes Timeout für Installation
    if hasattr(selenium, 'p') and selenium.p is not None:
        selenium.p.timeout = 600
    selenium.script_timeout = 600
    
    root = pathlib.Path(__file__).resolve().parents[1]
    req_file = root / "requirements.txt"
    
    reqs = []
    if req_file.exists():
        for line in req_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            reqs.append(line)
    
    print("\n=== Setting up Pyodide environment ===")
    print("Loading micropip...")
    selenium.run_js("""
        await pyodide.loadPackage("micropip");
    """)
    
    if reqs:
        for req in reqs:
            print(f"Installing {req}...")
            selenium.run_js(f"""
                return await pyodide.runPythonAsync(`
                    import micropip
                    await micropip.install({req!r})
                `);
            """)
    
    print("✓ Pyodide setup complete\n")
    
    return selenium


def test_sum_mm_node(pyodide_with_rdflib):
    """Test sum_mm.py with Pyodide in Node.js runtime."""
    
    selenium = pyodide_with_rdflib
    
    # Erhöhe Timeout deutlich für den Test
    if hasattr(selenium, 'p') and selenium.p is not None:
        selenium.p.timeout = 300
    selenium.script_timeout = 300
    
    # 1) Pfade vorbereiten
    root = pathlib.Path(__file__).resolve().parents[1]
    sum_mm_path = root / "sum_mm.py"
    ttl_path = root / "sum_semantic_graph.ttl"
    
    assert sum_mm_path.exists(), f"sum_mm.py not found: {sum_mm_path}"
    assert ttl_path.exists(), f"Input TTL file not found: {ttl_path}"
    
    # 2) Dateien einlesen
    sum_mm_code = sum_mm_path.read_text(encoding="utf-8")
    input_ttl = ttl_path.read_text(encoding="utf-8")
    
    # 3) Lade sum_mm.py Modul in Pyodide (als separater Schritt)
    print("Loading sum_mm.py module...")
    selenium.run_js(f"""
        pyodide.globals.set('sum_mm_code', {sum_mm_code!r});
        return await pyodide.runPythonAsync(`
            exec(sum_mm_code)
        `);
    """)
    
    # 4) Lade input TTL
    print("Loading input graph...")
    selenium.run_js(f"""
        pyodide.globals.set('input_ttl', {input_ttl!r});
    """)
    
    # 5) Führe Funktion aus
    print("Running sum_mm.py...")
    result_ttl = selenium.run("""
        run(input_ttl)
    """)
    
    # 6) Ergebnis mit rdflib in Python prüfen
    print("Validating results...")
    from rdflib import Graph, Namespace
    from rdflib.namespace import RDF

    g = Graph()
    g.parse(data=result_ttl, format="turtle")

    QUDT = Namespace("http://qudt.org/schema/qudt/")
    UNIT = Namespace("http://qudt.org/vocab/unit/")

    # Alle QuantityValues sammeln
    qvs = list(g.subjects(RDF.type, QUDT.QuantityValue))
    print(f"Found {len(qvs)} QuantityValues")
    assert len(qvs) >= 3, f"Expected at least 3 QuantityValues, found {len(qvs)}"

    # Prüfen, ob ein QV mit Wert 5.0 MilliM existiert
    found_sum = False
    for qv in qvs:
        val = g.value(qv, QUDT.numericValue)
        unit = g.value(qv, QUDT.unit)
        if val is None:
            continue
        try:
            f = float(val)
        except Exception:
            continue
        print(f"  QV: value={f}, unit={unit}")
        if f == 5.0 and unit == UNIT.MilliM:
            found_sum = True
            break

    assert found_sum, "No sum QuantityValue with value 5.0 MilliM found in result graph"
    print("✓ Test passed!")