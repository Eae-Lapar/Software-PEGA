"""Auditoria local, somente leitura, de domínio e de candidatos a wrfchemi."""

import argparse
import math
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import numpy as np
from netCDF4 import Dataset
from pyproj import Geod, Proj, Transformer

from backend.services.especiacao import PERFIL
from backend.services.wrf import DIMENSOES, NETCDF_LOCK, RAIO_WRF, DominioWRF, coordenada


ATRIBUTOS = (
    "TITLE", "GRID_ID", "PARENT_ID", "PARENT_GRID_RATIO", "I_PARENT_START", "J_PARENT_START",
    "DX", "DY", "MAP_PROJ", "TRUELAT1", "TRUELAT2", "STAND_LON", "MOAD_CEN_LAT", "CEN_LAT",
    "CEN_LON", "WEST-EAST_GRID_DIMENSION", "SOUTH-NORTH_GRID_DIMENSION",
    "CHEM_OPT", "EMISS_OPT", "EMISS_INPT_OPT", "IO_STYLE_EMISSIONS", "KEMIT",
)
GRADE_IGUAL = ATRIBUTOS[1:17]
DIMS_EMISSAO = ("Time", "emissions_zdim_stag", *DIMENSOES)
# Lista literal do ramo de área × tempo em APP_PEGA/R/processamento.R.
PARTICULADOS_R = frozenset("PAL PCA PCL PFE PH2O PK PMG PNA PMN PMOTHR PNH4 PNO3 PTI PM10_FRACT PSO4".split())
GEOD = Geod(a=RAIO_WRF, b=RAIO_WRF)


def metadados(nc, chaves=ATRIBUTOS):
    attrs = {}
    for k in chaves:
        if k in nc.ncattrs():
            v = nc.getncattr(k)
            if isinstance(v, np.generic):
                v = v.item()
            if isinstance(v, float) and not math.isfinite(v):
                attrs[k] = None
            elif isinstance(v, (str, int, float)):
                attrs[k] = v
    return attrs


def estatisticas(valores):
    return {"min": float(np.min(valores)), "media": float(np.mean(valores)),
            "max": float(np.max(valores))}


def inversa(dominio):
    return Transformer.from_crs(dominio.crs, dominio.crs.geodetic_crs, always_xy=True).transform


def casos_borda(grade):
    # Amostra dos extremos, do interior e das bordas compartilhadas em ambos os eixos.
    dx, dy = grade.dx, grade.dy
    perto = max(grade.borda_m * 4, 1e-3)
    i, j = grade.ny // 2 - 1, grade.nx // 2 - 1
    xj, yi = grade.x[j], grade.y[i]
    ox, oy = grade.x[0] - dx / 2, grade.y[0] - dy / 2
    ax, ay = grade.x[-1] + dx / 2, grade.y[-1] + dy / 2
    return [
        ("vertice_so", ox, oy, None, "borda_grade"), ("vertice_se", ax, oy, None, "borda_grade"),
        ("vertice_no", ox, ay, None, "borda_grade"), ("vertice_ne", ax, ay, None, "borda_grade"),
        ("limite_x", xj + dx / 2, yi, None, "borda_grade"),
        ("limite_y", xj, yi + dy / 2, None, "borda_grade"),
        ("esquerda_do_limite", xj + dx / 2 - perto, yi, (i, j), "mapeada"),
        ("direita_do_limite", xj + dx / 2 + perto, yi, (i, j + 1), "mapeada"),
        ("interior_sul_oeste", ox + perto, oy + perto, (0, 0), "mapeada"),
        ("interior_norte_leste", ax - perto, ay - perto, (grade.ny - 1, grade.nx - 1), "mapeada"),
        ("exterior_oeste", ox - perto, yi, None, "fora_grade"),
        ("exterior_norte", xj, ay + perto, None, "fora_grade"),
    ]


def auditar_geometria(grade):
    voltar = inversa(grade)
    px, py = grade.projetar(grade.lon, grade.lat)
    x, y = np.meshgrid(grade.x, grade.y)
    erros = np.hypot(px - x, py - y)
    lon, lat = voltar(px, py)
    retorno = np.abs(GEOD.inv(grade.lon, grade.lat, lon, lat)[2])
    idx_col = np.floor((px - grade.x[0]) / grade.dx + .5).astype(int)
    idx_lin = np.floor((py - grade.y[0]) / grade.dy + .5).astype(int)
    centros_corretos = int(np.count_nonzero(
        (idx_col == np.arange(grade.nx)) & (idx_lin == np.arange(grade.ny)[:, None])))
    testes = []
    for nome, xp, yp, celula, status in casos_borda(grade):
        observado = grade.localizar(*voltar(xp, yp))
        testes.append({"caso": nome, "status": observado[1], "celula": observado[0],
                       "confere": observado == (celula, status)})
    return {
        "centros": int(erros.size), "centros_nos_indices_esperados": centros_corretos,
        "erro_euclidiano_m": {**estatisticas(erros), "rmse": float(np.sqrt(np.mean(erros**2))),
                             "p95": float(np.percentile(erros, 95))},
        "erro_ida_volta_m": estatisticas(retorno), "tolerancia_borda_m": grade.borda_m,
        "casos_de_borda": testes,
    }


def areas_jacobiano(grade):
    """Integra dA = dx dy / areal_scale em cada célula, na esfera WRF."""
    voltar = inversa(grade)
    proj = Proj(grade.crs)
    t, w = np.polynomial.legendre.leggauss(3)
    area = np.zeros((grade.ny, grade.nx))
    for a, wa in zip(t, w):
        for b, wb in zip(t, w):
            x, y = np.meshgrid(grade.x + a * grade.dx / 2, grade.y + b * grade.dy / 2)
            lon, lat = voltar(x, y)
            escala = np.asarray(proj.get_factors(lon, lat).areal_scale)
            if not np.isfinite(escala).all() or np.any(escala <= 0):
                raise ValueError("Fator areal inválido na grade Lambert.")
            area += wa * wb / escala
    return area * grade.dx * grade.dy / 4


def area_geodesica(grade, i, j, segmentos):
    x = grade.x[j] + grade.dx * np.array([-.5, .5, .5, -.5, -.5])
    y = grade.y[i] + grade.dy * np.array([-.5, -.5, .5, .5, -.5])
    a = np.linspace(0, 1, segmentos, endpoint=False)
    xp = np.concatenate([x[k] + a * (x[k + 1] - x[k]) for k in range(4)])
    yp = np.concatenate([y[k] + a * (y[k + 1] - y[k]) for k in range(4)])
    lon, lat = inversa(grade)(xp, yp)
    return abs(GEOD.polygon_area_perimeter(lon, lat)[0])


def auditar_areas(grade, nc):
    area = areas_jacobiano(grade)
    nominal = grade.dx * grade.dy
    amostra_i = np.unique(np.linspace(0, grade.ny - 1, min(grade.ny, 11), dtype=int))
    amostra_j = np.unique(np.linspace(0, grade.nx - 1, min(grade.nx, 11), dtype=int))
    diferencas = []
    convergencia = []
    for i in amostra_i:
        for j in amostra_j:
            a8 = area_geodesica(grade, i, j, 8)
            a32 = area_geodesica(grade, i, j, 32)
            diferencas.append(100 * (a32 - area[i, j]) / area[i, j])
            convergencia.append(100 * abs(a32 - a8) / a32)
    fatores = {}
    nomes = set(nc.variables) & {"MAPFAC_M", "MAPFAC_MX", "MAPFAC_MY"}
    produto = None
    if {"MAPFAC_MX", "MAPFAC_MY"} <= nomes:
        mx, my = coordenada(nc, "MAPFAC_MX"), coordenada(nc, "MAPFAC_MY")
        if np.any(mx <= 0) or np.any(my <= 0):
            raise ValueError("MAPFAC_MX e MAPFAC_MY devem ser positivos.")
        produto = mx * my
    elif "MAPFAC_M" in nomes:
        m = coordenada(nc, "MAPFAC_M")
        if np.any(m <= 0):
            raise ValueError("MAPFAC_M deve ser positivo.")
        produto = m**2
    if produto is not None:
        if not np.isfinite(produto).all() or np.any(produto <= 0):
            raise ValueError("Produto dos fatores cartográficos inválido.")
        estimada = nominal / produto
        fatores = {"area_m2": estatisticas(estimada),
                   "diferenca_percentual_vs_integral": estatisticas(100 * (estimada - area) / area)}
    return {"area_fisica_m2": estatisticas(area), "nominal_m2": nominal,
            "diferenca_percentual_vs_nominal": estatisticas(100 * (area - nominal) / nominal),
            "amostra_geodesica_celulas": len(diferencas),
            "diferenca_geodesica_vs_integral_pct": estatisticas(diferencas),
            "convergencia_geodesica_8_32_pct": estatisticas(convergencia),
            "campos_mapfac_presentes": sorted(nomes), "aproximacao_por_mapfac": fatores or None}


def comparar_raster_legado(grade):
    """Reproduz índices do envelope gravado pelo eixport, sem a geometria S2 do R."""
    lon, lat = grade.lon, grade.lat
    ix = (lon - lon.min()) / ((lon.max() - lon.min()) / grade.nx)
    iy = (lat.max() - lat) / ((lat.max() - lat.min()) / grade.ny)
    col = np.minimum(np.floor(ix).astype(int), grade.nx - 1)
    fila_norte = np.minimum(np.floor(iy).astype(int), grade.ny - 1)
    esperado_x, esperado_y = np.meshgrid(np.arange(grade.nx), np.arange(grade.ny))
    xleg = lon.min() + (col + .5) * (lon.max() - lon.min()) / grade.nx
    yleg = lat.max() - (fila_norte + .5) * (lat.max() - lat.min()) / grade.ny
    dist = GEOD.inv(lon, lat, xleg, yleg)[2]
    return {
        "indices_iguais_ordem_legada": int(np.count_nonzero((col == esperado_x) & (fila_norte == esperado_y))),
        "indices_iguais_com_eixo_y_invertido": int(np.count_nonzero(
            (col == esperado_x) & (grade.ny - 1 - fila_norte == esperado_y))),
        "distancia_do_centro_legado_atribuido_m": {**estatisticas(dist), "rmse": float(np.sqrt(np.mean(dist**2)))},
        "metodo": "envelope regular em graus; comparação do join S2 realizada separadamente no R",
    }


def ler_times(nc):
    v = nc.variables.get("Times")
    if v is None or v.dimensions != ("Time", "DateStrLen") or v.shape[1] != 19 or not 0 < v.shape[0] <= 9000:
        return {"valido": False, "motivo": "Times ausente, formato inesperado ou acima de 9.000 registros."}
    v.set_auto_chartostring(False)
    try:
        valores = v[:]
        if np.ma.is_masked(valores):
            raise ValueError("mascarado")
        instantes = [datetime.strptime(b"".join(linha).decode("ascii"), "%Y-%m-%d_%H:%M:%S")
                    for linha in valores]
    except (ValueError, TypeError, UnicodeError):
        return {"valido": False, "motivo": "Times contém valores fora do formato WRF esperado."}
    passos = {(b - a).total_seconds() for a, b in zip(instantes, instantes[1:])}
    return {"valido": all(passo > 0 for passo in passos), "n": len(instantes),
            "inicio": instantes[0].isoformat(), "fim": instantes[-1].isoformat(),
            "intervalos_s": sorted(passos), "fuso_codificado": False}


def correspondencia(variaveis):
    linhas = []
    for origem, especies in PERFIL.items():
        for pol, _, mw in especies:
            alvo = variaveis.get(f"E_{pol}")
            unidade_r = "ug m^-2 s^-1" if pol in PARTICULADOS_R else "mol km^-2 hr^-1"
            linhas.append({"origem": origem, "especie": pol, "mw_pega_g_mol": mw,
                           "nome_candidato": f"E_{pol}", "encontrada": alvo is not None,
                           "unidade_legada_r": unidade_r, "unidade_alvo": alvo["unidade"] if alvo else None,
                           "unidade_coincide_com_r": bool(alvo and alvo["unidade"] == unidade_r),
                           "mapeamento_aprovado": False})
    return linhas


def auditar_alvo(arquivo, grade, attrs_base):
    with NETCDF_LOCK, Dataset(arquivo, "r") as nc:
        attrs = metadados(nc)
        dims = {k: len(v) for k, v in nc.dimensions.items()}
        variaveis = {k: {"dimensoes": list(v.dimensions), "forma": list(v.shape),
                         "tipo": str(v.dtype), "unidade": getattr(v, "units", None),
                         "atributos": metadados(v, ("FieldType", "MemoryOrder", "description", "stagger", "coordinates")),
                         "ordem_esperada": v.dimensions == DIMS_EMISSAO}
                     for k, v in nc.variables.items() if k.startswith("E_")}
        times = ler_times(nc)
        coords = {"disponiveis": "XLAT" in nc.variables and "XLONG" in nc.variables}
        if coords["disponiveis"]:
            try:
                lat, lon = coordenada(nc, "XLAT"), coordenada(nc, "XLONG")
                if lat.shape != grade.lat.shape or lon.shape != grade.lon.shape:
                    raise ValueError("Formato de grade distinto.")
                dist = np.abs(GEOD.inv(grade.lon, grade.lat, lon, lat)[2])
                if not np.isfinite(dist).all():
                    raise ValueError("Coordenadas geográficas fora dos limites.")
                coords["desvio_vs_dominio_m"] = estatisticas(dist)
            except ValueError as erro:
                coords["erro"] = str(erro)
        return {
            "arquivo": arquivo.name, "formato": nc.data_model,
            "atributos": attrs, "dimensoes": dims, "coordenadas": coords, "times": times,
            "conferencias_atributos_grade": {k: (
                attrs_base[k] == attrs[k] if attrs_base.get(k) is not None and attrs.get(k) is not None
                else None) for k in GRADE_IGUAL},
            "dimensoes_horizontais_conferem": (dims.get("south_north"), dims.get("west_east")) == grade.lat.shape,
            "variaveis": variaveis, "unidades_contagem": dict(Counter(v["unidade"] or "ausente" for v in variaveis.values())),
            "correspondencia_nominal": correspondencia(variaveis),
            "compatibilidade_wrfchem_verificada": False,
        }


def auditar(dominio, alvos):
    grade = DominioWRF(dominio)
    with NETCDF_LOCK, Dataset(dominio, "r") as nc:
        attrs = metadados(nc)
        detalhes = {"arquivo": dominio.name, "atributos": attrs, "formato": nc.data_model,
                    "dimensoes": {k: len(v) for k, v in nc.dimensions.items()},
                    "times": ler_times(nc), "areas": auditar_areas(grade, nc)}
    match = re.search(r"_d([0-9]+)$", dominio.stem)
    detalhes["sufixo_dominio"] = int(match[1]) if match else None
    detalhes["sufixo_confere_com_grid_id"] = (detalhes["sufixo_dominio"] == grade.grid_id) if match else None
    detalhes["geometria"] = auditar_geometria(grade)
    detalhes["comparacao_raster_legado"] = comparar_raster_legado(grade)
    return {"dominio": detalhes, "alvos": [auditar_alvo(p, grade, attrs) for p in alvos]}


def auditar_relogio(ano, nome_zona):
    """Conta duração e transições reais, sem mudar a projeção do inventário."""
    zona = ZoneInfo(nome_zona)
    paredes = (datetime(ano, 1, 1), datetime(ano + 1, 1, 1))
    limites = []
    for parede in paredes:
        candidatos = {parede.replace(tzinfo=zona, fold=f).astimezone(timezone.utc) for f in (0, 1)}
        validos = {t for t in candidatos if t.astimezone(zona).replace(tzinfo=None) == parede}
        if len(validos) != 1:
            raise ValueError("Meia-noite anual ausente ou ambígua. Defina explicitamente os limites.")
        limites.append(validos.pop())
    inicio, fim = limites
    segundos = int((fim - inicio).total_seconds())
    horas = segundos // 3600
    locais = [(inicio + timedelta(hours=i)).astimezone(zona) for i in range(horas)]
    civis = [t.replace(tzinfo=None) for t in locais]
    irregular = bool(segundos % 3600 or any(t.minute or t.second for t in civis))
    nominal = (paredes[1] - paredes[0]).days * 24
    return {"ano": ano, "zona": nome_zona, "inicio_utc": inicio.isoformat(), "fim_utc": fim.isoformat(),
            "horas_nominais": nominal, "segundos_decorridos": segundos, "horas_inteiras": horas,
            "rotulos_repetidos": None if irregular else len(civis) - len(set(civis)),
            "rotulos_ausentes": None if irregular else nominal - len(set(civis)),
            "subdivisao_temporal_a_avaliar": irregular,
            "deslocamentos_s": sorted({int(t.utcoffset().total_seconds()) for t in locais})}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dominio", type=Path)
    parser.add_argument("--alvo", type=Path, action="append", default=[])
    parser.add_argument("--relogio", nargs=2, action="append", metavar=("ANO", "IANA"), default=[])
    args = parser.parse_args()
    resultado = auditar(args.dominio, args.alvo)
    resultado["relogios"] = [auditar_relogio(int(ano), zona) for ano, zona in args.relogio]
    print(json.dumps(resultado, ensure_ascii=True, allow_nan=False, indent=2))


if __name__ == "__main__":
    main()
