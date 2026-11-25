"""Leitura conservadora da grade de massa Lambert do WRF."""

import math
from threading import Lock

import numpy as np
from netCDF4 import Dataset
from pyproj import CRS, Transformer


NETCDF_LOCK = Lock()
RAIO_WRF = 6_370_000
MAX_CELULAS = 500_000
DIMENSOES = ("south_north", "west_east")


def atributo(dataset, nome):
    try:
        valor = float(dataset.getncattr(nome))
    except (AttributeError, TypeError, ValueError) as erro:
        raise ValueError(f"Atributo WRF ausente ou inválido: {nome}.") from erro
    if not math.isfinite(valor):
        raise ValueError(f"Atributo WRF não finito: {nome}.")
    return valor


def coordenada(dataset, nome):
    if nome not in dataset.variables:
        raise ValueError(f"O domínio deve fornecer {nome}.")
    variavel = dataset.variables[nome]
    if variavel.dimensions == DIMENSOES:
        valores = variavel[:, :]
    elif variavel.dimensions == ("Time", *DIMENSOES) and variavel.shape[0] == 1:
        valores = variavel[0, :, :]
    else:
        raise ValueError(f"{nome} deve estar na grade de massa, estática e sem dimensões alternadas.")
    if np.ma.is_masked(valores) or not np.isfinite(valores).all():
        raise ValueError(f"{nome} contém coordenadas ausentes ou não finitas.")
    return np.asarray(valores, dtype=float)


class DominioWRF:
    def __init__(self, arquivo):
        with arquivo.open("rb") as entrada:
            assinatura = entrada.read(8)
        if assinatura[:4] not in (b"CDF\x01", b"CDF\x02", b"CDF\x05") and assinatura != b"\x89HDF\r\n\x1a\n":
            raise ValueError("O domínio deve ser um arquivo NetCDF local.")
        try:
            with NETCDF_LOCK, Dataset(arquivo, mode="r") as dataset:
                self.ler(dataset)
        except (OSError, RuntimeError) as erro:
            raise ValueError("Não foi possível ler o domínio NetCDF.") from erro

    def ler(self, dataset):
        if atributo(dataset, "MAP_PROJ") != 1:
            raise ValueError("A exportação atual aceita domínio Lambert do WRF (MAP_PROJ=1).")
        tamanhos = [len(dataset.dimensions[d]) if d in dataset.dimensions else 0 for d in DIMENSOES]
        self.ny, self.nx = tamanhos
        if min(tamanhos) < 2 or self.nx * self.ny > MAX_CELULAS:
            raise ValueError("Dimensões da grade de massa inválidas ou acima do limite de 500.000 células.")
        gid = atributo(dataset, "GRID_ID")
        if not gid.is_integer() or gid < 1:
            raise ValueError("GRID_ID deve ser um inteiro positivo.")
        self.grid_id = int(gid)
        self.dx, self.dy = (atributo(dataset, nome) for nome in ("DX", "DY"))
        if min(self.dx, self.dy) <= 0:
            raise ValueError("DX e DY devem ser positivos, em metros projetados.")
        self.lat = coordenada(dataset, "XLAT")
        self.lon = coordenada(dataset, "XLONG")
        if np.any(np.abs(self.lat) > 90) or np.any(np.abs(self.lon) > 180):
            raise ValueError("As coordenadas geográficas do domínio estão fora dos limites válidos.")
        lat0 = atributo(dataset, "MOAD_CEN_LAT" if "MOAD_CEN_LAT" in dataset.ncattrs() else "CEN_LAT")
        lon0 = atributo(dataset, "STAND_LON")
        lat1, lat2 = (atributo(dataset, nome) for nome in ("TRUELAT1", "TRUELAT2"))
        self.crs = CRS.from_proj4(
            f"+proj=lcc +lat_0={lat0} +lon_0={lon0} +lat_1={lat1} +lat_2={lat2} +R={RAIO_WRF} +units=m"
        )
        self.projetar = Transformer.from_crs(self.crs.geodetic_crs, self.crs, always_xy=True).transform
        px, py = self.projetar(self.lon, self.lat)
        if not np.isfinite(px).all() or not np.isfinite(py).all():
            raise ValueError("A projeção não produz coordenadas finitas.")
        j, i = np.arange(self.nx), np.arange(self.ny)
        self.x = np.median(px - j * self.dx) + j * self.dx
        self.y = np.median(py - i[:, None] * self.dy) + i * self.dy
        self.erro_m = float(max(np.max(np.abs(px - self.x)), np.max(np.abs(py - self.y[:, None]))))
        # Margem para a precisão de XLAT/XLONG de ponto flutuante e rejeição de outra malha.
        if self.erro_m > min(5.0, min(self.dx, self.dy) * .01):
            raise ValueError("XLAT/XLONG não reproduzem a grade retangular Lambert declarada por DX/DY.")
        self.borda_m = max(1e-6, self.erro_m)

    def localizar(self, lon, lat):
        x, y = self.projetar(lon, lat)
        if not (math.isfinite(x) and math.isfinite(y)):
            return None, "fora_grade"
        coluna = (x - self.x[0]) / self.dx + .5
        linha = (y - self.y[0]) / self.dy + .5
        tolerancia_x, tolerancia_y = self.borda_m / self.dx, self.borda_m / self.dy
        if (coluna < -tolerancia_x or coluna > self.nx + tolerancia_x
                or linha < -tolerancia_y or linha > self.ny + tolerancia_y):
            return None, "fora_grade"
        if (abs(coluna - round(coluna)) <= tolerancia_x or abs(linha - round(linha)) <= tolerancia_y):
            return None, "borda_grade"
        return (math.floor(linha), math.floor(coluna)), "mapeada"
