"""Extraccion de metricas de embudo conversacional de Botmaker para SQL Server / Power BI."""
from .config import cargar_env

# Antes que nada: api.py lee variables de entorno al importarse.
cargar_env()

__version__ = "1.1.0"
