# tests/test.py

import pathlib
import pytest


@pytest.mark.asyncio
async def test_sum_mm_node(pyodide):
    # 1) Requirements mit micropip installieren (aus requirements.txt im Repo-Root)
    import micropip

    root = pathlib.Path(__file__).resolve().parents[1]
    req_file = root / "requirements.txt"
    if req_file.exists():
        reqs = []
        for line in req_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # einfache Variante: ganze Zeile als Paket-Spec
            reqs.append(line)
        if reqs:
            await micropip.install(reqs)

    # 2) Deine Funktion aus sum_mm.py importieren
    #    (sum_mm.py liegt im Repo-Root)
    import sys
    if str(root) not in sys.path:
        sys.path.append(str(root))

    from sum_mm import run

    # 3) Input-Graph aus sum_semantic_graph.ttl einlesen
    ttl_path = root / "sum_semantic_graph.ttl"
    assert ttl_path.exists(), f"Input TTL file not found: {ttl_path}"
    input_ttl = ttl_path.read_text(encoding="utf-8")

    # 4) run(...) ausführen
    result_ttl = run(input_ttl)

    # 5) Ergebnis mit rdflib prüfen
    from rdflib import Graph, Namespace
    from rdflib.namespace import RDF

    g = Graph()
    g.parse(data=result_ttl, format="turtle")

    QUDT = Namespace("http://qudt.org/schema/qudt/")
    UNIT = Namespace("http://qudt.org/vocab/unit/")

    # Alle QuantityValues sammeln
    qvs = list(g.subjects(RDF.type, QUDT.QuantityValue))
    # Es sollten mindestens 3 sein: 2 Inputs + 1 Summe (oder mehr, falls du später erweiterst)
    assert len(qvs) >= 3

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
        if f == 5.0 and unit == UNIT.MilliM:
            found_sum = True
            break

    assert found_sum, "No sum QuantityValue with value 5.0 MilliM found in result graph"