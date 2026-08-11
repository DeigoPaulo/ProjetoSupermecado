import csv
import json
import re
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.permissions import ADMINISTRACAO, CLIENTES, COMPRAS, ESTOQUE, PDV, RELATORIOS, SISTEMA, role_required
from apps.auditoria.models import LogAuditoria

from .credenciais_sincronizacao import (
    credencial_sincronizacao_valida,
    credenciais_sincronizacao_para_cnpj,
)
from .forms import EmpresaForm, FilialForm
from .models import DocumentoFiscalSincronizado, Empresa, EventoEntradaSincronizacao, EventoSincronizacao, Filial, LancamentoFinanceiroSincronizado, ModoImplantacao, PoliticaConflitoSincronizacao, StatusEventoEntrada, StatusSincronizacao, VendaSincronizada
from .services_snapshots import gerar_carga_inicial_sincronizacao
from .services_lookup import diagnostico_prontidao_consulta_cadastro


def _apenas_digitos(valor):
    return re.sub(r"\D", "", valor or "")


def _cnpj_valido(cnpj):
    digitos = _apenas_digitos(cnpj)
    if len(digitos) != 14 or digitos == digitos[0] * 14:
        return False
    pesos_primeiro = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos_segundo = [6] + pesos_primeiro

    def calcular(posicoes, pesos):
        soma = sum(int(digito) * peso for digito, peso in zip(digitos[:posicoes], pesos))
        resto = soma % 11
        return "0" if resto < 2 else str(11 - resto)

    return digitos[-2:] == calcular(12, pesos_primeiro) + calcular(13, pesos_segundo)


def _dados_empresa(empresa):
    return {
        "tipo": "empresa",
        "id": empresa.pk,
        "razao_social": empresa.razao_social,
        "nome_fantasia": empresa.nome_fantasia,
        "cnpj": empresa.cnpj,
        "telefone": empresa.telefone,
        "email": empresa.email,
        "cep": empresa.cep,
        "logradouro": empresa.logradouro,
        "numero": empresa.numero,
        "complemento": empresa.complemento,
        "bairro": empresa.bairro,
        "endereco": empresa.endereco,
        "municipio": empresa.municipio,
        "uf": empresa.uf,
        "regime_tributario": empresa.regime_tributario,
    }


def _dados_filial(filial):
    return {
        "tipo": "filial",
        "id": filial.pk,
        "empresa_id": filial.empresa_id,
        "empresa": filial.empresa.nome_fantasia,
        "nome": filial.nome,
        "nome_fantasia": filial.nome,
        "razao_social": filial.empresa.razao_social,
        "cnpj": filial.cnpj or filial.empresa.cnpj,
        "telefone": filial.telefone,
        "email": filial.empresa.email,
        "cep": filial.cep,
        "logradouro": filial.logradouro,
        "numero": filial.numero,
        "complemento": filial.complemento,
        "bairro": filial.bairro,
        "endereco": filial.endereco,
        "municipio": filial.municipio,
        "uf": filial.uf,
        "codigo_municipio_ibge": filial.codigo_municipio_ibge,
    }


def _buscar_empresa_por_cnpj(digitos):
    for empresa in Empresa.objects.all():
        if _apenas_digitos(empresa.cnpj) == digitos:
            return empresa
    return None


def _buscar_filial_por_cnpj(digitos):
    for filial in Filial.objects.select_related("empresa"):
        if _apenas_digitos(filial.cnpj or filial.empresa.cnpj) == digitos:
            return filial
    return None



def _buscar_empresa_por_cep(digitos):
    for empresa in Empresa.objects.all():
        if digitos and (digitos == _apenas_digitos(empresa.cep) or digitos in _apenas_digitos(empresa.endereco)):
            return empresa
    return None


def _buscar_filial_por_cep(digitos):
    for filial in Filial.objects.select_related("empresa"):
        if digitos and (digitos == _apenas_digitos(filial.cep) or digitos in _apenas_digitos(filial.endereco)):
            return filial
    return None


def _montar_url_provider(base_url, tipo, valor):
    if "{" in base_url:
        return base_url.format(cnpj=valor, cep=valor, valor=valor)
    separador = "&" if "?" in base_url else "?"
    return f"{base_url}{separador}{urlencode({tipo: valor})}"


def _normalizar_endereco(dados):
    partes = [
        dados.get("logradouro") or dados.get("endereco") or dados.get("street"),
        dados.get("numero") or dados.get("number"),
        dados.get("bairro") or dados.get("district"),
        dados.get("municipio") or dados.get("localidade") or dados.get("city"),
        dados.get("uf") or dados.get("state"),
        dados.get("cep") or dados.get("zip_code"),
    ]
    return ", ".join(str(parte).strip() for parte in partes if str(parte or "").strip())


def _normalizar_payload_provider(tipo, valor, dados):
    endereco = {
        "cep": dados.get("cep") or dados.get("zip_code") or (valor if tipo == "cep" else ""),
        "logradouro": dados.get("logradouro") or dados.get("endereco") or dados.get("street") or "",
        "numero": dados.get("numero") or dados.get("number") or "",
        "complemento": dados.get("complemento") or dados.get("complement") or "",
        "bairro": dados.get("bairro") or dados.get("district") or "",
        "endereco": _normalizar_endereco(dados),
        "municipio": dados.get("municipio") or dados.get("localidade") or dados.get("city") or "",
        "uf": dados.get("uf") or dados.get("state") or "",
        "codigo_municipio_ibge": dados.get("codigo_municipio_ibge") or dados.get("ibge") or dados.get("city_ibge") or "",
    }
    if tipo == "cep":
        normalizado = {"tipo": "cep", **endereco}
    else:
        normalizado = {
            "tipo": "cnpj",
            "cnpj": dados.get("cnpj") or valor,
            "razao_social": dados.get("razao_social") or dados.get("nome") or dados.get("name") or "",
            "nome_fantasia": dados.get("nome_fantasia") or dados.get("fantasia") or dados.get("alias") or "",
            "telefone": dados.get("telefone") or dados.get("phone") or "",
            "email": dados.get("email") or "",
            **endereco,
        }
    return {chave: valor for chave, valor in normalizado.items() if valor not in (None, "")}


def _consultar_provider_cadastro(provider_url, tipo, valor):
    url = _montar_url_provider(provider_url, tipo, valor)
    timeout = getattr(settings, "CADASTRO_LOOKUP_TIMEOUT_SEGUNDOS", 5)
    requisicao = Request(url, headers={"Accept": "application/json", "User-Agent": "DeigoVarejoERP/cadastro_lookup_v1"})
    try:
        resposta = urlopen(requisicao, timeout=timeout)
        try:
            status_code = getattr(resposta, "status", 200)
            conteudo = resposta.read().decode("utf-8")
        finally:
            close = getattr(resposta, "close", None)
            if close:
                close()
    except HTTPError as exc:
        return {"status": "external_provider_error", "mensagem": f"Provedor externo respondeu HTTP {exc.code}.", "http_status": exc.code}
    except (URLError, TimeoutError, OSError) as exc:
        return {"status": "external_provider_error", "mensagem": f"Falha ao consultar provedor externo: {exc}."}
    try:
        dados = json.loads(conteudo)
    except json.JSONDecodeError:
        return {"status": "external_provider_error", "mensagem": "Provedor externo retornou resposta que não e JSON."}
    if status_code >= 400:
        return {"status": "external_provider_error", "mensagem": f"Provedor externo respondeu HTTP {status_code}.", "http_status": status_code}
    if isinstance(dados, dict) and (dados.get("erro") is True or str(dados.get("status", "")).lower() in {"erro", "error", "not_found"}):
        return {"status": "external_not_found", "mensagem": "Provedor externo não encontrou dados para a consulta.", "provider_payload": dados}
    if not isinstance(dados, dict):
        return {"status": "external_provider_error", "mensagem": "Provedor externo retornou formato inesperado."}
    return {
        "status": "external_match",
        "mensagem": "Cadastro preenchido por provedor externo configurado.",
        "dados": _normalizar_payload_provider(tipo, valor, dados),
        "provider_payload": dados,
    }


BUSCA_FILIAIS_ROLES = SISTEMA | CLIENTES | ESTOQUE | COMPRAS | RELATORIOS | PDV


def _empresa_id_do_usuario(user):
    if user.is_superuser:
        return None
    perfil = getattr(user, "perfil_supermercado", None)
    return perfil.filial.empresa_id if perfil and perfil.is_active and perfil.filial_id else 0


def _empresas_visiveis(user):
    empresas_qs = Empresa.objects.all()
    if user.is_superuser:
        return empresas_qs
    return empresas_qs.filter(pk=_empresa_id_do_usuario(user))


def _filiais_visiveis(user):
    filiais_qs = Filial.objects.all()
    if user.is_superuser:
        return filiais_qs
    return filiais_qs.filter(empresa_id=_empresa_id_do_usuario(user))


def _exigir_super_admin(user):
    if not user.is_superuser:
        raise PermissionDenied("Somente o super admin do software pode criar matrizes e filiais licenciadas.")


def _registrar_cadastro_licenciado(request, objeto, acao):
    LogAuditoria.objects.create(
        usuario=request.user,
        modulo="empresas",
        acao=acao,
        descricao=f"{objeto} cadastrado pelo super admin como nova unidade licenciada.",
        objeto_tipo=objeto._meta.label,
        objeto_id=str(objeto.pk),
        ip=request.META.get("REMOTE_ADDR"),
    )


def _erro_api(mensagem, status):
    return JsonResponse({"status": "erro", "mensagem": mensagem}, status=status)


@csrf_exempt
@require_POST
def receber_evento_sincronizacao(request):
    limite = settings.SINCRONIZACAO_MAX_EVENTO_BYTES
    try:
        tamanho_declarado = int(request.META.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        tamanho_declarado = 0
    if tamanho_declarado > limite:
        return _erro_api("Evento de sincronização excede o limite permitido.", 413)

    corpo = request.body
    if len(corpo) > limite:
        return _erro_api("Evento de sincronização excede o limite permitido.", 413)
    try:
        dados = json.loads(corpo)
        identificador = uuid.UUID(str(dados["id"]))
        tipo = str(dados["tipo"]).strip()
        empresa_cnpj = str(dados["empresa_cnpj"]).strip()
        payload = dados["payload"]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return _erro_api("Evento de sincronização malformado.", 400)

    token_recebido = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    token_valido, _origem_token = credencial_sincronizacao_valida(
        empresa_cnpj,
        token_recebido,
    )
    if not token_valido:
        return _erro_api("Credencial de sincronização inválida para a empresa.", 401)

    chave = request.headers.get("Idempotency-Key", "").strip()
    if (
        not chave
        or len(chave) > 180
        or not tipo
        or len(tipo) > 100
        or len(empresa_cnpj) > 18
        or not isinstance(payload, dict)
    ):
        return _erro_api("Tipo, payload e chave idempotente são obrigatórios.", 400)
    empresa = Empresa.objects.filter(cnpj=empresa_cnpj, is_active=True).first()
    if not empresa:
        return _erro_api("Empresa do evento não encontrada ou inativa.", 422)

    existente = EventoEntradaSincronizacao.objects.filter(identificador=identificador).first()
    if not existente:
        existente = EventoEntradaSincronizacao.objects.filter(chave_idempotencia=chave).first()
    if existente:
        if existente.identificador == identificador and existente.chave_idempotencia == chave:
            return JsonResponse({"status": "duplicado", "id": str(existente.identificador)}, status=200)
        return _erro_api("Conflito entre identificador e chave idempotente.", 409)
    if not empresa.sincronizacao_operacional_habilitada:
        return _erro_api("A empresa não permite sincronização operacional com a nuvem.", 409)
    try:
        with transaction.atomic():
            evento = EventoEntradaSincronizacao.objects.create(
                identificador=identificador,
                chave_idempotencia=chave,
                empresa=empresa,
                tipo=tipo,
                payload=dados,
            )
    except IntegrityError:
        return JsonResponse({"status": "duplicado", "id": str(identificador)}, status=200)
    return JsonResponse({"status": "recebido", "id": str(evento.identificador)}, status=202)


@login_required
@role_required(*ADMINISTRACAO)
def empresas(request):
    empresas_lista = _empresas_visiveis(request.user).prefetch_related("filiais").order_by("nome_fantasia")
    filiais = _filiais_visiveis(request.user).select_related("empresa").order_by("empresa__nome_fantasia", "nome")
    context = {
        "empresas": empresas_lista,
        "filiais": filiais,
        "total_empresas": empresas_lista.count(),
        "total_filiais": filiais.count(),
        "filiais_ativas": filiais.filter(is_active=True).count(),
        "filiais_sem_ibge": filiais.filter(codigo_municipio_ibge="").count(),
    }
    return render(request, "empresas/lista.html", context)


@login_required
@role_required(*BUSCA_FILIAIS_ROLES)
@require_GET
def filiais_busca(request):
    termo = (request.GET.get("q") or request.GET.get("term") or "").strip()
    if not termo:
        return JsonResponse({"results": []})
    filiais = (
        _filiais_visiveis(request.user).select_related("empresa")
        .filter(
            Q(nome__icontains=termo)
            | Q(empresa__nome_fantasia__icontains=termo)
            | Q(cnpj__icontains=termo)
            | Q(municipio__icontains=termo)
            | Q(codigo_municipio_ibge__icontains=termo)
        )
        .order_by("empresa__nome_fantasia", "nome")[:20]
    )
    return JsonResponse(
        {
            "results": [
                {
                    "id": filial.pk,
                    "text": f"{filial.empresa.nome_fantasia} - {filial.nome} | {filial.municipio or filial.cnpj or 'sem município'}",
                    "empresa": filial.empresa.nome_fantasia,
                    "nome": filial.nome,
                    "cnpj": filial.cnpj or filial.empresa.cnpj,
                    "municipio": filial.municipio,
                    "uf": filial.uf,
                    "codigo_municipio_ibge": filial.codigo_municipio_ibge,
                }
                for filial in filiais
            ]
        }
    )


@login_required
@role_required(*ADMINISTRACAO)
def empresa_form(request, pk=None):
    if pk is None:
        _exigir_super_admin(request.user)
    empresa = get_object_or_404(_empresas_visiveis(request.user), pk=pk) if pk else None
    form = EmpresaForm(request.POST or None, request.FILES or None, instance=empresa)
    if request.method == "POST" and form.is_valid():
        empresa_salva = form.save()
        if empresa is None:
            _registrar_cadastro_licenciado(request, empresa_salva, "empresa_licenciada_criada")
        messages.success(request, "Empresa salva com sucesso.")
        return redirect("empresas:lista")
    return render(request, "empresas/empresa_form.html", {"form": form, "empresa": empresa})


@login_required
@role_required(*ADMINISTRACAO)
def filial_form(request, pk=None):
    if pk is None:
        _exigir_super_admin(request.user)
    filial = get_object_or_404(_filiais_visiveis(request.user), pk=pk) if pk else None
    form = FilialForm(request.POST or None, instance=filial)
    form.fields["empresa"].queryset = _empresas_visiveis(request.user).order_by("nome_fantasia")
    if request.method == "POST" and form.is_valid():
        filial_salva = form.save()
        if filial is None:
            _registrar_cadastro_licenciado(request, filial_salva, "filial_licenciada_criada")
        messages.success(request, "Filial salva com sucesso.")
        return redirect("empresas:lista")
    return render(request, "empresas/filial_form.html", {"form": form, "filial": filial})


@login_required
@role_required(*ADMINISTRACAO)
def consulta_cadastro_placeholder(request):
    cnpj = request.GET.get("cnpj", "").strip()
    cep = request.GET.get("cep", "").strip()
    provider_cnpj = getattr(settings, "CADASTRO_CNPJ_PROVIDER_URL", "")
    provider_cep = getattr(settings, "CADASTRO_CEP_PROVIDER_URL", "")
    payload_base = {
        "contrato": "cadastro_lookup_v1",
        "provedores": {
            "cnpj_configurado": bool(provider_cnpj),
            "cep_configurado": bool(provider_cep),
            "timeout_segundos": getattr(settings, "CADASTRO_LOOKUP_TIMEOUT_SEGUNDOS", 5),
        },
        "campos_previstos": [
            "cnpj",
            "cep",
            "razao_social",
            "nome_fantasia",
            "telefone",
            "email",
            "cep",
            "logradouro",
            "numero",
            "complemento",
            "bairro",
            "endereco",
            "municipio",
            "uf",
            "codigo_municipio_ibge",
        ],
    }
    if cnpj:
        digitos = _apenas_digitos(cnpj)
        if not _cnpj_valido(digitos):
            return JsonResponse({**payload_base, "status": "invalid", "mensagem": "CNPJ inválido.", "consulta": {"tipo": "cnpj", "valor": digitos}}, status=400)
        filial = _buscar_filial_por_cnpj(digitos)
        empresa = _buscar_empresa_por_cnpj(digitos)
        if filial:
            return JsonResponse({**payload_base, "status": "local_match", "mensagem": "Cadastro encontrado nas filiais locais.", "dados": _dados_filial(filial)})
        if empresa:
            return JsonResponse({**payload_base, "status": "local_match", "mensagem": "Cadastro encontrado nas empresas locais.", "dados": _dados_empresa(empresa)})
        if provider_cnpj:
            resultado = _consultar_provider_cadastro(provider_cnpj, "cnpj", digitos)
            status_http = 502 if resultado["status"] == "external_provider_error" else 200
            return JsonResponse({**payload_base, "consulta": {"tipo": "cnpj", "valor": digitos}, **resultado}, status=status_http)
        return JsonResponse({**payload_base, "status": "external_provider_required", "mensagem": "CNPJ valido, mas não encontrado localmente. Configure um provedor externo para preenchimento automático.", "consulta": {"tipo": "cnpj", "valor": digitos}})
    if cep:
        digitos = _apenas_digitos(cep)
        if len(digitos) != 8:
            return JsonResponse({**payload_base, "status": "invalid", "mensagem": "CEP deve ter 8 digitos.", "consulta": {"tipo": "cep", "valor": digitos}}, status=400)
        filial = _buscar_filial_por_cep(digitos)
        empresa = _buscar_empresa_por_cep(digitos)
        if filial:
            return JsonResponse({**payload_base, "status": "local_match", "mensagem": "CEP encontrado nas filiais locais.", "consulta": {"tipo": "cep", "valor": digitos}, "dados": _dados_filial(filial)})
        if empresa:
            return JsonResponse({**payload_base, "status": "local_match", "mensagem": "CEP encontrado nas empresas locais.", "consulta": {"tipo": "cep", "valor": digitos}, "dados": _dados_empresa(empresa)})
        if provider_cep:
            resultado = _consultar_provider_cadastro(provider_cep, "cep", digitos)
            status_http = 502 if resultado["status"] == "external_provider_error" else 200
            return JsonResponse({**payload_base, "consulta": {"tipo": "cep", "valor": digitos}, **resultado}, status=status_http)
        return JsonResponse({**payload_base, "status": "external_provider_required", "mensagem": "CEP valido. Configure um provedor externo para preencher endereço, município, UF e IBGE.", "consulta": {"tipo": "cep", "valor": digitos}})
    return JsonResponse(
        {**payload_base,
            "status": "integration_pending",
            "mensagem": "Informe cnpj ou cep na query string. A consulta local ja valida CNPJ e reaproveita cadastros existentes; provedores externos podem ser conectados por configuração.",
        }
    )


@login_required
@role_required(*ADMINISTRACAO)
def consulta_cadastro_diagnostico(request):
    return JsonResponse(diagnostico_prontidao_consulta_cadastro())


def _pagina_nomeada(request, queryset, parametro):
    pagina = Paginator(queryset, 50).get_page(request.GET.get(parametro))
    params = request.GET.copy()
    if pagina.has_previous():
        params[parametro] = pagina.previous_page_number()
        pagina.previous_url = f"?{params.urlencode()}"
    else:
        pagina.previous_url = ""
    if pagina.has_next():
        params[parametro] = pagina.next_page_number()
        pagina.next_url = f"?{params.urlencode()}"
    else:
        pagina.next_url = ""
    return pagina

def _sincronizacao_querysets(request):
    q = request.GET.get("q", "").strip()
    empresa_id = request.GET.get("empresa", "").strip()
    filial_id = request.GET.get("filial", "").strip()
    status_entrada = request.GET.get("status_entrada", "").strip()

    eventos_qs = EventoSincronizacao.objects.select_related("empresa", "filial")
    eventos_entrada_qs = EventoEntradaSincronizacao.objects.select_related("empresa")
    vendas_qs = VendaSincronizada.objects.select_related("empresa", "filial")
    documentos_fiscais_qs = DocumentoFiscalSincronizado.objects.select_related("empresa", "filial")
    lancamentos_financeiros_qs = LancamentoFinanceiroSincronizado.objects.select_related("empresa", "filial")

    if empresa_id.isdigit():
        eventos_qs = eventos_qs.filter(empresa_id=empresa_id)
        eventos_entrada_qs = eventos_entrada_qs.filter(empresa_id=empresa_id)
        vendas_qs = vendas_qs.filter(empresa_id=empresa_id)
        documentos_fiscais_qs = documentos_fiscais_qs.filter(empresa_id=empresa_id)
        lancamentos_financeiros_qs = lancamentos_financeiros_qs.filter(empresa_id=empresa_id)
    if filial_id.isdigit():
        eventos_qs = eventos_qs.filter(filial_id=filial_id)
        vendas_qs = vendas_qs.filter(filial_id=filial_id)
        documentos_fiscais_qs = documentos_fiscais_qs.filter(filial_id=filial_id)
        lancamentos_financeiros_qs = lancamentos_financeiros_qs.filter(filial_id=filial_id)
    if status_entrada:
        eventos_entrada_qs = eventos_entrada_qs.filter(status=status_entrada)
    if q:
        eventos_qs = eventos_qs.filter(
            Q(tipo__icontains=q)
            | Q(identificador__icontains=q)
            | Q(objeto_tipo__icontains=q)
            | Q(objeto_id__icontains=q)
            | Q(chave_idempotencia__icontains=q)
            | Q(ultimo_erro__icontains=q)
        )
        eventos_entrada_qs = eventos_entrada_qs.filter(
            Q(tipo__icontains=q)
            | Q(identificador__icontains=q)
            | Q(chave_idempotencia__icontains=q)
            | Q(ultimo_erro__icontains=q)
            | Q(resolucao_conflito__icontains=q)
        )
        vendas_qs = vendas_qs.filter(
            Q(venda_externa_id__icontains=q)
            | Q(caixa_externo__icontains=q)
            | Q(operador__icontains=q)
            | Q(cliente__icontains=q)
        )
        documentos_fiscais_qs = documentos_fiscais_qs.filter(
            Q(documento_externo_id__icontains=q)
            | Q(venda_externa_id__icontains=q)
            | Q(chave_acesso__icontains=q)
            | Q(protocolo__icontains=q)
            | Q(status__icontains=q)
        )
        lancamentos_financeiros_qs = lancamentos_financeiros_qs.filter(
            Q(lancamento_externo_id__icontains=q)
            | Q(origem__icontains=q)
            | Q(descricao__icontains=q)
            | Q(conta_movimento__icontains=q)
            | Q(centro_custo__icontains=q)
            | Q(conta_contabil__icontains=q)
            | Q(usuario__icontains=q)
        )
    return {
        "eventos_qs": eventos_qs,
        "eventos_entrada_qs": eventos_entrada_qs,
        "vendas_qs": vendas_qs,
        "documentos_fiscais_qs": documentos_fiscais_qs,
        "lancamentos_financeiros_qs": lancamentos_financeiros_qs,
        "filtros": {"q": q, "empresa": empresa_id, "filial": filial_id, "status_entrada": status_entrada},
    }


def _prontidao_sincronizacao_payload(empresas_qs, saida, entrada, esgotados_saida):
    empresas_sync = empresas_qs.exclude(modo_implantacao=ModoImplantacao.LOCAL)
    empresas_sync_automaticas = empresas_sync.filter(sincronizacao_automatica=True)
    empresas_sync_sem_url = empresas_sync_automaticas.filter(url_sincronizacao="").count()
    empresas_sync_url_insegura = sum(
        1 for url in empresas_sync_automaticas.exclude(url_sincronizacao="").values_list("url_sincronizacao", flat=True) if not url.lower().startswith("https://")
    )
    pendencias_saida = saida.get(StatusSincronizacao.PENDENTE, 0) + saida.get(StatusSincronizacao.ERRO, 0)
    pendencias_entrada = entrada.get(StatusEventoEntrada.RECEBIDO, 0) + entrada.get(StatusEventoEntrada.ERRO, 0) + entrada.get(StatusEventoEntrada.CONFLITO, 0)
    pausados_saida = saida.get(StatusSincronizacao.PAUSADO, 0)
    pausados_entrada = entrada.get(StatusEventoEntrada.PAUSADO, 0)
    conflitos = entrada.get(StatusEventoEntrada.CONFLITO, 0)
    configuracoes_credenciais = [
        credenciais_sincronizacao_para_cnpj(cnpj)
        for cnpj in empresas_sync_automaticas.values_list("cnpj", flat=True)
    ]
    origens_credenciais = [origem for _tokens, origem in configuracoes_credenciais]
    credenciais_individuais = origens_credenciais.count("empresa")
    credenciais_em_rotacao = sum(
        1
        for tokens, origem in configuracoes_credenciais
        if origem == "empresa" and len(tokens) > 1
    )
    credenciais_globais_transicao = origens_credenciais.count("global_transicao")
    empresas_sem_credencial = origens_credenciais.count("ausente")
    token_configurado = not empresas_sem_credencial
    bloqueios = []
    recomendacoes = []
    if empresas_sem_credencial:
        bloqueios.append(
            f"Configure credencial individual de sincronizacao para {empresas_sem_credencial} empresa(s)."
        )
    if credenciais_globais_transicao:
        recomendacoes.append(
            f"Migrar {credenciais_globais_transicao} empresa(s) do token global de transicao "
            "para credencial individual."
        )
    if credenciais_em_rotacao:
        recomendacoes.append(
            f"Concluir a rotacao de credencial em {credenciais_em_rotacao} empresa(s) "
            "apos todos os servidores adotarem o token atual."
        )
    if empresas_sync_sem_url:
        bloqueios.append(f"{empresas_sync_sem_url} empresa(s) hibrida/nuvem estao sem URL de sincronizacao.")
    if empresas_sync_url_insegura:
        bloqueios.append(f"{empresas_sync_url_insegura} empresa(s) estao com URL de sincronizacao sem HTTPS.")
    if esgotados_saida:
        bloqueios.append(f"{esgotados_saida} evento(s) de saida esgotaram tentativas automaticas.")
    if conflitos:
        recomendacoes.append(f"Resolver {conflitos} conflito(s) de entrada antes de considerar a loja sincronizada.")
    if pendencias_saida or pendencias_entrada:
        recomendacoes.append("Manter o processador processar_sincronizacao_completa agendado no servidor local.")
    if pausados_saida or pausados_entrada:
        recomendacoes.append(
            f"{pausados_saida + pausados_entrada} evento(s) estão pausados pela política de implantação; "
            "serão retomados ao habilitar o modo híbrido com URL HTTPS."
        )
    if not empresas_sync.exists():
        status = "Local puro"
        percentual = 100
        proximo_passo = "Operação local liberada; sincronizacao com nuvem não está habilitada para as empresas filtradas."
    elif bloqueios:
        status = "Bloqueada"
        percentual = 45
        proximo_passo = bloqueios[0]
    elif recomendacoes:
        status = "Atencao"
        percentual = 80
        proximo_passo = recomendacoes[0]
    else:
        status = "Pronta"
        percentual = 100
        proximo_passo = "Sincronizacao pronta para operação assistida local/nuvem."
    return {
        "contrato": "sync_readiness_v1",
        "status": status,
        "percentual": percentual,
        "token_configurado": token_configurado,
        "credenciais": {
            "individuais": credenciais_individuais,
            "em_rotacao": credenciais_em_rotacao,
            "global_transicao": credenciais_globais_transicao,
            "sem_credencial": empresas_sem_credencial,
            "fallback_global_habilitado": settings.SINCRONIZACAO_PERMITE_TOKEN_GLOBAL,
        },
        "empresas": {
            "local": empresas_qs.filter(modo_implantacao=ModoImplantacao.LOCAL).count(),
            "hibrido": empresas_qs.filter(modo_implantacao=ModoImplantacao.HIBRIDO).count(),
            "nuvem_agente": empresas_qs.filter(modo_implantacao=ModoImplantacao.NUVEM_AGENTE).count(),
            "sincronizacao_automatica": empresas_sync_automaticas.count(),
            "sem_url": empresas_sync_sem_url,
            "url_insegura": empresas_sync_url_insegura,
        },
        "filas": {
            "saida_pendente_ou_erro": pendencias_saida,
            "entrada_pendente_erro_ou_conflito": pendencias_entrada,
            "saida_pausada": pausados_saida,
            "entrada_pausada": pausados_entrada,
            "conflitos": conflitos,
            "saida_esgotada": esgotados_saida,
        },
        "bloqueios": bloqueios,
        "recomendacoes": recomendacoes,
        "proximo_passo": proximo_passo,
    }


def _sincronizacao_diagnostico_payload(request):
    dados = _sincronizacao_querysets(request)
    eventos_qs = dados["eventos_qs"]
    eventos_entrada_qs = dados["eventos_entrada_qs"]
    vendas_qs = dados["vendas_qs"]
    documentos_fiscais_qs = dados["documentos_fiscais_qs"]
    lancamentos_financeiros_qs = dados["lancamentos_financeiros_qs"]
    saida = dict(eventos_qs.values_list("status").annotate(total=Count("id")))
    entrada = dict(eventos_entrada_qs.values_list("status").annotate(total=Count("id")))
    empresas_ativas_qs = Empresa.objects.filter(is_active=True)
    if dados["filtros"]["empresa"].isdigit():
        empresas_ativas_qs = empresas_ativas_qs.filter(pk=dados["filtros"]["empresa"])
    empresas_por_modo = dict(empresas_ativas_qs.values_list("modo_implantacao").annotate(total=Count("id")))
    politicas_conflito = dict(empresas_ativas_qs.values_list("politica_conflito_sincronizacao").annotate(total=Count("id")))
    politica_manual = politicas_conflito.get(PoliticaConflitoSincronizacao.MANUAL, 0)
    politica_remoto_produtos_estoque = politicas_conflito.get(PoliticaConflitoSincronizacao.REMOTO_PRODUTOS_ESTOQUE, 0)
    politica_local_produtos_estoque = politicas_conflito.get(PoliticaConflitoSincronizacao.LOCAL_PRODUTOS_ESTOQUE, 0)
    pendentes_saida = saida.get(StatusSincronizacao.PENDENTE, 0)
    pausados_saida = saida.get(StatusSincronizacao.PAUSADO, 0)
    erros_saida = saida.get(StatusSincronizacao.ERRO, 0)
    conflitos_entrada = entrada.get(StatusEventoEntrada.CONFLITO, 0)
    erros_entrada = entrada.get(StatusEventoEntrada.ERRO, 0)
    recebidos_entrada = entrada.get(StatusEventoEntrada.RECEBIDO, 0)
    pausados_entrada = entrada.get(StatusEventoEntrada.PAUSADO, 0)
    agora = timezone.now()
    evento_saida_antigo = eventos_qs.filter(status__in=[StatusSincronizacao.PENDENTE, StatusSincronizacao.ERRO]).order_by("criado_em").first()
    evento_entrada_antigo = eventos_entrada_qs.filter(
        status__in=[StatusEventoEntrada.RECEBIDO, StatusEventoEntrada.ERRO, StatusEventoEntrada.CONFLITO]
    ).order_by("recebido_em").first()
    idade_saida_minutos = int((agora - evento_saida_antigo.criado_em).total_seconds() // 60) if evento_saida_antigo else 0
    idade_entrada_minutos = int((agora - evento_entrada_antigo.recebido_em).total_seconds() // 60) if evento_entrada_antigo else 0
    esgotados_saida = eventos_qs.filter(
        status=StatusSincronizacao.ERRO,
        tentativas__gte=settings.SINCRONIZACAO_MAX_TENTATIVAS,
    ).count()
    alertas = []
    if erros_saida:
        alertas.append(f"{erros_saida} evento(s) de saida com erro aguardando reprocessamento.")
    if esgotados_saida:
        alertas.append(f"{esgotados_saida} evento(s) de saida esgotaram as tentativas automaticas.")
    if erros_entrada:
        alertas.append(f"{erros_entrada} evento(s) de entrada com erro técnico.")
    if conflitos_entrada:
        alertas.append(f"{conflitos_entrada} conflito(s) de entrada exigem decisão manual.")
    if pendentes_saida or recebidos_entrada:
        alertas.append("Fila possui eventos aguardando o comando processar_sincronizacao_completa.")
    if pausados_saida or pausados_entrada:
        alertas.append(f"{pausados_saida + pausados_entrada} evento(s) estão pausados pela política de implantação.")
    if Empresa.objects.filter(is_active=True, sincronizacao_automatica=True, url_sincronizacao="").exists():
        alertas.append("Existe empresa com sincronizacao automática sem URL configurada.")

    proxima_saida = eventos_qs.filter(status__in=[StatusSincronizacao.PENDENTE, StatusSincronizacao.ERRO]).order_by("proxima_tentativa_em", "criado_em").first()
    proxima_entrada = eventos_entrada_qs.filter(status__in=[StatusEventoEntrada.RECEBIDO, StatusEventoEntrada.ERRO, StatusEventoEntrada.CONFLITO]).order_by("recebido_em").first()
    prontidao = _prontidao_sincronizacao_payload(empresas_ativas_qs, saida, entrada, esgotados_saida)
    return {
        "status": "ok",
        "gerado_em": timezone.localtime().isoformat(),
        "filtros": dados["filtros"],
        "filas": {
            "saida": {
                "pendentes": pendentes_saida,
                "pausados": pausados_saida,
                "processando": saida.get(StatusSincronizacao.PROCESSANDO, 0),
                "enviados": saida.get(StatusSincronizacao.ENVIADO, 0),
                "erros": erros_saida,
                "esgotados": esgotados_saida,
                "idade_mais_antigo_minutos": idade_saida_minutos,
                "proxima_tentativa": timezone.localtime(proxima_saida.proxima_tentativa_em).isoformat() if proxima_saida and proxima_saida.proxima_tentativa_em else None,
                "proximo_evento": str(proxima_saida.identificador) if proxima_saida else None,
            },
            "entrada": {
                "recebidos": recebidos_entrada,
                "pausados": pausados_entrada,
                "processados": entrada.get(StatusEventoEntrada.PROCESSADO, 0),
                "conflitos": conflitos_entrada,
                "erros": erros_entrada,
                "resolvidos": entrada.get(StatusEventoEntrada.RESOLVIDO, 0),
                "idade_mais_antigo_minutos": idade_entrada_minutos,
                "proximo_evento": str(proxima_entrada.identificador) if proxima_entrada else None,
            },
        },
        "retaguarda": {
            "vendas": vendas_qs.count(),
            "valor_vendas": str(vendas_qs.aggregate(total=Sum("total_liquido"))["total"] or 0),
            "documentos_fiscais": documentos_fiscais_qs.count(),
            "lancamentos_financeiros": lancamentos_financeiros_qs.count(),
            "entradas_financeiras": str(lancamentos_financeiros_qs.filter(tipo="ENTRADA").aggregate(total=Sum("valor"))["total"] or 0),
            "saidas_financeiras": str(lancamentos_financeiros_qs.filter(tipo="SAIDA").aggregate(total=Sum("valor"))["total"] or 0),
        },
        "empresas": {
            "total_ativas": empresas_ativas_qs.count(),
            "por_modo": empresas_por_modo,
            "politicas_conflito": politicas_conflito,
            "politica_manual": politica_manual,
            "politica_remoto_produtos_estoque": politica_remoto_produtos_estoque,
            "politica_local_produtos_estoque": politica_local_produtos_estoque,
            "sincronizacao_automatica": empresas_ativas_qs.filter(sincronizacao_automatica=True).count(),
        },
        "operacao": {
            "comando": "python manage.py processar_sincronizacao_completa --limite-saida 50 --limite-entrada 50",
            "agendador_windows": "schtasks /Create /TN \"Supermercado Sincronizacao\" /SC MINUTE /MO 1 ...",
            "alertas": alertas,
            "pronto": not alertas,
        },
        "prontidao": prontidao,
    }


@login_required
@role_required(*SISTEMA)
def sincronizacao(request):
    _exigir_super_admin(request.user)
    dados = _sincronizacao_querysets(request)
    eventos_qs = dados["eventos_qs"]
    eventos_entrada_qs = dados["eventos_entrada_qs"]
    vendas_qs = dados["vendas_qs"]
    documentos_fiscais_qs = dados["documentos_fiscais_qs"]
    lancamentos_financeiros_qs = dados["lancamentos_financeiros_qs"]
    eventos = _pagina_nomeada(request, eventos_qs.order_by("-criado_em"), "saida_page")
    eventos_entrada = _pagina_nomeada(request, eventos_entrada_qs.order_by("-recebido_em"), "entrada_page")
    vendas_sincronizadas = _pagina_nomeada(request, vendas_qs.order_by("-realizada_em", "-recebida_em"), "vendas_page")
    documentos_fiscais = _pagina_nomeada(request, documentos_fiscais_qs.order_by("-emitido_em", "-recebido_em"), "fiscais_page")
    lancamentos_financeiros = _pagina_nomeada(request, lancamentos_financeiros_qs.order_by("-data", "-recebido_em"), "financeiro_page")
    contagens = dict(eventos_qs.values_list("status").annotate(total=Count("id")))
    contagens_entrada = dict(eventos_entrada_qs.values_list("status").annotate(total=Count("id")))
    total_vendas_sync = vendas_qs.aggregate(total=Sum("total_liquido"))["total"] or 0
    total_entradas_financeiras = lancamentos_financeiros_qs.filter(tipo="ENTRADA").aggregate(total=Sum("valor"))["total"] or 0
    total_saidas_financeiras = lancamentos_financeiros_qs.filter(tipo="SAIDA").aggregate(total=Sum("valor"))["total"] or 0
    diagnostico_operacional = _sincronizacao_diagnostico_payload(request)
    base_dir = Path(settings.BASE_DIR)
    python_exe = base_dir / ".venv" / "Scripts" / "python.exe"
    comando_sincronizacao = f'"{python_exe}" manage.py processar_sincronizacao_completa --limite-saida 50 --limite-entrada 50'
    comando_agendador = (
        'schtasks /Create /TN "Supermercado Sincronizacao" /SC MINUTE /MO 1 '
        f'/TR "cmd /c cd /d {base_dir} && {comando_sincronizacao}" /F'
    )
    script_agendador_sincronizacao = r".\scripts\register_sync_task.ps1 -IntervaloMinutos 1 -Force"
    context = {
        "eventos": eventos,
        "eventos_entrada": eventos_entrada,
        "vendas_sincronizadas": vendas_sincronizadas,
        "documentos_fiscais_sincronizados": documentos_fiscais,
        "lancamentos_financeiros_sincronizados": lancamentos_financeiros,
        "empresas_opcoes": Empresa.objects.filter(is_active=True).order_by("nome_fantasia"),
        "filiais_opcoes": Filial.objects.filter(is_active=True).select_related("empresa").order_by("empresa__nome_fantasia", "nome"),
        "empresas_carga_opcoes": Empresa.objects.filter(is_active=True, sincronizacao_automatica=True).exclude(
            modo_implantacao=ModoImplantacao.LOCAL
        ).order_by("nome_fantasia"),
        "filiais_carga_opcoes": Filial.objects.filter(
            is_active=True,
            empresa__is_active=True,
            empresa__sincronizacao_automatica=True,
        ).exclude(empresa__modo_implantacao=ModoImplantacao.LOCAL).select_related("empresa").order_by(
            "empresa__nome_fantasia", "nome"
        ),
        "status_entrada_opcoes": StatusEventoEntrada.choices,
        "filtros": dados["filtros"],
        "pendentes": contagens.get(StatusSincronizacao.PENDENTE, 0),
        "processando": contagens.get(StatusSincronizacao.PROCESSANDO, 0),
        "enviados": contagens.get(StatusSincronizacao.ENVIADO, 0),
        "erros": contagens.get(StatusSincronizacao.ERRO, 0),
        "entrada_recebidos": contagens_entrada.get(StatusEventoEntrada.RECEBIDO, 0),
        "entrada_processados": contagens_entrada.get(StatusEventoEntrada.PROCESSADO, 0),
        "entrada_conflitos": contagens_entrada.get(StatusEventoEntrada.CONFLITO, 0),
        "entrada_erros": contagens_entrada.get(StatusEventoEntrada.ERRO, 0),
        "entrada_resolvidos": contagens_entrada.get(StatusEventoEntrada.RESOLVIDO, 0),
        "total_vendas_sincronizadas": vendas_qs.count(),
        "valor_vendas_sincronizadas": total_vendas_sync,
        "total_documentos_fiscais_sincronizados": documentos_fiscais_qs.count(),
        "total_lancamentos_financeiros_sincronizados": lancamentos_financeiros_qs.count(),
        "total_entradas_financeiras_sincronizadas": total_entradas_financeiras,
        "total_saidas_financeiras_sincronizadas": total_saidas_financeiras,
        "resultado_financeiro_sincronizado": total_entradas_financeiras - total_saidas_financeiras,
        "diagnostico_operacional": diagnostico_operacional,
        "comando_sincronizacao": comando_sincronizacao,
        "comando_agendador": comando_agendador,
        "script_agendador_sincronizacao": script_agendador_sincronizacao,
    }
    return render(request, "empresas/sincronizacao.html", context)


@login_required
@role_required(*SISTEMA)
@require_POST
def sincronizacao_carga_inicial(request):
    _exigir_super_admin(request.user)
    empresa_id = request.POST.get("empresa", "").strip()
    if not empresa_id.isdigit():
        messages.error(request, "Selecione uma empresa valida.")
        return redirect("empresas:sincronizacao")
    empresa = get_object_or_404(Empresa, pk=empresa_id)
    filial_id = request.POST.get("filial", "").strip()
    filial = None
    if filial_id:
        if not filial_id.isdigit():
            messages.error(request, "Selecione uma filial valida.")
            return redirect("empresas:sincronizacao")
        filial = get_object_or_404(Filial, pk=filial_id, empresa=empresa)

    try:
        resultado = gerar_carga_inicial_sincronizacao(
            empresa=empresa,
            filial=filial,
            limite=request.POST.get("limite", 5000),
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("empresas:sincronizacao")

    destino = f"filial {filial.nome}" if filial else "todas as filiais"
    LogAuditoria.objects.create(
        usuario=request.user,
        modulo="sincronizacao",
        acao="GERA_CARGA_INICIAL_SINCRONIZACAO",
        descricao=(
            f"Carga inicial de {empresa.nome_fantasia} para {destino}: "
            f"{resultado['estoques_processados']} saldos processados, "
            f"{resultado['produtos_criados']} produtos e "
            f"{resultado['saldos_criados']} saldos novos na fila."
        ),
        objeto_tipo="Filial" if filial else "Empresa",
        objeto_id=str(filial.pk if filial else empresa.pk),
        ip=request.META.get("REMOTE_ADDR"),
    )
    messages.success(
        request,
        "Carga inicial processada: "
        f"{resultado['produtos_criados']} produto(s) e "
        f"{resultado['saldos_criados']} saldo(s) novo(s) na fila.",
    )
    return redirect("empresas:sincronizacao")
@login_required
@role_required(*SISTEMA)
def sincronizacao_diagnostico(request):
    _exigir_super_admin(request.user)
    return JsonResponse(_sincronizacao_diagnostico_payload(request))


@login_required
@role_required(*SISTEMA)
def vendas_sincronizadas_csv(request):
    _exigir_super_admin(request.user)
    vendas_qs = _sincronizacao_querysets(request)["vendas_qs"].select_related("empresa", "filial")
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="vendas_sincronizadas.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Venda externa", "Empresa", "Filial", "Caixa", "Operador", "Cliente", "Total bruto", "Desconto", "Total líquido", "Pagamentos", "Realizada", "Recebida"])
    for venda in vendas_qs.order_by("-realizada_em", "-recebida_em"):
        writer.writerow([
            venda.venda_externa_id,
            venda.empresa.nome_fantasia,
            venda.filial.nome if venda.filial else "",
            venda.caixa_externo,
            venda.operador,
            venda.cliente,
            str(venda.total_bruto).replace(".", ","),
            str(venda.desconto).replace(".", ","),
            str(venda.total_liquido).replace(".", ","),
            len(venda.pagamentos),
            venda.realizada_em.strftime("%d/%m/%Y %H:%M:%S") if venda.realizada_em else "",
            venda.recebida_em.strftime("%d/%m/%Y %H:%M:%S") if venda.recebida_em else "",
        ])
    return response


@login_required
@role_required(*SISTEMA)
def documentos_fiscais_sincronizados_csv(request):
    _exigir_super_admin(request.user)
    documentos_qs = _sincronizacao_querysets(request)["documentos_fiscais_qs"].select_related("empresa", "filial")
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="documentos_fiscais_sincronizados.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow([
        "Documento externo",
        "Venda externa",
        "Empresa",
        "Filial",
        "Tipo",
        "Ambiente",
        "Serie",
        "Numero",
        "Status",
        "Valor total",
        "Chave de acesso",
        "Protocolo",
        "Emitido em",
        "Recebido em",
    ])
    for documento in documentos_qs.order_by("-emitido_em", "-recebido_em"):
        writer.writerow([
            documento.documento_externo_id,
            documento.venda_externa_id,
            documento.empresa.nome_fantasia,
            documento.filial.nome if documento.filial else "",
            documento.tipo_documento,
            documento.ambiente,
            documento.serie,
            documento.numero,
            documento.status,
            str(documento.valor_total).replace(".", ","),
            documento.chave_acesso,
            documento.protocolo,
            documento.emitido_em.strftime("%d/%m/%Y %H:%M:%S") if documento.emitido_em else "",
            documento.recebido_em.strftime("%d/%m/%Y %H:%M:%S") if documento.recebido_em else "",
        ])
    return response


@login_required
@role_required(*SISTEMA)
def lancamentos_financeiros_sincronizados_csv(request):
    _exigir_super_admin(request.user)
    lancamentos_qs = _sincronizacao_querysets(request)["lancamentos_financeiros_qs"].select_related("empresa", "filial")
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="lancamentos_financeiros_sincronizados.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow([
        "Lancamento externo", "Empresa", "Filial", "Data", "Tipo", "Origem", "Descricao",
        "Valor", "Conta de movimento", "Centro de custo", "Conta contabil", "Usuario", "Estorno de", "Recebido em",
    ])
    for lancamento in lancamentos_qs.order_by("-data", "-recebido_em"):
        writer.writerow([
            lancamento.lancamento_externo_id,
            lancamento.empresa.nome_fantasia,
            lancamento.filial.nome if lancamento.filial else "",
            lancamento.data.strftime("%d/%m/%Y"),
            lancamento.tipo,
            lancamento.origem,
            lancamento.descricao,
            str(lancamento.valor).replace(".", ","),
            lancamento.conta_movimento,
            lancamento.centro_custo,
            lancamento.conta_contabil,
            lancamento.usuario,
            lancamento.estorno_de_externo_id,
            lancamento.recebido_em.strftime("%d/%m/%Y %H:%M:%S"),
        ])
    return response


@login_required
@role_required(*SISTEMA)
def eventos_sincronizacao_csv(request):
    _exigir_super_admin(request.user)
    eventos_qs = _sincronizacao_querysets(request)["eventos_qs"].select_related("empresa", "filial")
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="eventos_sincronizacao_saida.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Identificador", "Tipo", "Empresa", "Filial", "Objeto", "Chave idempotente", "Status", "Tentativas", "Ultimo erro", "Criado em", "Processado em"])
    for evento in eventos_qs.order_by("-criado_em"):
        writer.writerow([
            evento.identificador,
            evento.tipo,
            evento.empresa.nome_fantasia,
            evento.filial.nome if evento.filial else "",
            f"{evento.objeto_tipo} #{evento.objeto_id}",
            evento.chave_idempotencia,
            evento.get_status_display(),
            evento.tentativas,
            evento.ultimo_erro,
            evento.criado_em.strftime("%d/%m/%Y %H:%M:%S"),
            evento.processado_em.strftime("%d/%m/%Y %H:%M:%S") if evento.processado_em else "",
        ])
    return response


@login_required
@role_required(*SISTEMA)
def eventos_entrada_sincronizacao_csv(request):
    _exigir_super_admin(request.user)
    eventos_qs = _sincronizacao_querysets(request)["eventos_entrada_qs"].select_related("empresa", "resolvido_por")
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="eventos_sincronizacao_entrada.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Identificador", "Tipo", "Empresa", "Chave idempotente", "Status", "Ultimo erro", "Resolucao", "Resolvido por", "Recebido em", "Processado em", "Resolvido em"])
    for evento in eventos_qs.order_by("-recebido_em"):
        writer.writerow([
            evento.identificador,
            evento.tipo,
            evento.empresa.nome_fantasia,
            evento.chave_idempotencia,
            evento.get_status_display(),
            evento.ultimo_erro,
            evento.resolucao_conflito,
            evento.resolvido_por.get_username() if evento.resolvido_por else "",
            evento.recebido_em.strftime("%d/%m/%Y %H:%M:%S"),
            evento.processado_em.strftime("%d/%m/%Y %H:%M:%S") if evento.processado_em else "",
            evento.resolvido_em.strftime("%d/%m/%Y %H:%M:%S") if evento.resolvido_em else "",
        ])
    return response


@login_required
@role_required(*SISTEMA)
def venda_sincronizada_detalhe(request, pk):
    _exigir_super_admin(request.user)
    venda = get_object_or_404(
        VendaSincronizada.objects.select_related("empresa", "filial", "evento"),
        pk=pk,
    )
    itens = [
        {
            "produto": item.get("nome") or item.get("produto") or "Produto sincronizado",
            "codigo_barras": item.get("codigo_barras") or "-",
            "quantidade": item.get("quantidade") or "-",
            "preco_unitario": item.get("preco_unitario") or "0,00",
            "total": item.get("total") or "0,00",
        }
        for item in venda.itens
        if isinstance(item, dict)
    ]
    pagamentos = [
        {
            "tipo": pagamento.get("tipo") or "-",
            "valor": pagamento.get("valor") or "0,00",
            "status": pagamento.get("status") or "Confirmado",
        }
        for pagamento in venda.pagamentos
        if isinstance(pagamento, dict)
    ]
    return render(
        request,
        "empresas/venda_sincronizada_detalhe.html",
        {"venda": venda, "itens": itens, "pagamentos": pagamentos},
    )


@login_required
@role_required(*SISTEMA)
def documento_fiscal_sincronizado_detalhe(request, pk):
    _exigir_super_admin(request.user)
    documento = get_object_or_404(
        DocumentoFiscalSincronizado.objects.select_related("empresa", "filial", "evento"),
        pk=pk,
    )
    payload_formatado = json.dumps(documento.payload, ensure_ascii=False, indent=2)
    return render(
        request,
        "empresas/documento_fiscal_sincronizado_detalhe.html",
        {"documento": documento, "payload_formatado": payload_formatado},
    )


@login_required
@role_required(*SISTEMA)
def evento_sincronizacao_detalhe(request, pk):
    _exigir_super_admin(request.user)
    evento = get_object_or_404(
        EventoSincronizacao.objects.select_related("empresa", "filial"),
        pk=pk,
    )
    payload_formatado = json.dumps(evento.payload, ensure_ascii=False, indent=2)
    return render(
        request,
        "empresas/evento_sincronizacao_detalhe.html",
        {"evento": evento, "payload_formatado": payload_formatado},
    )


@login_required
@role_required(*SISTEMA)
def evento_entrada_sincronizacao_detalhe(request, pk):
    _exigir_super_admin(request.user)
    evento = get_object_or_404(
        EventoEntradaSincronizacao.objects.select_related("empresa"),
        pk=pk,
    )
    payload_formatado = json.dumps(evento.payload, ensure_ascii=False, indent=2)
    return render(
        request,
        "empresas/evento_entrada_sincronizacao_detalhe.html",
        {"evento": evento, "payload_formatado": payload_formatado},
    )


@login_required
@role_required(*SISTEMA)
def sincronizacao_entrada_resolver_conflito(request, pk):
    _exigir_super_admin(request.user)
    if request.method == "POST":
        evento = get_object_or_404(EventoEntradaSincronizacao, pk=pk)
        resolucao = request.POST.get("resolucao_conflito", "").strip()
        if evento.status != StatusEventoEntrada.CONFLITO:
            messages.warning(request, "Apenas eventos em conflito podem ser resolvidos manualmente.")
        elif not resolucao:
            messages.warning(request, "Informe a decisao tomada para resolver o conflito.")
            return redirect("empresas:evento_entrada_sincronizacao_detalhe", pk=evento.pk)
        else:
            evento.status = StatusEventoEntrada.RESOLVIDO
            evento.resolucao_conflito = resolucao
            evento.resolvido_por = request.user
            evento.resolvido_em = timezone.now()
            evento.save(update_fields=["status", "resolucao_conflito", "resolvido_por", "resolvido_em", "atualizado_em"])
            LogAuditoria.objects.create(
                usuario=request.user,
                modulo="sincronizacao",
                acao="RESOLVE_CONFLITO_SINCRONIZACAO",
                descricao=f"Conflito do evento de entrada {evento.identificador} resolvido: {resolucao}",
                objeto_tipo="EventoEntradaSincronizacao",
                objeto_id=str(evento.pk),
                ip=request.META.get("REMOTE_ADDR"),
            )
            messages.success(request, "Conflito marcado como resolvido manualmente.")
    return redirect("empresas:evento_entrada_sincronizacao_detalhe", pk=pk)


@login_required
@role_required(*SISTEMA)
def sincronizacao_reprocessar(request, pk):
    _exigir_super_admin(request.user)
    if request.method == "POST":
        evento = get_object_or_404(EventoSincronizacao, pk=pk)
        if not evento.empresa.sincronizacao_operacional_habilitada:
            if evento.status != StatusSincronizacao.PAUSADO:
                evento.status = StatusSincronizacao.PAUSADO
                evento.proxima_tentativa_em = None
                evento.ultimo_erro = "Pausado pela política de implantação ou sincronização desativada."
                evento.save(update_fields=["status", "proxima_tentativa_em", "ultimo_erro", "atualizado_em"])
            messages.warning(request, "Ative o modo híbrido com sincronização automática e URL HTTPS antes de reprocessar.")
        else:
            evento.status = StatusSincronizacao.PENDENTE
            evento.tentativas = 0
            evento.proxima_tentativa_em = None
            evento.ultimo_erro = ""
            evento.save(update_fields=["status", "tentativas", "proxima_tentativa_em", "ultimo_erro", "atualizado_em"])
            LogAuditoria.objects.create(
                usuario=request.user,
                modulo="sincronizacao",
                acao="REPROCESSA_SINCRONIZACAO_SAIDA",
                descricao=f"Evento de saida {evento.identificador} devolvido para a fila.",
                objeto_tipo="EventoSincronizacao",
                objeto_id=str(evento.pk),
                ip=request.META.get("REMOTE_ADDR"),
            )
            messages.success(request, "Evento devolvido para a fila de sincronizacao.")
    return redirect("empresas:sincronizacao")


@login_required
@role_required(*SISTEMA)
def sincronizacao_entrada_reprocessar(request, pk):
    _exigir_super_admin(request.user)
    if request.method == "POST":
        evento = get_object_or_404(EventoEntradaSincronizacao, pk=pk)
        if not evento.empresa.sincronizacao_operacional_habilitada:
            if evento.status != StatusEventoEntrada.PAUSADO:
                evento.status = StatusEventoEntrada.PAUSADO
                evento.ultimo_erro = "Pausado pela política de implantação ou sincronização desativada."
                evento.save(update_fields=["status", "ultimo_erro", "atualizado_em"])
            messages.warning(request, "Ative o modo híbrido com sincronização automática e URL HTTPS antes de reprocessar.")
        elif evento.status in {StatusEventoEntrada.ERRO, StatusEventoEntrada.CONFLITO}:
            evento.status = StatusEventoEntrada.RECEBIDO
            evento.ultimo_erro = ""
            evento.processado_em = None
            evento.save(update_fields=["status", "ultimo_erro", "processado_em", "atualizado_em"])
            LogAuditoria.objects.create(
                usuario=request.user,
                modulo="sincronizacao",
                acao="REPROCESSA_SINCRONIZACAO_ENTRADA",
                descricao=f"Evento de entrada {evento.identificador} devolvido para processamento.",
                objeto_tipo="EventoEntradaSincronizacao",
                objeto_id=str(evento.pk),
                ip=request.META.get("REMOTE_ADDR"),
            )
            messages.success(request, "Evento de entrada devolvido para processamento.")
        else:
            messages.warning(request, "Apenas eventos de entrada com erro ou conflito podem ser reprocessados.")
    return redirect("empresas:sincronizacao")
