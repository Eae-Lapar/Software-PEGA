import csv
import hashlib
import io
import json
import math
import os
import tracemalloc
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile

from fastapi.testclient import TestClient
from openpyxl import Workbook
from netCDF4 import Dataset
import numpy as np
import pandas as pd
from pyproj import Transformer

from backend.api import app
from backend.services import armazenamento
from backend.services.especiacao import ARQUIVOS_ESPECIACAO, PERFIL, especiar_emissoes
from backend.services.espacial import Grade, coordenadas
from backend.services.mapas import escala_cores
from backend.services.territorio import classificar, malha
from backend.services.modelagem import calendario_anual
from backend.services.temporal import SEMANA, HORAS
from backend.services.wrf import DominioWRF
from tests.fixtures_wrf import dominio_sintetico


SETOR = "1.A.1.a"
CABECALHOS = ("identificador", "combustível", "potência MW", "lat", "lon",
              "ano", "consumo GJ", "nota")


class PegaTest(unittest.TestCase):
    def test_central_exportacoes_pdf_lote_e_isolamento(self):
        temporario = tempfile.TemporaryDirectory(dir=".")
        self.addCleanup(temporario.cleanup)
        armazenamento.STORAGE_DIR = Path(os.path.relpath(temporario.name))
        inventario = self.upload(linhas=[
            ("RJ01", "Biomass", 20, -22.92, -43.25, 2017, 1000, "sintético"),
            ("SP01", "Biomass", 20, -23.50, -46.60, 2017, 700, "sintético"),
        ]).json()["inventario_id"]
        calculo = self.calcular(inventario, "Biomass").json()["calculo_id"]
        base = f"/api/inventarios/{inventario}/calculos/{calculo}"
        url = f"{base}/exportacoes"
        self.assertEqual(self.client.post(f"{base}/especiacao").status_code, 200)
        self.assertEqual(self.client.post(f"{base}/temporal/original").status_code, 200)
        self.assertEqual(self.client.post(f"{base}/espacial/original").status_code, 200)
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200, resposta.text)
        self.assertEqual(resposta.headers["Cache-Control"], "no-store")
        itens = {a["id"]: a for a in resposta.json()["arquivos"]}
        self.assertIn("inventario/dados.csv", itens)
        self.assertNotIn("modelagem", {i["categoria"] for i in itens.values()})
        self.assertTrue(itens["temporal/alocacao-original.csv"]["sob_demanda"])
        relatorio = self.client.get(f"{url}/arquivo/relatorios/relatorio-cientifico.pdf")
        self.assertEqual(relatorio.status_code, 200, relatorio.text[:200] if relatorio.status_code != 200 else "")
        self.assertTrue(relatorio.content.startswith(b"%PDF-"))
        configuracao = {"idioma": "en", "unidade": "kg", "poluentes": ["PM2.5"],
                        "mapa": True, "nivel": "uf", "codigo": "33"}
        mapa = self.client.post(f"{url}/relatorio", json=configuracao)
        self.assertEqual(mapa.status_code, 200, mapa.text[:200] if mapa.status_code != 200 else "")
        self.assertEqual(self.client.post(f"{url}/relatorio", json={"poluentes": ["inexistente"]}).status_code, 400)
        arquivo = "espacial/original-uf.csv"
        territorio = self.client.get(f"{url}/arquivo/{arquivo}")
        self.assertEqual(territorio.status_code, 200, territorio.text)
        pm = [r for r in csv.DictReader(io.StringIO(territorio.text)) if r["pol"] == "PM2.5"]
        resumo = next(r for r in self.client.get(base).json()["resumo"] if r["pol"] == "PM2.5")
        self.assertAlmostEqual(sum(float(r["massa_g"]) for r in pm), resumo["emissions"])
        token = str(uuid4())
        escolhidos = ["inventario/resumo.csv", arquivo, "relatorios/resumo-executivo.pdf"]
        lote = self.client.post(f"{url}/lotes", json={"token": token, "arquivos": escolhidos})
        self.assertEqual(lote.status_code, 200, lote.text)
        self.assertEqual(lote.json()["incluidos"], escolhidos)
        progresso = f"{url}/lotes/{token}"
        zip_url = f"{progresso}/zip"
        self.assertEqual(self.client.get(progresso).json()["concluidos"], len(escolhidos))
        with TestClient(app) as outra_sessao:
            for rota in (url, progresso, zip_url, f"{url}/arquivo/{arquivo}"):
                self.assertEqual(outra_sessao.get(rota).status_code, 404)
        zip_bytes = self.client.get(zip_url)
        self.assertEqual(zip_bytes.status_code, 200)
        with ZipFile(io.BytesIO(zip_bytes.content)) as pacote:
            self.assertEqual(set(pacote.namelist()), {*escolhidos, "manifesto.json"})
            self.assertEqual(pacote.read(arquivo), territorio.content)
            self.assertEqual(json.loads(pacote.read("manifesto.json"))["calculo_id"], calculo)
        self.assertEqual(self.client.get(zip_url).status_code, 404)
        self.assertEqual(self.client.post(f"{url}/lotes", json={"token": token, "arquivos": ["../../qualquer"]}).status_code, 400)
        with patch("backend.services.exportacoes.LIMITE_BYTES", 10):
            excesso = self.client.post(f"{url}/lotes", json={"token": token, "arquivos": escolhidos})
        self.assertEqual(excesso.status_code, 413)
        completo = self.client.post(f"{url}/lotes", json={"token": token})
        self.assertEqual(completo.status_code, 200, completo.text)
        with ZipFile(io.BytesIO(self.client.get(zip_url).content)) as pacote:
            padrao = {chave for chave in itens if not chave.startswith("figuras/") or chave.endswith("-300dpi.png")}
            self.assertEqual(set(pacote.namelist()), {*padrao, "manifesto.json"})
            manifesto = json.loads(pacote.read("manifesto.json"))
            self.assertTrue(all(figura["dpi"] == 300 for figura in manifesto["figuras"]))
        with patch("backend.services.exportacoes.LIMITE_SEGUNDOS", -1):
            tempo = self.client.post(f"{url}/lotes", json={"token": token, "arquivos": escolhidos[:1]})
        self.assertEqual(tempo.status_code, 413)
        self.assertIn("120 segundos", tempo.json()["detail"])
        configurado = self.client.post(f"{url}/lotes", json={"token": token, "variantes": {
            "totais": "figuras/totais.svg", "mapa-original": "figuras/mapa-original-600dpi.png"}})
        self.assertEqual(configurado.status_code, 200, configurado.text)
        with ZipFile(io.BytesIO(self.client.get(zip_url).content)) as pacote:
            figuras = json.loads(pacote.read("manifesto.json"))["figuras"]
            self.assertEqual({f["id"]: f.get("dpi") for f in figuras},
                             {"figuras/totais.svg": None, "figuras/mapa-original-600dpi.png": 600})
        with patch("backend.services.exportacoes.indexar", side_effect=FileNotFoundError):
            omissao = self.client.post(f"{url}/lotes", json={"token": token, "arquivos": escolhidos[:2]})
        self.assertEqual(omissao.status_code, 200, omissao.text)
        self.assertEqual(omissao.json()["incluidos"], escolhidos[:1])
        self.assertEqual(omissao.json()["omitidos"][0]["id"], arquivo)
        with ZipFile(io.BytesIO(self.client.get(zip_url).content)) as pacote:
            self.assertNotIn(arquivo, pacote.namelist())
            self.assertEqual(json.loads(pacote.read("manifesto.json"))["omitidos"], omissao.json()["omitidos"])
        self.assertEqual(self.client.delete(f"/api/inventarios/{inventario}").status_code, 200)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(f"{url}/relatorio", json=configuracao).status_code, 404)
        destino = os.environ.get("PEGA_EXEMPLOS")
        if destino:
            (Path(destino) / "relatorio-cientifico-sintetico.pdf").write_bytes(relatorio.content)
            (Path(destino) / "relatorio-sintetico-mapa-en.pdf").write_bytes(mapa.content)

    def test_calendario_utc_fixo_bissexto_e_limites(self):
        comum, unidades, _ = calendario_anual(2017, "UTC")
        bissexto, unidades_fixas, _ = calendario_anual(2020, "-03:00")
        self.assertEqual(len(comum), 8760)
        self.assertEqual(len(bissexto), 8784)
        self.assertTrue(unidades.endswith("2017-01-01 00:00:00 +00:00"))
        self.assertTrue(unidades_fixas.endswith("2020-01-01 03:00:00 +00:00"))
        self.assertAlmostEqual(math.fsum(comum), 1.0, places=14)
        self.assertAlmostEqual(math.fsum(bissexto), 1.0, places=14)
        self.assertAlmostEqual(comum[0] / comum[2], HORAS[0] / HORAS[2])
        self.assertAlmostEqual(comum[6 * 24] / comum[0], SEMANA[6] / SEMANA[0])
        for fuso in ("America/Sao_Paulo", "-00:00", "+14:01", "+03:60", ""):
            with self.subTest(fuso=fuso), self.assertRaises(ValueError):
                calendario_anual(2017, fuso)

    def test_dominio_netcdf_rejeita_projecao_coordenadas_e_formato(self):
        caminho = self.storage / "dominio.nc"
        for parametros in ({"modo": 3}, {"corromper": True}):
            with self.subTest(parametros=parametros):
                dominio_sintetico(caminho, **parametros)
                with self.assertRaises(ValueError):
                    DominioWRF(caminho)
        caminho.write_text("dados não NetCDF", encoding="utf-8")
        with self.assertRaises(ValueError):
            DominioWRF(caminho)
        dominio_sintetico(caminho, com_tempo=False)
        self.assertEqual(DominioWRF(caminho).lat.shape, (2, 3))

    def test_modelagem_balanco_orientacao_e_privacidade(self):
        caminho = self.storage / "dominio.nc"
        inversa = dominio_sintetico(caminho)
        pontos = [(0, 0, 1000), (6000, 4000, 2000), (1500, 0, 100), (-12000, 0, 200)]
        linhas = []
        for i, (x, y, consumo) in enumerate(pontos):
            lon, lat = inversa(x, y)
            linhas.append((f"F{i}", "Biomass", 20, lat, lon, 2017, consumo, "sintético"))
        inventario = self.upload(linhas=linhas).json()["inventario_id"]
        calculo = self.calcular(inventario, "Biomass").json()["calculo_id"]
        base = f"/api/inventarios/{inventario}/calculos/{calculo}"
        rota = f"{base}/modelagem/original"
        arquivo = {"dominio": ("wrfinput_d01", caminho.read_bytes())}
        self.assertEqual(self.client.post(rota, data={"anual": "true"}, files=arquivo).status_code, 400)
        resposta = self.client.post(rota, files=arquivo)
        self.assertEqual(resposta.status_code, 200, resposta.text)
        self.assertIsNone(resposta.json()["calendario"])
        resposta = self.client.post(rota, data={"convencao": "UTC"}, files=arquivo)
        self.assertEqual(resposta.status_code, 200, resposta.text)
        resultado = resposta.json()
        self.assertEqual((resultado["grid_id"], resultado["ny"], resultado["nx"]), (2, 2, 3))
        self.assertTrue(resultado["calendario"]["horario_materializado"])
        serie = next(s for s in resultado["series"] if s["pol"] == "PM2.5")
        self.assertEqual(serie["massa_base_g"], 438900)
        self.assertEqual(serie["balanco_g"], {
            "mapeada": 399000, "fora_grade": 26600, "borda_grade": 13300, "coordenada_invalida": 0
        })
        self.assertTrue(serie["referencias"][0]["fator_id"])
        projecao = self.client.get(f"{base}/exportacoes/arquivo/temporal/projecao-anual-original.csv")
        self.assertEqual(projecao.status_code, 200)
        alocacoes = [r for r in csv.DictReader(io.StringIO(projecao.text)) if r["pol"] == "PM2.5"]
        self.assertEqual(len(alocacoes), 8760)
        self.assertEqual(alocacoes[0]["relogio_perfil"], "UTC")
        self.assertAlmostEqual(math.fsum(float(r["massa_g"]) for r in alocacoes), 399000, places=8)
        mensal = self.client.get(f"{base}/exportacoes/arquivo/temporal/resumo-mensal-original.csv")
        self.assertEqual(mensal.status_code, 200)
        meses = [r for r in csv.DictReader(io.StringIO(mensal.text)) if r["pol"] == "PM2.5"]
        self.assertEqual(len(meses), 12)
        self.assertAlmostEqual(math.fsum(float(r["massa_g"]) for r in meses), 399000, places=8)
        url = f"{rota}/arquivos/emissoes-grade.nc"
        download = self.client.get(url)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.headers["cache-control"], "no-store")
        saida = self.storage / "saida.nc"
        saida.write_bytes(download.content)
        with Dataset(saida) as nc:
            i = serie["serie"]
            massa = nc.variables["inventory_mass"]
            self.assertEqual(massa.dimensions, ("series", "south_north", "west_east"))
            self.assertEqual(massa.units, "g")
            self.assertEqual(massa[i].tolist(), [[133000, 0, 0], [0, 0, 266000]])
            self.assertEqual(nc.variables["time_bounds"][-1].tolist(), [8759, 8760])
            ativos = np.asarray(nc.variables["active_series_index"][:]) == i
            acumulado = np.asarray(nc.variables["hourly_mass"][:])[:, ativos].sum()
            self.assertAlmostEqual(acumulado, 399000, places=7)
            self.assertEqual(nc.variables["latitude"].shape, (2, 3))
            self.assertEqual(nc.variables["crs"].grid_mapping_name, "lambert_conformal_conic")
        self.assertEqual(self.client.post(rota, data={"convencao": "UTC"}, files=arquivo).json(), resultado)
        self.assertEqual(self.client.get(url).content, download.content)
        with TestClient(app, base_url="https://testserver") as outra:
            self.assertEqual(outra.get(rota).status_code, 404)
            self.assertEqual(outra.get(url).status_code, 404)
            self.assertEqual(outra.post(rota, files=arquivo).status_code, 404)
        self.assertEqual(self.client.post(f"{base}/especiacao").status_code, 200)
        with patch("backend.services.modelagem.MAX_VALORES_HORARIOS", 1):
            resposta = self.client.post(f"{base}/modelagem/especiada",
                                        data={"convencao": "-03:00"}, files=arquivo)
        self.assertEqual(resposta.status_code, 200, resposta.text)
        derivada = resposta.json()
        self.assertFalse(derivada["calendario"]["horario_materializado"])
        self.assertNotIn("PM2.5", [s["pol"] for s in derivada["series"]])
        self.assertGreater(next(s for s in derivada["balanco_especiacao"]
                                if s["pol_origem"] == "PM2.5")["residuo_g"], 0)
        saida.write_bytes(self.client.get(f"{base}/modelagem/especiada/arquivos/emissoes-grade.nc").content)
        with Dataset(saida) as nc:
            self.assertNotIn("hourly_mass", nc.variables)
            self.assertAlmostEqual(math.fsum(nc.variables["hour_fraction"][:]), 1)
            self.assertTrue(nc.variables["time"].units.endswith("03:00:00 +00:00"))
        self.assertEqual(self.client.delete(f"/api/inventarios/{inventario}").status_code, 200)
        self.assertEqual(self.client.get(url).status_code, 404)
    def test_visualizacoes_massas_privacidade_e_exportacoes(self):
        from backend.services.visualizacoes import dados_emissoes, dados_especiacao, intervalo, projecao, serie_anual
        from backend.services.modelagem import resultado_atual

        caminho = self.storage / "dominio-figuras.nc"
        inversa = dominio_sintetico(caminho)
        locais = [(0, 0, 1000), (6000, 4000, 2000), (-12000, 0, 100)]
        linhas = []
        for i, (x, y, consumo) in enumerate(locais):
            lon, lat = inversa(x, y)
            linhas.append((f"F{i}", "Biomass", 20, lat, lon, 2017, consumo, "sintético"))
        inventario = self.upload(linhas=linhas).json()["inventario_id"]
        calculo = self.calcular(inventario, "Biomass").json()["calculo_id"]
        base = f"/api/inventarios/{inventario}/calculos/{calculo}"
        rota = f"{base}/visualizacoes"
        self.assertEqual(self.client.get(rota).json()["modelos"], {})
        self.assertEqual(self.client.get(f"{rota}/figura.png", params={"tipo": "mensal"}).status_code, 404)
        self.assertEqual(self.client.post(f"{base}/especiacao").status_code, 200)
        self.assertEqual(self.client.post(f"{base}/temporal/original").status_code, 200)
        resposta = self.client.post(f"{base}/modelagem/original", data={"convencao": "UTC"},
                                   files={"dominio": ("wrfinput_d01", caminho.read_bytes())})
        self.assertEqual(resposta.status_code, 200, resposta.text)
        self.assertIn("original", self.client.get(rota).json()["modelos"])
        pasta = next(self.storage.rglob("modelagem-original")).parent
        modelo = resultado_atual(pasta, "original")
        opcoes = dict(tipo="mensal", pol="PM2.5", pol_origem="PM2.5", inicio="", fim="",
                      comparar_inicio="2017-02-01", comparar_fim="2017-02-28")
        _, fatias = projecao(modelo, opcoes)
        todos, mensal = fatias
        self.assertAlmostEqual(todos[1].sum(), 399000)
        self.assertEqual(len(mensal[1]), 28 * 24)
        self.assertAlmostEqual(serie_anual("mensal", 2017, *mensal)[1][1], mensal[1].sum())
        self.assertEqual(intervalo(2020, 8784, "2020-02-29", "2020-02-29").stop -
                         intervalo(2020, 8784, "2020-02-29", "2020-02-29").start, 24)
        with self.assertRaises(ValueError):
            intervalo(2017, 8760, "2017-02-29", "")
        _, grade = projecao(modelo, dict(opcoes, tipo="grade-wrf", inicio="2017-02-01", fim="2017-02-28"))
        self.assertEqual(grade[0].shape, (3, 4))
        self.assertAlmostEqual(grade[2].sum(), mensal[1].sum())
        filtros = dict(tipo="fontes", origem="original", pol="PM2.5", pol_origem="PM2.5",
                       nivel="brasil", codigo="", ordem="maior", top=2, unidade="kg")
        _, massas, unidade, total = dados_emissoes(pasta, filtros)
        self.assertEqual(unidade, "kg")
        np.testing.assert_allclose(massas, [266, 133])
        self.assertAlmostEqual(total, 412300)
        _, percentuais, _, _ = dados_emissoes(pasta, dict(filtros, tipo="participacao"))
        self.assertAlmostEqual(percentuais.sum(), 100 * 399000 / 412300)
        _, acumulada, _, _ = dados_emissoes(pasta, dict(filtros, tipo="acumulada"))
        self.assertAlmostEqual(acumulada[-1], 412.3)
        _, quimica, _ = dados_especiacao(pasta, dict(filtros, tipo="especies", idioma="pt", unidade="%"))
        _, massas_balanco, _ = dados_especiacao(pasta, dict(filtros, tipo="balanco", idioma="pt"))
        self.assertAlmostEqual(quimica.sum(), 100 * massas_balanco[1] / massas_balanco[0])
        self.assertAlmostEqual(massas_balanco[0] - massas_balanco[1], massas_balanco[2])
        params = {"tipo": "participacao", "pol": "PM2.5", "pol_origem": "PM2.5", "download": "true"}
        figura = self.client.get(f"{rota}/figura.svg", params=params)
        self.assertEqual(figura.status_code, 200, figura.text[:500])
        self.assertEqual(figura.headers["cache-control"], "no-store")
        self.assertIn("participacao-2017-original-PM2.5", figura.headers["content-disposition"])
        self.assertEqual(self.client.get(f"{rota}/figura.svg", params=params).content, figura.content)
        with TestClient(app, base_url="https://testserver") as outra:
            self.assertEqual(outra.get(rota).status_code, 404)
            self.assertEqual(outra.get(f"{rota}/figura.svg", params=params).status_code, 404)

        import os
        destino = os.environ.get("PEGA_EXEMPLOS")
        if destino:
            exemplos = [
                ("totais", "PM2.5"), ("fontes", "PM2.5"), ("uf", "PM2.5"),
                ("balanco", "PM2.5"), ("especies", "PM2.5"), ("especies", "NMVOC"), ("horario", "PM2.5"),
                ("semanal", "PM2.5"), ("calor", "PM2.5"), ("mensal", "PM2.5"),
                ("serie-anual", "PM2.5"), ("grade-wrf", "PM2.5"), ("dominio-wrf", "PM2.5"),
            ]
            for tipo, pol in exemplos:
                figura = self.client.get(f"{rota}/figura.png",
                                         params={"tipo": tipo, "pol": pol, "pol_origem": pol, "dpi": 300,
                                                 "unidade": "%" if tipo in ("horario", "semanal", "calor") else "kg"})
                self.assertEqual(figura.status_code, 200, figura.content[:500])
                (Path(destino) / f"figura-{tipo}-{pol}-sintetico.png").write_bytes(figura.content)


    def test_ibge_2025_cobertura_classificacao_e_limites(self):
        import shapely
        atributos, geometrias, _ = malha()
        self.assertEqual(len(geometrias), 27)
        self.assertTrue(shapely.coverage_is_valid(geometrias))
        self.assertTrue(all(g.is_valid and not g.is_empty for g in geometrias))
        self.assertEqual(set(atributos[0]), {"CD_UF", "NM_UF", "SIGLA_UF", "CD_REGIAO",
                                          "NM_REGIAO", "SIGLA_RG", "AREA_KM2"})
        self.assertEqual(classificar(-43.25, -22.92), ("33", "3", "classificada"))
        self.assertEqual(classificar(-46.63, -23.55), ("35", "3", "classificada"))
        self.assertEqual(classificar(0, 0)[2], "fora")
        self.assertEqual(classificar(200, 0)[2], "invalida")
        poligono = geometrias[0].geoms[0] if geometrias[0].geom_type == "MultiPolygon" else geometrias[0]
        self.assertIn(classificar(*poligono.exterior.coords[0])[2], {"limite", "ambigua"})
        mapa = self.client.get("/api/cartografia/ibge").json()
        self.assertEqual((len(mapa["features"]), len(mapa["regioes"])), (27, 5))
        self.assertTrue(shapely.coverage_is_valid([shapely.geometry.shape(f["geometry"]) for f in mapa["features"]]))

    def test_territorio_indicadores_rankings_cache_e_exportacao(self):
        linhas = [("RJ", "Biomass", 20, -22.92, -43.25, 2017, 1000, "x"),
                  ("RJ", "Biomass", 20, -22.92, -43.25, 2017, 500, "x"),
                  ("RJ2", "Biomass", 25, -22.92, -43.25, 2017, 1000, "x"),
                  ("SP", "Biomass", 30, -23.55, -46.63, 2017, 2000, "x"),
                  ("FORA", "Biomass", 40, 0, 0, 2017, 100, "x")]
        inventario = self.upload(linhas=linhas).json()["inventario_id"]
        calculo = self.calcular(inventario, "Biomass").json()["calculo_id"]
        base = f"/api/inventarios/{inventario}/calculos/{calculo}"
        rota = f"{base}/espacial/original"
        resposta = self.client.post(rota)
        self.assertEqual(resposta.status_code, 200, resposta.text)
        serie = next(s["id"] for s in resposta.json()["series"] if s["pol"] == "PM2.5")
        caminho = f"{rota}/territorio/{serie}"
        br = self.client.get(caminho).json()
        self.assertEqual(br["indicadores"]["total_base_g"], 611800)
        self.assertEqual(br["totais"]["situacao"], {"classificada": 598500, "fora": 13300})
        rj = self.client.get(f"{caminho}?nivel=uf&codigo=33&unidade=kg&escopo=local&ordem=asc&top=5").json()
        self.assertEqual(rj["indicadores"]["fontes"], 2)
        self.assertEqual(rj["indicadores"]["registros"], 3)
        self.assertEqual(rj["indicadores"]["total_g"], 332500)
        self.assertEqual([s["id"] for s in rj["ranking"]], ["RJ2", "RJ"])
        self.assertEqual(rj["ranking"][1]["valor"], 199.5)
        self.assertEqual(rj["ranking"][1]["potencia_mw"], 20)
        self.assertEqual(rj["ranking"][1]["consumo_gj"], 1500)
        grupo = self.client.get(f"{caminho}/coincidentes?lon=-43.25&lat=-22.92&nivel=uf&codigo=33").json()["fontes"]
        self.assertEqual([s["id"] for s in grupo], ["RJ", "RJ2"])
        csv_rj = self.client.get(f"{caminho}/fontes.csv?nivel=uf&codigo=33")
        self.assertEqual(csv_rj.headers["cache-control"], "no-store")
        fontes = list(csv.DictReader(io.StringIO(csv_rj.text)))
        self.assertEqual([s["id"] for s in fontes], ["RJ", "RJ2"])
        self.assertTrue(all(s["sigla_uf"] == "RJ" for s in fontes))
        self.assertTrue(all(s["pol_origem"] == "PM2.5" and s["ano"] == "2017" for s in fontes))
        self.assertEqual(rj["legenda"]["max"], 199.5)
        self.assertEqual(br["legenda"]["max"], 266000)
        sudeste = self.client.get(f"{caminho}?nivel=regiao&codigo=3&pontos=false").json()
        self.assertEqual(sudeste["indicadores"]["total_g"], 598500)
        self.assertEqual(sudeste["pontos"], [])
        vazio = self.client.get(f"{caminho}?nivel=uf&codigo=53").json()
        self.assertEqual(vazio["indicadores"]["fontes"], 0)
        url = f"{rota}/mapas/{serie}.svg?modo=territorial&nivel=uf&codigo=33&paleta=cividis"
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Rio de Janeiro", resposta.text)
        self.assertEqual(resposta.content, self.client.get(url).content)
        self.assertNotEqual(resposta.content, self.client.get(url.replace("codigo=33", "codigo=35")).content)
        self.assertEqual(self.client.get(f"{caminho}?nivel=uf&codigo=00").status_code, 400)
        self.assertEqual(self.client.post(f"{base}/especiacao").status_code, 200)
        rota_especiada = f"{base}/espacial/especiada"
        derivadas = self.client.post(rota_especiada).json()["series"]
        especie = next(s for s in derivadas if s["pol"] == "PSO4" and s["pol_origem"] == "PM2.5")
        consulta = self.client.get(f"{rota_especiada}/territorio/{especie['id']}?nivel=uf&codigo=33").json()
        self.assertEqual(consulta["serie"]["pol_origem"], "PM2.5")
        self.assertAlmostEqual(consulta["indicadores"]["total_g"], 332500 * .096)
        with TestClient(app, base_url="https://testserver") as outra:
            self.assertEqual(outra.get(caminho).status_code, 404)
            self.assertEqual(outra.get(url).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/inventarios/{inventario}").status_code, 200)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_grade_interseccao_e_coordenadas(self):
        def celula(codigo, esquerda, direita):
            return {"type": "Feature", "properties": {"id_grid": codigo}, "geometry": {
                "type": "Polygon", "coordinates": [[[esquerda, -25], [direita, -25],
                    [direita, -22], [esquerda, -22], [esquerda, -25]]]
            }}
        grade = Grade({"type": "FeatureCollection", "features": [celula("A", -48, -46),
                                                                 celula("B", -46, -44)]}, 4326)
        self.assertEqual(grade.localizar(-46.6, -23.5), ("A", "mapeada"))
        self.assertEqual(grade.localizar(-46, -23.5), (None, "ambigua"))
        self.assertEqual(grade.localizar(-50, -23.5), (None, "fora_grade"))
        feicao = celula("A", -48, -46)
        anel = feicao["geometry"]["coordinates"][0]
        projetar = Transformer.from_crs(4326, 5880, always_xy=True).transform
        feicao["geometry"]["coordinates"] = [[projetar(lon, lat) for lon, lat in anel]]
        projetada = Grade({"type": "FeatureCollection", "features": [feicao]}, 5880)
        self.assertEqual(projetada.localizar(-46.6, -23.5), ("A", "mapeada"))
        self.assertEqual(projetada.localizar(-50, -23.5), (None, "fora_grade"))
        self.assertIsNone(coordenadas({"lon": 181, "lat": -23.5}))
        self.assertIsNone(coordenadas({"lon": "NaN", "lat": -23.5}))
        self.assertFalse(escala_cores([0, 0], "log")[1])

    def test_espacial_conservacao_cache_e_exportacao(self):
        linhas = [(f"{i:04d}", "Biomass", 20, -23.5, lon, 2017, 1000, "extra")
                  for i, lon in enumerate((-46.6, -46.7, -50))]
        inventario = self.upload(linhas=linhas).json()["inventario_id"]
        calculo = self.calcular(inventario, "Biomass").json()["calculo_id"]
        raiz = f"/api/inventarios/{inventario}/calculos/{calculo}"
        rota = f"{raiz}/espacial/original"
        grade = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"id_grid": "A"}, "geometry": {
                "type": "Polygon", "coordinates": [[[-48, -25], [-46, -25], [-46, -22],
                                                    [-48, -22], [-48, -25]]]}
             }]}
        tracemalloc.start()
        try:
            resposta = self.client.post(rota, files={"grade": ("grade.geojson", json.dumps(grade))})
            _, pico = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(pico, 24 * 1024 * 1024)
        self.assertEqual(resposta.status_code, 200, resposta.text)
        dados = resposta.json()
        serie = next(x for x in dados["series"] if x["pol"] == "PM2.5")
        self.assertEqual(serie["massa_g"], 399000)
        self.assertEqual(serie["balanco_g"]["mapeada"], 266000)
        self.assertEqual(serie["balanco_g"]["fora_grade"], 133000)
        uri = f"{rota}/series/{serie['id']}"
        pontos = self.client.get(f"{uri}?interativo=true&unidade=kg").json()
        self.assertEqual(pontos["pontos"][0]["valor"], 133)
        self.assertEqual(pontos["fontes"][0]["id"], "0000")
        self.assertEqual(pontos["fontes"][0]["lat"], "-23.5")
        self.assertEqual(pontos["celulas"][0]["massa_g"], "266000.0")
        url = f"{rota}/mapas/{serie['id']}"
        for formato, marca in (("png", b"\x89PNG"), ("pdf", b"%PDF"), ("svg", b"<svg")):
            opcoes = "dpi=300&modo=grade&idioma=en&download=true"
            imagem = self.client.get(f"{url}.{formato}?{opcoes}")
            self.assertEqual(imagem.status_code, 200, imagem.text[:80])
            self.assertIn(marca, imagem.content[:500])
            self.assertEqual(imagem.headers["cache-control"], "no-store")
            self.assertIn("attachment", imagem.headers["content-disposition"])
            self.assertEqual(imagem.content, self.client.get(f"{url}.{formato}?{opcoes}").content)
        self.assertEqual(self.client.post(f"{raiz}/especiacao").status_code, 200)
        especiado = self.client.post(f"{raiz}/espacial/especiada").json()
        self.assertNotIn("PM2.5", [x["pol"] for x in especiado["series"]])
        self.assertTrue(any(x["pol"] == "PSO4" for x in especiado["series"]))
        with TestClient(app, base_url="https://testserver") as outra:
            self.assertEqual(outra.get(f"{url}.png").status_code, 404)
            self.assertEqual(outra.get(f"{rota}/arquivos/fontes.csv").status_code, 404)

    def setUp(self):
        self.storage = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(armazenamento, "STORAGE_DIR", self.storage))
        self.client = self.enterContext(TestClient(app, base_url="https://testserver"))

    def upload(self, combustivel="Biomass_thermal", *, formato="csv", linhas=None,
               ano="2017", consumo="1000"):
        if linhas is None:
            linhas = [("0001", combustivel, "20", "-23.5", "-46.6", ano, consumo, "extra")]
        if formato == "xlsx":
            conteudo = io.BytesIO()
            planilha = Workbook()
            planilha.active.append(CABECALHOS)
            for linha in linhas:
                planilha.active.append(linha)
            planilha.save(conteudo)
            planilha.close()
            arquivo = conteudo.getvalue()
        else:
            texto = io.StringIO()
            escritor = csv.writer(texto, delimiter=";" if formato == "csv" else "\t")
            escritor.writerow(CABECALHOS)
            escritor.writerows(linhas)
            arquivo = texto.getvalue().encode("utf-8-sig")
        resposta = self.client.post("/api/upload", files={"arquivo": (f"dados.{formato}", arquivo)})
        self.assertEqual(resposta.status_code, 200, resposta.text)
        self.assertEqual(resposta.headers["cache-control"], "no-store")
        return resposta

    def calcular(self, inventario, combustivel, selecoes=None, cliente=None):
        return (cliente or self.client).post(
            f"/api/inventarios/{inventario}/calcular",
            json={"setor": SETOR, "ano": 2017, "combustivel": combustivel,
                  "selecoes": selecoes or {}},
        )

    def analisar(self, combustivel):
        resposta = self.client.get("/api/fatores/analise",
                                   params={"setor": SETOR, "combustivel": combustivel})
        self.assertEqual(resposta.status_code, 200, resposta.text)
        return resposta.json()

    def test_rotas_publicas_e_base(self):
        for url in ("/", "/docs", "/openapi.json", "/static/script.js",
                    "/static/style.css", "/static/assets/logo-img.png",
                    "/static/assets/Pega-bravo.mp4", "/static/assets/video.mp4"):
            with self.subTest(url=url):
                self.assertEqual(self.client.head(url).status_code if url.startswith("/static/")
                                 else self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get("/api/health").json()["status"], "online")
        info = self.client.get("/api/fatores/info").json()
        self.assertEqual((info["versao_pega_r"], info["total_registros"], info["total_colunas"],
                          info["total_fatores_tier1"]), ("0.9.8", 39756, 17, 2169))
        self.assertIn(SETOR, self.client.get("/api/setores").json()["setores"])
        self.assertEqual(self.client.get("/api/setores/suportados").json()["setores"], [SETOR])
        fatores = self.client.get("/api/fatores", params={"setor": SETOR, "combustivel": "Biomass"})
        self.assertEqual(fatores.status_code, 200)
        self.assertEqual(fatores.json()["total_fatores"], 24)
        self.assertEqual(self.client.get("/api/fatores/analise",
                                       params={"setor": "outro", "combustivel": "Biomass"}).status_code, 400)

    def test_importacao_dos_tres_formatos(self):
        for formato in ("csv", "txt", "xlsx"):
            with self.subTest(formato=formato):
                resposta = self.upload(formato=formato)
                dados = resposta.json()
                self.assertTrue(dados["validacao"]["valido"])
                self.assertEqual(dados["validacao"]["anos"], ["2017"])
                self.assertEqual(dados["validacao"]["combustiveis"], ["Biomass_thermal"])
                self.assertEqual(dados["previa"][0]["ID"], "0001")
                self.assertEqual(dados["colunas_extras"], ["nota"])
                pasta = self.storage / dados["inventario_id"]
                self.assertTrue((pasta / f"original.{formato}").is_file())
                self.assertTrue((pasta / "dados.csv").is_file())
                cookie = resposta.headers["set-cookie"].lower()
                for atributo in ("httponly", "samesite=strict", "max-age=86400"):
                    self.assertIn(atributo, cookie)

    def test_importacao_invalida(self):
        for parametros in ({"ano": "1899"}, {"consumo": "-1"}, {"consumo": "inf"},
                           {"consumo": ""}):
            with self.subTest(parametros=parametros):
                dados = self.upload(**parametros).json()
                self.assertFalse(dados["validacao"]["valido"])
                self.assertTrue(dados["validacao"]["problemas"])
                self.assertIsNone(dados["inventario_id"])
        for nome, conteudo in (
            ("dados.xlsx", b"arquivo danificado"),
            ("dados.csv", b"id;ID;ano\n1;2;2017\n"),
            ("dados.csv", b"id;ano\n1;2017\n"),
            ("dados.pdf", b"formato invalido"),
        ):
            with self.subTest(nome=nome, conteudo=conteudo):
                resposta = self.client.post("/api/upload", files={"arquivo": (nome, conteudo)})
                self.assertEqual(resposta.status_code, 400, resposta.text)
        self.assertEqual(list(self.storage.iterdir()), [])

    def test_limite_de_upload(self):
        with patch("backend.api.MAX_UPLOAD", 4):
            resposta = self.client.post("/api/upload", files={"arquivo": ("dados.csv", b"12345")})
        self.assertEqual(resposta.status_code, 413)
        self.assertEqual(list(self.storage.iterdir()), [])

    def test_biomassa_e_persistencia(self):
        linhas = [(f"{i:04d}", "Biomass_thermal", 20, -23.5, -46.6, 2017, 1000 + i)
                  for i in range(505)]
        linhas.extend([("zero", "Biomass", 20, 0, 0, 2017, 0),
                       ("outro-ano", "Biomass", 20, 0, 0, 2018, 9999),
                       ("outro-fuel", "Biogas", 20, 0, 0, 2017, 9999)])
        inventario = self.upload(linhas=linhas).json()["inventario_id"]
        resposta = self.calcular(inventario, "Biomass")
        self.assertEqual(resposta.status_code, 200, resposta.text)
        self.assertEqual(resposta.headers["cache-control"], "no-store")
        dados = resposta.json()
        self.assertEqual(dados["total_atividades"], 505)
        self.assertEqual(dados["total_fontes"], 505)
        self.assertEqual(dados["total_poluentes"], 24)
        self.assertEqual(dados["total_registros"], 12120)
        consumo = sum(range(1000, 1505))
        self.assertEqual(dados["consumo_total_GJ"], consumo)
        self.assertEqual(dados["unidade_emissoes"], "g")
        self.assertEqual(dados["avisos"][0]["tipo"], "consumo_zero")
        self.assertEqual(dados["avisos"][0]["quantidade"], 1)
        resumo = {linha["pol"]: linha["emissions"] for linha in dados["resumo"]}
        self.assertEqual(resumo["PM2.5"], consumo * 133)
        self.assertTrue(math.isclose(resumo["BC"], consumo * 133 * 0.033, rel_tol=1e-14))
        pasta = self.storage / inventario / "calculos" / dados["calculo_id"]
        self.assertEqual({f.name for f in pasta.iterdir()},
                         {"metadados.json", "emissoes_base.csv", "resumo.csv", "fatores_utilizados.csv"})
        salvo = json.loads((pasta / "metadados.json").read_text(encoding="utf-8"))
        self.assertEqual(salvo, {k: v for k, v in dados.items() if k != "previa"})
        with (pasta / "emissoes_base.csv").open(encoding="utf-8", newline="") as arquivo:
            emissoes = list(csv.DictReader(arquivo))
        self.assertEqual(len(emissoes), 12120)
        self.assertEqual(emissoes[0]["id"], "0000")
        for linha in emissoes:
            consumo_linha = 1000 + int(linha["id"])
            fator = float(linha["ef"])
            esperado = consumo_linha * (133 if linha["pol"] == "BC" else 1) * fator
            self.assertTrue(math.isclose(float(linha["emissions"]), esperado, rel_tol=1e-14))
        with (pasta / "fatores_utilizados.csv").open(encoding="utf-8", newline="") as arquivo:
            fatores = {fator["pol"]: fator for fator in csv.DictReader(arquivo)}
        self.assertEqual(float(fatores["BC"]["ef"]), 0.033)
        self.assertEqual(fatores["BC"]["unit"], "fraction of PM2.5")
        self.assertTrue(fatores["BC"]["reference"])
        with (pasta / "resumo.csv").open(encoding="utf-8", newline="") as arquivo:
            self.assertEqual({r["pol"]: float(r["emissions"]) for r in csv.DictReader(arquivo)}, resumo)
        nova = self.calcular(inventario, "Biomass")
        self.assertEqual(nova.status_code, 200, nova.text)
        self.assertEqual(nova.json()["configuracao_id"], dados["configuracao_id"])
        self.assertNotEqual(nova.json()["calculo_id"], dados["calculo_id"])
        self.assertEqual(len(list(pasta.parent.iterdir())), 2)

    def test_consulta_download_e_isolamento_das_execucoes(self):
        resposta = self.upload()
        inventario = resposta.json()["inventario_id"]
        rota = f"/api/inventarios/{inventario}"
        inventario_salvo = self.client.get(rota).json()
        self.assertEqual(inventario_salvo["previa"], resposta.json()["previa"])
        self.assertEqual(inventario_salvo["colunas_extras"], ["nota"])
        self.assertEqual(inventario_salvo["atividades"], [{
            "ano": "2017", "combustivel_original": "Biomass_thermal", "combustivel": "Biomass"
        }])
        self.assertEqual(self.client.get(f"{rota}/calculos").json(), {"calculos": []})
        calculo = self.calcular(inventario, "Biomass").json()
        caminho = f'{rota}/calculos/{calculo["calculo_id"]}'
        consulta = self.client.get(caminho)
        self.assertEqual(consulta.status_code, 200)
        self.assertEqual(consulta.headers["cache-control"], "no-store")
        self.assertEqual(consulta.json()["resumo"], calculo["resumo"])
        self.assertEqual(consulta.json()["previa"][0]["id"], "0001")
        lista = self.client.get(f"{rota}/calculos")
        self.assertEqual(lista.headers["cache-control"], "no-store")
        self.assertEqual([item["calculo_id"] for item in lista.json()["calculos"]], [calculo["calculo_id"]])
        for nome in armazenamento.ARQUIVOS_CALCULO:
            with self.subTest(nome=nome):
                arquivo = self.client.get(f"{caminho}/arquivos/{nome}")
                self.assertEqual(arquivo.status_code, 200)
                self.assertEqual(arquivo.headers["cache-control"], "no-store")
                self.assertIn("attachment", arquivo.headers["content-disposition"])
                self.assertIn(nome, arquivo.headers["content-disposition"])
                self.assertTrue(arquivo.content)
        self.assertEqual(self.client.get(f"{caminho}/arquivos/dados.csv").status_code, 404)
        self.assertEqual(self.client.get(f"{rota}/calculos/invalido").status_code, 404)
        with TestClient(app, base_url="https://testserver") as outra:
            with patch.object(self, "client", outra):
                outro = self.upload().json()["inventario_id"]
            for url in (f"{rota}/calculos", caminho, f"{caminho}/arquivos/resumo.csv",
                        f'/api/inventarios/{outro}/calculos/{calculo["calculo_id"]}'):
                resposta = outra.get(url)
                self.assertEqual(resposta.status_code, 404)
                self.assertEqual(resposta.headers["cache-control"], "no-store")
        self.assertEqual(self.client.delete(rota).status_code, 200)
        self.assertEqual(self.client.get(f"{caminho}/arquivos/resumo.csv").status_code, 404)

    def test_especiacao_fracoes_massa_e_rastreabilidade(self):
        # Referência calculada a partir das 45 linhas extraídas diretamente do R.
        perfil_serializado = json.dumps(
            [(origem, *linha) for origem, grupo in PERFIL.items() for linha in grupo],
            separators=(",", ":"),
        ).encode()
        self.assertEqual(hashlib.sha256(perfil_serializado).hexdigest(),
                         "92605bfaf259f1bbcd8eccf7694c265a9a0e0f56d438941f86f109d8e3c956ad")
        base = pd.DataFrame({
            "pol": ["PM2.5", "SOx", "NOx", "NMVOC", "BC"],
            "emissions": [1000.0] * 5, "unit_emissions": ["g"] * 5,
            "id": ["0007"] * 5, "lat": [-23.5] * 5, "lon": [-46.6] * 5,
        })
        resultado, resumo, perfil, balanco, avisos = especiar_emissoes(base)
        self.assertEqual(perfil.groupby("pol_origem").size().to_dict(),
                         {"PM2.5": 16, "SOx": 2, "NOx": 2, "NMVOC": 25})
        self.assertEqual(len(resultado), 46)
        self.assertEqual(set(resultado["id"]), {"0007"})
        self.assertEqual(set(resultado["lat"]), {-23.5})
        self.assertEqual(set(resultado["lon"]), {-46.6})
        saida = resumo.set_index(["pol_origem", "pol"])["emissions"]
        self.assertEqual(saida[("PM2.5", "PSO4")], 96)
        self.assertEqual(saida[("SOx", "PSO4")], 50)
        self.assertEqual(saida[("BC", "BC")], 1000)
        self.assertAlmostEqual(saida[("NMVOC", "BENZENE")], .000001)
        dados_perfil = perfil.set_index(["pol_origem", "especie"])
        self.assertEqual(dados_perfil.loc[("NOx", "HONO"), "mw"], 47.01)
        self.assertTrue(pd.isna(dados_perfil.loc[("PM2.5", "PAL"), "mw"]))
        for grupo, esperado in zip(balanco, [5.7, 0, 0, .870869], strict=True):
            self.assertAlmostEqual(grupo["residuo_g"], esperado)
        self.assertEqual(len(avisos), 2)
        self.assertEqual(list(base["emissions"]), [1000.0] * 5)

    def test_especiacao_privada_e_persistente(self):
        inventario = self.upload().json()["inventario_id"]
        calculo = self.calcular(inventario, "Biomass").json()["calculo_id"]
        raiz = f"/api/inventarios/{inventario}/calculos/{calculo}"
        original = self.client.get(f"{raiz}/arquivos/emissoes_base.csv").content
        rota = f"{raiz}/especiacao"
        self.assertEqual(self.client.get(rota).status_code, 404)
        resposta = self.client.post(rota)
        self.assertEqual(resposta.status_code, 200, resposta.text)
        dados = resposta.json()
        self.assertEqual(dados["calculo_id"], calculo)
        self.assertEqual(self.client.post(rota).json(), dados)
        self.assertEqual(self.client.get(rota).json(), dados)
        self.assertEqual(self.client.get(f"{rota}/resumo").json()["resumo"], dados["resumo"])
        self.assertEqual(self.client.get(f"{raiz}/arquivos/emissoes_base.csv").content, original)
        for nome in ARQUIVOS_ESPECIACAO:
            resposta = self.client.get(f"{rota}/arquivos/{nome}")
            self.assertEqual(resposta.status_code, 200)
            self.assertEqual(resposta.headers["cache-control"], "no-store")
            self.assertIn(nome, resposta.headers["content-disposition"])
        derivado = self.client.get(f"{rota}/arquivos/emissoes_especiadas.csv")
        original_linha = next(csv.DictReader(io.StringIO(original.decode())))
        derivado_linha = next(csv.DictReader(io.StringIO(derivado.text)))
        for coluna in ("registro_id", "id", "lat", "lon", "reference", "fator_id"):
            self.assertEqual(derivado_linha[coluna], original_linha[coluna])
        with TestClient(app, base_url="https://testserver") as outra:
            self.assertEqual(outra.post(rota).status_code, 404)
            self.assertEqual(outra.get(rota).status_code, 404)
            self.assertEqual(outra.get(f"{rota}/arquivos/resumo_especies.csv").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/inventarios/{inventario}").status_code, 200)
        self.assertEqual(self.client.get(f"{rota}/arquivos/resumo_especies.csv").status_code, 404)

    def test_temporal_preserva_massas_separa_bases_e_protege_download(self):
        inventario = self.upload().json()["inventario_id"]
        calculo = self.calcular(inventario, "Biomass").json()
        base = f"/api/inventarios/{inventario}/calculos/{calculo['calculo_id']}"
        original = f"{base}/temporal/original"
        especiada = f"{base}/temporal/especiada"
        self.assertEqual(self.client.post(especiada).status_code, 404)
        resposta = self.client.post(original)
        self.assertEqual(resposta.status_code, 200, resposta.text)
        dados = resposta.json()
        self.assertEqual(dados, self.client.get(original).json())
        self.assertEqual([len(dados[c]) for c in ("horario", "semanal", "combinado")], [24, 7, 168])
        for chave in ("horario", "semanal", "combinado"):
            self.assertAlmostEqual(dados["somas_pesos"][chave], 1)
        bruto = [.030, .030, .031, .033, .037, .045, .050, .050, .050, .051, .051, .048,
                 .045, .040, .041, .041, .041, .048, .050, .048, .043, .036, .031, .030]
        self.assertEqual([h["peso_original"] for h in dados["horario"]], bruto)
        self.assertEqual([d["peso"] for d in dados["semanal"]], [.1428] * 6 + [.1432])
        self.assertAlmostEqual(dados["combinado"][0]["peso"], .1428 * .030 / sum(bruto))
        self.assertEqual(self.client.post(f"{base}/especiacao").status_code, 200)
        derivado = self.client.post(especiada).json()
        self.assertTrue(any(row["especiado"] for row in derivado["resumo"]))
        self.assertFalse(any(row["pol"] == "PM2.5" for row in derivado["resumo"]))
        saldo = next(row for row in derivado["balanco_especiacao"] if row["pol_origem"] == "PM2.5")
        self.assertAlmostEqual(saldo["residuo_g"], 133000 * .0057)
        url = f"{especiada}/arquivos/alocacao_relativa.csv"
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.headers["cache-control"], "no-store")
        linhas = [row for row in csv.DictReader(io.StringIO(resposta.text))
                  if row["pol_origem"] == "PM2.5"]
        self.assertTrue(all(row["id"] == "0001" and float(row["lat"]) == -23.5 for row in linhas))
        self.assertEqual(len(linhas), 16 * 168)
        self.assertAlmostEqual(math.fsum(float(row["massa_alocada_g"]) for row in linhas),
                               133000 - saldo["residuo_g"])
        self.assertEqual(self.client.get(f"{original}/arquivos/perfil_temporal.json").json(), dados)
        with TestClient(app, base_url="https://testserver") as outra:
            self.assertEqual(outra.post(original).status_code, 404)
            self.assertEqual(outra.get(url).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/inventarios/{inventario}").status_code, 200)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_consumo_total_acima_do_limite_de_int64(self):
        linhas = [(str(i), "Biomass", 20, 0, 0, 2017, 5_000_000_000_000_000_000)
                  for i in range(2)]
        inventario = self.upload(linhas=linhas).json()["inventario_id"]
        resposta = self.calcular(inventario, "Biomass")
        self.assertEqual(resposta.status_code, 200, resposta.text)
        self.assertEqual(resposta.json()["consumo_total_GJ"], 1e19)

    def test_escolhas_obrigatorias(self):
        for combustivel, poluente, valores in (
            ("Natural Gas", "SOx", {0.281, 0.244}),
            ("Brown Coal", "Cu", {0.001, 0.00027}),
        ):
            with self.subTest(combustivel=combustivel):
                inventario = self.upload(combustivel).json()["inventario_id"]
                analise = self.analisar(combustivel)
                self.assertTrue(analise["requer_escolha"])
                grupo, = analise["escolhas"]
                self.assertEqual(grupo["poluente"], poluente)
                self.assertEqual({opcao["ef"] for opcao in grupo["opcoes"]}, valores)
                self.assertEqual(len({opcao["reference"] for opcao in grupo["opcoes"]}), 2)
                for selecao in ({}, {poluente: "invalido"}, {"outro": "invalido"}):
                    self.assertEqual(self.calcular(inventario, combustivel, selecao).status_code, 400)
                self.assertFalse((self.storage / inventario / "calculos").exists())
                for opcao in grupo["opcoes"]:
                    selecao = {poluente: opcao["fator_id"]}
                    resposta = self.calcular(inventario, combustivel, selecao)
                    self.assertEqual(resposta.status_code, 200, resposta.text)
                    dados = resposta.json()
                    self.assertEqual(dados["selecoes"], selecao)
                    fator, = [f for f in dados["fatores_utilizados"] if f["pol"] == poluente]
                    self.assertEqual(fator["reference"], opcao["reference"])
                    linha, = [r for r in dados["resumo"] if r["pol"] == poluente]
                    self.assertAlmostEqual(linha["emissions"], 1000 * opcao["ef"])

    def test_biogas_e_outros_combustiveis(self):
        combustiveis = self.client.get(f"/api/setores/{SETOR}/combustiveis").json()["combustiveis"]
        restantes = {"Biogas", "Blast furnace/Basic O2 furnace gas", "Hard Coal",
                     "Heavy Fuel Oil", "Oil Gas"}
        self.assertEqual(set(combustiveis), restantes | {"Biomass", "Brown Coal", "Natural Gas"})
        for combustivel in sorted(restantes):
            with self.subTest(combustivel=combustivel):
                inventario = self.upload(combustivel).json()["inventario_id"]
                analise = self.analisar(combustivel)
                self.assertFalse(analise["requer_escolha"])
                resposta = self.calcular(inventario, combustivel)
                self.assertEqual(resposta.status_code, 200, resposta.text)
                dados = resposta.json()
                resumo = {r["pol"]: r["emissions"] for r in dados["resumo"]}
                self.assertEqual(set(resumo), {f["pol"] for f in analise["automaticos"]})
                for fator in analise["automaticos"]:
                    base = resumo["PM2.5"] if fator["pol"] == "BC" else 1000
                    self.assertAlmostEqual(resumo[fator["pol"]], base * fator["ef"])
                if combustivel == "Biogas":
                    self.assertNotIn("Pb", resumo)
                    indisponivel, = [f for f in analise["indisponiveis"] if f["pol"] == "Pb"]
                    self.assertIsNone(indisponivel["ef"])
                    aviso, = [a for a in dados["avisos"] if a["poluente"] == "Pb"]
                    for chave in ("fator_id", "reference", "motivo"):
                        self.assertEqual(aviso[chave], indisponivel[chave])

    def test_isolamento_e_exclusao(self):
        inventario = self.upload().json()["inventario_id"]
        rota = f"/api/inventarios/{inventario}"
        with TestClient(app, base_url="https://testserver") as outra:
            self.assertEqual(outra.get(rota).status_code, 404)
            with patch.object(self, "client", outra):
                outro_id = self.upload().json()["inventario_id"]
            self.assertEqual(outra.get(rota).status_code, 404)
            self.assertEqual(outra.delete(rota).status_code, 404)
            self.assertEqual(self.calcular(inventario, "Biomass", cliente=outra).status_code, 404)
            self.assertEqual(self.client.get(f"/api/inventarios/{outro_id}").status_code, 404)
        resposta = self.client.get(rota)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.headers["cache-control"], "no-store")
        self.assertNotIn("sessao_hash", resposta.json())
        criado = datetime.fromisoformat(resposta.json()["criado_em"])
        expira = datetime.fromisoformat(resposta.json()["expira_em"])
        self.assertEqual(expira - criado, timedelta(hours=24))
        self.assertEqual(self.calcular(inventario, "Biomass").status_code, 200)
        self.assertEqual(self.client.get(f"/static/{inventario}/dados.csv").status_code, 404)
        self.assertEqual(self.client.delete(rota).status_code, 200)
        self.assertEqual(self.client.get(rota).status_code, 404)
        self.assertFalse((self.storage / inventario).exists())
        self.assertTrue((self.storage / outro_id).exists())

    def test_expiracao_no_acesso_e_na_limpeza(self):
        for acesso in (True, False):
            with self.subTest(acesso=acesso):
                inventario = self.upload().json()["inventario_id"]
                pasta = self.storage / inventario
                arquivo = pasta / "metadados.json"
                metadados = json.loads(arquivo.read_text(encoding="utf-8"))
                metadados["expira_em"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
                arquivo.write_text(json.dumps(metadados), encoding="utf-8")
                if acesso:
                    self.assertEqual(self.client.get(f"/api/inventarios/{inventario}").status_code, 404)
                else:
                    self.assertEqual(armazenamento.limpar_expirados(), 1)
                self.assertFalse(pasta.exists())
