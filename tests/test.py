# tests/test.py

import pathlib
import pytest


@pytest.mark.driver_timeout(60)
async def test_sum_mm_node(selenium):
    # 1) Requirements mit micropip installieren
    await selenium.load_package("micropip")
    
    root = pathlib.Path(__file__).resolve().parents[1]
    req_file = root / "requirements.txt"
    
    if req_file.exists():
        reqs = []
        for line in req_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            reqs.append(line)
        
        if reqs:
            await selenium.run_async(f"""
                import micropip
                await micropip.install({reqs!r})
            """)

    # 2) sum_mm.py laden
    sum_mm_path = root / "sum_mm.py"
    sum_mm_code = sum_mm_path.read_text(encoding="utf-8")
    
    # 3) Input-Graph einlesen
    ttl_path = root / "sum_semantic_graph.ttl"
    assert ttl_path.exists(), f"Input TTL file not found: {ttl_path}"
    input_ttl = ttl_path.read_text(encoding="utf-8")

    # 4) In Pyodide ausführen
    result_ttl = await selenium.run_async(f"""
        {sum_mm_code}
        
        input_ttl = {input_ttl!r}
        result = run(input_ttl)
        result
    """)

    # 5) Ergebnis prüfen
    from rdflib import Graph, Namespace
    from rdflib.namespace import RDF

    g = Graph()
    g.parse(data=result_ttl, format="turtle")

    QUDT = Namespace("http://qudt.org/schema/qudt/")
    UNIT = Namespace("http://qudt.org/vocab/unit/")

    qvs = list(g.subjects(RDF.type, QUDT.QuantityValue))
    assert len(qvs) >= 3

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
        if f == 5.0 and unit == UNIT.MilliM:
            found_sum = True
            break

    assert found_sum, "No sum QuantityValue with value 5.0 MilliM found in result graph"