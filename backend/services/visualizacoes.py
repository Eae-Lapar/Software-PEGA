"""Consultas e figuras dos resultados persistidos de uma execução."""

import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import date
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.collections import LineCollection
from netCDF4 import Dataset
from pyproj import CRS, Transformer

from backend.services.armazenamento import ler_metadados_calculo
from backend.services.especiacao import ler_especiacao
from backend.services.espacial import carregar_resultado
from backend.services.mapas import TRAVA, LimiteMapas, barra_geodesica, escala_cores, limites
from backend.services.modelagem import ARQUIVO_METADADOS, ARQUIVO_NETCDF, resultado_atual
from backend.services.temporal import consultar_temporal, origem_csv
from backend.services.territorio import assinatura, catalogo, classificar, coordenadas, validar_selecao
from backend.services.wrf import NETCDF_LOCK, DominioWRF

EMISSOES = ("totais", "fontes", "participacao", "acumulada", "distribuicao", "uf", "regiao")
RELATIVOS = ("horario", "semanal", "combinado", "calor")
ANUAIS = ("mensal", "diario", "horas", "serie-anual", "calendario", "grade-wrf", "dominio-wrf")
QUIMICOS = ("balanco", "especies", "perfil")
UNIDADES = {"g": 1, "kg": 1e-3, "t": 1e-6}
TITULOS = {
    "totais": ("Totais por poluente", "Totals by pollutant"),
    "fontes": ("Emissões por fonte", "Emissions by source"),
    "participacao": ("Participação das fontes", "Source shares"),
    "acumulada": ("Emissão acumulada das fontes", "Cumulative source emissions"),
    "distribuicao": ("Distribuição entre fontes", "Distribution across sources"),
    "uf": ("Emissões por UF", "Emissions by state"),
    "regiao": ("Emissões por região", "Emissions by region"),
    "balanco": ("Balanço da especiação", "Speciation mass balance"),
    "especies": ("Massa por espécie", "Mass by species"),
    "perfil": ("Frações do perfil químico", "Chemical profile fractions"),
    "horario": ("Perfil horário relativo", "Relative hourly profile"),
    "semanal": ("Perfil semanal relativo", "Relative weekly profile"),
    "combinado": ("Perfil relativo de 168 horas", "Relative 168-hour profile"),
    "calor": ("Mapa de calor do perfil relativo", "Relative profile heatmap"),
    "mensal": ("Massa projetada por mês", "Projected monthly mass"),
    "diario": ("Massa projetada por dia", "Projected daily mass"),
    "horas": ("Massa projetada por hora selecionada", "Projected mass by selected hour"),
    "serie-anual": ("Série cronológica de massas horárias", "Chronological series of hourly masses"),
    "calendario": ("Calendário de massas diárias", "Calendar of daily masses"),
    "grade-wrf": ("Massa projetada por célula WRF", "Projected mass per WRF cell"),
    "dominio-wrf": ("Domínio computacional WRF", "WRF computational domain"),
}


def par(linha):
    return linha.get("pol_origem", linha["pol"]), linha["pol"]


def opcionais(leitor):
    try:
        return leitor()
    except FileNotFoundError:
        return None


def metadados_modelagem(pasta):
    return json.loads((pasta / ARQUIVO_METADADOS).read_text(encoding="utf-8"))


def opcoes(pasta):
    calculo = ler_metadados_calculo(pasta)
    valores = {"original": [par(linha) for linha in calculo["resumo"]]}
    quimica = opcionais(lambda: ler_especiacao(pasta))
    if quimica:
        valores["especiada"] = [par(linha) for linha in quimica["resumo"]]
    modelos = {}
    temporais, espaciais = [], []
    for origem in valores:
        if opcionais(lambda: carregar_resultado(pasta, origem)):
            espaciais.append(origem)
        if opcionais(lambda: consultar_temporal(pasta, origem)):
            temporais.append(origem)
        modelo = opcionais(lambda: metadados_modelagem(resultado_atual(pasta, origem)))
        if modelo:
            modelos[origem] = {"series": [par(linha) for linha in modelo["series"]],
                               "calendario": modelo["calendario"]}
    return {"ano": calculo["ano"], "series": valores, "territorios": catalogo(),
            "quimica": [linha["pol_origem"] for linha in (quimica or {}).get("balanco", [])
                        if linha["disponivel"]], "temporais": temporais, "espaciais": espaciais, "modelos": modelos}


def dados_emissoes(pasta, op):
    tipo, origem, selecao = op["tipo"], op["origem"], (op["pol_origem"], op["pol"])
    nivel, codigo = op["nivel"], op["codigo"]
    grupos = defaultdict(float)
    rotulos = {}
    classificar_local = lru_cache(maxsize=32000)(classificar)
    with origem_csv(pasta, origem).open(encoding="utf-8", newline="") as entrada:
        for linha in csv.DictReader(entrada):
            chave = par(linha)
            if tipo != "totais" and chave != selecao:
                continue
            if nivel != "brasil" or tipo in ("uf", "regiao"):
                uf, regiao, situacao = classificar_local(*coordenadas(linha["lon"], linha["lat"]))
                if (nivel == "uf" and uf != codigo) or (nivel == "regiao" and regiao != codigo):
                    continue
            if tipo in ("uf", "regiao"):
                local = uf if tipo == "uf" else regiao
                chave = local or situacao
                rotulos[chave] = catalogo()[tipo].get(chave, chave)
            elif tipo != "totais":
                chave = (linha["id"], *coordenadas(linha["lon"], linha["lat"]))
                rotulos[chave] = f"{chave[0]} ({chave[2]}, {chave[1]})" if chave[1] is not None else chave[0]
            else:
                rotulos[chave] = chave[1] if chave[0] == chave[1] else " ← ".join(reversed(chave))
            grupos[chave] += float(linha["emissions"])
    if not grupos:
        raise ValueError("Nenhuma emissão disponível para esta seleção.")
    ordenados = sorted(grupos, key=grupos.get, reverse=tipo == "acumulada" or op["ordem"] == "maior")
    valores = [grupos[chave] for chave in ordenados]
    total = math.fsum(valores)
    if tipo == "acumulada" and op["unidade"] != "%":
        return np.arange(1, len(valores) + 1), np.cumsum(valores) * UNIDADES[op["unidade"]], op["unidade"], total
    if tipo in ("participacao", "acumulada"):
        if total <= 0 or min(valores) < 0:
            raise ValueError("O percentual exige massa total positiva e massas não negativas.")
        valores = [100 * massa / total for massa in valores]
        if tipo == "acumulada":
            return list(range(1, len(valores) + 1)), np.cumsum(valores), "%", total
    if tipo == "distribuicao":
        return [], np.asarray(valores) * UNIDADES[op["unidade"]], op["unidade"], total
    if tipo in ("fontes", "participacao"):
        ordenados, valores = ordenados[:op["top"]], valores[:op["top"]]
    fator = 1 if tipo == "participacao" else UNIDADES[op["unidade"]]
    return [rotulos[chave] for chave in ordenados], np.asarray(valores) * fator, (
        "%" if tipo == "participacao" else op["unidade"]), None if tipo == "totais" else total


def dados_especiacao(pasta, op):
    dados = ler_especiacao(pasta)
    origem = op["pol_origem"]
    balanco = next((linha for linha in dados["balanco"]
                    if linha["pol_origem"] == origem and linha["disponivel"]), None)
    if balanco is None:
        raise ValueError("Perfil químico indisponível.")
    tipo, unidade = op["tipo"], op["unidade"]
    ingles = op["idioma"] == "en"
    if tipo == "balanco":
        rotulos = ["Original", "Allocated", "Residual"] if ingles else ["Original", "Alocada", "Residual"]
        massas = [balanco[campo] for campo in ("original_g", "derivado_g", "residuo_g")]
    elif tipo == "perfil":
        perfil = [linha for linha in dados["perfil"] if linha["pol_origem"] == origem]
        return [linha["especie"] for linha in perfil], [100 * linha["fracao"] for linha in perfil], "%"
    else:
        especies = [linha for linha in dados["resumo"] if linha["pol_origem"] == origem]
        rotulos, massas = [linha["pol"] for linha in especies], [linha["emissions"] for linha in especies]
        if unidade == "%":
            if balanco["original_g"] <= 0:
                raise ValueError("A participação exige massa original positiva.")
            return rotulos, np.asarray(massas) * (100 / balanco["original_g"]), "% original"
    return rotulos, np.asarray(massas) * UNIDADES[unidade], unidade


def dados_relativos(pasta, op):
    dados = consultar_temporal(pasta, op["origem"])
    tipo = op["tipo"]
    chave = "combinado" if tipo == "calor" else tipo
    linhas = dados[chave]
    valores = np.array([linha["peso"] for linha in linhas])
    rotulos = [linha.get("dia", i) for i, linha in enumerate(linhas)] if tipo == "semanal" else range(len(linhas))
    if tipo == "semanal" and op["idioma"] == "en":
        rotulos = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    if op["unidade"] == "%":
        return rotulos, valores * 100, "%", None
    massa = next((linha["massa_base_g"] for linha in dados["resumo"]
                  if par(linha) == (op["pol_origem"], op["pol"])), None)
    if massa is None:
        raise ValueError("Série temporal indisponível.")
    return rotulos, valores * massa * UNIDADES[op["unidade"]], op["unidade"], massa


def intervalo(ano, horas, inicio, fim):
    base = date(ano, 1, 1)
    primeiro = (date.fromisoformat(inicio) - base).days * 24 if inicio else 0
    ultimo = ((date.fromisoformat(fim) - base).days + 1) * 24 if fim else horas
    if not 0 <= primeiro < ultimo <= horas:
        raise ValueError("Selecione um intervalo válido dentro do ano do inventário.")
    return slice(primeiro, ultimo)


def projecao(pasta_modelo, op):
    modelo = metadados_modelagem(pasta_modelo)
    tipo = op["tipo"]
    calendario = modelo["calendario"]
    serie = next((i for i, linha in enumerate(modelo["series"])
                  if par(linha) == (op["pol_origem"], op["pol"])), None)
    if tipo != "dominio-wrf" and serie is None:
        raise ValueError("Série indisponível no domínio selecionado.")
    if tipo not in ("dominio-wrf", "grade-wrf") and not calendario:
        raise ValueError("A visualização exige uma projeção anual concluída.")
    if not calendario and any(op[campo] for campo in ("inicio", "fim", "comparar_inicio", "comparar_fim")):
        raise ValueError("A seleção de período exige uma projeção anual concluída.")
    periodos = []
    if calendario:
        ano, horas = modelo["ano"], calendario["horas"]
        periodos.append(intervalo(ano, horas, op["inicio"], op["fim"]))
        if op["comparar_inicio"] or op["comparar_fim"]:
            periodos.append(intervalo(ano, horas, op["comparar_inicio"], op["comparar_fim"]))
    with NETCDF_LOCK, Dataset(pasta_modelo / ARQUIVO_NETCDF) as nc:
        pesos = np.asarray(nc["hour_fraction"][:]) if calendario else None
        if tipo in ("dominio-wrf", "grade-wrf"):
            xb, yb = (np.asarray(nc[nome][:]) for nome in ("west_east_bounds", "south_north_bounds"))
            crs = CRS.from_cf({attr: nc["crs"].getncattr(attr) for attr in nc["crs"].ncattrs()})
            inversa = Transformer.from_crs(crs, crs.geodetic_crs, always_xy=True)
            lon, lat = inversa.transform(*np.meshgrid(np.r_[xb[:, 0], xb[-1, 1]], np.r_[yb[:, 0], yb[-1, 1]]))
            if tipo == "dominio-wrf":
                nx, ny = modelo["nx"], modelo["ny"]
                grade = (crs, xb, yb, nx, ny)
            else:
                grade = np.asarray(nc["inventory_mass"][serie])
                if calendario:
                    grade *= math.fsum(pesos[periodos[0]])
            return modelo, (lon, lat, grade)
    massa = modelo["series"][serie]["massa_grade_g"]
    return modelo, [(periodo, pesos[periodo] * massa) for periodo in periodos]


def pontos_dominio(pasta, op, modelo, parametros):
    crs, xb, yb, nx, ny = parametros
    dominio = DominioWRF.__new__(DominioWRF)
    dominio.projetar = Transformer.from_crs(crs.geodetic_crs, crs, always_xy=True).transform
    dominio.x, dominio.y = xb.mean(axis=1), yb.mean(axis=1)
    dominio.nx, dominio.ny = nx, ny
    dominio.dx, dominio.dy = modelo["dx_m"], modelo["dy_m"]
    dominio.borda_m = modelo["tolerancia_borda_m"]
    pontos = defaultdict(set)
    with origem_csv(pasta, op["origem"]).open(encoding="utf-8", newline="") as entrada:
        for linha in csv.DictReader(entrada):
            coords = coordenadas(linha["lon"], linha["lat"])
            if coords[0] is not None:
                pontos[coords].add(linha["id"])
    grupos = defaultdict(list)
    for coords, fontes in pontos.items():
        _, situacao = dominio.localizar(*coords)
        grupos[situacao].append((*coords, len(fontes)))
    return grupos


def serie_anual(tipo, ano, periodo, massas):
    horas = np.arange(periodo.start, periodo.stop)
    if tipo == "serie-anual":
        return horas, massas
    if tipo == "horas":
        return np.arange(24), np.bincount(horas % 24, weights=massas, minlength=24)
    dias = horas // 24
    if tipo == "mensal":
        por_dia = np.array([(date.fromordinal(date(ano, 1, 1).toordinal() + int(dia))).month - 1
                            for dia in np.unique(dias)])
        valores = np.bincount(dias - dias[0], weights=massas)
        return np.arange(1, 13), np.bincount(por_dia, weights=valores, minlength=12)
    return np.unique(dias) + 1, np.bincount(dias - dias[0], weights=massas)


def desenhar(pasta, modelo_pasta, op):
    tipo, unidade = op["tipo"], op["unidade"]
    if tipo not in TITULOS:
        raise ValueError("Visualização indisponível.")
    if unidade == "%" and tipo not in (*RELATIVOS, "especies", "acumulada"):
        raise ValueError("Unidade indisponível para esta visualização.")
    calculo = ler_metadados_calculo(pasta)
    territorio = validar_selecao(op["nivel"], op["codigo"])
    ingles = op["idioma"] == "en"
    fig = Figure(figsize=(10, 6), facecolor="white", layout="constrained")
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    contexto = []
    titulo = TITULOS[tipo][ingles]
    if ingles:
        territorio = {"Brasil": "Brazil", "Norte": "North", "Nordeste": "Northeast", "Sul": "South",
                      "Sudeste": "Southeast", "Centro-Oeste": "Central-West"}.get(territorio, territorio)
    if tipo == "grade-wrf" and not metadados_modelagem(modelo_pasta)["calendario"]:
        titulo = "Inventory mass per WRF cell" if ingles else "Massa do inventário por célula WRF"
    if tipo in EMISSOES:
        x, y, unidade, total = dados_emissoes(pasta, op)
        if total is not None and tipo in ("participacao", "acumulada"):
            unidade_total = op["unidade"] if op["unidade"] != "%" else "g"
            contexto.append(f"{total * UNIDADES[unidade_total]:.6g} {unidade_total}")
        if len(x) > 20 and tipo not in ("acumulada", "distribuicao"):
            fig.set_size_inches(10, 2 + len(x) * .2)
        if tipo == "distribuicao":
            ax.hist(y, bins="auto", color=op["cor"])
            ax.set(xlabel=unidade, ylabel="Sources" if ingles else "Fontes")
        elif tipo == "acumulada":
            ax.plot(x, y, color=op["cor"])
            ax.set(xlabel="Sources by descending mass" if ingles else "Fontes em ordem decrescente",
                   ylabel=unidade)
        else:
            barras(ax, x, y, unidade, op)
        if tipo != "totais":
            contexto.append(op["pol"] if op["pol"] == op["pol_origem"] else
                            f'{op["pol"]} ← {op["pol_origem"]}' )
    elif tipo in QUIMICOS:
        x, y, unidade = dados_especiacao(pasta, op)
        if len(x) > 20:
            fig.set_size_inches(10, 2 + len(x) * .19)
        barras(ax, x, y, unidade, op)
        if op["unidade"] == "%":
            ax.set_xlabel("% of original mass" if ingles else "% da massa original")
        contexto.extend((op["pol_origem"], "PEGA R · perfil original / original profile"))
    elif tipo in RELATIVOS:
        x, y, unidade, _ = dados_relativos(pasta, op)
        contexto.append("Without calendar" if ingles else "Sem calendário")
        if unidade != "%":
            contexto.append(op["pol"] if op["pol"] == op["pol_origem"] else
                            f'{op["pol"]} ← {op["pol_origem"]}')
            contexto.append("Relative allocation of annual base" if ingles else "Alocação relativa da base anual")
        if tipo == "calor":
            imagem = ax.imshow(y.reshape(7, 24), aspect="auto", cmap=op["paleta"])
            ax.set_yticks(range(7), ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] if ingles
                          else ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"])
            ax.set_xlabel("Hour of day" if ingles else "Hora do dia")
            fig.colorbar(imagem, ax=ax, label=unidade)
        elif tipo == "semanal":
            ax.bar(x, y, color=op["cor"])
            ax.set_ylabel(unidade)
        else:
            ax.plot(x, y, color=op["cor"], marker="o" if tipo == "horario" else None, markersize=3)
            ax.set(xlabel="Profile hour" if ingles else "Hora do perfil", ylabel=unidade)
    else:
        modelo, dados = projecao(modelo_pasta, op)
        if modelo["calendario"]:
            contexto.append(modelo["calendario"]["convencao"])
        if tipo != "dominio-wrf":
            contexto.append(op["pol"] if op["pol"] == op["pol_origem"] else
                            f'{op["pol"]} ← {op["pol_origem"]}')
        fator = UNIDADES[unidade]
        if tipo in ("grade-wrf", "dominio-wrf"):
            lon, lat, grade = dados
            borda = lambda v: np.r_[v[0, :], v[1:, -1], v[-1, -2::-1], v[-2::-1, 0]]
            if tipo == "dominio-wrf":
                rotulos = {"mapeada": ("Na grade", "Mapped"), "fora_grade": ("Fora da grade", "Outside"),
                           "borda_grade": ("Em borda", "On boundary")}
                cores = {"mapeada": "#1b7669", "fora_grade": "#b83d3d", "borda_grade": "#a56b16"}
                for situacao, pontos in pontos_dominio(pasta, op, modelo, grade).items():
                    xx, yy, fontes = zip(*pontos)
                    ax.scatter(xx, yy, s=12, color=cores[situacao],
                               label=f"{rotulos[situacao][ingles]} ({sum(fontes)})", rasterized=True)
                if ax.collections:
                    ax.legend(loc="best", fontsize=8)
            else:
                valores = grade * fator
                norma, _ = escala_cores(valores.ravel().tolist(), op["escala"])
                mesh = ax.pcolormesh(lon, lat, valores, shading="flat", cmap=op["paleta"], norm=norma, rasterized=True)
                fig.colorbar(mesh, ax=ax, label=unidade)
                contexto.append(f"{math.fsum(valores.ravel()):.6g} {unidade}")
                if op["inicio"] or op["fim"]:
                    contexto.append(f'{op["inicio"] or "01/01"} → {op["fim"] or "31/12"}')
            ax.plot(np.r_[borda(lon), lon[0, 0]], np.r_[borda(lat), lat[0, 0]], color="#17283d")
            ax.annotate("N", xy=(.95, .96), xytext=(.95, .87), xycoords="axes fraction", ha="center",
                        arrowprops={"arrowstyle": "-|>", "color": "#202939"})
            ax.set_aspect(1 / max(.65, math.cos(math.radians(sum(ax.get_ylim()) / 2))))
            ax.set(xlabel="Longitude (°)", ylabel="Latitude (°)")
            xmin, xmax = ax.get_xlim()
            ymin, ymax = ax.get_ylim()
            if xmin < -34 and xmax > -74 and ymin < 6 and ymax > -34:
                ax.add_collection(LineCollection(limites("brasil", ""), colors="#7b8790",
                                                 linewidths=.35, alpha=.7, zorder=2), autolim=False)
                contexto.append("IBGE · Malha UF 2025")
            barra_geodesica(ax)
        else:
            for periodo, massas in dados:
                x, y = serie_anual(tipo, modelo["ano"], periodo, massas * fator)
                base = date(modelo["ano"], 1, 1).toordinal()
                inicio = date.fromordinal(base + periodo.start // 24)
                fim = date.fromordinal(base + (periodo.stop - 1) // 24)
                legenda = f"{inicio.isoformat()} → {fim.isoformat()} · {math.fsum(massas) * fator:.6g} {unidade}"
                if tipo == "calendario":
                    matriz = np.full((7, 54), np.nan)
                    dias = x - 1 + date(modelo["ano"], 1, 1).weekday()
                    matriz[dias % 7, dias // 7] = y
                    fig.colorbar(ax.imshow(matriz, aspect="auto", cmap=op["paleta"]), ax=ax, label=unidade)
                    ax.set_yticks(range(7), ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] if ingles
                                  else ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"])
                    ax.set_xlabel("Calendar week" if ingles else "Semana do calendário")
                    contexto.append(legenda)
                    break
                ax.plot(x, y, marker="o" if tipo in ("horas", "mensal") else None, markersize=3, label=legenda)
            if tipo != "calendario":
                eixo = {"mensal": ("Month", "Mês"), "diario": ("Day of year", "Dia do ano"),
                        "horas": ("Hour of day", "Hora do dia"),
                        "serie-anual": ("Hour of year", "Hora do ano")}
                ax.set(xlabel=eixo[tipo][not ingles], ylabel=unidade)
                ax.legend(loc="best", fontsize=8)
    ax.grid(alpha=.2)
    if op["escala"] == "log" and tipo not in ("grade-wrf", "dominio-wrf", "calor", "calendario", "balanco", "perfil"):
        if tipo == "distribuicao":
            ax.set_yscale("log")
        elif tipo in (*EMISSOES, *QUIMICOS) and tipo != "acumulada":
            ax.set_xscale("log")
        else:
            ax.set_yscale("log")
    ax.set_title(" · ".join([str(calculo["ano"]), calculo["setor"], calculo["combustivel"], territorio, *contexto]),
                 fontsize=9, wrap=True)
    fig.suptitle(titulo, fontsize=16, weight="bold")
    return fig


def barras(ax, rotulos, valores, unidade, op):
    ax.barh(rotulos, valores, color=op["cor"])
    ax.invert_yaxis()
    ax.set_xlabel(unidade)


def gerar(pasta, op, formato, dpi, conferir):
    modelo = resultado_atual(pasta, op["origem"]) if op["tipo"] in ANUAIS else None
    chave = hashlib.sha256(json.dumps([3, assinatura(), modelo.name if modelo else None, op, formato, dpi],
                                     sort_keys=True).encode()).hexdigest()
    cache = pasta / "figuras"
    arquivo = cache / f"{chave}.{formato}"
    with TRAVA:
        conferir()
        if arquivo.is_file():
            return arquivo
        cache.mkdir(exist_ok=True)
        existentes = list(cache.glob("*.*"))
        usados = sum(f.stat().st_size for f in existentes)
        limite = 192 * 1024 ** 2
        if len(existentes) >= 80 or usados >= limite:
            raise LimiteMapas("Limite de figuras desta execução atingido.")
        with TemporaryDirectory(dir=cache) as temporario:
            temporaria = Path(temporario) / arquivo.name
            figura = desenhar(pasta, modelo, op)
            try:
                figura.savefig(temporaria, format=formato, dpi=dpi, facecolor="white")
            finally:
                figura.clear()
            if usados + temporaria.stat().st_size > limite:
                raise LimiteMapas("Limite de armazenamento de figuras atingido.")
            conferir()
            temporaria.replace(arquivo)
    return arquivo
