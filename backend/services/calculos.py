
import numpy as np
import pandas as pd

from backend.services.fatores_emissao import (
    resolver_fatores,
    converter_registros,
    SETORES_SUPORTADOS
)
from backend.services.importacao import PEGA_COLUNAS


# ==================================================
# 1. VALIDAR COLUNAS OBRIGATORIAS
# ==================================================

COLUNAS_OBRIGATORIAS = PEGA_COLUNAS
# ==================================================
# MAPEAMENTO DE COMBUSTIVEIS
# ==================================================

MAPEAMENTO_COMBUSTIVEIS = {
    "biomass_thermal": "Biomass"
}


def normalizar_combustivel(valor):

    valor = str(valor).strip()

    return MAPEAMENTO_COMBUSTIVEIS.get(
        valor.casefold(),
        valor
    )

def validar_colunas(dados):

    faltantes = [
        coluna
        for coluna in COLUNAS_OBRIGATORIAS
        if coluna not in dados.columns
    ]

    if faltantes:

        raise ValueError(
            "Colunas obrigatórias ausentes: "
            + ", ".join(faltantes)
        )


# ==================================================
# 2. PREPARAR DADOS DE ATIVIDADE
# ==================================================

def preparar_atividade(
    dados,
    setor,
    ano,
    combustivel
):

    validar_colunas(dados)

    dados = dados.copy()

    dados["year"] = pd.to_numeric(
        dados["year"],
        errors="coerce"
    )

    dados["Fuel_type"] = (
        dados["Fuel_type"]
        .apply(normalizar_combustivel)
    )

    # Filtrar ano e combustivel

    filtro = (
        (dados["year"] == ano)
        &
        (
            dados["Fuel_type"].str.casefold()
            == combustivel.strip().casefold()
        )
    )

    dados = dados.loc[filtro].copy()

    if dados.empty:

        raise ValueError(
            f"Nenhum registro encontrado para "
            f"{combustivel} no ano {ano}."
        )

    # Converter colunas numericas

    colunas_numericas = [
        "Granted_power_MW",
        "latitude",
        "longitude",
        "Fuel_consumed_plant_GJ"
    ]

    for coluna in colunas_numericas:

        dados[coluna] = pd.to_numeric(
            dados[coluna],
            errors="coerce"
        )

        if not np.isfinite(dados[coluna]).all():

            raise ValueError(
                f"Valores inválidos na coluna {coluna}."
            )

    # Validar identificadores

    if (
        dados["ID"].isna().any()
        or dados["ID"].astype(str).str.strip().eq("").any()
    ):

        raise ValueError(
            "Existem fontes sem identificador."
        )

    # Validar coordenadas

    if not dados["latitude"].between(-90, 90).all():

        raise ValueError(
            "Existem latitudes inválidas."
        )

    if not dados["longitude"].between(-180, 180).all():

        raise ValueError(
            "Existem longitudes inválidas."
        )

    # Validar potencia

    if (dados["Granted_power_MW"] < 0).any():

        raise ValueError(
            "Existem valores negativos de potência."
        )

    # Validar consumo

    if (dados["Fuel_consumed_plant_GJ"] < 0).any():

        raise ValueError(
            "Existem valores negativos de consumo."
        )

    total_consumo_zero = int(
        (dados["Fuel_consumed_plant_GJ"] == 0).sum()
    )

    # Manter somente atividades com consumo positivo

    dados = dados[
        dados["Fuel_consumed_plant_GJ"] > 0
    ].copy()

    if dados.empty:

        raise ValueError(
            "Nenhuma atividade possui consumo positivo."
        )

    dados = dados.reset_index(drop=True)

    # Criar identificador interno por registro

    atividade = pd.DataFrame({

        "registro_id": np.arange(len(dados)),

        "id": dados["ID"].astype(str),

        "lat": dados["latitude"],

        "lon": dados["longitude"],

        "alt": 20,

        "code": setor,

        "activity": dados["Fuel_consumed_plant_GJ"],

        "unit_activity": "GJ",

        "date_activity": f"{ano}-01-01",

        "region": "UF"

    })

    return atividade, total_consumo_zero


# ==================================================
# 3. CALCULAR EMISSOES
# ==================================================

def calcular_emissoes(
    dados,
    setor,
    ano,
    combustivel,
    selecoes=None
):

    if setor not in SETORES_SUPORTADOS:

        raise ValueError(
            "Setor ainda não suportado pelo "
            "módulo de cálculo."
        )

    # Resolver fatores cientificos

    fatores, avisos = resolver_fatores(
        setor,
        combustivel,
        selecoes
    )

    # Garantir um fator por poluente

    if fatores["pol"].duplicated().any():

        raise ValueError(
            "Existem múltiplos fatores selecionados "
            "para o mesmo poluente."
        )

    # Preparar atividades

    atividade, total_consumo_zero = preparar_atividade(
        dados,
        setor,
        ano,
        combustivel
    )

    if total_consumo_zero > 0:

        avisos.append({

            "tipo": "consumo_zero",

            "quantidade": total_consumo_zero,

            "motivo": (
                "Registros com consumo igual a zero "
                "não foram incluídos no cálculo."
            )

        })

    # Preservar referencias cientificas

    fatores_calculo = fatores[[
        "fator_id",
        "fuel",
        "pol",
        "ef",
        "unit",
        "Value",
        "Unit",
        "source",
        "reference",
        "tech",
        "tech2",
        "other"
    ]].copy()

    # Cruzar atividades com fatores de emissao

    dt = atividade.merge(
        fatores_calculo,
        how="cross"
    )

    # Inicializar emissoes

    dt["emissions"] = np.nan

    dt["unit_emissions"] = "g"

    # ==================================================
    # 4. EMISSOES CONVENCIONAIS
    # ==================================================

    filtro_convencional = (
        dt["pol"] != "BC"
    )

    if not (
        dt.loc[filtro_convencional, "unit"] == "g/GJ"
    ).all():

        raise ValueError(
            "Existem fatores com unidades incompatíveis."
        )

    dt.loc[
        filtro_convencional,
        "emissions"
    ] = (

        dt.loc[
            filtro_convencional,
            "ef"
        ]

        *

        dt.loc[
            filtro_convencional,
            "activity"
        ]

    )

    # ==================================================
    # 5. CARBONO NEGRO - BC
    # ==================================================

    filtro_bc = (
        dt["pol"] == "BC"
    )

    if filtro_bc.any():

        if not (
            dt.loc[filtro_bc, "unit"]
            == "fraction of PM2.5"
        ).all():

            raise ValueError(
                "Unidade incompatível para BC."
            )

        # Obter PM2.5 de cada registro

        pm25 = (

            dt.loc[
                dt["pol"] == "PM2.5",
                ["registro_id", "emissions"]
            ]

            .set_index("registro_id")["emissions"]

        )

        if pm25.empty:

            raise ValueError(
                "O cálculo de BC exige emissões de PM2.5."
            )

        emissoes_pm25 = (

            dt.loc[
                filtro_bc,
                "registro_id"
            ]

            .map(pm25)

        )

        if emissoes_pm25.isna().any():

            raise ValueError(
                "Não foi possível associar BC ao PM2.5."
            )

        # Equacao corrigida:
        # BC = fracao de BC * emissao de PM2.5

        dt.loc[
            filtro_bc,
            "emissions"
        ] = (

            dt.loc[
                filtro_bc,
                "ef"
            ]

            *

            emissoes_pm25

        )

    # ==================================================
    # 6. VALIDAR RESULTADOS
    # ==================================================

    if not np.isfinite(dt["emissions"]).all():

        raise ValueError(
            "Foram encontradas emissões inválidas."
        )

    if (dt["emissions"] < 0).any():

        raise ValueError(
            "Foram encontradas emissões negativas."
        )

    # Organizar resultados

    dt = dt.sort_values(
        ["registro_id", "pol"]
    ).reset_index(drop=True)

    # ==================================================
    # 7. RESUMO POR POLUENTE
    # ==================================================

    resumo = (

        dt.groupby(
            "pol",
            as_index=False
        )["emissions"]

        .sum()

    )

    if not np.isfinite(resumo["emissions"]).all():

        raise ValueError(
            "Valores inválidos no resumo das emissões."
        )

    resumo["unit_emissions"] = "g"

    consumo_total = float(atividade["activity"].to_numpy(dtype=float).sum())
    if not np.isfinite(consumo_total):
        raise ValueError("Consumo total inválido.")

    # ==================================================
    # 8. RETORNAR RESULTADOS
    # ==================================================

    return {

        "dados": dt,

        "resumo": converter_registros(resumo),

        "fatores_utilizados": converter_registros(
            fatores
        ),

        "avisos": avisos,

        "total_registros": len(dt),

        "total_atividades": len(atividade),

        "total_fontes": atividade["id"].nunique(),

        "total_poluentes": dt["pol"].nunique(),

        "consumo_total_GJ": consumo_total,

        "unidade_emissoes": "g"

    }
