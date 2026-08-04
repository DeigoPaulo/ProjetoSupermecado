import hashlib
from pathlib import Path

from django.utils import timezone

from .deployment_evidence import validar_dossie_implantacao
from .post_deployment import diagnostico_pos_implantacao_local


def gerar_evidencia_aceite(
    caminho_dossie,
    *,
    url=None,
    timeout=5,
    idade_maxima_backup_horas=36,
    pos_implantacao=None,
):
    caminho_dossie = Path(caminho_dossie)
    try:
        hash_dossie = hashlib.sha256(caminho_dossie.read_bytes()).hexdigest()
    except OSError:
        hash_dossie = ""
    validacao = validar_dossie_implantacao(caminho_dossie)
    pos_implantacao = pos_implantacao or diagnostico_pos_implantacao_local(
        url=url,
        timeout=timeout,
        idade_maxima_backup_horas=idade_maxima_backup_horas,
    )
    bloqueios = [f"dossie: {item}" for item in validacao["erros"] + validacao["avisos"]]
    bloqueios.extend(f"pos_implantacao: {item}" for item in pos_implantacao["bloqueios"])
    liberavel = bool(validacao["liberavel"] and pos_implantacao["pronto"])
    return {
        "contrato": "local_installation_acceptance_evidence_v1",
        "gerado_em": timezone.now().isoformat(),
        "perfil": validacao["perfil"],
        "alvo": validacao["alvo"],
        "liberavel": liberavel,
        "status": "ready" if liberavel else "blocked",
        "dossie": {
            "sha256": hash_dossie,
            "validacao": validacao,
        },
        "pos_implantacao": pos_implantacao,
        "bloqueios": list(dict.fromkeys(bloqueios)),
        "seguranca": {
            "segredos_expostos": False,
            "caminhos_absolutos_expostos": False,
        },
    }
