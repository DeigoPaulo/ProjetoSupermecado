import hashlib
import hmac
import json
import re

from django.conf import settings



ITENS_HOMOLOGACAO_SERVIDOR_LOCAL = (
    ("INSTALACAO_LIMPA", "Instalação do pacote em máquina limpa"),
    ("SERVICO_HEALTH", "Serviço Windows, inicialização e healthcheck"),
    ("BANCO_MIGRACOES", "PostgreSQL, migrations e acesso administrativo"),
    ("BACKUP_RESTAURACAO", "Backup e restauração testados"),
    ("ATUALIZACAO_ROLLBACK", "Atualização e rollback testados"),
    ("SEGURANCA_ACESSO", "Permissões, auditoria e acesso restrito"),
    ("PDV_REDE_LOCAL", "Ativação e acesso do PDV pela rede local"),
)
CODIGOS_CRITICOS_HOMOLOGACAO_SERVIDOR_LOCAL = frozenset(
    codigo for codigo, _ in ITENS_HOMOLOGACAO_SERVIDOR_LOCAL
)
ROTULOS_ITENS_HOMOLOGACAO_SERVIDOR_LOCAL = dict(
    ITENS_HOMOLOGACAO_SERVIDOR_LOCAL
)


def rotulos_itens_homologacao(codigos):
    return [
        ROTULOS_ITENS_HOMOLOGACAO_SERVIDOR_LOCAL.get(codigo, codigo)
        for codigo in (codigos or [])
    ]


CONTRATO_ACEITE = "local_installation_acceptance_evidence_v1"
TAMANHO_MAXIMO_JSON = 1024 * 1024
TAMANHO_MAXIMO_HASH = 4096


class EvidenciaHomologacaoInvalida(ValueError):
    pass


def _ler_limitado(arquivo, limite, nome):
    tamanho = getattr(arquivo, "size", None)
    if tamanho is not None and (tamanho <= 0 or tamanho > limite):
        raise EvidenciaHomologacaoInvalida(
            f"{nome} deve possuir entre 1 byte e {limite} bytes."
        )
    conteudo = arquivo.read(limite + 1)
    try:
        arquivo.seek(0)
    except (AttributeError, OSError):
        pass
    if not conteudo or len(conteudo) > limite:
        raise EvidenciaHomologacaoInvalida(
            f"{nome} deve possuir entre 1 byte e {limite} bytes."
        )
    return conteudo


def validar_arquivos_evidencia(arquivo_json, arquivo_sha256):
    """Valida o par de evidências sem persistir conteúdo potencialmente sensível."""
    nome_json = str(getattr(arquivo_json, "name", "") or "")
    nome_hash = str(getattr(arquivo_sha256, "name", "") or "")
    if not nome_json.lower().endswith(".json"):
        raise EvidenciaHomologacaoInvalida("A evidência deve ser um arquivo JSON.")
    if not nome_hash.lower().endswith((".sha256", ".sha256.txt")):
        raise EvidenciaHomologacaoInvalida(
            "Envie o arquivo SHA-256 que acompanha a evidência."
        )

    conteudo_json = _ler_limitado(
        arquivo_json, TAMANHO_MAXIMO_JSON, "A evidência JSON"
    )
    conteudo_hash = _ler_limitado(
        arquivo_sha256, TAMANHO_MAXIMO_HASH, "O arquivo SHA-256"
    )
    digest = hashlib.sha256(conteudo_json).hexdigest()
    try:
        texto_hash = conteudo_hash.decode("ascii", errors="strict").strip()
    except UnicodeDecodeError as exc:
        raise EvidenciaHomologacaoInvalida(
            "O arquivo SHA-256 não está em formato ASCII válido."
        ) from exc
    esperado = texto_hash.split()[0].lower() if texto_hash else ""
    if not re.fullmatch(r"[0-9a-f]{64}", esperado):
        raise EvidenciaHomologacaoInvalida(
            "O arquivo SHA-256 não contém um hash válido."
        )
    if not hmac.compare_digest(digest, esperado):
        raise EvidenciaHomologacaoInvalida(
            "O SHA-256 não corresponde à evidência enviada."
        )

    try:
        payload = json.loads(conteudo_json.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenciaHomologacaoInvalida(
            "A evidência contém JSON inválido."
        ) from exc
    if not isinstance(payload, dict):
        raise EvidenciaHomologacaoInvalida(
            "A raiz da evidência deve ser um objeto JSON."
        )
    if payload.get("contrato") != CONTRATO_ACEITE:
        raise EvidenciaHomologacaoInvalida("Contrato de evidência incompatível.")
    if (
        payload.get("perfil") != "servidor-local"
        or payload.get("alvo") != "producao"
    ):
        raise EvidenciaHomologacaoInvalida(
            "A homologação exige evidência do perfil servidor-local para produção."
        )
    seguranca = payload.get("seguranca")
    if not isinstance(seguranca, dict):
        raise EvidenciaHomologacaoInvalida(
            "A evidência não contém o bloco de segurança."
        )
    if (
        seguranca.get("segredos_expostos") is not False
        or seguranca.get("caminhos_absolutos_expostos") is not False
    ):
        raise EvidenciaHomologacaoInvalida(
            "A evidência indica exposição de dados sensíveis."
        )
    liberavel = payload.get("liberavel") is True
    if payload.get("status") != ("ready" if liberavel else "blocked"):
        raise EvidenciaHomologacaoInvalida(
            "Status e decisão de liberação estão inconsistentes."
        )
    dossie = payload.get("dossie")
    pos_implantacao = payload.get("pos_implantacao")
    if (
        not isinstance(dossie, dict)
        or not isinstance(dossie.get("validacao"), dict)
    ):
        raise EvidenciaHomologacaoInvalida(
            "A validação do dossiê não foi encontrada."
        )
    if (
        not isinstance(pos_implantacao, dict)
        or pos_implantacao.get("contrato")
        != "local_post_deployment_health_v1"
    ):
        raise EvidenciaHomologacaoInvalida(
            "O diagnóstico pós-instalação é incompatível."
        )
    if liberavel and not (
        dossie["validacao"].get("liberavel") is True
        and pos_implantacao.get("pronto") is True
    ):
        raise EvidenciaHomologacaoInvalida(
            "A evidência liberável contém validações pendentes."
        )
    return {
        "sha256": digest,
        "liberavel": liberavel,
        "bloqueios": (
            payload.get("bloqueios")
            if isinstance(payload.get("bloqueios"), list)
            else []
        ),
        "gerado_em": str(payload.get("gerado_em") or ""),
    }

def diagnostico_homologacao_servidor_local(*, versao_vigente=None):
    """Indica se a versão distribuída possui aceite técnico em máquina limpa."""
    from .models import HomologacaoServidorLocal, ResultadoHomologacaoServidor

    versao_vigente = str(versao_vigente or settings.LOCAL_SERVER_VERSION).strip()
    atual = HomologacaoServidorLocal.objects.filter(
        versao_artefato=versao_vigente
    ).first()
    ultimo = HomologacaoServidorLocal.objects.first()
    registro = atual or ultimo
    resumo_registro = None
    if registro:
        resumo_registro = {
            "id": registro.pk,
            "maquina": registro.maquina,
            "versao": registro.versao_artefato,
            "resultado": registro.resultado,
            "criada_em": registro.criada_em,
        }

    base = {
        "contrato": "local_server_homologation_readiness_v1",
        "versao_vigente": versao_vigente,
        "registro": resumo_registro,
    }
    if atual and atual.resultado == ResultadoHomologacaoServidor.APROVADA:
        faltantes = (
            CODIGOS_CRITICOS_HOMOLOGACAO_SERVIDOR_LOCAL
            - set(atual.itens_validados or [])
        )
        if faltantes:
            return {
                **base,
                "status": "INCOMPLETA",
                "pronta": False,
                "titulo": "Homologação aprovada sem checklist completo",
                "descricao": (
                    f"A versão {versao_vigente} possui um aceite anterior em "
                    f"{atual.maquina}, mas precisa repetir os testes críticos."
                ),
            }
        return {
            **base,
            "status": "APROVADA",
            "pronta": True,
            "titulo": "Homologação aprovada para a versão vigente",
            "descricao": (
                f"A versão {versao_vigente} foi aprovada em {atual.maquina}."
            ),
        }
    if atual:
        return {
            **base,
            "status": "REPROVADA",
            "pronta": False,
            "titulo": "Homologação reprovada para a versão vigente",
            "descricao": (
                f"A versão {versao_vigente} possui uma reprovação registrada em "
                f"{atual.maquina}. Corrija a ocorrência e execute novo aceite."
            ),
        }
    if ultimo:
        return {
            **base,
            "status": "DESATUALIZADA",
            "pronta": False,
            "titulo": "Homologação de outra versão",
            "descricao": (
                f"O último registro é da versão {ultimo.versao_artefato}. "
                f"Homologue a versão vigente {versao_vigente}."
            ),
        }
    return {
        **base,
        "status": "PENDENTE",
        "pronta": False,
        "titulo": "Homologação em máquina limpa pendente",
        "descricao": (
            f"Ainda não existe aceite técnico para a versão {versao_vigente}."
        ),
    }
