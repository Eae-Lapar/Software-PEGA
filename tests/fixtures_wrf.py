"""Domínio Lambert pequeno com posições geradas por projeção inversa."""

import numpy as np
from netCDF4 import Dataset
from pyproj import CRS, Transformer


def dominio_sintetico(caminho, modo=1, corromper=False, com_tempo=True, dx=3000.0, dy=4000.0):
    attrs = dict(MAP_PROJ=modo, GRID_ID=2, DX=dx, DY=dy,
                 MOAD_CEN_LAT=-23.5, STAND_LON=-46.6, TRUELAT1=-20.0, TRUELAT2=-30.0)
    crs = CRS.from_proj4("+proj=lcc +lat_0=-23.5 +lon_0=-46.6 +lat_1=-20 +lat_2=-30 +R=6370000")
    inversa = Transformer.from_crs(crs, crs.geodetic_crs, always_xy=True).transform
    px, py = np.meshgrid(np.arange(3) * attrs["DX"], np.arange(2) * attrs["DY"])
    lon, lat = inversa(px, py)
    if corromper:
        lon[1, 2] += .02
    with Dataset(caminho, "w", format="NETCDF3_CLASSIC") as nc:
        nc.setncatts(attrs)
        nc.createDimension("south_north", 2)
        nc.createDimension("west_east", 3)
        dims = ("south_north", "west_east")
        if com_tempo:
            nc.createDimension("Time", 1)
            dims = ("Time", *dims)
        for nome, valores in (("XLAT", lat), ("XLONG", lon)):
            campo = nc.createVariable(nome, "f8", dims)
            if com_tempo:
                campo[0] = valores
            else:
                campo[:] = valores
    return inversa
