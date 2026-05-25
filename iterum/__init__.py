"""Iterum - CX Management Platform.

Convierte cada experiencia negativa en un ciclo de mejora continua.

Capacidades:
- Ingesta incremental/historica de XLSX (NPS)
- Dashboard operativo, ranking y analisis semantico
- Causa raiz (5 Porques)
- Auditoria operativa con trazabilidad legal
- Coaching y presentacion ejecutiva (PDF nativo)

Modulo organizado en capas: routes (vistas) / api (JSON) / services (logica) /
models (ORM). Cada archivo bajo 500 lineas — si crece, se parte.
"""
from .routes import iterum_bp

__all__ = ['iterum_bp']
