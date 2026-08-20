"""Compatibilidade com o caminho antigo do adaptador SEFAZ direta.

Novas configurações devem usar ``apps.fiscal.sefaz_direta.SefazDiretaAdapter``.
"""

from .sefaz_direta import *  # noqa: F401,F403
