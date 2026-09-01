from django import forms

from apps.clientes.escopo import empresa_id_do_usuario

from .cfop import validar_cfop

from .models import (
    ConfiguracaoFiscal,
    HomologacaoFiscal,
    ProvedorEmissaoFiscal,
    InutilizacaoNumeracaoFiscal,
    ModoTransicaoIbsCbs,
    NaturezaOperacao,
    SerieFiscal,
    StatusHomologacaoFiscal,
)
from .perfis_uf import aplicar_endpoints_nfce_uf, pendencias_endpoints_nfce, perfil_fiscal_uf


class ConfiguracaoFiscalForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.perfil_fiscal = perfil_fiscal_uf(
            getattr(getattr(self.instance, "filial", None), "uf", "")
        )
        empresa_id = empresa_id_do_usuario(user) if user else None
        if empresa_id is not None:
            self.fields["filial"].queryset = self.fields["filial"].queryset.filter(
                empresa_id=empresa_id
            )
        if "provedor_emissao" in self.fields:
            self.fields["provedor_emissao"].required = False
        if not user or not user.is_superuser:
            self.fields.pop("provedor_emissao", None)

    certificado_arquivo = forms.FileField(
        required=False,
        label="Certificado A1 (.pfx/.p12)",
        help_text="O arquivo será armazenado criptografado e não ficara disponível para download.",
    )
    certificado_senha = forms.CharField(
        required=False,
        label="Senha do certificado",
        widget=forms.PasswordInput(render_value=False),
        help_text="Informe a senha apenas quando enviar um novo certificado.",
    )

    class Meta:
        model = ConfiguracaoFiscal
        fields = [
            "filial",
            "provedor_emissao",
            "ambiente",
            "regime_tributario",
            "crt",
            "inscricao_estadual",
            "csc_id",
            "csc_token",
            "url_qrcode_nfce",
            "url_consulta_nfce",
            "certificado_nome",
            "certificado_validade",
            "permite_contingencia_offline",
            "modo_transicao_ibs_cbs",
            "ibs_cbs_vigencia_inicio",
            "ibs_cbs_versao_leiaute",
            "certificado_arquivo",
            "certificado_senha",
            "ativo",
        ]
        widgets = {
            "certificado_validade": forms.DateInput(attrs={"type": "date"}),
            "ibs_cbs_vigencia_inicio": forms.DateInput(attrs={"type": "date"}),
        }

    def clean_certificado_arquivo(self):
        arquivo = self.cleaned_data.get("certificado_arquivo")
        if not arquivo:
            return arquivo
        nome = arquivo.name.lower()
        if not nome.endswith((".pfx", ".p12")):
            raise forms.ValidationError(
                "Envie um certificado A1 nos formatos .pfx ou .p12."
            )
        if arquivo.size > 2 * 1024 * 1024:
            raise forms.ValidationError("O certificado deve ter no máximo 2 MB.")
        return arquivo

    def clean(self):
        cleaned = super().clean()
        self.perfil_fiscal = aplicar_endpoints_nfce_uf(cleaned) or self.perfil_fiscal
        arquivo = cleaned.get("certificado_arquivo")
        senha = cleaned.get("certificado_senha")
        if arquivo and not senha:
            self.add_error(
                "certificado_senha", "Informe a senha do certificado A1."
            )
        if senha and not arquivo:
            self.add_error(
                "certificado_arquivo",
                "Envie o arquivo do certificado para trocar a senha.",
            )
        modo_ibs_cbs = (
            cleaned.get("modo_transicao_ibs_cbs") or ModoTransicaoIbsCbs.LEGADO
        )
        if modo_ibs_cbs != ModoTransicaoIbsCbs.LEGADO:
            if not cleaned.get("ibs_cbs_vigencia_inicio"):
                self.add_error(
                    "ibs_cbs_vigencia_inicio",
                    "Informe a data de vigência aprovada pelo contador.",
                )
            if not (cleaned.get("ibs_cbs_versao_leiaute") or "").strip():
                self.add_error(
                    "ibs_cbs_versao_leiaute",
                    "Informe a Nota Técnica ou versão do leiaute homologado.",
                )
        if modo_ibs_cbs == ModoTransicaoIbsCbs.EMISSAO_HOMOLOGADA:
            self.add_error(
                "modo_transicao_ibs_cbs",
                "A emissão IBS/CBS ainda não está disponível nesta versão. "
                "Mantenha o modo Preparação até instalar o schema oficial e "
                "homologar o adaptador fiscal.",
            )

        filial = cleaned.get("filial")
        provedor = cleaned.get("provedor_emissao") or getattr(
            self.instance,
            "provedor_emissao",
            ProvedorEmissaoFiscal.PADRAO_SERVIDOR,
        )
        if (
            "provedor_emissao" in self.fields
            and filial
            and provedor == ProvedorEmissaoFiscal.SEFAZ_DIRETA_GO
            and filial.uf != "GO"
        ):
            self.add_error(
                "provedor_emissao",
                "A conexão direta está disponível somente para filiais de Goiás.",
            )

        if filial and self.perfil_fiscal:
            self.instance.ambiente = (
                cleaned.get("ambiente") or self.instance.ambiente
            )
            self.instance.url_qrcode_nfce = cleaned.get("url_qrcode_nfce") or ""
            self.instance.url_consulta_nfce = (
                cleaned.get("url_consulta_nfce") or ""
            )
            for pendencia in pendencias_endpoints_nfce(filial, self.instance):
                campo = (
                    "url_qrcode_nfce"
                    if "QR Code" in pendencia
                    else "url_consulta_nfce"
                )
                self.add_error(campo, pendencia)
        return cleaned


class SerieFiscalForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        empresa_id = empresa_id_do_usuario(user) if user else None
        if empresa_id is not None:
            self.fields["filial"].queryset = self.fields["filial"].queryset.filter(empresa_id=empresa_id)
    class Meta:
        model = SerieFiscal
        fields = ["filial", "tipo_documento", "serie", "proximo_numero", "ativo"]


class InutilizacaoNumeracaoFiscalForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        empresa_id = empresa_id_do_usuario(user) if user else None
        if empresa_id is not None:
            self.fields["filial"].queryset = self.fields["filial"].queryset.filter(
                empresa_id=empresa_id,
                is_active=True,
            )
        self.fields["ano"].widget.attrs.update({"min": 2006, "max": 2099})
        self.fields["serie"].widget.attrs.update({"min": 0, "max": 889})
        self.fields["numero_inicial"].widget.attrs.update({"min": 1, "max": 999999999})
        self.fields["numero_final"].widget.attrs.update({"min": 1, "max": 999999999})
        self.fields["justificativa"].widget.attrs.update({"minlength": 15, "maxlength": 255, "rows": 3})

    class Meta:
        model = InutilizacaoNumeracaoFiscal
        fields = [
            "filial",
            "tipo_documento",
            "ano",
            "serie",
            "numero_inicial",
            "numero_final",
            "justificativa",
        ]
        widgets = {
            "justificativa": forms.Textarea,
        }


class NaturezaOperacaoForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        empresa_id = empresa_id_do_usuario(user) if user else None
        if empresa_id is not None:
            self.instance.empresa_id = empresa_id
            self.fields.pop("empresa", None)
        elif self.instance.pk:
            self.fields["empresa"].disabled = True

    class Meta:
        model = NaturezaOperacao
        fields = [
            "empresa", "descricao", "cfop", "tipo_documento", "movimenta_estoque",
            "ipi_incluso_preco", "ipi_compoe_base_icms", "ipi_compoe_base_pis_cofins",
            "ativo",
        ]

    def clean(self):
        cleaned = super().clean()
        if self.user and empresa_id_do_usuario(self.user) == 0:
            self.add_error(None, "Usuario sem empresa ativa nao pode cadastrar natureza de operacao.")
        cfop = cleaned.get("cfop")
        if cfop:
            pendencia_cfop = validar_cfop(
                cfop,
                direcao="SAIDA",
                modelo=cleaned.get("tipo_documento"),
            )
            if pendencia_cfop:
                self.add_error("cfop", pendencia_cfop)
        if not cleaned.get("ipi_incluso_preco") and (
            cleaned.get("ipi_compoe_base_icms") or cleaned.get("ipi_compoe_base_pis_cofins")
        ):
            self.add_error(
                "ipi_incluso_preco",
                "Para definir as bases, confirme primeiro que o IPI tributado está incluído no preço.",
            )
        return cleaned

    def save(self, commit=True):
        natureza = super().save(commit=False)
        empresa_id = empresa_id_do_usuario(self.user) if self.user else None
        if empresa_id is not None:
            natureza.empresa_id = empresa_id
        if commit:
            natureza.save()
            self.save_m2m()
        return natureza
class HomologacaoFiscalForm(forms.ModelForm):
    class Meta:
        model = HomologacaoFiscal
        fields = ["status", "responsavel_tecnico", "evidencia_referencia", "observacoes"]
        widgets = {
            "observacoes": forms.Textarea(attrs={"rows": 5}),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("status") == StatusHomologacaoFiscal.CONCLUIDA:
            if not (cleaned.get("responsavel_tecnico") or "").strip():
                self.add_error("responsavel_tecnico", "Informe quem executou a homologação técnica.")
            if not (cleaned.get("evidencia_referencia") or "").strip():
                self.add_error("evidencia_referencia", "Informe a referência da evidência ou do chamado técnico.")
        return cleaned

class ImportarDFeRecebidoForm(forms.Form):
    arquivo_xml = forms.FileField(
        label="XML autorizado da NF-e",
        help_text="Armazena o documento na caixa fiscal. Não cria entrada, estoque, financeiro ou manifestação.",
    )

    def clean_arquivo_xml(self):
        arquivo = self.cleaned_data["arquivo_xml"]
        if not arquivo.name.lower().endswith(".xml"):
            raise forms.ValidationError("Envie um arquivo XML de NF-e.")
        if arquivo.size > 5 * 1024 * 1024:
            raise forms.ValidationError("O XML deve ter no máximo 5 MB.")
        return arquivo