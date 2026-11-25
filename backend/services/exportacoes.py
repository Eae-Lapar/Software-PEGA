"""Catálogo e geração limitada de artefatos privados de uma execução."""

import csv
import io
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import chain
from math import fsum
from pathlib import Path
from time import monotonic
from zipfile import ZIP_DEFLATED, ZipFile
from netCDF4 import Dataset

from backend.services import relatorios, visualizacoes
from backend.services.armazenamento import ler_metadados_calculo
from backend.services.especiacao import PASTA_ESPECIACAO
from backend.services.espacial import carregar_resultado, pasta_espacial
from backend.services.mapas import gerar_mapa
from backend.services.modelagem import ARQUIVO_METADADOS, ARQUIVO_NETCDF, resultado_atual
from backend.services.temporal import caminho_temporal, origem_csv, transmitir_alocacao
from backend.services.territorio import catalogo, indexar
from backend.services.wrf import NETCDF_LOCK

LIMITE_BYTES = 256 * 1024 ** 2
LIMITE_ARQUIVOS = 64
LIMITE_SEGUNDOS = 120
BLOCO = 256 * 1024
ORIGENS = ("original", "especiada")
FORMATOS_FIGURA = (("png", 300, "-300dpi"), ("png", 600, "-600dpi"), ("pdf", 150, ""), ("svg", 150, ""))
TIPOS = {
    "csv": "text/csv", "json": "application/json", "geojson": "application/geo+json",
    "nc": "application/x-netcdf", "pdf": "application/pdf", "png": "image/png", "svg": "image/svg+xml",
}


class LimiteExportacao(ValueError):
    pass


@dataclass(frozen=True)
class Item:
    categoria: str
    nome: str
    titulo: str
    descricao: str
    caminho: Path | None = None
    gerador: tuple = ()

    @property
    def id(self):
        return f"{self.categoria}/{self.nome}"

    @property
    def formato(self):
        return self.nome.rsplit(".", 1)[-1]

    def publico(self):
        return dict(id=self.id, categoria=self.categoria, nome=self.nome, titulo=self.titulo,
                    descricao=self.descricao, formato=self.formato,
                    bytes=self.caminho.stat().st_size if self.caminho else None,
                    sob_demanda=self.caminho is None)


def listar(pasta):
    itens = {}

    def adicionar(categoria, nome, titulo, descricao, caminho=None, gerador=()):
        if caminho is None or caminho.is_file():
            item = Item(categoria, nome, titulo, descricao, caminho, gerador)
            itens[item.id] = item

    adicionar("inventario", "dados.csv", "Dados padronizados", "Planilha padronizada da importação.", pasta.parent.parent / "dados.csv")
    for nome, titulo, descricao in (
        ("emissoes_base.csv", "Emissões calculadas", "Massa por atividade, fonte e poluente."),
        ("resumo.csv", "Resumo", "Totais em gramas por poluente."),
        ("fatores_utilizados.csv", "Fatores utilizados", "Fatores, unidades e referências."),
        ("metadados.json", "Metadados da execução", "Seleções, totais e avisos da execução."),
    ):
        adicionar("inventario", nome, titulo, descricao, pasta / nome)
    for nome, titulo, descricao in (
        ("emissoes_especiadas.csv", "Emissões especiadas", "Massa por espécie e origem."),
        ("resumo_especies.csv", "Resumo por espécie", "Totais com origem química explícita."),
        ("perfil_especiacao.csv", "Perfil químico", "Frações, massas moleculares quando disponíveis e referência."),
        ("metadados_especiacao.json", "Balanço da especiação", "Massas originais, derivadas e residuais, com avisos."),
    ):
        adicionar("especiacao", nome, titulo, descricao, pasta / PASTA_ESPECIACAO / nome)

    for origem in ORIGENS:
        perfil = caminho_temporal(pasta, origem)
        if perfil.is_file():
            adicionar("temporal", f"perfil-{origem}.json", f"Perfis e resumos · {origem}",
                      "Pesos de 24, 7 e 168 intervalos, referência e massas-base.", perfil)
            adicionar("temporal", f"alocacao-{origem}.csv", f"Alocação relativa · {origem}",
                      "Massa por fonte nos 168 intervalos sem calendário.", gerador=("temporal", origem))
        try:
            dados = carregar_resultado(pasta, origem)
        except FileNotFoundError:
            dados = None
        if dados:
            local = pasta_espacial(pasta, origem) / dados["configuracao_espacial"]
            for nome, titulo, descricao in (
                ("fontes.csv", "Emissões por fonte", "Massas, coordenadas e situação espacial."),
                ("celulas.csv", "Emissões por célula", "Massas em células da grade GeoJSON."),
                ("grade.geojson", "Grade utilizada", "Geometria de células do domínio informado."),
                ("metadados.json", "Balanço espacial", "Massas mapeadas, fora da grade e casos ambíguos."),
            ):
                adicionar("espacial", f"{origem}-{nome}", f"{titulo} · {origem}", descricao, local / nome)
            for nivel, nome in (("uf", "UF"), ("regiao", "região")):
                adicionar("espacial", f"{origem}-{nivel}.csv", f"Emissões por {nome} · {origem}",
                          "Massas por série e território, inclusive casos sem atribuição.",
                          gerador=("territorio", local, dados, nivel))
            serie = next((s for s in dados["series"] if s["pol"] == "PM2.5"), dados["series"][0])
            for formato, dpi, sufixo in FORMATOS_FIGURA:
                titulo = f"Mapa nacional · {origem} · {serie['pol']}" + (f" · {dpi} DPI" if sufixo else "")
                adicionar("figuras", f"mapa-{origem}{sufixo}.{formato}", titulo,
                          "Fontes no IBGE 2025 em gramas.",
                          gerador=("mapa", local, dados, serie, formato, dpi))
        try:
            modelo = resultado_atual(pasta, origem)
        except FileNotFoundError:
            continue
        adicionar("modelagem", f"{origem}-{ARQUIVO_NETCDF}", f"Inventário em grade · {origem}",
                  "NetCDF intermediário com massa em células e projeção anual quando disponível.",
                  modelo / ARQUIVO_NETCDF)
        adicionar("modelagem", f"{origem}-{ARQUIVO_METADADOS}", f"Metadados NetCDF · {origem}",
                  "Grade, calendário e balanços de massa por série.", modelo / ARQUIVO_METADADOS)
        dados_modelo = visualizacoes.metadados_modelagem(modelo)
        if dados_modelo["calendario"]:
            adicionar("temporal", f"projecao-anual-{origem}.csv", f"Projeção anual · {origem}",
                      "Massas horárias por série no domínio WRF, no relógio do perfil.",
                      gerador=("anual", modelo, dados_modelo, False))
            adicionar("temporal", f"resumo-mensal-{origem}.csv", f"Resumo mensal · {origem}",
                      "Massas acumuladas por mês e série no domínio WRF.",
                      gerador=("anual", modelo, dados_modelo, True))

    for formato, dpi, sufixo in FORMATOS_FIGURA:
        adicionar("figuras", f"totais{sufixo}.{formato}", f"Totais por poluente{(' · ' + str(dpi) + ' DPI') if sufixo else ''}",
                  "Gráfico nacional da base original em gramas.", gerador=("figura", formato, dpi))
    adicionar("relatorios", "relatorio-cientifico.pdf", "Relatório científico",
              "Documento em português com resultados, fatores e etapas executadas.", gerador=("relatorio", "completo"))
    adicionar("relatorios", "resumo-executivo.pdf", "Resumo executivo",
              "Identificação, metodologia, totais e alertas.", gerador=("relatorio", "resumido"))
    return itens


def blocos(item, pasta, temporario, op_relatorio, escrever_relatorio, conferir):
    if item.caminho:
        arquivo = item.caminho
    elif item.gerador[0] == "temporal":
        origem = item.gerador[1]
        with origem_csv(pasta, origem).open(encoding="utf-8", newline="") as entrada:
            for bloco in transmitir_alocacao(entrada, ler_metadados_calculo(pasta), origem):
                yield bloco.encode("utf-8")
        return
    elif item.gerador[0] == "anual":
        _, modelo, dados, mensal = item.gerador
        with NETCDF_LOCK, Dataset(modelo / ARQUIVO_NETCDF) as nc:
            pesos = nc["hour_fraction"][:].tolist()
        calendario = dados["calendario"]
        inicio = datetime(dados["ano"], 1, 1)
        buffer = io.StringIO()
        escritor = csv.writer(buffer)
        escritor.writerow(["calculo_id", "base", "dominio_sha256", "pol_origem", "pol", "inicio_intervalo",
                            "relogio_perfil", "fracao", "massa_g"])
        if mensal:
            inicio_mes = [(inicio.replace(month=m) - inicio).days * 24 for m in range(1, 13)]
            fim_mes = [*inicio_mes[1:], len(pesos)]
            periodos = ((inicio.replace(month=mes).isoformat(timespec="minutes"), fsum(pesos[a:b]))
                        for mes, (a, b) in enumerate(zip(inicio_mes, fim_mes), 1))
        else:
            periodos = (((inicio + timedelta(hours=hora)).isoformat(timespec="minutes"), peso)
                        for hora, peso in enumerate(pesos))
        for instante, peso in periodos:
            for serie in dados["series"]:
                escritor.writerow([dados["calculo_id"], dados["origem"], dados["dominio_sha256"], serie["pol_origem"],
                                    serie["pol"], instante, calendario["convencao"], peso, serie["massa_grade_g"] * peso])
            if buffer.tell() >= BLOCO:
                yield buffer.getvalue().encode("utf-8")
                buffer.seek(0)
                buffer.truncate()
        if buffer.tell():
            yield buffer.getvalue().encode("utf-8")
        return
    elif item.gerador[0] == "territorio":
        _, local, dados, nivel = item.gerador
        nomes = catalogo()[nivel]
        buffer = io.StringIO()
        escritor = csv.writer(buffer)
        escritor.writerow(["calculo_id", "ano", "setor", "combustivel", "base",
                            "pol_origem", "pol", "codigo", "territorio", "situacao", "massa_g"])
        with closing(sqlite3.connect(indexar(local, dados))) as conn:
            linhas = conn.execute(f"""SELECT serie, {nivel}, situacao, SUM(massa)
                                  FROM fontes GROUP BY serie, {nivel}, situacao
                                  ORDER BY serie, {nivel}, situacao""")
            for serie, codigo, situacao, massa in linhas:
                pol = dados["series"][serie]
                escritor.writerow([*(dados[k] for k in ("calculo_id", "ano", "setor", "combustivel", "origem")),
                                    pol["pol_origem"], pol["pol"], codigo, nomes.get(codigo), situacao, massa])
        yield buffer.getvalue().encode("utf-8")
        return
    elif item.gerador[0] == "mapa":
        _, local, dados, serie, formato, dpi = item.gerador
        arquivo = gerar_mapa(local, dados, serie,
                            ("g", "viridis", "linear", "pt", "pontos", "cor", "brasil", "", "nacional"),
                            formato, dpi, conferir)
    elif item.gerador[0] == "figura":
        _, formato, dpi = item.gerador
        filtros = dict(tipo="totais", origem="original", pol="", pol_origem="", unidade="g", nivel="brasil",
                       codigo="", inicio="", fim="", comparar_inicio="", comparar_fim="", idioma="pt",
                       escala="linear", paleta="viridis", ordem="maior", top=10, cor="#26827f")
        arquivo = visualizacoes.gerar(pasta, filtros, formato, dpi, conferir)
    else:
        arquivo = temporario / item.nome
        escrever_relatorio(arquivo, op_relatorio.model_copy(update={"modo": item.gerador[1]}))
    with arquivo.open("rb") as entrada:
        while bloco := entrada.read(BLOCO):
            yield bloco


def grupo_figura(item):
    if item.categoria == "figuras":
        return item.nome.rsplit(".", 1)[0].removesuffix("-300dpi").removesuffix("-600dpi")
    return None


def selecao(itens, ids, variantes=None):
    if ids is None:
        variantes = variantes or {}
        for grupo, chave in variantes.items():
            if chave not in itens or grupo_figura(itens[chave]) != grupo:
                raise ValueError("Variante de figura indisponível para esta execução.")
        escolhidos = [item for item in itens.values() if not grupo_figura(item) or item.id ==
                      variantes.get(grupo_figura(item), f"figuras/{grupo_figura(item)}-300dpi.png")]
    else:
        chaves = list(dict.fromkeys(ids))
        if not chaves:
            raise ValueError("Selecione pelo menos um arquivo desta execução.")
        ausentes = [chave for chave in chaves if chave not in itens]
        if ausentes:
            raise ValueError(f"Arquivos indisponíveis na execução selecionada: {', '.join(ausentes)}. Atualize a seleção.")
        escolhidos = [itens[chave] for chave in chaves]
    if len(escolhidos) > LIMITE_ARQUIVOS:
        raise LimiteExportacao("O ZIP aceita até 64 arquivos. Selecione menos arquivos.")
    if sum(
        item.caminho.stat().st_size for item in escolhidos if item.caminho and item.caminho.is_file()
    ) > LIMITE_BYTES:
        raise LimiteExportacao("Os arquivos disponíveis em disco já excedem 256 MiB descompactados. Selecione menos arquivos.")
    return escolhidos


def escrever_zip(destino, itens, obter_blocos, metadados, conferir, progresso):
    inicio = monotonic()
    total = 0
    incluidos, omitidos = [], []
    with ZipFile(destino, "w", ZIP_DEFLATED, compresslevel=3) as zip_file:
        for indice, item in enumerate(itens):
            conferir()
            progresso(indice, item.titulo)
            with closing(obter_blocos(item)) as conteudo:
                try:
                    primeiro = next(conteudo, b"")
                except FileNotFoundError as erro:
                    conferir()
                    motivo = "Arquivo de origem ou dependência da geração indisponível."
                    if item.categoria == "inventario":
                        raise ValueError(f"{item.titulo}: {motivo}") from erro
                    omitidos.append({"id": item.id, "titulo": item.titulo, "motivo": motivo})
                    continue
                with zip_file.open(item.id, "w") as arquivo:
                    for bloco in chain((primeiro,), conteudo):
                        total += len(bloco)
                        if total > LIMITE_BYTES:
                            raise LimiteExportacao(f"O ZIP excedeu 256 MiB descompactados ao incluir {item.nome}. Selecione menos arquivos.")
                        if monotonic() - inicio > LIMITE_SEGUNDOS:
                            raise LimiteExportacao(f"O ZIP atingiu 120 segundos de processamento ao incluir {item.nome}. Selecione menos arquivos.")
                        arquivo.write(bloco)
            incluidos.append(item.id)
        conferir()
        if not incluidos:
            raise ValueError("Nenhum arquivo selecionado pôde ser incluído. " +
                             " ".join(f"{item['titulo']}: {item['motivo']}" for item in omitidos))
        zip_file.writestr("manifesto.json", json.dumps(
            {**metadados, "gerado_em": datetime.now(timezone.utc).isoformat(),
             "arquivos": incluidos, "omitidos": omitidos,
             "figuras": [{"id": item.id, "formato": item.formato,
                          **({"dpi": item.gerador[-1]} if item.formato == "png" else {})}
                         for item in itens if item.id in incluidos and grupo_figura(item)]},
            ensure_ascii=False, indent=2))
    return incluidos, omitidos
