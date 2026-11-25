"""Intersecção fonte–célula com grade explícita e balanço de massa."""

import csv
import hashlib
import json
import math
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory

from pyproj import CRS, Transformer, network
from shapely import Point, STRtree
from shapely.errors import ShapelyError
from shapely.geometry import shape
from shapely.ops import transform

from backend.services.temporal import origem_csv
from backend.services.especiacao import ler_especiacao


CONVERSAO = {"g": 1, "kg": 1e-3, "t": 1e-6}
ESTADOS = ("mapeada", "fora_grade", "ambigua", "coordenada_invalida")
network.set_network_enabled(False)


class Grade:
    def __init__(self, dados, epsg):
        try:
            crs = CRS.from_epsg(epsg)
            if not (crs.is_projected or crs.is_geographic):
                raise ValueError("Forneça um CRS horizontal para a grade.")
            self.projetar = Transformer.from_crs(4326, crs, always_xy=True).transform
            self.desprojetar = Transformer.from_crs(crs, 4326, always_xy=True).transform
            feicoes = dados["features"]
            if dados["type"] != "FeatureCollection" or not 0 < len(feicoes) <= 25000:
                raise ValueError("Forneça de 1 a 25.000 células em uma FeatureCollection.")
            ids = [f["properties"]["id_grid"] for f in feicoes]
            if any(type(id_) not in (str, int) for id_ in ids):
                raise ValueError("Os IDs de célula devem ser textos ou inteiros.")
            self.ids = [str(id_).strip() for id_ in ids]
            self.poligonos = [shape(f["geometry"]) for f in feicoes]
        except (KeyError, TypeError, AttributeError, ShapelyError, RuntimeError) as erro:
            raise ValueError("Grade inválida. Informe o CRS e polígonos com id_grid.") from erro
        if ("" in self.ids or len(set(self.ids)) != len(self.ids) or
                any(p.geom_type not in {"Polygon", "MultiPolygon"} or p.is_empty or
                    not p.is_valid or p.has_z or not all(map(math.isfinite, p.bounds))
                    for p in self.poligonos)):
            raise ValueError("Use polígonos 2D válidos com IDs de célula únicos.")
        self.indice = STRtree(self.poligonos)

    def localizar(self, lon, lat):
        x, y = self.projetar(lon, lat)
        if not (math.isfinite(x) and math.isfinite(y)):
            return None, "fora_grade"
        indices = self.indice.query(Point(x, y), predicate="intersects")
        if len(indices) > 1:
            return None, "ambigua"
        if len(indices) == 0:
            return None, "fora_grade"
        return self.ids[int(indices[0])], "mapeada"


def coordenadas(linha):
    try:
        lon, lat = float(linha["lon"]), float(linha["lat"])
        if -180 <= lon <= 180 and -90 <= lat <= 90:
            return lon, lat
    except (KeyError, ValueError, TypeError):
        pass
    return None


def pasta_espacial(pasta, origem):
    return pasta / f"espacial-{origem}"


def carregar_resultado(pasta, origem):
    return json.loads((pasta_espacial(pasta, origem) / "resultado.json").read_text(encoding="utf-8"))


def chave_serie(linha):
    return linha.get("pol_origem", linha["pol"]), linha["pol"]


def publicar_espacial(pasta, origem, calculo, dados_grade, epsg, conferir):
    destino = pasta_espacial(pasta, origem)
    destino.mkdir(exist_ok=True)
    grade = Grade(dados_grade, epsg) if dados_grade is not None else None
    grade_bytes = json.dumps(dados_grade, separators=(",", ":")).encode()
    identificador = hashlib.sha256(str(epsg if grade else 0).encode() + grade_bytes).hexdigest()
    artefatos = destino / identificador
    if not artefatos.is_dir():
        with TemporaryDirectory(dir=destino) as temporario:
            arquivos = Path(temporario) / "resultado"
            arquivos.mkdir()
            dados = processar(origem_csv(pasta, origem), arquivos, grade, origem, calculo)
            dados.update({"grade_epsg": epsg if grade else None, "configuracao_espacial": identificador})
            if origem == "especiada":
                dados["balanco_especiacao"] = ler_especiacao(pasta)["balanco"]
            if grade:
                (arquivos / "grade.geojson").write_bytes(grade_bytes)
            (arquivos / "metadados.json").write_text(json.dumps(dados, allow_nan=False), encoding="utf-8")
            conferir()
            try:
                arquivos.rename(artefatos)
            except OSError:
                if not (artefatos / "metadados.json").is_file():
                    raise
    with TemporaryDirectory(dir=destino) as temporario:
        arquivo = Path(temporario) / "resultado.json"
        arquivo.write_bytes((artefatos / "metadados.json").read_bytes())
        conferir()
        arquivo.replace(destino / "resultado.json")
    return carregar_resultado(pasta, origem)


def processar(entrada, pasta, grade, origem, calculo):
    series = {}
    totais = defaultdict(lambda: defaultdict(float))
    celulas = defaultdict(float)
    fontes = defaultdict(set)

    @lru_cache(maxsize=16000)
    def localizar(coords):
        if coords is None:
            return None, "coordenada_invalida"
        return grade.localizar(*coords) if grade else (None, "mapeada")

    with (entrada.open(encoding="utf-8", newline="") as arquivo,
          (pasta / "fontes.csv").open("w", encoding="utf-8", newline="") as saida):
        leitor = csv.DictReader(arquivo)
        writer = csv.DictWriter(saida, [*leitor.fieldnames, "serie", "celula", "situacao_espacial"])
        writer.writeheader()
        for linha in leitor:
            chave = chave_serie(linha)
            serie = series.setdefault(chave, len(series))
            massa = float(linha["emissions"])
            if linha["unit_emissions"] != "g" or not math.isfinite(massa) or massa < 0:
                raise ValueError("A base espacial exige massas finitas e não negativas em gramas.")
            coords = coordenadas(linha)
            celula, situacao = localizar(coords)
            totais[serie][situacao] += massa
            fontes[serie].add((linha["id"], coords, linha.get("alt")))
            if celula is not None:
                celulas[serie, celula] += massa
            writer.writerow({**linha, "serie": serie, "celula": celula, "situacao_espacial": situacao})
    if grade:
        with (pasta / "celulas.csv").open("w", encoding="utf-8", newline="") as arquivo:
            writer = csv.writer(arquivo)
            writer.writerow(["serie", "id_grid", "massa_g"])
            writer.writerows((serie, celula, massa) for (serie, celula), massa in celulas.items())
    return {
        **{k: calculo[k] for k in ("ano", "setor", "combustivel", "calculo_id", "configuracao_id")},
        "origem": origem, "grade": grade is not None, "unidade": "g",
        "series": [{"id": serie, "pol_origem": chave[0], "pol": chave[1], "fontes": len(fontes[serie]),
                    "massa_g": math.fsum(totais[serie].values()),
                    "balanco_g": {estado: totais[serie][estado] for estado in ESTADOS}}
                   for chave, serie in series.items()],
    }


def ler_serie(pasta, serie, arquivo, limite=None):
    with (pasta / arquivo).open(encoding="utf-8", newline="") as entrada:
        for i, linha in enumerate(linha for linha in csv.DictReader(entrada) if linha["serie"] == str(serie)):
            if limite is not None and i >= limite:
                break
            yield linha
