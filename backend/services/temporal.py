"""Perfil relativo industrial de APP_PEGA/R/calculos.R."""

import csv
import io
import json
import math
from collections import defaultdict
from tempfile import TemporaryDirectory
from pathlib import Path

from backend.services.especiacao import PASTA_ESPECIACAO, ler_especiacao


DIAS = ("Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sab")
SEMANA = (0.1428,) * 6 + (0.1432,)
HORAS_R = (
    .030, .030, .031, .033, .037, .045, .050, .050, .050, .051, .051, .048,
    .045, .040, .041, .041, .041, .048, .050, .048, .043, .036, .031, .030,
)
HORAS = tuple(peso / math.fsum(HORAS_R) for peso in HORAS_R)
COMBINADO = tuple(
    {"dia": dia, "hora": hora, "peso": semanal * horario}
    for dia, semanal in zip(DIAS, SEMANA)
    for hora, horario in enumerate(HORAS)
)


def origem_csv(pasta, origem):
    if origem == "especiada":
        return pasta / PASTA_ESPECIACAO / "emissoes_especiadas.csv"
    return pasta / "emissoes_base.csv"


def caminho_temporal(pasta, origem):
    return pasta / f"temporal-{origem}.json"


def consultar_temporal(pasta, origem):
    with caminho_temporal(pasta, origem).open(encoding="utf-8") as arquivo:
        return json.load(arquivo)


def salvar_temporal(pasta, origem, calculo, conferir_acesso):
    try:
        return consultar_temporal(pasta, origem)
    except FileNotFoundError:
        pass
    somas = defaultdict(float)
    with origem_csv(pasta, origem).open(encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            chave = (linha.get("pol_origem", linha["pol"]), linha["pol"],
                     linha.get("especiado") == "True")
            somas[chave] += float(linha["emissions"])
    dados = {chave: calculo[chave] for chave in
             ("inventario_id", "calculo_id", "configuracao_id", "ano", "setor", "combustivel")}
    dados.update(
        origem=origem,
        referencia="APP_PEGA/R/calculos.R, perfil_horario_ind e perfil_semanal_ind",
        tipo="alocacao_relativa_sem_calendario",
        unidade="g",
        horario=[{"hora": hora, "peso_original": bruto, "peso": normalizado}
                 for hora, (bruto, normalizado) in enumerate(zip(HORAS_R, HORAS))],
        semanal=[{"dia": dia, "peso": peso} for dia, peso in zip(DIAS, SEMANA)],
        combinado=COMBINADO,
        somas_pesos={"horario_original": math.fsum(HORAS_R), "horario": math.fsum(HORAS),
                     "semanal": math.fsum(SEMANA),
                     "combinado": math.fsum(intervalo["peso"] for intervalo in COMBINADO)},
        resumo=[{"pol_origem": origem_pol, "pol": pol, "especiado": especie, "massa_base_g": massa}
                for (origem_pol, pol, especie), massa in sorted(somas.items())],
        balanco_especiacao=ler_especiacao(pasta)["balanco"] if origem == "especiada" else [],
    )
    with TemporaryDirectory(dir=pasta) as temporaria:
        temporario = Path(temporaria) / "metadados.json"
        temporario.write_text(json.dumps(dados, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        conferir_acesso()
        temporario.replace(caminho_temporal(pasta, origem))
    return consultar_temporal(pasta, origem)


def transmitir_alocacao(arquivo, calculo, origem):
    """Expande a dimensão temporal apenas durante o download, uma fonte por vez."""
    with arquivo:
        leitor = csv.DictReader(arquivo)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        campos = leitor.fieldnames or []
        writer.writerow([*campos, "ano", "setor", "combustivel", "origem_temporal",
                         "dia_modelo", "hora_modelo", "peso_temporal", "massa_alocada_g"])
        for linha in leitor:
            massa = float(linha["emissions"])
            base = [linha[chave] for chave in campos]
            for indice, intervalo in enumerate(COMBINADO):
                ponderada = massa * SEMANA[indice // 24] * HORAS[indice % 24]
                writer.writerow([*base, calculo["ano"], calculo["setor"], calculo["combustivel"],
                                 origem, intervalo["dia"], intervalo["hora"],
                                 intervalo["peso"], ponderada])
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate()
        if buffer.tell():
            yield buffer.getvalue()
