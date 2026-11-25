import tempfile
import unittest
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from backend.services.auditoria_wrf import auditar, auditar_geometria, auditar_relogio
from backend.services.wrf import DominioWRF
from tests.fixtures_wrf import dominio_sintetico


class AuditoriaWrfTest(unittest.TestCase):
    def setUp(self):
        self.pasta = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def test_centros_vertices_limites_e_exterior_em_tres_resolucoes(self):
        arquivo = self.pasta / "dominio"
        for dx, dy in [(1000, 1500), (3000, 4000), (18000, 20000)]:
            with self.subTest(dx=dx, dy=dy):
                dominio_sintetico(arquivo, dx=dx, dy=dy)
                relatorio = auditar_geometria(DominioWRF(arquivo))
                self.assertEqual(relatorio["centros"], 6)
                self.assertEqual(relatorio["centros_nos_indices_esperados"], 6)
                self.assertLess(relatorio["erro_euclidiano_m"]["max"], 1e-6)
                self.assertLess(relatorio["erro_ida_volta_m"]["max"], 1e-6)
                self.assertEqual(len(relatorio["casos_de_borda"]), 12)
                self.assertTrue(all(c["confere"] for c in relatorio["casos_de_borda"]))

    def test_areas_geodesicas_integral_e_mapfac(self):
        arquivo = self.pasta / "wrfinput_d01"
        dominio_sintetico(arquivo)
        primeira = auditar(arquivo, [])["dominio"]
        self.assertFalse(primeira["sufixo_confere_com_grid_id"])
        area = primeira["areas"]
        self.assertEqual(area["amostra_geodesica_celulas"], 6)
        self.assertLess(max(abs(v) for v in area["diferenca_geodesica_vs_integral_pct"].values()), 1e-4)
        self.assertIsNone(area["aproximacao_por_mapfac"])
        with Dataset(arquivo, "a") as nc:
            for nome, fator in (("MAPFAC_MX", 1.02), ("MAPFAC_MY", .98)):
                var = nc.createVariable(nome, "f8", ("south_north", "west_east"))
                var[:] = fator
        relatorio = auditar(arquivo, [])["dominio"]["areas"]
        esperado = 3000 * 4000 / (1.02 * .98)
        self.assertAlmostEqual(relatorio["aproximacao_por_mapfac"]["area_m2"]["min"], esperado)
        self.assertEqual(relatorio["campos_mapfac_presentes"], ["MAPFAC_MX", "MAPFAC_MY"])

    def test_alvo_relata_horario_unidades_e_forma_sem_aprovar_mapeamento(self):
        dominio = self.pasta / "wrfinput_d01"
        alvo = self.pasta / "wrfchemi_00z_d02"
        dominio_sintetico(dominio)
        dominio_sintetico(alvo)
        with Dataset(alvo, "a") as nc:
            nc.createDimension("emissions_zdim_stag", 1)
            nc.createDimension("DateStrLen", 19)
            nc.createVariable("Times", "S1", ("Time", "DateStrLen"))[0] = np.asarray(
                list("2020-01-01_00:00:00"), dtype="S1")
            nc.createVariable("E_SO2", "f4", ("Time", "emissions_zdim_stag", "south_north", "west_east")
                              ).units = "ug m^-2 s^-1"
            nc.createVariable("E_PS0", "f4", ("Time", "west_east")).units = "ug m^-2 s^-1"
        relatorio = auditar(dominio, [alvo])["alvos"][0]
        self.assertTrue(relatorio["dimensoes_horizontais_conferem"])
        self.assertEqual(relatorio["coordenadas"]["desvio_vs_dominio_m"]["max"], 0)
        self.assertTrue(relatorio["times"]["valido"])
        self.assertFalse(relatorio["times"]["fuso_codificado"])
        self.assertFalse(relatorio["variaveis"]["E_PS0"]["ordem_esperada"])
        so2 = next(s for s in relatorio["correspondencia_nominal"] if s["especie"] == "SO2")
        self.assertTrue(so2["encontrada"])
        self.assertFalse(so2["unidade_coincide_com_r"])
        self.assertFalse(so2["mapeamento_aprovado"])
        self.assertEqual(len([s for s in relatorio["correspondencia_nominal"] if s["especie"] == "PSO4"]), 2)

    def test_relogio_iana_historico_e_duracao_civil(self):
        relogio = auditar_relogio(2018, "America/Sao_Paulo")
        self.assertEqual(relogio["horas_inteiras"], 8760)
        self.assertEqual((relogio["rotulos_ausentes"], relogio["rotulos_repetidos"]), (1, 1))
        transicao = auditar_relogio(2019, "America/Sao_Paulo")
        self.assertEqual(transicao["horas_inteiras"], 8761)
        self.assertEqual((transicao["rotulos_ausentes"], transicao["rotulos_repetidos"]), (0, 1))
        utc = auditar_relogio(2020, "UTC")
        self.assertEqual(utc["horas_inteiras"], 8784)
        self.assertFalse(utc["subdivisao_temporal_a_avaliar"])
