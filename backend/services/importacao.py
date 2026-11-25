
import re
import unicodedata
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl.utils.exceptions import InvalidFileException


ANO_MINIMO = 1900
ANO_MAXIMO = 9999


# Colunas obrigatórias
PEGA_COLUNAS = [
    "ID",
    "Fuel_type",
    "Granted_power_MW",
    "latitude",
    "longitude",
    "year",
    "Fuel_consumed_plant_GJ"
]


# Nomes alternativos das colunas
PEGA_ALIASES = {
    "ID": [
        "id", "identificador", "id_fonte",
        "id_usina", "plant_id"
    ],

    "Fuel_type": [
        "fuel_type", "tipo_combustivel",
        "combustivel", "fuel"
    ],

    "Granted_power_MW": [
        "granted_power_mw", "potencia_mw",
        "potencia_autorizada_mw", "power_mw"
    ],

    "latitude": [
        "latitude", "lat"
    ],

    "longitude": [
        "longitude", "lon", "long", "lng"
    ],

    "year": [
        "year", "ano", "ano_referencia"
    ],

    "Fuel_consumed_plant_GJ": [
        "fuel_consumed_plant_gj", "consumo_gj",
        "consumo_combustivel_gj", "fuel_consumed_gj"
    ]
}


# Normalização dos nomes
def pega_normalizar_nome(nome):

    nome = str(nome).strip()

    nome = unicodedata.normalize("NFKD", nome)

    nome = nome.encode(
        "ascii", "ignore"
    ).decode("ascii")

    nome = nome.lower()

    nome = re.sub(r"[^a-z0-9]+", "_", nome)

    return nome.strip("_")


# Leitura de arquivos
def pega_ler_arquivo(
    caminho,
    nome_original=None,
    aba=0
):

    caminho = Path(caminho)

    if not caminho.is_file():
        raise ValueError(
            "Arquivo enviado não encontrado."
        )

    nome_original = nome_original or caminho.name

    extensao = Path(nome_original).suffix.lower()

    if extensao == ".xlsx":

        try:
            tabela = pd.read_excel(
                caminho,
                sheet_name=aba,
                header=None,
                dtype=str,
                keep_default_na=False,
                engine="openpyxl"
            )
        except (BadZipFile, InvalidFileException, KeyError, ParseError, ValueError) as erro:
            raise ValueError("Não foi possível ler a planilha XLSX.") from erro

    elif extensao in [".csv", ".txt"]:

        tabela = pd.read_csv(
            caminho,
            sep=None,
            engine="python",
            header=None,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig"
        )

    else:

        raise ValueError(
            "Formato não suportado. "
            "Envie CSV, TXT ou XLSX."
        )

    if tabela.empty:
        raise ValueError(
            "A planilha não possui dados."
        )

    cabecalhos = tabela.iloc[0].tolist()

    if any(
        pd.isna(nome) or not str(nome).strip()
        for nome in cabecalhos
    ):
        raise ValueError(
            "A planilha contém cabeçalhos vazios."
        )

    dados = tabela.iloc[1:].copy()

    dados.columns = [
        str(nome) for nome in cabecalhos
    ]

    dados = dados.reset_index(drop=True)

    if dados.empty:
        raise ValueError(
            "A planilha não possui linhas de dados."
        )

    return dados


# Identificação das colunas obrigatórias
def pega_mapear_colunas(nomes):

    nomes = list(nomes)

    normalizados = [
        pega_normalizar_nome(nome)
        for nome in nomes
    ]

    if len(normalizados) != len(set(normalizados)):
        raise ValueError(
            "Existem cabeçalhos repetidos "
            "após a normalização."
        )

    mapa = {}

    for campo in PEGA_COLUNAS:

        candidatos = {
            pega_normalizar_nome(nome)
            for nome in [
                campo,
                *PEGA_ALIASES[campo]
            ]
        }

        encontrados = [
            original
            for original, normalizado
            in zip(nomes, normalizados)
            if normalizado in candidatos
        ]

        if len(encontrados) > 1:

            raise ValueError(
                f"Mais de uma coluna corresponde "
                f"a '{campo}': {encontrados}"
            )

        if len(encontrados) == 1:

            mapa[campo] = encontrados[0]

    faltantes = [
        campo for campo in PEGA_COLUNAS
        if campo not in mapa
    ]

    if faltantes:

        raise ValueError(
            "Colunas obrigatórias não identificadas: "
            + ", ".join(faltantes)
        )

    if len(set(mapa.values())) != len(mapa):

        raise ValueError(
            "Uma coluna foi associada "
            "a mais de um campo."
        )

    return mapa


# Identificação das linhas com problemas
def pega_linhas(mascara):

    indices = np.flatnonzero(
        mascara.to_numpy(dtype=bool)
    )

    return ", ".join(
        str(indice + 2)
        for indice in indices[:8]
    )


# Validação dos dados
def pega_validar_dados(dados):

    problemas = []

    # Verificação de campos vazios
    for campo in PEGA_COLUNAS:

        valores = dados[campo].astype("string")

        vazios = (
            valores.isna()
            | valores.str.strip().eq("")
        ).fillna(True)

        if vazios.any():

            problemas.append(
                f"{campo}: {int(vazios.sum())} "
                f"valor(es) ausente(s). "
                f"Linhas: {pega_linhas(vazios)}."
            )

    campos_numericos = [
        "Granted_power_MW",
        "latitude",
        "longitude",
        "Fuel_consumed_plant_GJ"
    ]

    # Validação dos valores numéricos
    for campo in campos_numericos:

        valores = dados[campo].astype("string")

        preenchidos = (
            valores.notna()
            & valores.str.strip().ne("")
        ).fillna(False)

        numeros = pd.to_numeric(
            valores.str.strip(),
            errors="coerce"
        ).astype(float)

        finitos = pd.Series(
            np.isfinite(numeros),
            index=dados.index
        )

        invalidos = preenchidos & ~finitos

        if invalidos.any():

            problemas.append(
                f"{campo}: valor numérico inválido. "
                f"Linhas: {pega_linhas(invalidos)}. "
                "Utilize ponto decimal."
            )

        if campo == "latitude":

            fora = (numeros < -90) | (numeros > 90)

        elif campo == "longitude":

            fora = (numeros < -180) | (numeros > 180)

        else:

            fora = numeros < 0

        fora = fora & finitos

        if fora.any():

            problemas.append(
                f"{campo}: valor fora do intervalo "
                f"esperado. Linhas: {pega_linhas(fora)}."
            )

    # Validação dos anos
    anos = dados["year"].astype("string").str.strip()

    preenchidos = (
        anos.notna() & anos.ne("")
    ).fillna(False)

    anos_validos = anos.str.fullmatch(
        r"[0-9]{4}",
        na=False
    ) & anos.between(str(ANO_MINIMO), str(ANO_MAXIMO)).fillna(False)

    anos_invalidos = preenchidos & ~anos_validos

    if anos_invalidos.any():

        problemas.append(
            f"year: informe um ano entre {ANO_MINIMO} e {ANO_MAXIMO}. "
            f"Linhas: {pega_linhas(anos_invalidos)}."
        )

    combustiveis = (
        dados["Fuel_type"]
        .dropna()
        .astype(str)
        .str.strip()
    )

    combustiveis = combustiveis[
        combustiveis.ne("")
    ]

    return {
        "valido": len(problemas) == 0,

        "problemas": problemas,

        "anos": sorted(
            anos[anos_validos].unique().tolist()
        ),

        "combustiveis": sorted(
            combustiveis.unique().tolist()
        )
    }


# Função principal de importação
def pega_importar(
    caminho,
    nome_original=None,
    aba=0
):

    original = pega_ler_arquivo(
        caminho,
        nome_original,
        aba
    )

    mapa = pega_mapear_colunas(
        original.columns
    )

    padronizado = original[
        list(mapa.values())
    ].copy()

    padronizado.columns = list(mapa.keys())

    validacao = pega_validar_dados(
        padronizado
    )

    colunas_extras = [
        coluna
        for coluna in original.columns
        if coluna not in mapa.values()
    ]

    return {
        "original": original,
        "dados": padronizado,
        "mapa_colunas": mapa,
        "validacao": validacao,
        "colunas_extras": colunas_extras,
        "nome_arquivo": (
            nome_original or Path(caminho).name
        )
    }
