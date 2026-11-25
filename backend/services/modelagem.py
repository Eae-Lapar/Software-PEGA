"""Artefato intermediário de massa, com calendário anual opcional."""

import calendar
import csv
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

import numpy as np
from netCDF4 import Dataset

from backend.services.especiacao import ler_especiacao
from backend.services.espacial import chave_serie, coordenadas
from backend.services.temporal import HORAS, SEMANA, origem_csv
from backend.services.wrf import DominioWRF, NETCDF_LOCK


ARQUIVO_NETCDF = "emissoes-grade.nc"
ARQUIVO_METADADOS = "metadados-modelagem.json"
MAX_VALORES_HORARIOS = 12_000_000
MAX_VALORES_GRADE = 36_000_000
MAX_CONFIGURACOES = 8
PUBLICACAO_LOCK = Lock()
SITUACOES = ("mapeada", "fora_grade", "borda_grade", "coordenada_invalida")


def calendario_anual(ano, convencao):
    if convencao == "UTC":
        fuso = timezone.utc
    else:
        partes = re.fullmatch(r"([+-])([0-9]{2}):([0-9]{2})", convencao)
        if not partes:
            raise ValueError("Informe UTC ou um deslocamento fixo, por exemplo -03:00.")
        sinal, horas, minutos = partes.groups()
        minutos_totais = 60 * int(horas) + int(minutos)
        if int(minutos) >= 60 or minutos_totais > 14 * 60 or convencao == "-00:00":
            raise ValueError("Deslocamento fixo inválido.")
        fuso = timezone(timedelta(minutes=minutos_totais * (-1 if sinal == "-" else 1)))
    inicio = datetime(ano, 1, 1, tzinfo=fuso)
    dias = 366 if calendar.isleap(ano) else 365
    pesos = [SEMANA[(inicio.weekday() + dia + 1) % 7] * hora
             for dia in range(dias) for hora in HORAS]
    soma = math.fsum(pesos)
    inicio_utc = inicio.astimezone(timezone.utc)
    unidades = f"hours since {inicio_utc:%Y-%m-%d %H:%M:%S} +00:00"
    return np.asarray(pesos) / soma, unidades, soma


def agregar(arquivo, dominio):
    series = {}
    massas = defaultdict(float)
    balanco = defaultdict(lambda: defaultdict(float))
    referencias = defaultdict(set)

    @lru_cache(maxsize=32000)
    def classificar(coords):
        return dominio.localizar(*coords) if coords else (None, "coordenada_invalida")

    with arquivo.open(encoding="utf-8", newline="") as entrada:
        for linha in csv.DictReader(entrada):
            chave = chave_serie(linha)
            serie = series.setdefault(chave, len(series))
            massa = float(linha["emissions"])
            if linha["unit_emissions"] != "g" or not math.isfinite(massa) or massa < 0:
                raise ValueError("A base deve conter massas finitas e não negativas em gramas.")
            celula, situacao = classificar(coordenadas(linha))
            balanco[serie][situacao] += massa
            if celula is not None and massa:
                massas[serie, *celula] += massa
            referencias[serie].add(tuple(linha.get(k, "") for k in ("fator_id", "source", "reference")))
    if not series:
        raise ValueError("A base de emissões está vazia.")
    somas_grade = defaultdict(list)
    for (serie, _, _), massa in massas.items():
        somas_grade[serie].append(massa)
    resumo = []
    for (origem_pol, pol), serie in series.items():
        categorias = {estado: balanco[serie][estado] for estado in SITUACOES}
        massa_grade = math.fsum(somas_grade[serie])
        if not math.isclose(massa_grade, categorias["mapeada"], rel_tol=1e-10, abs_tol=1e-12):
            raise ValueError("A soma das células não confere com a massa mapeada.")
        resumo.append({"serie": serie, "pol_origem": origem_pol, "pol": pol,
                       "massa_base_g": math.fsum(categorias.values()), "massa_grade_g": massa_grade,
                       "balanco_g": categorias,
                       "referencias": [{"fator_id": f, "fonte": s, "referencia": r}
                                       for f, s, r in sorted(referencias[serie])]})
    return resumo, massas


def escrever_netcdf(caminho, dominio, metadados, massas, calendario):
    series = metadados["series"]
    if len(series) * dominio.nx * dominio.ny > MAX_VALORES_GRADE:
        raise ValueError("O produto série × grade excede 36 milhões de valores.")
    with NETCDF_LOCK, Dataset(caminho, "w", format="NETCDF4") as nc:
        nc.title = "PEGA - massas de emissão em grade Lambert do WRF"
        nc.product_type = "intermediate_inventory_mass_not_wrfchemi"
        nc.source = "PEGA; geometrias reconstruídas de XLAT/XLONG, DX/DY e atributos Lambert"
        nc.inventory_year = metadados["ano"]
        nc.emission_base = metadados["origem"]
        nc.sector = metadados["setor"]
        nc.fuel = metadados["combustivel"]
        nc.calculation_id = metadados["calculo_id"]
        nc.input_domain_sha256 = metadados["dominio_sha256"]
        nc.grid_id = dominio.grid_id
        for nome, tamanho in (("series", len(series)), ("south_north", dominio.ny),
                              ("west_east", dominio.nx), ("nv", 2)):
            nc.createDimension(nome, tamanho)
        for nome, eixo, passo, sentido in (("west_east", dominio.x, dominio.dx, "x"),
                                           ("south_north", dominio.y, dominio.dy, "y")):
            var = nc.createVariable(nome, "f8", (nome,))
            var.units = "m"
            var.standard_name = f"projection_{sentido}_coordinate"
            var.bounds = f"{nome}_bounds"
            var[:] = eixo
            nc.createVariable(var.bounds, "f8", (nome, "nv"))[:] = np.column_stack(
                (eixo - passo / 2, eixo + passo / 2))
        for nome, valores, unidades in (("latitude", dominio.lat, "degrees_north"),
                                        ("longitude", dominio.lon, "degrees_east")):
            var = nc.createVariable(nome, "f8", ("south_north", "west_east"), zlib=True)
            var.units = unidades
            var.standard_name = nome
            var[:] = valores
        nc.createVariable("crs", "i4").setncatts(dominio.crs.to_cf())
        nc.createVariable("series", "i4", ("series",))[:] = np.arange(len(series))
        for campo in ("pol", "pol_origem"):
            var = nc.createVariable(campo, str, ("series",))
            var[:] = np.asarray([s[campo] for s in series], dtype=object)
        for nome, chave in (("input_mass_g", "massa_base_g"), ("mapped_mass_g", "massa_grade_g")):
            var = nc.createVariable(nome, "f8", ("series",))
            var.units = "g"
            var[:] = [s[chave] for s in series]
        for situacao in SITUACOES[1:]:
            var = nc.createVariable(f"{situacao}_mass_g", "f8", ("series",))
            var.units = "g"
            var[:] = [s["balanco_g"][situacao] for s in series]
        cube = nc.createVariable("inventory_mass", "f8", ("series", "south_north", "west_east"),
                                 zlib=True, chunksizes=(1, min(dominio.ny, 128), min(dominio.nx, 128)))
        cube.units = "g"
        cube.long_name = "Inventory mass accumulated per cell"
        cube.grid_mapping = "crs"
        cube.coordinates = "latitude longitude"
        por_serie = defaultdict(list)
        for (serie, y, x), massa in massas.items():
            por_serie[serie].append((y, x, massa))
        for serie in range(len(series)):
            fatia = np.zeros((dominio.ny, dominio.nx))
            for y, x, massa in por_serie[serie]:
                fatia[y, x] = massa
            cube[serie] = fatia
        if calendario:
            escrever_horas(nc, massas, calendario, metadados)


def escrever_horas(nc, massas, calendario, metadados):
    pesos, unidades, _ = calendario
    nc.time_profile_timezone = metadados["calendario"]["convencao"]
    nc.createDimension("time", len(pesos))
    tempo = nc.createVariable("time", "f8", ("time",))
    tempo.standard_name = "time"
    tempo.units = unidades
    tempo.calendar = "proleptic_gregorian"
    tempo.bounds = "time_bounds"
    indices = np.arange(len(pesos))
    tempo[:] = indices + .5
    nc.createVariable(tempo.bounds, "i4", ("time", "nv"))[:] = np.column_stack((indices, indices + 1))
    fracao = nc.createVariable("hour_fraction", "f8", ("time",))
    fracao.units = "1"
    fracao.long_name = "Fraction of inventory mass assigned to this hour"
    fracao[:] = pesos
    fracao.reconstruction = "hourly mass in g = inventory_mass * hour_fraction"
    if not metadados["calendario"]["horario_materializado"]:
        return
    ativos = sorted(massas)
    nc.createDimension("active", len(ativos))
    for eixo, nome in enumerate(("active_series_index", "active_row_index", "active_column_index")):
        var = nc.createVariable(nome, "i4", ("active",))
        var.index_base = 0
        var[:] = [chave[eixo] for chave in ativos]
    horario = nc.createVariable("hourly_mass", "f8", ("time", "active"), zlib=True,
                                 chunksizes=(24, min(len(ativos), 1024)))
    horario.units = "g"
    horario.cell_methods = "time: sum"
    horario.long_name = "Accumulated mass per one-hour interval for active series/cell pairs"
    valores = np.asarray([massas[chave] for chave in ativos])
    for inicio in range(0, len(pesos), 24):
        horario[inicio:inicio + 24] = pesos[inicio:inicio + 24, None] * valores[None, :]


def pasta_resultados(pasta, origem):
    return pasta / f"modelagem-{origem}"


def resultado_atual(pasta, origem):
    destino = pasta_resultados(pasta, origem)
    identificador = (destino / "atual").read_text(encoding="ascii")
    if not re.fullmatch(r"[0-9a-f]{64}", identificador):
        raise FileNotFoundError("A preparação não está disponível.")
    return destino / identificador


def publicar(pasta, origem, arquivo, calculo, convencao, conferir):
    calendario = calendario_anual(calculo["ano"], convencao) if convencao else None
    with arquivo.open("rb") as entrada:
        digest = hashlib.file_digest(entrada, "sha256").hexdigest()
    identificador = hashlib.sha256(f"1:{digest}:{convencao}".encode()).hexdigest()
    destino = pasta_resultados(pasta, origem)
    publicado = destino / identificador
    if publicado.is_dir():
        selecionar(destino, identificador, conferir)
        return json.loads((publicado / ARQUIVO_METADADOS).read_text(encoding="utf-8"))
    if sum(f.is_dir() and re.fullmatch(r"[0-9a-f]{64}", f.name) is not None
           for f in destino.glob("*")) >= MAX_CONFIGURACOES:
        raise ValueError("Limite de oito configurações de modelagem para esta base.")
    dominio = DominioWRF(arquivo)
    series, massas = agregar(origem_csv(pasta, origem), dominio)
    dados = {k: calculo[k] for k in ("calculo_id", "configuracao_id", "ano", "setor", "combustivel")}
    dados.update(
        origem=origem, dominio_sha256=digest, formato="netcdf_intermediario",
        grid_id=dominio.grid_id, nx=dominio.nx, ny=dominio.ny, dx_m=dominio.dx, dy_m=dominio.dy,
        erro_projecao_m=dominio.erro_m, tolerancia_borda_m=dominio.borda_m, series=series,
        balanco_especiacao=ler_especiacao(pasta)["balanco"] if origem == "especiada" else [],
        calendario=None,
    )
    if calendario:
        pesos, unidades, soma_bruta = calendario
        dados["calendario"] = {
            "horas": len(pesos), "convencao": convencao, "unidades_tempo": unidades,
            "soma_pesos_brutos": soma_bruta, "soma_pesos_normalizados": math.fsum(pesos),
            "pares_serie_celula_ativos": len(massas),
            "horario_materializado": 0 < len(massas) * len(pesos) <= MAX_VALORES_HORARIOS,
        }
    with TemporaryDirectory(dir=pasta) as temp:
        candidato = Path(temp) / "resultado"
        candidato.mkdir()
        escrever_netcdf(candidato / ARQUIVO_NETCDF, dominio, dados, massas, calendario)
        (candidato / ARQUIVO_METADADOS).write_text(json.dumps(dados, ensure_ascii=False, allow_nan=False),
                                                  encoding="utf-8")
        # Uma configuração concluída é imutável; a seleção do histórico aponta para a última.
        with PUBLICACAO_LOCK:
            destino.mkdir(exist_ok=True)
            conferir()
            if not publicado.is_dir():
                if sum(f.is_dir() and re.fullmatch(r"[0-9a-f]{64}", f.name) is not None
                       for f in destino.iterdir()) >= MAX_CONFIGURACOES:
                    raise ValueError("Limite de oito configurações de modelagem para esta base.")
                try:
                    candidato.rename(publicado)
                except OSError:
                    if not (publicado / ARQUIVO_METADADOS).is_file():
                        raise
            selecionar(destino, identificador, conferir)
    return dados


def selecionar(destino, identificador, conferir):
    with TemporaryDirectory(dir=destino) as temp:
        ponteiro = Path(temp) / "atual"
        ponteiro.write_text(identificador, encoding="ascii")
        conferir()
        ponteiro.replace(destino / "atual")
