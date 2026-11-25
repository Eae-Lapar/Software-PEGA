
import hashlib
import json

import pandas as pd
import numpy as np

from pathlib import Path
from functools import lru_cache


BASE_DIR = Path(__file__).resolve().parents[2]

ARQUIVO_FATORES = (
    BASE_DIR / "data" / "fatores_emissao.csv"
)

VERSAO_PEGA_R = "0.9.8"

TIPO_FATOR = "Tier 1 Emission Factor"

SETORES_SUPORTADOS = ["1.A.1.a"]


# ==================================================
# 1. CARREGAR BASE CIENTIFICA
# ==================================================

@lru_cache(maxsize=1)
def carregar_fatores():

    if not ARQUIVO_FATORES.is_file():

        raise FileNotFoundError(
            "Base de fatores de emissão não encontrada."
        )

    db = pd.read_csv(
        ARQUIVO_FATORES,
        dtype=str,
        keep_default_na=False
    )

    colunas_obrigatorias = [
        "code",
        "fuel",
        "type",
        "region",
        "ef",
        "unit",
        "pol",
        "source",
        "reference",
        "tech",
        "tech2",
        "other",
        "Value",
        "Unit"
    ]

    faltantes = [
        coluna
        for coluna in colunas_obrigatorias
        if coluna not in db.columns
    ]

    if faltantes:

        raise ValueError(
            f"Colunas ausentes na base: {faltantes}"
        )

    # Eliminar somente registros integralmente iguais

    db = db.drop_duplicates().reset_index(drop=True)

    # Criar identificador estável para cada fator

    def gerar_id(registro):

        conteudo = json.dumps(
            registro.to_dict(),
            sort_keys=True,
            ensure_ascii=False
        )

        return hashlib.sha256(
            conteudo.encode("utf-8")
        ).hexdigest()

    db["fator_id"] = db.apply(
        gerar_id,
        axis=1
    )

    db["ef"] = pd.to_numeric(
        db["ef"],
        errors="coerce"
    )

    return db


# ==================================================
# 2. SELECIONAR FATORES TIER 1
# ==================================================

def fatores_tier1():

    db = carregar_fatores()

    filtro = (
        (db["type"] == TIPO_FATOR)
        & (db["region"] == "")
        & (db["code"] != "")
    )

    return db.loc[filtro].copy()


# ==================================================
# 3. LISTAR SETORES
# ==================================================

def listar_setores():

    db = fatores_tier1()

    return sorted(
        db["code"].unique().tolist()
    )


def listar_setores_suportados():

    return [
        setor
        for setor in listar_setores()
        if setor in SETORES_SUPORTADOS
    ]


# ==================================================
# 4. LISTAR COMBUSTIVEIS
# ==================================================

def listar_combustiveis(setor):

    db = fatores_tier1()

    filtro = (
        (db["code"] == setor)
        & (db["fuel"] != "")
    )

    return sorted(
        db.loc[filtro, "fuel"].unique().tolist()
    )


# ==================================================
# 5. OBTER FATORES
# ==================================================

def obter_fatores(setor, combustivel):

    db = fatores_tier1()

    filtro = (
        (db["code"] == setor)
        & (db["fuel"] == combustivel)
    )

    fatores = db.loc[filtro].copy()

    if fatores.empty:

        raise ValueError(
            "Nenhum fator de emissão Tier 1 "
            f"encontrado para {setor} "
            f"e {combustivel}."
        )

    return fatores


# ==================================================
# 6. CONVERTER REGISTROS PARA JSON
# ==================================================

def converter_registros(dados):

    dados = dados.replace(
        [np.inf, -np.inf],
        np.nan
    )

    dados = dados.astype(object).where(
        pd.notna(dados),
        None
    )

    return dados.to_dict(
        orient="records"
    )


# ==================================================
# 7. VALIDAR FATOR INDIVIDUAL
# ==================================================

def motivo_indisponibilidade(fator):

    ef = fator["ef"]

    unidade = fator["unit"]

    poluente = fator["pol"]

    if not poluente.strip():

        return "Poluente não identificado."

    if pd.isna(ef) or not np.isfinite(ef):

        return "Fator de emissão indisponível."

    if ef < 0:

        return "Fator de emissão negativo."

    if poluente == "BC":

        if unidade != "fraction of PM2.5":

            return "Unidade de BC incompatível."

        if not 0 <= ef <= 1:

            return "Fração de BC inválida."

    elif unidade != "g/GJ":

        return "Unidade de emissão incompatível."

    return None


# ==================================================
# 8. ANALISAR FATORES DISPONIVEIS
# ==================================================

def analisar_fatores(setor, combustivel):

    if setor not in SETORES_SUPORTADOS:

        raise ValueError(
            "Setor ainda não suportado pelo "
            "módulo de cálculo."
        )

    fatores = obter_fatores(
        setor,
        combustivel
    )

    automaticos = []

    escolhas = []

    indisponiveis = []

    for poluente, grupo in fatores.groupby(
        "pol",
        sort=True
    ):

        validos = []

        for _, fator in grupo.iterrows():

            registro = converter_registros(
                fator.to_frame().T
            )[0]

            motivo = motivo_indisponibilidade(
                fator
            )

            if motivo:

                registro["motivo"] = motivo

                indisponiveis.append(registro)

            else:

                validos.append(registro)

        if len(validos) == 1:

            automaticos.append(validos[0])

        elif len(validos) > 1:

            escolhas.append({

                "poluente": poluente,

                "opcoes": validos

            })

    return {

        "setor": setor,

        "combustivel": combustivel,

        "versao_pega_r": VERSAO_PEGA_R,

        "total_fatores": len(fatores),

        "total_automaticos": len(automaticos),

        "total_escolhas": len(escolhas),

        "total_indisponiveis": len(indisponiveis),

        "automaticos": automaticos,

        "escolhas": escolhas,

        "indisponiveis": indisponiveis,

        "requer_escolha": len(escolhas) > 0

    }


# ==================================================
# 9. RESOLVER ESCOLHAS DO PESQUISADOR
# ==================================================

def resolver_fatores(
    setor,
    combustivel,
    selecoes=None
):

    selecoes = selecoes or {}

    analise = analisar_fatores(
        setor,
        combustivel
    )

    selecionados = list(
        analise["automaticos"]
    )

    avisos = []

    poluentes_com_escolha = {
        grupo["poluente"]
        for grupo in analise["escolhas"]
    }

    selecoes_extras = (
        set(selecoes) - poluentes_com_escolha
    )

    if selecoes_extras:

        raise ValueError(
            "Seleções não reconhecidas: "
            + ", ".join(sorted(selecoes_extras))
        )

    for grupo in analise["escolhas"]:

        poluente = grupo["poluente"]

        fator_id = selecoes.get(poluente)

        if not fator_id:

            raise ValueError(
                "É necessário selecionar um "
                f"fator para {poluente}."
            )

        escolhido = next(
            (
                fator
                for fator in grupo["opcoes"]
                if fator["fator_id"] == fator_id
            ),
            None
        )

        if escolhido is None:

            raise ValueError(
                f"Fator inválido para {poluente}."
            )

        selecionados.append(escolhido)

    for fator in analise["indisponiveis"]:

        avisos.append({

            "poluente": fator["pol"],

            "combustivel": combustivel,

            "motivo": fator["motivo"],

            "reference": fator["reference"],

            "fator_id": fator["fator_id"]

        })

    if not selecionados:

        raise ValueError(
            "Nenhum fator válido disponível."
        )

    resultado = pd.DataFrame(selecionados)

    poluentes = set(resultado["pol"])

    if "BC" in poluentes and "PM2.5" not in poluentes:

        raise ValueError(
            "O cálculo de BC exige um fator "
            "válido de PM2.5."
        )

    return resultado, avisos


# ==================================================
# 10. INFORMACOES DA BASE
# ==================================================

def informacoes_base():

    db = carregar_fatores()

    tier1 = fatores_tier1()

    return {

        "versao_pega_r": VERSAO_PEGA_R,

        "total_registros": len(db),

        "total_colunas": len(db.columns) - 1,

        "total_fatores_tier1": len(tier1),

        "total_setores": len(listar_setores()),

        "setores_suportados":
            listar_setores_suportados(),

        "colunas": [
            coluna
            for coluna in db.columns
            if coluna != "fator_id"
        ]

    }
