"""Mapas científicos locais, renderizados sob demanda com Matplotlib."""

import hashlib
import json
import math
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

import numpy as np
from matplotlib import colormaps
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.collections import LineCollection, PatchCollection
from matplotlib.colors import LogNorm, Normalize, to_hex
from matplotlib.figure import Figure
from matplotlib.patches import PathPatch
from matplotlib.path import Path as GeoPath
from pyproj import Geod
from shapely import transform
from shapely.geometry import mapping

from backend.services.espacial import CONVERSAO, Grade, coordenadas, ler_serie
from backend.services.territorio import assinatura, consulta, fontes_mapa, malha, validar_selecao


TRAVA = Lock()
GEOD = Geod(ellps="WGS84")


class LimiteMapas(Exception):
    pass


@lru_cache(maxsize=32)
def geometrias_territorio(nivel, codigo):
    atributos, geometrias, _ = malha()
    chave = {"uf": "CD_UF", "regiao": "CD_REGIAO"}.get(nivel)
    return [(str(a["CD_UF"]), g) for a, g in zip(atributos, geometrias)
            if chave is None or str(a[chave]) == codigo]


def partes(geometria):
    return geometria.geoms if geometria.geom_type == "MultiPolygon" else [geometria]


@lru_cache(maxsize=32)
def limites(nivel, codigo):
    return [np.asarray(anel.coords) for _, ge in geometrias_territorio(nivel, codigo)
            for parte in partes(ge) for anel in (parte.exterior, *parte.interiors)]


def pontos(pasta, serie):
    massas = defaultdict(float)
    for linha in ler_serie(pasta, serie, "fontes.csv"):
        coords = coordenadas(linha)
        if coords is not None:
            massas[linha["id"], *coords, linha.get("alt")] += float(linha["emissions"])
    return [{"id": id_, "lon": lon, "lat": lat, "alt": alt, "massa_g": massa}
            for (id_, lon, lat, alt), massa in massas.items()]


def escala_cores(valores, escala):
    disponiveis = [v for v in valores if v > 0] if escala == "log" else valores
    if not disponiveis or not any(disponiveis):
        return Normalize(0, 1), False
    maximo = max(disponiveis)
    minimo = min(disponiveis) if escala == "log" else 0
    if escala == "log" and minimo == maximo:
        minimo, maximo = minimo / 1.1, maximo * 1.1
    return (LogNorm(minimo, maximo) if escala == "log" else Normalize(0, maximo or 1)), True


def cor(cmap, norma, escala, valor):
    return "#868b93" if escala == "log" and valor == 0 else to_hex(cmap(norma(valor)))


def colorir_territorio(dados, unidade, paleta, escala, escopo, nivel, codigo):
    fator = CONVERSAO[unidade]
    faixa = dados["faixa_nacional" if escopo == "nacional" else "faixa_local"]
    norma, definida = escala_cores([v * fator for v in faixa if v is not None], escala)
    cmap = colormaps[paleta]
    for linha in dados["pontos"] + dados["ranking"]:
        linha["valor"] = linha["massa_g"] * fator
        linha["cor"] = cor(cmap, norma, escala, linha["valor"])
    ufs = dados["totais"]["uf"]
    ufs_visiveis = {k for k, _ in geometrias_territorio(nivel, codigo)}
    norma_uf, definida_uf = escala_cores(
        [v * fator for k, v in ufs.items() if escopo == "nacional" or k in ufs_visiveis], escala)
    dados["cores_uf"] = {k: cor(cmap, norma_uf, escala, v * fator) for k, v in dados["totais"]["uf"].items()}
    dados["legenda"] = {
        "min": norma.vmin if definida else None, "max": norma.vmax if definida else None,
        "cores": [to_hex(cmap(i / 8)) for i in range(9)], "unidade": unidade, "escopo": escopo,
        "min_uf": norma_uf.vmin if definida_uf else None, "max_uf": norma_uf.vmax if definida_uf else None,
    }


def grade_interativa(pasta, dados, resultado, unidade, paleta, escala, nivel, escopo, serie):
    grade = Grade(json.loads((pasta / "grade.geojson").read_text(encoding="utf-8")), dados["grade_epsg"])
    massas = resultado["celulas"]
    if len(grade.ids) > 2500:
        return {"features": [], "limitada": True}
    fator = CONVERSAO[unidade]
    referencia = massas.values()
    if escopo == "nacional" and nivel != "brasil":
        referencia = [float(linha["massa_g"]) for linha in ler_serie(pasta, serie, "celulas.csv")]
    norma, definida = escala_cores([massa * fator for massa in referencia], escala)
    cmap = colormaps[paleta]
    feicoes = []
    for id_, poligono in zip(grade.ids, grade.poligonos):
        if nivel != "brasil" and id_ not in massas:
            continue
        ge = transform(poligono, grade.desprojetar, interleaved=False)
        if all(map(math.isfinite, ge.bounds)):
            massa = massas.get(id_)
            feicoes.append({"geometry": mapping(ge), "id": id_, "valor": massa * fator if massa is not None else None,
                            "cor": cor(cmap, norma, escala, massa * fator) if massa is not None else None})
    return {"features": feicoes, "limitada": False, "min": norma.vmin if definida else None,
            "max": norma.vmax if definida else None}


def pontos_interativos(pasta, serie, unidade, paleta, escala):
    dados = pontos(pasta, serie)
    valores = [item["massa_g"] * CONVERSAO[unidade] for item in dados]
    norma, _ = escala_cores(valores, escala)
    for item, valor in zip(dados, valores):
        item["valor"] = valor
        item["cor"] = "#868b93" if escala == "log" and valor == 0 else to_hex(colormaps[paleta](norma(valor)))
    return dados


def barra_geodesica(ax):
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    longitude = xmin + (xmax - xmin) * .06
    latitude = ymin + (ymax - ymin) * .07
    limite = min(25, (xmax - xmin) * .23)
    disponivel = GEOD.inv(longitude, latitude, longitude + limite, latitude)[2]
    distancia = next((km for km in (2000, 1000, 500, 200, 100, 50, 20, 10, 5, 2, 1)
                      if km * 1000 <= disponivel), None)
    if distancia:
        esquerda, direita = 0, limite
        for _ in range(32):
            meio = (esquerda + direita) / 2
            if GEOD.inv(longitude, latitude, longitude + meio, latitude)[2] < distancia * 1000:
                esquerda = meio
            else:
                direita = meio
        ax.plot([longitude, longitude + direita], [latitude, latitude], color="#222", linewidth=2)
        ax.annotate(f"{distancia} km", (longitude + direita / 2, latitude),
                    xytext=(0, 4), textcoords="offset points", ha="center", fontsize=8)


def legenda_serie(serie):
    return serie["pol"] if serie["pol"] == serie["pol_origem"] else f'{serie["pol"]} ({serie["pol_origem"]})'


def desenhar(pasta, dados, serie, opcoes):
    unidade, paleta, escala, idioma, modo, marcador, nivel, codigo, escopo = opcoes
    ingles = idioma == "en"
    idioma_texto = lambda pt, en: en if ingles else pt
    fator = CONVERSAO[unidade]
    fig = Figure(figsize=(8, 8), facecolor="white", layout="constrained")
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    ax.add_collection(LineCollection(limites(nivel, codigo), colors="#657284", linewidths=.5, zorder=2))
    cmap = colormaps[paleta]
    territorial = consulta(pasta, dados, serie["id"], nivel, codigo, incluir_pontos=False)
    pontos_validos = fontes_mapa(pasta, dados, serie["id"], nivel, codigo) if modo == "pontos" else []
    valores = [p["massa_g"] * fator for p in pontos_validos]
    geometrias = geometrias_territorio(nivel, codigo)
    valores_uf = territorial["totais"]["uf"]
    massa_celulas = territorial["celulas"]
    regionais = territorial["totais"]["regiao"]
    uf_regiao = {str(a["CD_UF"]): str(a["CD_REGIAO"]) for a in malha()[0]}
    if modo == "grade":
        valores = [v * fator for v in massa_celulas.values()]
    if modo == "territorial":
        valores = [valores_uf[k] * fator for k, _ in geometrias if k in valores_uf]
    if modo == "regional":
        valores = [regionais.get(k, 0) * fator for k in {uf_regiao[uf] for uf, _ in geometrias}]
    referencia = valores
    if escopo == "nacional" and modo == "pontos":
        referencia = [v * fator for v in territorial["faixa_nacional"] if v is not None]
    elif escopo == "nacional" and modo == "territorial":
        referencia = [v * fator for v in valores_uf.values()]
    elif escopo == "nacional" and modo == "regional":
        referencia = [v * fator for v in regionais.values()]
    elif escopo == "nacional" and modo == "grade" and nivel != "brasil":
        referencia = [float(linha["massa_g"]) * fator for linha in ler_serie(pasta, serie["id"], "celulas.csv")]
    norma, definida = escala_cores(referencia, escala)
    cores = [cor(cmap, norma, escala, valor) for valor in valores]
    if modo in {"grade", "territorial", "regional"}:
        if modo == "grade":
            grade = Grade(json.loads((pasta / "grade.geojson").read_text(encoding="utf-8")), dados["grade_epsg"])
            desenho = [(id_, transform(poligono, grade.desprojetar, interleaved=False))
                       for id_, poligono in zip(grade.ids, grade.poligonos)
                       if nivel == "brasil" or id_ in massa_celulas]
            massas = {chave: cor(cmap, norma, escala, val * fator) for chave, val in massa_celulas.items()}
        else:
            desenho = geometrias
            massas = {chave: cor(cmap, norma, escala, val * fator) for chave, val in valores_uf.items()}
            if modo == "regional":
                massas = {uf: cor(cmap, norma, escala, regionais[regiao] * fator)
                          for uf, regiao in uf_regiao.items() if regiao in regionais}
        preenchimentos = []
        for id_, geometria in desenho:
            if not all(map(math.isfinite, geometria.bounds)):
                continue
            for parte in partes(geometria):
                caminho = GeoPath.make_compound_path(
                    *(GeoPath(np.asarray(anel.coords), closed=True) for anel in [parte.exterior, *parte.interiors])
                )
                preenchimentos.append(PathPatch(caminho, facecolor=massas.get(id_, "none"),
                                                 edgecolor="#667085", linewidth=.38))
        ax.add_collection(PatchCollection(preenchimentos, match_original=True))
    elif pontos_validos:
        maximo = max(referencia, default=0) or 1
        ax.scatter([p["lon"] for p in pontos_validos], [p["lat"] for p in pontos_validos],
                   s=[18 + 105 * v / maximo if marcador != "cor" else 29 for v in valores],
                   c=["#245c8b"] if marcador == "tamanho" else cores,
                   edgecolors="#202939", linewidths=.4, zorder=3)
    if definida and not (modo == "pontos" and marcador == "tamanho"):
        from matplotlib.cm import ScalarMappable

        fig.colorbar(ScalarMappable(norm=norma, cmap=cmap), ax=ax, shrink=.69, pad=.03,
                     label=f"{legenda_serie(serie)} ({unidade})")
    ax.autoscale()
    ax.set_aspect(1 / max(.65, math.cos(math.radians(sum(ax.get_ylim()) / 2))))
    ax.grid(color="#d4dae2", linewidth=.45, linestyle=":")
    ax.set(xlabel=idioma_texto("Longitude (°)", "Longitude (°)"),
           ylabel=idioma_texto("Latitude (°)", "Latitude (°)"))
    ax.annotate("N", xy=(.95, .96), xytext=(.95, .87), xycoords="axes fraction", ha="center",
                arrowprops={"arrowstyle": "-|>", "color": "#202939"})
    barra_geodesica(ax)
    titulo = {"pontos": idioma_texto("Emissões por fonte", "Emissions by source"),
              "grade": idioma_texto("Emissões por célula", "Emissions by cell"),
              "territorial": idioma_texto("Massa total por UF", "Total mass by state"),
              "regional": idioma_texto("Massa total por região", "Total mass by region")}[modo]
    fig.suptitle(f"{titulo} · {legenda_serie(serie)}", fontsize=17, weight="bold")
    massa = {"pontos": sum(p["massa_g"] for p in pontos_validos), "grade": sum(massa_celulas.values()),
             "regional": math.fsum(regionais.values()) if nivel == "brasil" else regionais.get(codigo, 0),
             "territorial": territorial["indicadores"]["total_nacional_g"] if nivel == "brasil"
             else territorial["indicadores"]["total_g"]}[modo]
    fontes = len(pontos_validos) if modo == "pontos" else territorial["indicadores"]["fontes"]
    nome = validar_selecao(nivel, codigo)
    if ingles:
        nome = {"Brasil": "Brazil", "Norte": "North", "Nordeste": "Northeast", "Sudeste": "Southeast",
                "Sul": "South", "Centro-Oeste": "Central-West"}.get(nome, nome)
    ax.set_title(f'{nome} · {dados["setor"]} · {dados["combustivel"]} · {dados["ano"]}\n'
                 f'{idioma_texto("Total exibido", "Displayed total")}: {massa * fator:.5g} {unidade}  |  '
                 f'{fontes} {idioma_texto("fontes exibidas", "displayed sources") if modo == "pontos" else idioma_texto("fontes no inventário", "inventory sources")}\n'
                 f'{idioma_texto("Base cartográfica adaptada", "Adapted basemap")}: IBGE · Malha UF 2025'
                 + (idioma_texto(" · Cinza: zero", " · Grey: zero") if escala == "log" else ""), fontsize=9)
    return fig


def gerar_mapa(pasta, dados, serie, opcoes, formato, dpi, conferir):
    chave = hashlib.sha256(json.dumps([2, serie["id"], *opcoes, formato, dpi]).encode()
                           + assinatura().encode()).hexdigest()
    cache = pasta / "mapas"
    cache.mkdir(exist_ok=True)
    arquivo = cache / f"{chave}.{formato}"
    with TRAVA:
        if not arquivo.is_file():
            existentes = list(cache.glob("*.*"))
            usados = sum(f.stat().st_size for f in existentes)
            if len(existentes) >= 80 or usados >= 192 * 1024**2:
                raise LimiteMapas("Limite de mapas desta configuração atingido.")
            with TemporaryDirectory(dir=cache) as temporario:
                caminho = Path(temporario) / arquivo.name
                figura = desenhar(pasta, dados, serie, opcoes)
                try:
                    figura.savefig(caminho, format=formato, dpi=dpi if formato == "png" else 150)
                finally:
                    figura.clear()
                if usados + caminho.stat().st_size > 192 * 1024**2:
                    raise LimiteMapas("Limite de armazenamento de mapas atingido.")
                conferir()
                caminho.replace(arquivo)
    return arquivo
