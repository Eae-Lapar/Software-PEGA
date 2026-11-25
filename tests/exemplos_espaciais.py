"""Gera mapas públicos de avaliação usando exclusivamente inventário sintético."""

import json
from pathlib import Path
from time import perf_counter

from PIL import Image

from tests.test_pega import PegaTest


def gerar(teste):
    coordenadas = [(-23.55, -46.63), (-22.92, -43.25), (-19.92, -43.94),
                   (-30.03, -51.23), (-15.78, -47.93), (-12.97, -38.50),
                   (-8.05, -34.88), (-3.12, -60.02)]
    linhas = [(f"SINT{i}", "Biomass", 20, lat, lon, 2017, 1000 * (i + 1)**2, "Sintético")
              for i, (lat, lon) in enumerate(coordenadas)]
    inventario = teste.upload(linhas=linhas).json()["inventario_id"]
    calculo = teste.calcular(inventario, "Biomass").json()["calculo_id"]
    metadados = teste.storage / inventario / "calculos" / calculo / "metadados.json"
    dados = json.loads(metadados.read_text(encoding="utf-8"))
    dados["combustivel"] += " (dados sintéticos)"
    metadados.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    rota = f"/api/inventarios/{inventario}/calculos/{calculo}/espacial/original"
    celulas = []
    for i, (x, y) in enumerate([(-49, -25), (-45, -25), (-49, -21), (-45, -21), (-55, -33), (-63, -6)]):
        anel = [[x, y], [x + 4, y], [x + 4, y + 4], [x, y + 4], [x, y]]
        celulas.append({"type": "Feature", "properties": {"id_grid": i + 1},
                        "geometry": {"type": "Polygon", "coordinates": [anel]}})
    grade = {"type": "FeatureCollection", "features": celulas}
    resposta = teste.client.post(rota, files={"grade": ("grade-sintetica.geojson", json.dumps(grade))})
    resposta.raise_for_status()
    serie = next(s for s in resposta.json()["series"] if s["pol"] == "PM2.5")
    pasta = Path("exemplos")
    pasta.mkdir(exist_ok=True)
    for modo, dpi, nome, opcoes in [
        ("pontos", 600, "pm25-fontes-sinteticas.png", "marcador=ambos&paleta=plasma&escala=log"),
        ("grade", 300, "pm25-grade-sintetica.png", "paleta=viridis"),
        ("pontos", 300, "pm25-rio-sintetico.png", "nivel=uf&codigo=33&paleta=inferno&escopo=local"),
        ("pontos", 300, "pm25-saopaulo-sintetico.png", "nivel=uf&codigo=35&paleta=cividis&escopo=local"),
        ("territorial", 300, "pm25-ufs-sintetico.png", "paleta=viridis"),
    ]:
        url = f"{rota}/mapas/{serie['id']}.png?modo={modo}&dpi={dpi}&unidade=t&{opcoes}"
        inicio = perf_counter()
        imagem = teste.client.get(url)
        novo = perf_counter() - inicio
        imagem.raise_for_status()
        arquivo = pasta / nome
        arquivo.write_bytes(imagem.content)
        with Image.open(arquivo) as png:
            assert png.size == (dpi * 8, dpi * 8)
            assert abs(png.info["dpi"][0] - dpi) < 1
        inicio = perf_counter()
        assert imagem.content == teste.client.get(url).content
        print(f"{nome}: {len(imagem.content)} bytes, novo {novo:.3f}s, cache {perf_counter() - inicio:.3f}s")
    print(serie["balanco_g"])


if __name__ == "__main__":
    teste = PegaTest()
    try:
        teste.setUp()
        gerar(teste)
    finally:
        teste.doCleanups()
