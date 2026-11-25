"""Perfil complexo de APP_PEGA/R/calculos.R (sem normalização)."""

import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from backend.services.fatores_emissao import converter_registros


PERFIL = {
    "PM2.5": [
        ("PAL", .030, None), ("PCA", .050, None), ("PCL", .006, None),
        ("PFE", .030, None), ("PH2O", .008, None), ("PK", .002, None),
        ("PMG", .014, None), ("PMN", .0013, None), ("PMOTHR", .570, None),
        ("PNA", .010, None), ("PNCOM", .080, None), ("PNH4", .002, None),
        ("PNO3", .004, None), ("PSI", .089, None), ("PSO4", .096, None),
        ("PTI", .002, None),
    ],
    "SOx": [("SO2", .95, 64.06), ("PSO4", .05, None)],
    "NOx": [("NO2", .92, 46.01), ("HONO", .08, 47.01)],
    "NMVOC": [
        ("ACET", .044008, 58.08), ("ALD2", .000118, 44.05),
        ("ALDX", .000152, 58.00), ("ETH", .00567, 28.05),
        ("ETHA", .000692, 30.07), ("ETHY", .132, 26.04), ("ETOH", .000126, 46.07),
        ("FORM", .0158, 30.03), ("IOLE", .000508, 56.10), ("ISOP", .00211, 68.12),
        ("KET", .0000138, 72.11), ("MEOH", .00187, 32.04), ("NAPH", .0146, 128.17),
        ("OLE", .000171, 42.08), ("PAR", .00326, 16.00), ("PRPA", .312, 44.10),
        ("SOAALK", .102, 100.00), ("TOL", .221, 92.14), ("UNK", .0375, 100.00),
        ("XYLMN", .0713, 106.17), ("NVOL", .0258, 100.00), ("TERP", .00215, 136.23),
        ("XYL", .00628, 106.17), ("SULF", .00000033, 98.07),
        ("BENZENE", .000000001, 78.11),
    ],
}

REFERENCIA = "APP_PEGA/R/calculos.R, perfil_complexo"
PASTA_ESPECIACAO = "especiacao"
ARQUIVOS_ESPECIACAO = {
    "emissoes_especiadas.csv": "text/csv",
    "resumo_especies.csv": "text/csv",
    "perfil_especiacao.csv": "text/csv",
    "metadados_especiacao.json": "application/json",
}


def especiar_emissoes(dados):
    if not dados["unit_emissions"].eq("g").all():
        raise ValueError("A especiação exige emissões em gramas.")
    perfil = pd.DataFrame(
        [(origem, especie, fracao, mw) for origem, especies in PERFIL.items()
         for especie, fracao, mw in especies],
        columns=["pol_origem", "especie", "fracao", "mw"],
    )
    perfil["referencia_perfil"] = REFERENCIA
    base = dados.rename(columns={"pol": "pol_origem", "emissions": "emissao_original_g"})
    resultado = base.merge(perfil, how="left", on="pol_origem", sort=False)
    resultado["especiado"] = resultado["especie"].notna()
    resultado["pol"] = resultado["especie"].fillna(resultado["pol_origem"])
    resultado["emissions"] = resultado["emissao_original_g"] * resultado["fracao"].fillna(1)
    resumo = (
        resultado.groupby(["pol_origem", "pol", "especiado", "unit_emissions"], as_index=False)
        ["emissions"].sum()
    )
    entrada = base.groupby("pol_origem")["emissao_original_g"].sum()
    saida = resumo.groupby("pol_origem")["emissions"].sum()
    balanco = []
    for origem, especies in PERFIL.items():
        soma = math.fsum(fracao for _, fracao, _ in especies)
        disponivel = origem in entrada.index
        original = float(entrada[origem]) if disponivel else None
        derivado = float(saida[origem]) if disponivel else None
        residuo = original - derivado if disponivel else None
        if disponivel and math.isclose(original, derivado, rel_tol=1e-12):
            residuo = 0.0
        balanco.append({
            "pol_origem": origem, "soma_fracoes": soma, "disponivel": disponivel,
            "original_g": original, "derivado_g": derivado, "residuo_g": residuo,
        })
    avisos = [
        f"{grupo['pol_origem']}: as frações do perfil somam {grupo['soma_fracoes']:.9g}. "
        "O saldo de massa não foi redistribuído."
        for grupo in balanco
        if grupo["disponivel"] and not math.isclose(grupo["soma_fracoes"], 1)
    ]
    return resultado, resumo, perfil, balanco, avisos


def ler_especiacao(pasta_calculo):
    caminho = pasta_calculo / PASTA_ESPECIACAO / "metadados_especiacao.json"
    with caminho.open(encoding="utf-8") as arquivo:
        return json.load(arquivo)


def salvar_especiacao(pasta_calculo, dados_calculo, conferir_acesso):
    try:
        return ler_especiacao(pasta_calculo)
    except FileNotFoundError:
        pass
    dados = pd.read_csv(pasta_calculo / "emissoes_base.csv", dtype=str, keep_default_na=False)
    dados["emissions"] = dados["emissions"].map(float)
    resultado, resumo, perfil, balanco, avisos = especiar_emissoes(dados)
    metadados = {
        "inventario_id": dados_calculo["inventario_id"],
        "calculo_id": dados_calculo["calculo_id"],
        "configuracao_id": dados_calculo["configuracao_id"],
        "referencia_perfil": REFERENCIA,
        "unidade_emissoes": "g",
        "total_registros": len(resultado),
        "resumo": converter_registros(resumo),
        "perfil": converter_registros(perfil),
        "balanco": balanco,
        "avisos": avisos,
        "previa": converter_registros(resultado.head(20)),
    }
    with TemporaryDirectory(dir=pasta_calculo) as temporario:
        pasta = Path(temporario) / PASTA_ESPECIACAO
        pasta.mkdir()
        resultado.to_csv(pasta / "emissoes_especiadas.csv", index=False)
        resumo.to_csv(pasta / "resumo_especies.csv", index=False)
        perfil.to_csv(pasta / "perfil_especiacao.csv", index=False)
        with (pasta / "metadados_especiacao.json").open("w", encoding="utf-8") as arquivo:
            json.dump(metadados, arquivo, ensure_ascii=False, allow_nan=False, indent=2)
        conferir_acesso()
        try:
            pasta.rename(pasta_calculo / PASTA_ESPECIACAO)
        except OSError:
            # Outra solicitação pode ter publicado a mesma transformação.
            if (pasta_calculo / PASTA_ESPECIACAO / "metadados_especiacao.json").is_file():
                return ler_especiacao(pasta_calculo)
            raise
    return metadados
