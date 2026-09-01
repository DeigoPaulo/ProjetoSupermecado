import os
from pathlib import Path

from django.conf import settings
from django.db import connections
from django.db.migrations.executor import MigrationExecutor

from apps.accounts.services import diagnostico_prontidao_recuperacao_senha
from apps.empresas.services_lookup import diagnostico_prontidao_consulta_cadastro
from apps.licenciamento.services import diagnostico_prontidao_licenciamento

from .offline_bundle import artefato_servidor_offline


SERVIDOR_LOCAL_ARQUIVOS = {
    "subir_servidor": "scripts/run_local_server.ps1",
    "registrar_servidor": "scripts/register_local_server_task.ps1",
    "instalar_servico": "scripts/install_local_server_service.ps1",
    "empacotar_servidor": "scripts/package_local_server.ps1",
    "publicar_servidor": "scripts/publish_local_server.ps1",
    "atualizar_servidor": "scripts/update_local_server.ps1",
    "diagnosticar_servico": "scripts/test_local_server_service.ps1",
    "remover_servico": "scripts/uninstall_local_server_service.ps1",
    "template_servico": "server_local/windows/DeigoVarejoServidorLocal.xml.template",
    "backup_local": "scripts/backup_local.ps1",
    "registrar_resultado_backup": "apps/configuracoes/management/commands/registrar_resultado_backup_operacional.py",
    "verificar_evidencias_fiscais": "apps/fiscal/management/commands/verificar_integridade_evidencias_fiscais.py",
    "restaurar_backup": "scripts/restore_local_backup.ps1",
    "registrar_backup": "scripts/register_backup_task.ps1",
    "registrar_sincronizacao": "scripts/register_sync_task.ps1",
    "registrar_manutencao_validade": "scripts/register_inventory_expiry_maintenance_task.ps1",
    "verificar_fluxo_estoque_piloto": "apps/estoque/management/commands/verificar_fluxo_estoque_piloto.py",
    "guia": "docs/IMPLANTACAO_SERVIDOR_LOCAL.md",
    "manual_instalacao": "docs/MANUAL_INSTALACAO_SUPERMERCADO.md",
}


def _diagnostico_seguranca_django(*, producao: bool) -> dict:
    secret_key = str(getattr(settings, "SECRET_KEY", "") or "")
    allowed_hosts = list(getattr(settings, "ALLOWED_HOSTS", []) or [])
    chave_propria = bool(secret_key and not secret_key.startswith("django-insecure"))
    hosts_explicitos = bool(allowed_hosts) and "*" not in allowed_hosts
    debug_desativado = not bool(getattr(settings, "DEBUG", False))
    alertas = []
    if not chave_propria:
        alertas.append("Defina uma SECRET_KEY exclusiva fora do código-fonte.")
    if not hosts_explicitos:
        alertas.append("Configure ALLOWED_HOSTS com os nomes ou endereços reais, sem curinga.")
    if producao and not debug_desativado:
        alertas.append("Desative DEBUG no ambiente de produção.")
    pronto = chave_propria and hosts_explicitos and (debug_desativado or not producao)
    return {
        "contrato": "django_deployment_security_v1",
        "pronto": pronto,
        "debug_desativado": debug_desativado,
        "secret_key_propria": chave_propria,
        "allowed_hosts_explicitos": hosts_explicitos,
        "alertas": alertas,
    }


def diagnostico_prontidao_https() -> dict:
    cookies_sessao = bool(getattr(settings, "SESSION_COOKIE_SECURE", False))
    cookies_csrf = bool(getattr(settings, "CSRF_COOKIE_SECURE", False))
    redireciona_https = bool(getattr(settings, "SECURE_SSL_REDIRECT", False))
    hsts_segundos = int(getattr(settings, "SECURE_HSTS_SECONDS", 0) or 0)
    proxy_header = getattr(settings, "SECURE_PROXY_SSL_HEADER", None)
    proxy_https = proxy_header == ("HTTP_X_FORWARDED_PROTO", "https")
    origens = list(getattr(settings, "CSRF_TRUSTED_ORIGINS", []) or [])
    origens_https = all(str(origem).lower().startswith("https://") for origem in origens)
    alertas = []
    if not cookies_sessao:
        alertas.append("Ative SESSION_COOKIE_SECURE.")
    if not cookies_csrf:
        alertas.append("Ative CSRF_COOKIE_SECURE.")
    if not redireciona_https:
        alertas.append("Ative SECURE_SSL_REDIRECT.")
    if hsts_segundos <= 0:
        alertas.append("Configure SECURE_HSTS_SECONDS após validar o HTTPS.")
    if not proxy_https:
        alertas.append("Configure USE_X_FORWARDED_PROTO para o proxy reverso HTTPS.")
    if not origens_https:
        alertas.append("Todas as origens CSRF configuradas devem usar HTTPS.")
    recomendacoes = []
    if not origens:
        recomendacoes.append("Informe CSRF_TRUSTED_ORIGINS quando o ERP usar domínio, IP ou porta externa.")
    pronto = bool(
        cookies_sessao
        and cookies_csrf
        and redireciona_https
        and hsts_segundos > 0
        and proxy_https
        and origens_https
    )
    return {
        "contrato": "https_deployment_readiness_v1",
        "pronto": pronto,
        "session_cookie_secure": cookies_sessao,
        "csrf_cookie_secure": cookies_csrf,
        "ssl_redirect": redireciona_https,
        "hsts_configurado": hsts_segundos > 0,
        "proxy_https_configurado": proxy_https,
        "origens_csrf_configuradas": len(origens),
        "origens_csrf_https": origens_https,
        "alertas": alertas,
        "recomendacoes": recomendacoes,
        "nao_expoe_origens": True,
    }


def diagnostico_prontidao_banco_dados(*, producao: bool) -> dict:
    connection = connections["default"]
    conectado = False
    migracoes_pendentes = None
    erro_tipo = ""
    alertas = []
    try:
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        conectado = True
        executor = MigrationExecutor(connection)
        plano = executor.migration_plan(executor.loader.graph.leaf_nodes())
        migracoes_pendentes = len(plano)
    except Exception as exc:
        erro_tipo = exc.__class__.__name__
    postgresql = connection.vendor == "postgresql"
    if not conectado:
        alertas.append("O banco de dados não respondeu ao teste de conexão.")
    if conectado and migracoes_pendentes:
        alertas.append(f"Existem {migracoes_pendentes} migração(ões) pendente(s).")
    if producao and not postgresql:
        alertas.append("Produção exige PostgreSQL; SQLite é permitido somente em desenvolvimento ou homologação.")
    pronto = bool(conectado and migracoes_pendentes == 0 and (postgresql or not producao))
    return {
        "contrato": "database_deployment_readiness_v1",
        "pronto": pronto,
        "conectado": conectado,
        "backend": "postgresql" if postgresql else "outro",
        "postgresql": postgresql,
        "migracoes_pendentes": migracoes_pendentes,
        "erro_tipo": erro_tipo,
        "alertas": alertas,
        "nao_expoe_credenciais": True,
    }


def diagnostico_prontidao_servidor_local(
    *,
    base_dir=None,
    scripts=None,
    pendencias=None,
    modos=None,
) -> dict:
    base_dir = Path(base_dir or settings.BASE_DIR)
    scripts = scripts or SERVIDOR_LOCAL_ARQUIVOS
    pendencias = pendencias or []
    modos = modos or {}
    caminhos_obrigatorios = {
        chave: scripts.get(chave, caminho)
        for chave, caminho in SERVIDOR_LOCAL_ARQUIVOS.items()
    }
    arquivos = {
        chave: {"caminho": caminho, "existe": (base_dir / caminho).exists()}
        for chave, caminho in caminhos_obrigatorios.items()
    }
    ausentes = [info["caminho"] for info in arquivos.values() if not info["existe"]]
    planejados = [item["titulo"] for item in pendencias if item.get("status") == "planejado"]
    iniciados = [item["titulo"] for item in pendencias if item.get("status") == "iniciado"]
    backup_criptografia_configurada = bool(os.getenv("BACKUP_ENCRYPTION_PASSPHRASE"))
    bloqueios = []
    recomendacoes = []
    if ausentes:
        bloqueios.append("Arquivos obrigatórios ausentes: " + ", ".join(ausentes))
    if planejados:
        recomendacoes.append("Concluir itens planejados: " + ", ".join(planejados))
    if iniciados:
        recomendacoes.append("Homologar itens iniciados: " + ", ".join(iniciados))
    if not backup_criptografia_configurada:
        recomendacoes.append(
            "Configure BACKUP_ENCRYPTION_PASSPHRASE antes de usar backup criptografado em produção."
        )
    pronto = not bloqueios
    if bloqueios:
        status = "Bloqueada"
        percentual = 50
        proximo_passo = bloqueios[0]
    elif planejados:
        status = "Homologação parcial"
        percentual = 78
        proximo_passo = recomendacoes[0]
    elif recomendacoes:
        status = "Pronta com ressalvas"
        percentual = 90
        proximo_passo = recomendacoes[0]
    else:
        status = "Pronta"
        percentual = 100
        proximo_passo = "Servidor local administrativo pronto para operação assistida."
    return {
        "contrato": "local_admin_readiness_v1",
        "pronto": pronto,
        "status": status,
        "percentual": percentual,
        "proximo_passo": proximo_passo,
        "backup_criptografia_configurada": backup_criptografia_configurada,
        "arquivos": arquivos,
        "bloqueios": bloqueios,
        "recomendacoes": recomendacoes,
        "empresas_por_modo": {
            "local": modos.get("LOCAL", modos.get("local", 0)),
            "hibrido": modos.get("HIBRIDO", modos.get("hibrido", 0)),
            "nuvem_agente": modos.get("NUVEM_AGENTE", modos.get("nuvem_agente", 0)),
        },
    }


def diagnostico_prontidao_midia_offline(*, resultado=None) -> dict:
    resultado = resultado or artefato_servidor_offline()
    pronta = bool(resultado.get("publicacao_valida"))
    alertas = list(resultado.get("problemas") or [])
    if not pronta and not alertas:
        alertas.append("O instalador offline ainda não possui publicação íntegra.")
    return {
        "contrato": "offline_installation_media_readiness_v1",
        "pronto": pronta,
        "pacote_contrato": resultado.get("contrato", ""),
        "publicacao_contrato": resultado.get("contrato_publicacao", ""),
        "pacote_encontrado": bool(resultado.get("arquivo_encontrado")),
        "checksum_encontrado": bool(resultado.get("checksum_encontrado")),
        "checksum_hash_valido": bool(resultado.get("checksum_hash_valido")),
        "checksum_nome_vinculado": bool(resultado.get("checksum_nome_vinculado")),
        "publicacao_valida": pronta,
        "alertas": alertas,
        "caminho_exposto": False,
    }


def _verificacao(
    *, identificador, diagnostico, obrigatoria, pronta=None, alertas=None, recomendacoes=None
):
    pronta = diagnostico.get("pronto") if pronta is None else pronta
    if pronta:
        status = "ready"
    elif obrigatoria:
        status = "blocked"
    else:
        status = diagnostico.get("status", "recommended")
    return {
        "id": identificador,
        "contrato": diagnostico["contrato"],
        "obrigatoria": obrigatoria,
        "pronta": bool(pronta),
        "status": status,
        "alertas": list(alertas if alertas is not None else diagnostico.get("alertas", [])),
        "recomendacoes": list(
            recomendacoes
            if recomendacoes is not None
            else diagnostico.get("recomendacoes", [])
        ),
    }


def diagnostico_prontidao_implantacao(
    *,
    producao: bool = False,
    perfil: str = "central",
    exigir_midia_offline: bool = False,
) -> dict:
    if perfil not in {"central", "servidor-local"}:
        raise ValueError("Perfil de implantação inválido.")

    alvo = "produção" if producao else "homologação"
    seguranca = _diagnostico_seguranca_django(producao=producao)
    https = diagnostico_prontidao_https()
    banco = diagnostico_prontidao_banco_dados(producao=producao)
    senha = diagnostico_prontidao_recuperacao_senha()
    consulta = diagnostico_prontidao_consulta_cadastro()
    verificacoes = [
        _verificacao(identificador="seguranca_django", diagnostico=seguranca, obrigatoria=True),
        _verificacao(
            identificador="seguranca_https",
            diagnostico=https,
            obrigatoria=producao,
            alertas=https["alertas"] + https["recomendacoes"],
        ),
        _verificacao(identificador="banco_dados", diagnostico=banco, obrigatoria=True),
    ]

    if perfil == "central":
        licenciamento = diagnostico_prontidao_licenciamento()
        pronta_licenca = (
            licenciamento["pronto_producao"] if producao else licenciamento["pronto_homologacao"]
        )
        verificacoes.extend(
            [
                _verificacao(
                    identificador="licenciamento_central",
                    diagnostico=licenciamento,
                    obrigatoria=True,
                    pronta=pronta_licenca,
                ),
                _verificacao(
                    identificador="recuperacao_senha",
                    diagnostico=senha["prontidao"],
                    obrigatoria=True,
                    pronta=senha["prontidao"]["configuracao_smtp_completa"],
                    alertas=senha["prontidao"]["bloqueios"],
                ),
            ]
        )
    else:
        servidor_local = diagnostico_prontidao_servidor_local()
        midia_offline = diagnostico_prontidao_midia_offline()
        verificacoes.extend(
            [
                _verificacao(
                    identificador="servidor_local",
                    diagnostico=servidor_local,
                    obrigatoria=True,
                    alertas=servidor_local["bloqueios"],
                    recomendacoes=servidor_local["recomendacoes"],
                ),
                _verificacao(
                    identificador="recuperacao_senha",
                    diagnostico=senha["prontidao"],
                    obrigatoria=False,
                    pronta=senha["prontidao"]["configuracao_smtp_completa"],
                    alertas=senha["prontidao"]["bloqueios"],
                ),
                _verificacao(
                    identificador="midia_instalacao_offline",
                    diagnostico=midia_offline,
                    obrigatoria=exigir_midia_offline,
                ),
            ]
        )

    verificacoes.append(
        _verificacao(
            identificador="consulta_cnpj_cep",
            diagnostico=consulta["prontidao"],
            obrigatoria=False,
            pronta=consulta["prontidao"]["pronto_homologacao"],
            alertas=consulta["prontidao"]["bloqueios"],
        )
    )
    obrigatorias = [item for item in verificacoes if item["obrigatoria"]]
    recomendadas = [item for item in verificacoes if not item["obrigatoria"]]
    bloqueios = [
        f"{item['id']}: {alerta}"
        for item in obrigatorias
        if not item["pronta"]
        for alerta in (item["alertas"] or ["Verificação obrigatória pendente."])
    ]
    recomendacoes = [
        f"{item['id']}: {alerta}"
        for item in recomendadas
        if not item["pronta"]
        for alerta in (item["alertas"] or ["Homologação recomendada pendente."])
    ]
    recomendacoes.extend(
        f"{item['id']}: {recomendacao}"
        for item in verificacoes
        for recomendacao in item.get("recomendacoes", [])
    )
    recomendacoes = list(dict.fromkeys(recomendacoes))
    prontas_obrigatorias = sum(1 for item in obrigatorias if item["pronta"])
    prontas_recomendadas = sum(1 for item in recomendadas if item["pronta"])
    pronto = prontas_obrigatorias == len(obrigatorias)
    observacoes = [
        "Fiscal, TEF, impressoras, dispositivos e sincronização exigem homologação por empresa, filial ou terminal.",
        "Nenhuma credencial, chave privada, senha SMTP ou URL de provedor é exposta.",
    ]
    if perfil == "central":
        observacoes.insert(0, "Este diagnóstico valida a configuração global do servidor central.")
    else:
        observacoes.insert(
            0,
            "Este diagnóstico valida o servidor local da loja sem exigir segredos privados da central, Asaas ou webhook público.",
        )
        observacoes.append(
            "Ativação comercial, concessão de licença e sincronização devem ser validadas na instalação real."
        )
    return {
        "contrato": "deployment_readiness_v2",
        "perfil": perfil,
        "alvo": alvo,
        "politica_instalacao": {
            "contrato": "local_installation_media_policy_v1",
            "midia_offline_exigida": bool(perfil == "servidor-local" and exigir_midia_offline),
        },
        "status": "ready" if pronto else "blocked",
        "pronto": pronto,
        "resumo": {
            "obrigatorias": len(obrigatorias),
            "obrigatorias_prontas": prontas_obrigatorias,
            "recomendadas": len(recomendadas),
            "recomendadas_prontas": prontas_recomendadas,
            "percentual_obrigatorio": round(prontas_obrigatorias * 100 / len(obrigatorias)),
        },
        "verificacoes": verificacoes,
        "bloqueios": bloqueios,
        "recomendacoes": recomendacoes,
        "observacoes": observacoes,
    }
