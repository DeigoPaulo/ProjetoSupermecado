from apps.empresas.models import Empresa, Filial

from .models import ConfiguracaoImpressao, ModeloPapel, TipoDocumentoImpressao


DEFAULT_MENSAGENS = {
    TipoDocumentoImpressao.CUPOM_NAO_FISCAL: "Documento sem valor fiscal. Obrigado pela preferência.",
    TipoDocumentoImpressao.CUPOM_FISCAL: "Documento fiscal emitido conforme configuração fiscal da filial.",
    TipoDocumentoImpressao.PEDIDO_SEPARACAO: "Documento auxiliar de venda. Sem baixa de estoque até a conversão.",
    TipoDocumentoImpressao.ETIQUETA: "Etiqueta de gôndola.",
    TipoDocumentoImpressao.RELATORIO: "Relatório gerado pelo sistema.",
    TipoDocumentoImpressao.FECHAMENTO_CAIXA: "Conferência sujeita à aprovação do supervisor.",
}


def configuracao_impressao_para(filial, tipo_documento):
    if not filial:
        return None
    return (
        ConfiguracaoImpressao.objects.filter(filial=filial, tipo_documento=tipo_documento, is_active=True).first()
        or ConfiguracaoImpressao.objects.filter(empresa=filial.empresa, filial__isnull=True, tipo_documento=tipo_documento, is_active=True).first()
    )


def estilos_impressao(configuracao):
    papel = ModeloPapel.BOBINA_80
    fonte = 11
    margens = (4, 4, 4, 4)
    if configuracao:
        papel = configuracao.modelo_papel
        fonte = configuracao.tamanho_fonte
        margens = (
            configuracao.margem_superior_mm,
            configuracao.margem_direita_mm,
            configuracao.margem_inferior_mm,
            configuracao.margem_esquerda_mm,
        )
    largura = {"58MM": "58mm", "80MM": "80mm", "A4": "210mm"}.get(papel, "80mm")
    page_size = "A4" if papel == ModeloPapel.A4 else f"{largura} auto"
    return {
        "largura": largura,
        "page_size": page_size,
        "fonte": fonte,
        "margem_css": f"{margens[0]}mm {margens[1]}mm {margens[2]}mm {margens[3]}mm",
    }


def criar_configuracoes_padrao(empresa=None):
    criadas = 0
    empresa = empresa or Empresa.objects.filter(is_active=True).order_by("id").first()
    if not empresa:
        return criadas
    for tipo in [
        TipoDocumentoImpressao.CUPOM_NAO_FISCAL,
        TipoDocumentoImpressao.CUPOM_FISCAL,
        TipoDocumentoImpressao.PEDIDO_SEPARACAO,
        TipoDocumentoImpressao.ETIQUETA,
        TipoDocumentoImpressao.RELATORIO,
        TipoDocumentoImpressao.FECHAMENTO_CAIXA,
    ]:
        _, criado = ConfiguracaoImpressao.objects.get_or_create(
            empresa=empresa,
            filial=None,
            tipo_documento=tipo,
            defaults={
                "modelo_papel": ModeloPapel.BOBINA_80 if tipo not in {TipoDocumentoImpressao.RELATORIO} else ModeloPapel.A4,
                "mensagem_rodape": DEFAULT_MENSAGENS.get(tipo, ""),
                "tamanho_fonte": 11 if tipo != TipoDocumentoImpressao.RELATORIO else 10,
            },
        )
        criadas += int(criado)
    for filial in Filial.objects.filter(empresa=empresa, is_active=True):
        _, criado = ConfiguracaoImpressao.objects.get_or_create(
            empresa=empresa,
            filial=filial,
            tipo_documento=TipoDocumentoImpressao.CUPOM_NAO_FISCAL,
            defaults={"modelo_papel": ModeloPapel.BOBINA_80, "mensagem_rodape": DEFAULT_MENSAGENS[TipoDocumentoImpressao.CUPOM_NAO_FISCAL]},
        )
        criadas += int(criado)
        _, criado = ConfiguracaoImpressao.objects.get_or_create(
            empresa=empresa,
            filial=filial,
            tipo_documento=TipoDocumentoImpressao.CUPOM_FISCAL,
            defaults={"modelo_papel": ModeloPapel.BOBINA_80, "mensagem_rodape": DEFAULT_MENSAGENS[TipoDocumentoImpressao.CUPOM_FISCAL]},
        )
        criadas += int(criado)
    return criadas
