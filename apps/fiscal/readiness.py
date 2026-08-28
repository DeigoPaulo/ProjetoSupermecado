from .adapters import diagnosticar_adaptador_sefaz
from .models import (
    AmbienteFiscal,
    DocumentoFiscal,
    NaturezaOperacao,
    SerieFiscal,
    StatusDocumentoFiscal,
    TipoDocumentoFiscal,
)
from .validacoes import diagnosticar_schemas_fiscais
from .perfis_uf import pendencias_endpoints_nfce


def diagnostico_prontidao_homologacao_goias(configuracao):
    """Diagnóstico local por filial; não acessa rede nem retorna segredos."""
    filial = configuracao.filial
    adapter = diagnosticar_adaptador_sefaz(filial=filial)
    operacional = adapter["configuracao_operacional"]
    schema = diagnosticar_schemas_fiscais()
    natureza = NaturezaOperacao.objects.filter(
        empresa_id=filial.empresa_id,
        tipo_documento=TipoDocumentoFiscal.NFCE,
        ativo=True,
        padrao=True,
    ).exists()
    serie = SerieFiscal.objects.filter(
        filial=filial,
        tipo_documento=TipoDocumentoFiscal.NFCE,
        ativo=True,
    ).exists()
    documento_homologacao = DocumentoFiscal.objects.filter(
        filial=filial,
        ambiente=AmbienteFiscal.HOMOLOGACAO,
        status=StatusDocumentoFiscal.EMITIDO,
    ).exists()
    itens = [
        (
            "Dados da filial",
            bool(
                filial.uf == "GO"
                and filial.codigo_municipio_ibge
                and configuracao.inscricao_estadual
            ),
            "UF Goiás, código IBGE e inscrição estadual configurados.",
        ),
        (
            "Ambiente de homologação",
            configuracao.ambiente == AmbienteFiscal.HOMOLOGACAO,
            "A filial piloto deve permanecer explicitamente em homologação.",
        ),
        (
            "Configuração NFC-e",
            bool(configuracao.ativo and configuracao.csc_id and configuracao.csc_token),
            "Configuração fiscal ativa com ID CSC e token CSC.",
        ),
        (
            "URLs oficiais de Goiás",
            not pendencias_endpoints_nfce(filial, configuracao),
            "QR Code e consulta NFC-e coerentes com UF e ambiente.",
        ),
        (
            "Certificado A1",
            configuracao.certificado_status == "valido",
            "Certificado A1 protegido e dentro da validade.",
        ),
        (
            "Série e natureza",
            bool(serie and natureza),
            "Série NFC-e e natureza de operação padrão ativas.",
        ),
        (
            "Schema XML",
            bool(schema["pronto"] or adapter["valida_schema"]),
            "Schema local válido ou validação declarada pelo adaptador.",
        ),
        (
            "Adaptador SEFAZ",
            bool(adapter["carregavel"]),
            "Adaptador oficial configurado e carregável.",
        ),
        (
            "Configuração do adaptador",
            bool(operacional["diagnostico_disponivel"] and operacional["pronto"]),
            "Credencial da filial, ambiente e travas validados localmente sem transmissão.",
        ),
        (
            "Evidência de homologação",
            documento_homologacao,
            "Existe documento emitido no ambiente de homologação.",
        ),
    ]
    checklist = [
        {"titulo": titulo, "pronto": pronto, "detalhe": detalhe}
        for titulo, pronto, detalhe in itens
    ]
    pendencias = [item["titulo"] for item in checklist if not item["pronto"]]
    return {
        "contrato": "fiscal_branch_homologation_readiness_v1",
        "filial": {
            "id": filial.pk,
            "nome": filial.nome,
            "cnpj_final": (filial.cnpj or filial.empresa.cnpj or "")[-4:],
            "uf": filial.uf,
            "ambiente": configuracao.ambiente,
        },
        "pronto": not pendencias,
        "total_itens": len(checklist),
        "itens_prontos": len(checklist) - len(pendencias),
        "pendencias": pendencias,
        "checklist": checklist,
    }
