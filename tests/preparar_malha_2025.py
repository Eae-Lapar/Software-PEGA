"""Gera derivados da malha oficial transformada para EPSG:4326 por GDAL/sf."""

import gzip
import json
import sys
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import MultiPolygon, mapping, shape


def poligonos(geometria):
    if geometria.geom_type == "Polygon":
        yield geometria
    elif hasattr(geometria, "geoms"):
        for parte in geometria.geoms:
            yield from poligonos(parte)


def preparar(entrada, destino):
    with entrada.open(encoding="utf-8") as arquivo:
        feicoes = [json.loads(linha.lstrip("\x1e")) for linha in arquivo if linha.strip()]
    assert len(feicoes) == 27
    atributos = [f["properties"] for f in feicoes]
    assert len({a["CD_UF"] for a in atributos}) == 27
    assert {str(a["CD_REGIAO"]) for a in atributos} == set("12345")
    brutas = [shape(f["geometry"]) for f in feicoes]
    detalhadas = np.asarray([MultiPolygon(list(poligonos(shapely.make_valid(g))))
                             if not g.is_valid else g for g in brutas], dtype=object)
    assert shapely.is_valid(detalhadas).all() and shapely.coverage_is_valid(detalhadas)
    metros = Transformer.from_crs(4326, 5880, always_xy=True).transform
    graus = Transformer.from_crs(5880, 4326, always_xy=True).transform
    metricas = shapely.transform(detalhadas, metros, interleaved=False)
    simples = shapely.coverage_simplify(metricas, tolerance=1600)
    simples = shapely.transform(simples, graus, interleaved=False)
    assert shapely.is_valid(simples).all() and shapely.coverage_is_valid(simples)
    assert not shapely.is_empty(simples).any()
    linhas = (json.dumps({"properties": a, "wkb": g.wkb_hex}, ensure_ascii=False)
              for a, g in zip(atributos, detalhadas))
    (destino / "br_uf_2025_detalhada.jsonl.gz").write_bytes(
        gzip.compress(("\n".join(linhas) + "\n").encode(), compresslevel=6, mtime=0))
    estados = [{"type": "Feature", "properties": a, "geometry": mapping(g)}
               for a, g in zip(atributos, simples)]
    regioes = []
    for codigo in sorted({a["CD_REGIAO"] for a in atributos}):
        indices = [i for i, a in enumerate(atributos) if a["CD_REGIAO"] == codigo]
        regioes.append({"type": "Feature", "properties": {
            "CD_REGIAO": codigo, "NM_REGIAO": atributos[indices[0]]["NM_REGIAO"]
        }, "geometry": mapping(shapely.coverage_union_all(simples[indices]))})
    mapa = {"type": "FeatureCollection", "features": estados, "regioes": regioes}
    (destino / "br_uf_2025_simplificada.geojson").write_text(
        json.dumps(mapa, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"27 UFs; cobertura válida; geometrias detalhadas reparadas: {sum(not g.is_valid for g in brutas)}")


if __name__ == "__main__":
    preparar(Path(sys.argv[1]), Path("data/geospatial"))
