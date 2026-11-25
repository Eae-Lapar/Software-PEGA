"""Classificação IBGE 2025 independente da atribuição em grade."""

import csv
import gzip
import hashlib
import io
import json
import math
import sqlite3
from contextlib import closing
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

from shapely import Point, STRtree, from_wkb, prepare


DADOS = Path(__file__).resolve().parents[2] / "data" / "geospatial"
DETALHADA = DADOS / "br_uf_2025_detalhada.jsonl.gz"
SIMPLIFICADA = DADOS / "br_uf_2025_simplificada.geojson"
TRAVA = Lock()
MAX_PONTOS = 4000


@lru_cache(maxsize=1)
def malha():
    with gzip.open(DETALHADA, "rt", encoding="utf-8") as arquivo:
        linhas = [json.loads(linha) for linha in arquivo]
    atributos = [linha["properties"] for linha in linhas]
    geometrias = [from_wkb(bytes.fromhex(linha["wkb"])) for linha in linhas]
    prepare(geometrias)
    return atributos, geometrias, STRtree(geometrias)


@lru_cache(maxsize=1)
def assinatura():
    with DETALHADA.open("rb") as arquivo:
        return hashlib.file_digest(arquivo, "sha256").hexdigest()


@lru_cache(maxsize=1)
def catalogo():
    atributos, _, _ = malha()
    return {
        "uf": {str(a["CD_UF"]): a["NM_UF"] for a in atributos},
        "regiao": {str(a["CD_REGIAO"]): a["NM_REGIAO"] for a in atributos},
    }


def validar_selecao(nivel, codigo):
    if nivel == "brasil" and not codigo:
        return "Brasil"
    nome = catalogo().get(nivel, {}).get(codigo)
    if nome is None:
        raise ValueError("Território inválido.")
    return nome


def classificar(lon, lat):
    if lon is None or lat is None or not (-180 <= lon <= 180 and -90 <= lat <= 90):
        return None, None, "invalida"
    atributos, geometrias, indice = malha()
    ponto = Point(lon, lat)
    candidatos = [int(i) for i in indice.query(ponto) if geometrias[int(i)].covers(ponto)]
    if len(candidatos) > 1:
        return None, None, "ambigua"
    if not len(candidatos):
        return None, None, "fora"
    i = int(candidatos[0])
    if not geometrias[i].contains(ponto):
        return None, None, "limite"
    a = atributos[i]
    return str(a["CD_UF"]), str(a["CD_REGIAO"]), "classificada"


def numero(valor):
    try:
        valor = float(valor)
        return valor if math.isfinite(valor) else None
    except (TypeError, ValueError):
        return None


def coordenadas(lon, lat):
    lon, lat = numero(lon), numero(lat)
    if lon is not None and lat is not None and -180 <= lon <= 180 and -90 <= lat <= 90:
        return lon, lat
    return None, None


def potencias(pasta, dados):
    arquivo = pasta.parents[3] / "dados.csv"
    resultado = {}
    from backend.services.calculos import normalizar_combustivel

    if not arquivo.is_file():
        return resultado
    with arquivo.open(encoding="utf-8", newline="") as entrada:
        for linha in csv.DictReader(entrada):
            if (numero(linha.get("year")) != dados["ano"] or
                    normalizar_combustivel(linha.get("Fuel_type", "")).casefold() != dados["combustivel"].casefold()):
                continue
            chave = (linha["ID"], *coordenadas(linha.get("longitude"), linha.get("latitude")))
            potencia = numero(linha.get("Granted_power_MW"))
            resultado[chave] = potencia if resultado.get(chave, potencia) == potencia else None
    return resultado


def indexar(pasta, dados):
    destino = pasta / f"territorio-2025-v2-{assinatura()[:16]}.sqlite"
    if destino.is_file():
        return destino
    with TRAVA:
        if destino.is_file():
            return destino
        with TemporaryDirectory(dir=pasta) as temp:
            arquivo = Path(temp) / "territorio.sqlite"
            with closing(sqlite3.connect(arquivo)) as conexao:
                conexao.execute("""CREATE TABLE fontes (
                    serie INTEGER, id TEXT, lon REAL, lat REAL, alt TEXT, massa REAL,
                    uf TEXT, regiao TEXT, situacao TEXT, celula TEXT, consumo REAL, potencia REAL)""")
                classificar_local = lru_cache(maxsize=32000)(classificar)
                dados_potencia = potencias(pasta, dados)
                with (pasta / "fontes.csv").open(encoding="utf-8", newline="") as entrada:
                    def linhas():
                        for linha in csv.DictReader(entrada):
                            lon, lat = coordenadas(linha["lon"], linha["lat"])
                            uf, regiao, situacao = classificar_local(lon, lat)
                            yield (int(linha["serie"]), linha["id"], lon, lat, linha["alt"],
                                   float(linha["emissions"]), uf, regiao, situacao,
                                   linha["celula"] or None, numero(linha.get("activity")),
                                   dados_potencia.get((linha["id"], lon, lat)))

                    conexao.executemany("INSERT INTO fontes VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", linhas())
                conexao.executescript("""
                    CREATE INDEX por_serie_uf ON fontes(serie, uf);
                    CREATE INDEX por_serie_regiao ON fontes(serie, regiao);
                    CREATE INDEX por_serie_coord ON fontes(serie, lon, lat);
                """)
                conexao.commit()
            arquivo.replace(destino)
    return destino


def filtro(serie, nivel, codigo):
    validar_selecao(nivel, codigo)
    return ("serie = ?", (serie,)) if nivel == "brasil" else (f"serie = ? AND {nivel} = ?", (serie, codigo))


def consulta(pasta, dados, serie, nivel="brasil", codigo="", top=10, ordem="desc", incluir_pontos=True):
    condicao, args = filtro(serie, nivel, codigo)
    destino = indexar(pasta, dados)
    agrupado = f"""SELECT id, lon, lat, alt, uf, regiao, situacao, SUM(massa) AS massa_g,
                   COUNT(*) AS registros, SUM(consumo) AS consumo_gj, MAX(potencia) AS potencia_mw
                   FROM fontes WHERE {condicao} GROUP BY id, lon, lat, alt, uf, regiao, situacao"""
    nacional = """SELECT id, lon, lat, alt, uf, SUM(massa) AS massa_g FROM fontes
                  WHERE serie = ? GROUP BY id, lon, lat, alt, uf"""
    with closing(sqlite3.connect(destino)) as conn:
        conn.row_factory = sqlite3.Row
        indicadores = dict(conn.execute(f"""SELECT COALESCE(SUM(massa_g),0) AS total_g,
            COUNT(*) AS fontes, COALESCE(SUM(registros),0) AS registros,
            COALESCE(AVG(massa_g),0) AS media_g, COALESCE(MAX(massa_g),0) AS maximo_g
            FROM ({agrupado})""", args).fetchone())
        totais_nacionais = conn.execute(f"""SELECT COALESCE(SUM(massa_g),0),
            COUNT(CASE WHEN uf IS NULL THEN 1 END), MIN(CASE WHEN massa_g > 0 AND lon IS NOT NULL THEN massa_g END),
            MAX(CASE WHEN lon IS NOT NULL THEN massa_g END) FROM ({nacional})""", (serie,)).fetchone()
        total, sem_uf, minimo, maximo = totais_nacionais
        direcao = "ASC" if ordem == "asc" else "DESC"
        com_coincidentes = f"SELECT *, COUNT(*) OVER (PARTITION BY lon, lat) AS coincidentes FROM ({agrupado})"
        ranking = [dict(r) for r in conn.execute(
            f"{com_coincidentes} ORDER BY massa_g {direcao}, id, lon, lat, alt LIMIT ?", (*args, top))]
        amostra = [dict(r) for r in conn.execute(f"SELECT * FROM ({agrupado}) ORDER BY id LIMIT 100", args)]
        pontos = [dict(r) for r in conn.execute(
            f"SELECT * FROM ({com_coincidentes}) WHERE lon IS NOT NULL ORDER BY massa_g DESC, id, lon, lat, alt LIMIT ?",
            (*args, MAX_PONTOS))] if incluir_pontos else []
        totais = {}
        for campo in ("uf", "regiao", "situacao"):
            totais[campo] = dict(conn.execute(
                f"SELECT {campo}, SUM(massa) FROM fontes WHERE serie = ? AND {campo} IS NOT NULL GROUP BY {campo}",
                (serie,)))
        total_nacional = math.fsum(totais["uf"].values())
        parcela = total_nacional if nivel == "brasil" else indicadores["total_g"]
        indicadores.update(sem_classificacao=sem_uf, total_nacional_g=total_nacional, total_base_g=total,
                           participacao_pct=100 * parcela / total_nacional if total_nacional else None)
        celulas = dict(conn.execute(
            f"SELECT celula, SUM(massa) FROM fontes WHERE {condicao} AND celula IS NOT NULL GROUP BY celula", args))
        faixa_local = list(conn.execute(f"""SELECT MIN(CASE WHEN massa_g > 0 THEN massa_g END), MAX(massa_g)
            FROM ({agrupado}) WHERE lon IS NOT NULL""", args).fetchone())
        total_pontos = conn.execute(f"SELECT COUNT(*) FROM ({agrupado}) WHERE lon IS NOT NULL", args).fetchone()[0]
    return dict(indicadores=indicadores, ranking=ranking, pontos=pontos, amostra=amostra, totais=totais, celulas=celulas,
                total_pontos=total_pontos, faixa_nacional=[minimo, maximo], faixa_local=faixa_local)


def fontes_mapa(pasta, dados, serie, nivel, codigo):
    condicao, args = filtro(serie, nivel, codigo)
    with closing(sqlite3.connect(indexar(pasta, dados))) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(linha) for linha in conn.execute(f"""SELECT id, lon, lat, alt, SUM(massa) AS massa_g
            FROM fontes WHERE {condicao} AND lon IS NOT NULL GROUP BY id, lon, lat, alt""", args)]


def coincidentes(pasta, dados, serie, nivel, codigo, lon, lat, pagina):
    condicao, args = filtro(serie, nivel, codigo)
    with closing(sqlite3.connect(indexar(pasta, dados))) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(linha) for linha in conn.execute(f"""SELECT id, lon, lat, alt, uf, regiao,
            SUM(massa) AS massa_g, COUNT(*) AS registros, SUM(consumo) AS consumo_gj,
            MAX(potencia) AS potencia_mw
            FROM fontes WHERE {condicao} AND lon = ? AND lat = ?
            GROUP BY id, lon, lat, alt, uf, regiao ORDER BY id, alt LIMIT 100 OFFSET ?""",
            (*args, lon, lat, (pagina - 1) * 100))]


def transmitir_fontes(destino, criterio, dados, serie):
    condicao, args = criterio
    atributos, _, _ = malha()
    ufs = {str(a["CD_UF"]): a for a in atributos}
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    with closing(sqlite3.connect(destino, check_same_thread=False)) as conn:
        writer.writerow(["id", "lon", "lat", "alt", "uf", "nome_uf", "sigla_uf", "regiao",
                         "nome_regiao", "situacao", "massa_g", "registros", "consumo_gj", "potencia_mw",
                         "pol_origem", "pol", "ano", "setor", "combustivel", "base"])
        contexto = (serie["pol_origem"], serie["pol"], dados["ano"], dados["setor"],
                    dados["combustivel"], dados["origem"])
        fonte = conn.execute(f"""SELECT id, lon, lat, alt, uf, regiao, situacao, SUM(massa),
            COUNT(*), SUM(consumo), MAX(potencia) FROM fontes WHERE {condicao}
            GROUP BY id, lon, lat, alt, uf, regiao, situacao ORDER BY id, lon, lat, alt""", args)
        for linha in fonte:
            a = ufs.get(linha[4], {})
            writer.writerow((*linha[:5], a.get("NM_UF"), a.get("SIGLA_UF"), linha[5],
                             a.get("NM_REGIAO"), *linha[6:], *contexto))
            if buffer.tell() >= 65536:
                yield buffer.getvalue()
                buffer.seek(0)
                buffer.truncate()
        if buffer.tell():
            yield buffer.getvalue()
