"""Relatórios PDF a partir dos resultados persistidos da execução."""

import json
from datetime import datetime, timezone
from pathlib import Path
from textwrap import wrap

from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.image import imread

from backend.services.armazenamento import ler_metadados_calculo
from backend.services.mapas import TRAVA, gerar_mapa
from backend.services.territorio import catalogo, validar_selecao
from backend.services.visualizacoes import UNIDADES, metadados_modelagem

LOGO = Path(__file__).resolve().parents[2] / "frontend/assets/logo-img.png"
SECOES = {
    "fatores": ("Fatores e referências", "Factors and references"),
    "especiacao": ("Especiação química", "Chemical speciation"),
    "temporal": ("Distribuição temporal", "Temporal allocation"),
    "espacial": ("Distribuição espacial", "Spatial allocation"),
    "modelagem": ("Modelagem atmosférica", "Atmospheric modelling"),
}
COR = "#176658"


def escrever(destino, pasta, inventario, catalogados, op, versao, conferir):
    calculo = ler_metadados_calculo(pasta)
    ingles = op.idioma == "en"

    def tr(pt, en):
        return en if ingles else pt

    selecionados = set(op.poluentes) or {linha["pol"] for linha in calculo["resumo"]}
    resumo = [linha for linha in calculo["resumo"] if linha["pol"] in selecionados]
    if selecionados != {linha["pol"] for linha in resumo}:
        raise ValueError("Selecione poluentes presentes na execução.")
    unidade = op.unidade
    fator = UNIDADES[unidade]
    secoes = catalogados.keys() if op.secoes is None else op.secoes
    validar_selecao(op.nivel, op.codigo)

    def massa(valor):
        return f"{valor * fator:.10g}" if valor is not None else "—"

    def ler(item):
        return json.loads(item.caminho.read_text(encoding="utf-8"))

    mapa = None
    pol_mapa = None
    if op.mapa:
        for item in catalogados["espacial"]:
            dados = ler(item)
            if dados["origem"] != "original":
                continue
            serie = next((s for s in dados["series"] if s["pol_origem"] in selecionados), None)
            if serie:
                pol_mapa = serie["pol"]
                mapa = gerar_mapa(item.caminho.parent, dados, serie,
                                  (unidade, "viridis", "linear", op.idioma, "pontos", "cor",
                                   op.nivel, op.codigo, "nacional"), "png", 300, conferir)
                break
        if mapa is None:
            raise ValueError("Execute a distribuição espacial da base original para incluir o mapa.")

    agora = datetime.now(timezone.utc)
    titulo = tr("Inventário de emissões atmosféricas", "Atmospheric emissions inventory")
    with TRAVA, PdfPages(destino, metadata={"Title": titulo, "Author": "PEGA", "CreationDate": agora}) as pdf:
        pagina = 0
        fig = None
        y = 0

        def nova(titulo_pagina, capa=False):
            nonlocal pagina, fig, y
            if fig is not None:
                pdf.savefig(fig, dpi=300)
                fig.clear()
            conferir()
            pagina += 1
            fig = Figure(figsize=(8.27, 11.69), facecolor="white")
            fig.text(.09, .96, "PEGA", color=COR, weight="bold", size=11)
            fig.text(.91, .96, str(calculo["ano"]), ha="right", size=10)
            fig.text(.09, .04, f"PEGA {versao}  ·  {calculo['calculo_id']}", size=8, color="#42535a")
            fig.text(.91, .04, str(pagina), ha="right", size=9)
            y = .87 if not capa else .65
            fig.text(.09, y, titulo_pagina, size=19, weight="bold", color=COR)
            y -= .045

        def linha(texto, destaque=False):
            nonlocal y
            for parte in wrap(str(texto), width=87) or [""]:
                if y < .075:
                    nova(tr("Continuação", "Continued"))
                fig.text(.09, y, parte, size=10, weight="bold" if destaque else "normal", parse_math=False)
                y -= .023

        nova(titulo, capa=True)
        logo = fig.add_axes((.08, .72, .21, .13))
        logo.imshow(imread(LOGO))
        logo.axis("off")
        linha(tr("Relatório científico", "Scientific report") if op.modo == "completo"
              else tr("Resumo executivo", "Executive summary"), True)
        linha(f"{calculo['ano']} · {calculo['setor']} · {calculo['combustivel']}")
        linha(f"{tr('Execução', 'Run')} {calculo['calculo_id']}")
        linha(f"{tr('Inventário', 'Inventory')} {calculo['inventario_id']}")
        linha(f"{tr('Configuração', 'Configuration')} {calculo['configuracao_id']}")
        linha(f"{tr('Gerado em', 'Generated at')} {agora.isoformat(timespec='seconds')}")
        linha(f"{tr('Poluentes selecionados', 'Selected pollutants')} · {', '.join(sorted(selecionados))}")
        linha(f"{tr('Unidade de apresentação', 'Reporting unit')} · {unidade}")
        nova(tr("Resumo executivo", "Executive summary"))
        linha(f"{calculo['total_atividades']} {tr('atividades', 'activities')}  ·  "
              f"{calculo['total_fontes']} {tr('fontes', 'sources')}  ·  {calculo['consumo_total_GJ']:.10g} GJ")
        linha(tr("Caracterização dos dados de entrada", "Input data characteristics"), True)
        linha(f"{inventario['total_linhas']} {tr('linhas no inventário padronizado', 'rows in the standardized inventory')}")
        linha(", ".join(inventario["colunas"]))
        linha(tr("Metodologia de cálculo", "Calculation methodology"), True)
        linha(tr("Emissões convencionais = atividade (GJ) × fator (g/GJ). "
                 "BC = emissão de PM2.5 × fração normalizada.",
                 "Conventional emissions = activity (GJ) × factor (g/GJ). "
                 "BC = PM2.5 emissions × normalized fraction."))
        linha(f"{tr('Poluente', 'Pollutant')}  ·  {tr('Emissão', 'Emissions')} ({unidade})", True)
        for row in resumo:
            linha(f"{row['pol']}  ·  {massa(row['emissions'])}")
        if op.grafico:
            nova(tr("Emissões por poluente", "Emissions by pollutant"))
            ax = fig.add_axes((.16, .13, .72, .67))
            ax.barh([r["pol"] for r in resumo], [r["emissions"] * fator for r in resumo], color=COR)
            ax.invert_yaxis()
            ax.set_xlabel(unidade)
            ax.grid(axis="x", alpha=.2)
        if mapa:
            nova(tr("Mapa científico por fonte", "Scientific source map"))
            nome = catalogo()[op.nivel].get(op.codigo, "") if op.nivel != "brasil" else tr("Brasil", "Brazil")
            linha(f"{nome} · {pol_mapa}")
            ax = fig.add_axes((.08, .15, .84, .62))
            ax.imshow(imread(mapa))
            ax.axis("off")

        if op.modo == "completo":
            if "fatores" in secoes:
                nova(tr(*SECOES["fatores"]))
                for row in calculo["fatores_utilizados"]:
                    if row["pol"] in selecionados:
                        linha(f"{row['pol']} · {row['ef']} {row['unit']} · {row.get('source') or '—'}", True)
                        linha(f"{tr('Identificador do fator', 'Factor identifier')} · {row['fator_id']}")
                        linha(row.get("reference") or "—")
            if "especiacao" in secoes and catalogados["especiacao"]:
                dados = ler(catalogados["especiacao"][0])
                nova(tr(*SECOES["especiacao"]))
                linha(dados["referencia_perfil"])
                linha(f"{tr('Origem · Original · Alocado · Resíduo', 'Origin · Original · Allocated · Residual')} ({unidade})", True)
                for row in dados["balanco"]:
                    if row["disponivel"] and row["pol_origem"] in selecionados:
                        linha(f"{row['pol_origem']} · {massa(row['original_g'])} · {massa(row['derivado_g'])} · {massa(row['residuo_g'])}")
                for row in dados["resumo"]:
                    if row["pol_origem"] in selecionados:
                        linha(f"{row['pol_origem']} → {row['pol']} · {massa(row['emissions'])} {unidade}")
            for secao in ("temporal", "espacial", "modelagem"):
                if secao not in secoes or not catalogados[secao]:
                    continue
                nova(tr(*SECOES[secao]))
                for item in catalogados[secao]:
                    dados = metadados_modelagem(item.caminho.parent) if secao == "modelagem" else ler(item)
                    linha(f"{tr('Base', 'Basis')} · {dados['origem']}", True)
                    if secao == "temporal":
                        linha(dados["referencia"])
                        linha(tr("Perfil relativo de 168 intervalos sem calendário.",
                                 "Relative profile of 168 intervals without a calendar."))
                    if secao == "espacial":
                        linha(tr("Classificação territorial baseada na malha IBGE UF 2025.",
                                 "Territorial classification uses the IBGE 2025 state boundaries."))
                        linha(f"CRS: {dados['grade_epsg'] or '—'}")
                    if secao == "modelagem":
                        linha(f"NetCDF · GRID_ID={dados['grid_id']} · {dados['nx']} × {dados['ny']} · "
                              f"DX={dados['dx_m']} m · DY={dados['dy_m']} m")
                        calendario = dados["calendario"]
                        if calendario:
                            linha(f"{calendario['horas']} h · {calendario['convencao']} · Σ "
                                  f"{calendario['soma_pesos_normalizados']:.12g}")
                    for row in dados.get("resumo", dados.get("series", [])):
                        if row["pol_origem"] not in selecionados:
                            continue
                        linha(f"{row['pol_origem']} → {row['pol']} · "
                              f"{massa(row.get('massa_base_g', row.get('massa_g')))} {unidade}")
                        if "balanco_g" in row:
                            linha("   ".join(f"{chave} {massa(valor)}" for chave, valor in row["balanco_g"].items()))
        nova(tr("Alertas e limitações", "Alerts and limitations"))
        for aviso in calculo["avisos"]:
            linha(f"{aviso.get('pol', '')} · {aviso.get('motivo', str(aviso))}" if isinstance(aviso, dict) else aviso)
        if catalogados["especiacao"]:
            for aviso in ler(catalogados["especiacao"][0])["avisos"]:
                linha(aviso)
        if catalogados["modelagem"]:
            linha(tr("NetCDF intermediário em massa por célula ou intervalo. A escrita de wrfchemi "
                     "depende da configuração e da validação pelo modelo de destino.",
                     "Intermediate NetCDF stores mass per cell or interval. Writing wrfchemi "
                     "depends on target configuration and validation with the destination model."))
        pdf.savefig(fig, dpi=300)
        fig.clear()

