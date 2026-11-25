import pandas as pd
import hashlib
import re
import json

from uuid import uuid4
from pydantic import BaseModel, Field

from backend.services.calculos import calcular_emissoes, normalizar_combustivel
from backend.services.especiacao import (
    ARQUIVOS_ESPECIACAO, PASTA_ESPECIACAO, ler_especiacao, salvar_especiacao,
)
import asyncio
import os

from contextlib import asynccontextmanager, suppress
from tempfile import TemporaryDirectory
from pathlib import Path

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    HTTPException,
    Request,
    Response
)

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from typing import Literal
from fastapi import Form
from backend.services.espacial import (
    carregar_resultado, ler_serie, pasta_espacial, publicar_espacial,
)
from backend.services.mapas import LimiteMapas, colorir_territorio, gerar_mapa, grade_interativa, pontos_interativos
from backend.services.territorio import (
    SIMPLIFICADA, coincidentes, consulta as consulta_territorial, filtro as filtro_territorial,
    indexar as indexar_territorio, transmitir_fontes, validar_selecao,
)
from backend.services.temporal import (
    caminho_temporal, consultar_temporal, origem_csv, salvar_temporal, transmitir_alocacao,
)
from backend.services import visualizacoes
from backend.services.modelagem import ARQUIVO_METADADOS, ARQUIVO_NETCDF, publicar as publicar_modelagem, resultado_atual

from backend.services.importacao import ANO_MAXIMO, ANO_MINIMO, pega_importar

from backend.services.armazenamento import (
    criar_sessao,
    salvar_inventario,
    excluir_inventario,
    limpar_expirados,
    verificar_acesso,
    ARQUIVOS_CALCULO,
    listar_calculos,
    ler_metadados_calculo,
    obter_pasta_calculo
)

from backend.services.fatores_emissao import (
    informacoes_base,
    listar_setores,
    listar_combustiveis,
    obter_fatores,
    analisar_fatores,
    listar_setores_suportados,
    converter_registros
)


# ==================================================
# 1. CONFIGURACOES
# ==================================================

COOKIE_SEGURO = (
    os.getenv("COOKIE_SECURE", "false").lower()
    == "true"
)

MAX_UPLOAD = 50 * 1024 * 1024

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"

class SolicitacaoCalculo(BaseModel):

    setor: str

    ano: int = Field(ge=ANO_MINIMO, le=ANO_MAXIMO)

    combustivel: str

    selecoes: dict[str, str] = Field(
        default_factory=dict
    )
# ==================================================
# 2. LIMPEZA PERIODICA
# ==================================================

async def limpeza_periodica():

    while True:

        await asyncio.to_thread(
            limpar_expirados
        )

        await asyncio.sleep(300)


@asynccontextmanager
async def lifespan(app):

    tarefa = asyncio.create_task(
        limpeza_periodica()
    )

    try:

        yield

    finally:

        tarefa.cancel()

        with suppress(asyncio.CancelledError):

            await tarefa


# ==================================================
# 3. CONFIGURACAO DA API
# ==================================================

app = FastAPI(
    title="PEGA",
    description="Inventários de Emissões Atmosféricas",
    version="1.0.0",
    lifespan=lifespan
)


# ==================================================
# 4. ARQUIVOS ESTATICOS
# ==================================================

app.mount(
    "/static",
    StaticFiles(directory=FRONTEND_DIR),
    name="static"
)


# ==================================================
# 5. PAGINA INICIAL
# ==================================================

@app.get("/")
def inicio():

    return FileResponse(
        FRONTEND_DIR / "index.html"
    )


# ==================================================
# 6. STATUS DO SERVIDOR
# ==================================================

@app.get("/api/health")
def health():

    return {

        "software": "PEGA",

        "status": "online",

        "mensagem": "Backend conectado com sucesso!"

    }


# ==================================================
# 7. UPLOAD PRIVADO
# ==================================================

@app.post("/api/upload")
def upload_planilha(
    request: Request,
    response: Response,
    arquivo: UploadFile = File(...)
):

    try:

        nome = arquivo.filename or "arquivo"

        extensao = Path(nome).suffix.lower()

        # Validar formato

        if extensao not in [".csv", ".txt", ".xlsx"]:

            raise HTTPException(
                status_code=400,
                detail="Formato não suportado."
            )

        # Validar tamanho

        if arquivo.size is not None:

            if arquivo.size > MAX_UPLOAD:

                raise HTTPException(
                    status_code=413,
                    detail="Arquivo excede o limite de 50 MB."
                )

        # Criar pasta temporaria

        with TemporaryDirectory() as pasta:

            caminho = Path(pasta) / f"entrada{extensao}"

            # Salvar arquivo temporariamente

            with caminho.open("wb") as destino:

                total = 0

                while bloco := arquivo.file.read(1024 * 1024):

                    total += len(bloco)

                    if total > MAX_UPLOAD:

                        raise HTTPException(
                            status_code=413,
                            detail="Arquivo excede o limite de 50 MB."
                        )

                    destino.write(bloco)

            # Importar e validar planilha

            resultado = pega_importar(
                caminho,
                nome_original=nome
            )

            dados = resultado["dados"]

            inventario_id = None

            # Salvar somente inventarios validos

            if resultado["validacao"]["valido"]:

                token_sessao = request.cookies.get(
                    "pega_session"
                )

                # Criar sessao privada

                if not token_sessao:

                    token_sessao = criar_sessao()

                # Armazenar inventario

                inventario_id = salvar_inventario(
                    caminho,
                    resultado,
                    token_sessao
                )

                # Configurar cookie privado

                response.set_cookie(
                    key="pega_session",
                    value=token_sessao,
                    httponly=True,
                    secure=COOKIE_SEGURO,
                    samesite="strict",
                    max_age=86400
                )

            # Preparar previa dos dados

            previa = converter_registros(
                dados.head(20).fillna("")
            )

            # Impedir cache dos dados privados

            response.headers["Cache-Control"] = "no-store"

            return {

                "inventario_id": inventario_id,

                "arquivo": resultado["nome_arquivo"],

                "total_linhas": len(dados),

                "colunas": list(dados.columns),

                "mapa_colunas": resultado["mapa_colunas"],

                "colunas_extras": resultado["colunas_extras"],

                "validacao": resultado["validacao"],

                "previa": previa,

                "atividades": listar_atividades(dados) if inventario_id else []

            }

    except HTTPException:

        raise

    except ValueError as erro:

        raise HTTPException(
            status_code=400,
            detail=str(erro)
        )

    except Exception:

        raise HTTPException(
            status_code=500,
            detail="Erro interno ao importar a planilha."
        )


# ==================================================
# 8. CONSULTAR INVENTARIO PRIVADO
# ==================================================

@app.get("/api/inventarios/{inventario_id}")
def consultar_inventario(
    inventario_id: str,
    request: Request,
    response: Response
):

    token_sessao = request.cookies.get(
        "pega_session"
    )

    try:

        pasta, resultado = verificar_acesso(inventario_id, token_sessao)
        resultado.pop("sessao_hash", None)
        dados = ler_csv_privado(pasta / "dados.csv")
        resultado["previa"] = converter_registros(dados.head(20))
        resultado["atividades"] = listar_atividades(dados)

        response.headers["Cache-Control"] = "no-store"

        return resultado

    except (PermissionError, FileNotFoundError):

        raise HTTPException(
            status_code=404,
            detail="Inventário indisponível.",
            headers={"Cache-Control": "no-store"},
        )


def ler_csv_privado(caminho, **opcoes):
    return pd.read_csv(caminho, dtype=str, keep_default_na=False, **opcoes)


def listar_atividades(dados):
    pares = dados[["year", "Fuel_type"]].copy()
    pares["year"] = pares["year"].astype(str).str.strip()
    return [
        {"ano": str(ano), "combustivel_original": str(combustivel),
         "combustivel": normalizar_combustivel(combustivel)}
        for ano, combustivel in pares.drop_duplicates().itertuples(index=False, name=None)
    ]


def pasta_privada(request, inventario_id, calculo_id=None):
    try:
        pasta, _ = verificar_acesso(inventario_id, request.cookies.get("pega_session"))
        return pasta if calculo_id is None else obter_pasta_calculo(pasta, calculo_id)
    except (PermissionError, FileNotFoundError) as erro:
        raise HTTPException(
            status_code=404, detail="Inventário ou cálculo indisponível.",
            headers={"Cache-Control": "no-store"},
        ) from erro


def recurso_indisponivel():
    return HTTPException(
        status_code=404, detail="Resultado indisponível.",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/inventarios/{inventario_id}/calculos")
def consultar_calculos(inventario_id: str, request: Request, response: Response):
    pasta = pasta_privada(request, inventario_id)
    response.headers["Cache-Control"] = "no-store"
    return {"calculos": listar_calculos(pasta)}


@app.get("/api/inventarios/{inventario_id}/calculos/{calculo_id}")
def consultar_calculo(inventario_id: str, calculo_id: str, request: Request, response: Response):
    pasta = pasta_privada(request, inventario_id, calculo_id)
    try:
        dados = ler_metadados_calculo(pasta)
        previa = ler_csv_privado(pasta / "emissoes_base.csv", nrows=20)
    except FileNotFoundError as erro:
        raise recurso_indisponivel() from erro
    response.headers["Cache-Control"] = "no-store"
    return {**dados, "previa": converter_registros(previa)}


@app.get("/api/inventarios/{inventario_id}/calculos/{calculo_id}/arquivos/{nome}")
def baixar_calculo(inventario_id: str, calculo_id: str, nome: str, request: Request):
    pasta = pasta_privada(request, inventario_id, calculo_id)
    tipo = ARQUIVOS_CALCULO.get(nome)
    if tipo is None or not (pasta / nome).is_file():
        raise recurso_indisponivel()
    return FileResponse(
        pasta / nome, media_type=tipo, filename=nome,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


ROTA_ESPECIACAO = "/api/inventarios/{inventario_id}/calculos/{calculo_id}/especiacao"


@app.post(ROTA_ESPECIACAO)
def executar_especiacao(inventario_id: str, calculo_id: str, request: Request, response: Response):
    pasta = pasta_privada(request, inventario_id, calculo_id)
    try:
        dados = salvar_especiacao(
            pasta, ler_metadados_calculo(pasta),
            lambda: pasta_privada(request, inventario_id, calculo_id),
        )
    except FileNotFoundError as erro:
        raise recurso_indisponivel() from erro
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro),
                            headers={"Cache-Control": "no-store"}) from erro
    response.headers["Cache-Control"] = "no-store"
    return dados


@app.get(ROTA_ESPECIACAO)
def consultar_especiacao(inventario_id: str, calculo_id: str, request: Request, response: Response):
    pasta = pasta_privada(request, inventario_id, calculo_id)
    try:
        dados = ler_especiacao(pasta)
    except FileNotFoundError as erro:
        raise recurso_indisponivel() from erro
    response.headers["Cache-Control"] = "no-store"
    return dados


@app.get(ROTA_ESPECIACAO + "/resumo")
def consultar_resumo_especies(inventario_id: str, calculo_id: str, request: Request, response: Response):
    dados = consultar_especiacao(inventario_id, calculo_id, request, response)
    return {"resumo": dados["resumo"], "balanco": dados["balanco"]}


@app.get(ROTA_ESPECIACAO + "/arquivos/{nome}")
def baixar_especiacao(inventario_id: str, calculo_id: str, nome: str, request: Request):
    pasta = pasta_privada(request, inventario_id, calculo_id) / PASTA_ESPECIACAO
    tipo = ARQUIVOS_ESPECIACAO.get(nome)
    if tipo is None or not (pasta / nome).is_file():
        raise recurso_indisponivel()
    return FileResponse(pasta / nome, media_type=tipo, filename=nome,
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


# ==================================================
# 9. EXCLUIR INVENTARIO PRIVADO
# ==================================================

ROTA_TEMPORAL = "/api/inventarios/{inventario_id}/calculos/{calculo_id}/temporal/{origem}"
OrigemTemporal = Literal["original", "especiada"]


@app.post(ROTA_TEMPORAL)
def executar_temporal(inventario_id: str, calculo_id: str, origem: OrigemTemporal,
                      request: Request, response: Response):
    pasta = pasta_privada(request, inventario_id, calculo_id)
    try:
        dados = salvar_temporal(pasta, origem, ler_metadados_calculo(pasta),
                                lambda: pasta_privada(request, inventario_id, calculo_id))
    except FileNotFoundError as erro:
        raise recurso_indisponivel() from erro
    response.headers["Cache-Control"] = "no-store"
    return dados


@app.get(ROTA_TEMPORAL)
def consultar_resultado_temporal(inventario_id: str, calculo_id: str, origem: OrigemTemporal,
                                 request: Request, response: Response):
    pasta = pasta_privada(request, inventario_id, calculo_id)
    try:
        dados = consultar_temporal(pasta, origem)
    except FileNotFoundError as erro:
        raise recurso_indisponivel() from erro
    response.headers["Cache-Control"] = "no-store"
    return dados


@app.get(ROTA_TEMPORAL + "/arquivos/{nome}")
def baixar_temporal(inventario_id: str, calculo_id: str, origem: OrigemTemporal,
                    nome: Literal["perfil_temporal.json", "alocacao_relativa.csv"], request: Request):
    pasta = pasta_privada(request, inventario_id, calculo_id)
    caminho = caminho_temporal(pasta, origem)
    if not caminho.is_file():
        raise recurso_indisponivel()
    headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    if nome == "perfil_temporal.json":
        return FileResponse(caminho, filename=nome, media_type="application/json", headers=headers)
    try:
        calculo = ler_metadados_calculo(pasta)
        arquivo = origem_csv(pasta, origem).open(encoding="utf-8", newline="")
    except FileNotFoundError as erro:
        raise recurso_indisponivel() from erro
    headers["Content-Disposition"] = f'attachment; filename="{nome}"'
    return StreamingResponse(transmitir_alocacao(arquivo, calculo, origem),
                             media_type="text/csv", headers=headers)


ROTA_ESPACIAL = "/api/inventarios/{inventario_id}/calculos/{calculo_id}/espacial/{origem}"
UnidadeEspacial = Literal["g", "kg", "t"]
PaletaEspacial = Literal["viridis", "plasma", "inferno", "cividis"]
EscalaEspacial = Literal["linear", "log"]


@app.get("/api/cartografia/ibge")
def consultar_cartografia():
    return FileResponse(SIMPLIFICADA, media_type="application/geo+json")


@app.post(ROTA_ESPACIAL)
def executar_espacial(inventario_id: str, calculo_id: str, origem: OrigemTemporal,
                     request: Request, response: Response, grade: UploadFile | None = File(None),
                     epsg: int = Form(4326)):
    pasta = pasta_privada(request, inventario_id, calculo_id)
    try:
        dados_grade = None
        if grade:
            conteudo = grade.file.read(15 * 1024 * 1024 + 1)
            if len(conteudo) > 15 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="A grade deve ter até 15 MB.")
            dados_grade = json.loads(conteudo)
            if not isinstance(dados_grade, dict):
                raise ValueError("Informe a grade como FeatureCollection GeoJSON.")
        dados = publicar_espacial(pasta, origem, ler_metadados_calculo(pasta), dados_grade, epsg,
                                  lambda: pasta_privada(request, inventario_id, calculo_id))
    except FileNotFoundError as erro:
        raise recurso_indisponivel() from erro
    except (ValueError, OverflowError) as erro:
        raise HTTPException(status_code=400, detail=str(erro),
                            headers={"Cache-Control": "no-store"}) from erro
    response.headers["Cache-Control"] = "no-store"
    return dados


def contexto_espacial(request, inventario_id, calculo_id, origem):
    pasta = pasta_privada(request, inventario_id, calculo_id)
    try:
        dados = carregar_resultado(pasta, origem)
    except FileNotFoundError as erro:
        raise recurso_indisponivel() from erro
    return pasta_espacial(pasta, origem) / dados["configuracao_espacial"], dados


@app.get(ROTA_ESPACIAL)
def consultar_espacial(inventario_id: str, calculo_id: str, origem: OrigemTemporal,
                       request: Request, response: Response):
    _, dados = contexto_espacial(request, inventario_id, calculo_id, origem)
    response.headers["Cache-Control"] = "no-store"
    return dados


def selecionar_serie(dados, serie):
    if not 0 <= serie < len(dados["series"]):
        raise recurso_indisponivel()
    return dados["series"][serie]


NivelTerritorial = Literal["brasil", "regiao", "uf"]
EscopoCores = Literal["nacional", "local"]


@app.get(ROTA_ESPACIAL + "/territorio/{serie}")
def explorar_territorio(inventario_id: str, calculo_id: str, origem: OrigemTemporal, serie: int,
                       request: Request, response: Response, nivel: NivelTerritorial = "brasil",
                       codigo: str = "", unidade: UnidadeEspacial = "g", paleta: PaletaEspacial = "viridis",
                       escala: EscalaEspacial = "linear", escopo: EscopoCores = "nacional",
                       top: int = 10, ordem: Literal["asc", "desc"] = "desc",
                       pontos: bool = True, grade_visual: bool = False):
    pasta, dados = contexto_espacial(request, inventario_id, calculo_id, origem)
    selecionada = selecionar_serie(dados, serie)
    if top not in (5, 10, 20):
        raise HTTPException(status_code=400, detail="Selecione Top 5, 10 ou 20.")
    try:
        nome = validar_selecao(nivel, codigo)
        resultado = consulta_territorial(pasta, dados, serie, nivel, codigo, top, ordem, pontos)
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro
    colorir_territorio(resultado, unidade, paleta, escala, escopo, nivel, codigo)
    if grade_visual and dados["grade"]:
        resultado["grade_visual"] = grade_interativa(pasta, dados, resultado, unidade, paleta,
                                                      escala, nivel, escopo, serie)
    response.headers["Cache-Control"] = "no-store"
    return {**resultado, "nome": nome, "serie": selecionada}


@app.get(ROTA_ESPACIAL + "/territorio/{serie}/coincidentes")
def consultar_coincidentes(inventario_id: str, calculo_id: str, origem: OrigemTemporal, serie: int,
                            request: Request, response: Response, lon: float, lat: float,
                            nivel: NivelTerritorial = "brasil", codigo: str = "", pagina: int = 1):
    pasta, dados = contexto_espacial(request, inventario_id, calculo_id, origem)
    selecionar_serie(dados, serie)
    if not (-180 <= lon <= 180 and -90 <= lat <= 90 and 1 <= pagina <= 10000):
        raise HTTPException(status_code=400, detail="Coordenadas ou página inválidas.")
    try:
        fontes = coincidentes(pasta, dados, serie, nivel, codigo, lon, lat, pagina)
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro
    response.headers["Cache-Control"] = "no-store"
    return {"fontes": fontes}


@app.get(ROTA_ESPACIAL + "/territorio/{serie}/fontes.csv")
def baixar_fontes_territoriais(inventario_id: str, calculo_id: str, origem: OrigemTemporal, serie: int,
                               request: Request, nivel: NivelTerritorial = "brasil", codigo: str = ""):
    pasta, dados = contexto_espacial(request, inventario_id, calculo_id, origem)
    selecionada = selecionar_serie(dados, serie)
    try:
        criterio = filtro_territorial(serie, nivel, codigo)
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro
    return StreamingResponse(transmitir_fontes(indexar_territorio(pasta, dados), criterio, dados, selecionada),
                             media_type="text/csv; charset=utf-8",
                             headers={"Cache-Control": "no-store",
                                      "Content-Disposition": 'attachment; filename="fontes-territoriais.csv"'})


@app.get(ROTA_ESPACIAL + "/series/{serie}")
def consultar_serie_espacial(inventario_id: str, calculo_id: str, origem: OrigemTemporal,
                             serie: int, request: Request, response: Response,
                             unidade: UnidadeEspacial = "g", paleta: PaletaEspacial = "viridis",
                             escala: EscalaEspacial = "linear", interativo: bool = False):
    pasta, dados = contexto_espacial(request, inventario_id, calculo_id, origem)
    selecionar_serie(dados, serie)
    response.headers["Cache-Control"] = "no-store"
    return {
        "fontes": list(ler_serie(pasta, serie, "fontes.csv", 100)),
        "celulas": list(ler_serie(pasta, serie, "celulas.csv", 100)) if dados["grade"] else [],
        "pontos": pontos_interativos(pasta, serie, unidade, paleta, escala) if interativo else [],
    }


@app.get(ROTA_ESPACIAL + "/arquivos/{nome}")
def baixar_espacial(inventario_id: str, calculo_id: str, origem: OrigemTemporal, request: Request,
                    nome: Literal["fontes.csv", "celulas.csv", "metadados.json", "grade.geojson"]):
    pasta, _ = contexto_espacial(request, inventario_id, calculo_id, origem)
    arquivo = pasta / nome
    if not arquivo.is_file():
        raise recurso_indisponivel()
    return FileResponse(arquivo, filename=nome, headers={"Cache-Control": "no-store"})


@app.get(ROTA_ESPACIAL + "/mapas/{serie}.{formato}")
def consultar_mapa(inventario_id: str, calculo_id: str, origem: OrigemTemporal, serie: int,
                   formato: Literal["png", "svg", "pdf"], request: Request,
                   unidade: UnidadeEspacial = "g", paleta: PaletaEspacial = "viridis",
                   escala: EscalaEspacial = "linear", idioma: Literal["pt", "en"] = "pt",
                   modo: Literal["pontos", "grade", "territorial", "regional"] = "pontos", tamanho: bool = False,
                   dpi: int = 300, download: bool = False, nivel: NivelTerritorial = "brasil",
                   codigo: str = "", escopo: EscopoCores = "nacional",
                   marcador: Literal["cor", "tamanho", "ambos"] = "cor"):
    pasta, dados = contexto_espacial(request, inventario_id, calculo_id, origem)
    selecionada = selecionar_serie(dados, serie)
    if (modo == "grade" and not dados["grade"]) or dpi not in (100, 300, 600) or (modo == "regional" and nivel == "uf"):
        raise recurso_indisponivel()
    try:
        validar_selecao(nivel, codigo)
        arquivo = gerar_mapa(
            pasta, dados, selecionada,
            (unidade, paleta, escala, idioma, modo, "ambos" if tamanho else marcador, nivel, codigo, escopo),
            formato, dpi if formato == "png" else 0,
            lambda: pasta_privada(request, inventario_id, calculo_id),
        )
    except LimiteMapas as erro:
        raise HTTPException(status_code=429, detail=str(erro)) from erro
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro
    tipo = {"png": "image/png", "pdf": "application/pdf", "svg": "image/svg+xml"}[formato]
    return FileResponse(arquivo, filename=f"mapa-{modo}-{dados['ano']}-{origem}-{serie}-{codigo or nivel}.{formato}", media_type=tipo,
                        content_disposition_type="attachment" if download else "inline",
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


ROTA_VISUALIZACOES = "/api/inventarios/{inventario_id}/calculos/{calculo_id}/visualizacoes"


@app.get(ROTA_VISUALIZACOES)
def consultar_visualizacoes(request: Request, inventario_id: str, calculo_id: str):
    pasta = pasta_privada(request, inventario_id, calculo_id)
    return JSONResponse(visualizacoes.opcoes(pasta), headers={"Cache-Control": "no-store"})


@app.get(ROTA_VISUALIZACOES + "/figura.{formato}")
def figura_cientifica(
    request: Request, inventario_id: str, calculo_id: str,
    formato: Literal["png", "pdf", "svg"], tipo: str, origem: OrigemTemporal = "original",
    pol: str = "", pol_origem: str = "", unidade: Literal["g", "kg", "t", "%"] = "g",
    nivel: NivelTerritorial = "brasil", codigo: str = "", inicio: str = "", fim: str = "",
    comparar_inicio: str = "", comparar_fim: str = "", idioma: Literal["pt", "en"] = "pt",
    escala: Literal["linear", "log"] = "linear", paleta: Literal["viridis", "plasma", "cividis"] = "viridis",
    ordem: Literal["maior", "menor"] = "maior", top: int = 10, dpi: int = 300,
    download: bool = False,
):
    pasta = pasta_privada(request, inventario_id, calculo_id)
    if (tipo not in visualizacoes.TITULOS or dpi not in (100, 300, 600) or not 1 <= top <= 30
            or (tipo not in visualizacoes.EMISSOES and (nivel != "brasil" or codigo))
            or ((inicio or fim) and tipo not in visualizacoes.ANUAIS[:-1])
            or ((comparar_inicio or comparar_fim) and tipo not in ("mensal", "diario", "horas", "serie-anual"))):
        raise HTTPException(status_code=400, detail="Configuração de visualização inválida.")
    filtros = dict(tipo=tipo, origem=origem, pol=pol, pol_origem=pol_origem, unidade=unidade,
                   nivel=nivel, codigo=codigo, inicio=inicio, fim=fim, comparar_inicio=comparar_inicio,
                   comparar_fim=comparar_fim, idioma=idioma, escala=escala, paleta=paleta,
                   ordem=ordem, top=top, cor={"viridis": "#26827f", "plasma": "#9c207f",
                                             "cividis": "#52637d"}[paleta])
    try:
        arquivo = visualizacoes.gerar(pasta, filtros, formato, dpi if formato == "png" else 150,
                                      lambda: pasta_privada(request, inventario_id, calculo_id))
    except FileNotFoundError as erro:
        raise recurso_indisponivel() from erro
    except LimiteMapas as erro:
        raise HTTPException(status_code=429, detail=str(erro)) from erro
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro
    ano = ler_metadados_calculo(pasta)["ano"]
    partes = [tipo, str(ano), origem, pol_origem, pol, nivel, codigo]
    nome = re.sub(r"[^A-Za-z0-9_.-]+", "-", "-".join(filter(None, partes)))[:150]
    return FileResponse(arquivo, filename=f"{nome}.{formato}",
                        media_type={"png": "image/png", "pdf": "application/pdf", "svg": "image/svg+xml"}[formato],
                        content_disposition_type="attachment" if download else "inline",
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


ROTA_MODELAGEM = "/api/inventarios/{inventario_id}/calculos/{calculo_id}/modelagem/{origem}"
MAX_UPLOAD_DOMINIO = 256 * 1024 * 1024


def copiar_dominio(arquivo, destino):
    if arquivo.size is not None and arquivo.size > MAX_UPLOAD_DOMINIO:
        raise HTTPException(status_code=413, detail="O NetCDF deve ter até 256 MiB.")
    with destino.open("wb") as saida:
        total = 0
        while bloco := arquivo.file.read(1024 * 1024):
            total += len(bloco)
            if total > MAX_UPLOAD_DOMINIO:
                raise HTTPException(status_code=413, detail="O NetCDF deve ter até 256 MiB.")
            saida.write(bloco)


@app.post(ROTA_MODELAGEM)
def executar_modelagem(inventario_id: str, calculo_id: str, origem: OrigemTemporal,
                      request: Request, response: Response, dominio: UploadFile = File(...),
                      convencao: str = Form(""), anual: bool = Form(False)):
    pasta = pasta_privada(request, inventario_id, calculo_id)
    try:
        if anual and not convencao.strip():
            raise ValueError("Escolha a convenção temporal para a projeção anual.")
        with TemporaryDirectory(dir=pasta) as temporario:
            entrada = Path(temporario) / "dominio.nc"
            copiar_dominio(dominio, entrada)
            dados = publicar_modelagem(pasta, origem, entrada, ler_metadados_calculo(pasta), convencao.strip(),
                                      lambda: pasta_privada(request, inventario_id, calculo_id))
    except FileNotFoundError as erro:
        raise recurso_indisponivel() from erro
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro),
                            headers={"Cache-Control": "no-store"}) from erro
    response.headers["Cache-Control"] = "no-store"
    return dados


@app.get(ROTA_MODELAGEM)
def consultar_modelagem(inventario_id: str, calculo_id: str, origem: OrigemTemporal,
                       request: Request, response: Response):
    pasta = pasta_privada(request, inventario_id, calculo_id)
    try:
        caminho = resultado_atual(pasta, origem) / ARQUIVO_METADADOS
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError as erro:
        raise recurso_indisponivel() from erro
    response.headers["Cache-Control"] = "no-store"
    return dados


@app.get(ROTA_MODELAGEM + "/arquivos/{nome}")
def baixar_modelagem(inventario_id: str, calculo_id: str, origem: OrigemTemporal, request: Request,
                    nome: Literal["emissoes-grade.nc", "metadados-modelagem.json"]):
    pasta = pasta_privada(request, inventario_id, calculo_id)
    try:
        arquivo = resultado_atual(pasta, origem) / nome
    except FileNotFoundError as erro:
        raise recurso_indisponivel() from erro
    if not arquivo.is_file():
        raise recurso_indisponivel()
    tipo = "application/x-netcdf" if nome == ARQUIVO_NETCDF else "application/json"
    return FileResponse(arquivo, filename=nome, media_type=tipo,
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@app.delete("/api/inventarios/{inventario_id}")
def remover_inventario(
    inventario_id: str,
    request: Request
):

    token_sessao = request.cookies.get(
        "pega_session"
    )

    try:

        excluir_inventario(
            inventario_id,
            token_sessao
        )

        return {

            "mensagem": "Inventário excluído com sucesso."

        }

    except (PermissionError, FileNotFoundError):

        raise HTTPException(
            status_code=404,
            detail="Inventário indisponível."
        )


# ==================================================
# 10. INFORMACOES DA BASE CIENTIFICA
# ==================================================

@app.get("/api/fatores/info")
def consultar_base():

    return informacoes_base()


# ==================================================
# 11. LISTAR SETORES
# ==================================================

@app.get("/api/setores")
def consultar_setores():

    return {

        "setores": listar_setores()

    }


# ==================================================
# 12. LISTAR SETORES SUPORTADOS
# ==================================================

@app.get("/api/setores/suportados")
def consultar_setores_suportados():

    return {

        "setores": listar_setores_suportados()

    }


# ==================================================
# 13. LISTAR COMBUSTIVEIS
# ==================================================

@app.get("/api/setores/{setor}/combustiveis")
def consultar_combustiveis(setor: str):

    return {

        "setor": setor,

        "combustiveis": listar_combustiveis(setor)

    }


# ==================================================
# 14. CONSULTAR FATORES DE EMISSAO
# ==================================================

@app.get("/api/fatores")
def consultar_fatores(
    setor: str,
    combustivel: str
):

    try:

        fatores = obter_fatores(
            setor,
            combustivel
        )

        registros = converter_registros(
            fatores
        )

        return {

            "setor": setor,

            "combustivel": combustivel,

            "total_fatores": len(fatores),

            "fatores": registros

        }

    except ValueError as erro:

        raise HTTPException(
            status_code=400,
            detail=str(erro)
        )


# ==================================================
# 15. ANALISAR FATORES DE EMISSAO
# ==================================================

@app.get("/api/fatores/analise")
def consultar_analise_fatores(
    setor: str,
    combustivel: str
):

    try:

        resultado = analisar_fatores(
            setor,
            combustivel
        )

        return resultado

    except ValueError as erro:

        raise HTTPException(
            status_code=400,
            detail=str(erro)
        )



# ==================================================
# 16. EXECUTAR CALCULO PRIVADO
# ==================================================

@app.post("/api/inventarios/{inventario_id}/calcular")
def executar_calculo(
    inventario_id: str,
    solicitacao: SolicitacaoCalculo,
    request: Request,
    response: Response
):

    token_sessao = request.cookies.get(
        "pega_session"
    )

    # Verificar autorizacao

    try:

        pasta, _ = verificar_acesso(
            inventario_id,
            token_sessao
        )

    except (PermissionError, FileNotFoundError):

        raise HTTPException(
            status_code=404,
            detail="Inventário indisponível."
        )

    try:

        setor = solicitacao.setor.strip()

        ano = solicitacao.ano

        combustivel = solicitacao.combustivel.strip()

        selecoes = solicitacao.selecoes
        # Carregar dados privados

        dados = ler_csv_privado(pasta / "dados.csv")

        # Executar calculo cientifico

        resultado = calcular_emissoes(
            dados=dados,
            setor=setor,
            ano=ano,
            combustivel=combustivel,
            selecoes=selecoes
        )

        # Conferir novamente após o cálculo, antes de persistir os arquivos.
        verificar_acesso(inventario_id, token_sessao)

        # Identificar configuracao cientifica

        configuracao = {

            "setor": setor,

            "ano": ano,

            "combustivel": combustivel,

            "selecoes": selecoes,

            "fatores_utilizados": [
                fator["fator_id"]
                for fator in resultado["fatores_utilizados"]
            ]

        }

        configuracao_json = json.dumps(
            configuracao,
            sort_keys=True,
            ensure_ascii=False
        )

        configuracao_id = hashlib.sha256(
            configuracao_json.encode("utf-8")
        ).hexdigest()

        # Identificador exclusivo da execucao

        calculo_id = str(uuid4())

        # Organizar resultados privados

        pasta_calculos = pasta / "calculos"

        pasta_calculos.mkdir(
            exist_ok=True
        )

        pasta_calculo = pasta_calculos / calculo_id

        pasta_calculo.mkdir(
            exist_ok=False
        )

        try:

            # Salvar emissoes calculadas

            resultado["dados"].to_csv(
                pasta_calculo / "emissoes_base.csv",
                index=False,
                encoding="utf-8"
            )

            # Salvar resumo por poluente

            pd.DataFrame(
                resultado["resumo"]
            ).to_csv(
                pasta_calculo / "resumo.csv",
                index=False,
                encoding="utf-8"
            )

            # Salvar fatores cientificos utilizados

            pd.DataFrame(
                resultado["fatores_utilizados"]
            ).to_csv(
                pasta_calculo / "fatores_utilizados.csv",
                index=False,
                encoding="utf-8"
            )

            # Preparar metadados

            metadados = {

                "inventario_id": inventario_id,

                "calculo_id": calculo_id,

                "configuracao_id": configuracao_id,

                "status": "calculado",

                "setor": setor,

                "ano": ano,

                "combustivel": combustivel,

                "selecoes": selecoes,

                "total_registros":
                    int(resultado["total_registros"]),

                "total_atividades":
                    int(resultado["total_atividades"]),

                "total_fontes":
                    int(resultado["total_fontes"]),

                "total_poluentes":
                    int(resultado["total_poluentes"]),

                "consumo_total_GJ":
                    resultado["consumo_total_GJ"],

                "unidade_emissoes":
                    resultado["unidade_emissoes"],

                "resumo":
                    resultado["resumo"],

                "fatores_utilizados":
                    resultado["fatores_utilizados"],

                "avisos":
                    resultado["avisos"]

            }

            # Salvar metadados

            metadados_temporarios = pasta_calculo / "metadados.tmp"
            with metadados_temporarios.open(
                "w",
                encoding="utf-8"
            ) as arquivo:

                json.dump(
                    metadados,
                    arquivo,
                    ensure_ascii=False,
                    indent=4,
                    allow_nan=False
                )
            metadados_temporarios.replace(pasta_calculo / "metadados.json")

        except Exception:

            import shutil

            shutil.rmtree(
                pasta_calculo,
                ignore_errors=True
            )

            raise

        # Preparar previa

        previa = converter_registros(
            resultado["dados"].head(20)
        )

        response.headers["Cache-Control"] = "no-store"

        return {

            **metadados,

            "previa": previa

        }

    except (PermissionError, FileNotFoundError):
        raise HTTPException(status_code=404, detail="Inventário indisponível.")

    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro))

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Erro interno no cálculo das emissões."
        )
