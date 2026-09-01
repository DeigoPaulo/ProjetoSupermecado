from django import forms
from django.core.exceptions import ImproperlyConfigured, ValidationError

from apps.accounts.models import PerfilUsuario, TipoPerfil
from apps.clientes.escopo import clientes_para_usuario
from apps.empresas.models import Empresa, Filial
from apps.core_forms import aplicar_select2
from apps.fornecedores.escopo import fornecedores_para_usuario

from .extrato_adapters import listar_adaptadores_extrato, validar_arquivo_adaptador

from .models import CategoriaFinanceira, CentroCusto, ContaContabil, ContaFinanceira, ContaMovimentoFinanceiro, FormatoEntregaContabil, RegraLiquidacaoEletronica, ResponsavelEFDICMSIPI, TransferenciaFinanceira


def _filiais_para_usuario(user):
    filiais = Filial.objects.filter(is_active=True)
    if not user or user.is_superuser:
        return filiais
    perfil = PerfilUsuario.objects.select_related("filial").filter(
        usuario=user, is_active=True, filial__isnull=False
    ).first()
    if not perfil:
        return filiais.none()
    if perfil.tipo == TipoPerfil.ADMINISTRADOR:
        return filiais.filter(empresa_id=perfil.filial.empresa_id)
    return filiais.filter(pk=perfil.filial_id)


class ContaContabilForm(forms.ModelForm):
    class Meta:
        model = ContaContabil
        fields = ["empresa", "codigo", "nome", "natureza", "tipo", "conta_pai", "ativa"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        filiais = _filiais_para_usuario(user)
        self.empresa_id_do_usuario = filiais.values_list("empresa", flat=True).first()
        if user and user.is_superuser:
            self.fields["empresa"].queryset = Empresa.objects.order_by("nome_fantasia", "razao_social")
            self.fields["conta_pai"].queryset = ContaContabil.objects.filter(ativa=True).order_by("empresa", "codigo")
            aplicar_select2(self, ["empresa", "conta_pai"])
        else:
            self.fields.pop("empresa")
            self.fields["conta_pai"].queryset = ContaContabil.objects.filter(
                empresa_id=self.empresa_id_do_usuario, ativa=True
            ).order_by("codigo") if self.empresa_id_do_usuario else ContaContabil.objects.none()
            aplicar_select2(self, ["conta_pai"])
        if self.instance.pk:
            self.fields["conta_pai"].queryset = self.fields["conta_pai"].queryset.exclude(pk=self.instance.pk)

    def clean(self):
        cleaned = super().clean()
        empresa = cleaned.get("empresa")
        if "empresa" not in self.fields:
            empresa = Empresa.objects.filter(pk=self.empresa_id_do_usuario).first()
            cleaned["empresa"] = empresa
        if not empresa:
            raise ValidationError("Não foi possível identificar a empresa da conta contábil.")
        conta_pai = cleaned.get("conta_pai")
        if conta_pai and conta_pai.empresa_id != empresa.pk:
            self.add_error("conta_pai", "A conta superior pertence a outra empresa.")
        if self.instance.pk and self.instance.empresa_id != empresa.pk and (
            self.instance.subcontas.exists() or self.instance.categorias_financeiras.exists() or self.instance.lancamentos.exists()
        ):
            self.add_error("empresa", "Não altere a empresa de uma conta contábil em uso.")
        return cleaned

    def save(self, commit=True):
        conta = super().save(commit=False)
        if "empresa" not in self.fields:
            conta.empresa_id = self.empresa_id_do_usuario
        if commit:
            conta.full_clean()
            conta.save()
        return conta


class CentroCustoForm(forms.ModelForm):
    class Meta:
        model = CentroCusto
        fields = ["empresa", "codigo", "nome", "ativo"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        filiais = _filiais_para_usuario(user)
        self.empresa_id_do_usuario = filiais.values_list("empresa", flat=True).first()
        if user and user.is_superuser:
            self.fields["empresa"].queryset = Empresa.objects.order_by("nome_fantasia", "razao_social")
            aplicar_select2(self, ["empresa"])
        else:
            self.fields.pop("empresa")

    def clean(self):
        cleaned_data = super().clean()
        empresa = cleaned_data.get("empresa")
        if "empresa" not in self.fields:
            empresa = Empresa.objects.filter(pk=self.empresa_id_do_usuario).first()
            cleaned_data["empresa"] = empresa
        if not empresa:
            raise ValidationError("Não foi possível identificar a empresa do centro de custo.")
        if self.instance.pk and self.instance.empresa_id != empresa.id and self.instance.contas_financeiras.exists():
            self.add_error("empresa", "Não altere a empresa de um centro de custo que j? possui contas financeiras.")
        return cleaned_data

    def save(self, commit=True):
        centro = super().save(commit=False)
        if "empresa" not in self.fields:
            centro.empresa_id = self.empresa_id_do_usuario
        if commit:
            centro.save()
        return centro


class CategoriaFinanceiraForm(forms.ModelForm):
    class Meta:
        model = CategoriaFinanceira
        fields = ["empresa", "nome", "tipo", "conta_contabil", "is_active"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        filiais = _filiais_para_usuario(user)
        self.empresa_id_do_usuario = filiais.values_list("empresa", flat=True).first()
        if user and user.is_superuser:
            self.fields["empresa"].queryset = Empresa.objects.order_by("nome_fantasia", "razao_social")
            self.fields["conta_contabil"].queryset = ContaContabil.objects.filter(
                ativa=True, tipo="ANALITICA"
            ).order_by("empresa", "codigo")
            aplicar_select2(self, ["empresa", "conta_contabil"])
        else:
            self.fields.pop("empresa")
            self.fields["conta_contabil"].queryset = ContaContabil.objects.filter(
                empresa_id=self.empresa_id_do_usuario, ativa=True, tipo="ANALITICA"
            ).order_by("codigo") if self.empresa_id_do_usuario else ContaContabil.objects.none()
            aplicar_select2(self, ["conta_contabil"])

    def clean(self):
        cleaned_data = super().clean()
        empresa = cleaned_data.get("empresa")
        if "empresa" not in self.fields:
            empresa = Empresa.objects.filter(pk=self.empresa_id_do_usuario).first()
            cleaned_data["empresa"] = empresa
        conta_contabil = cleaned_data.get("conta_contabil")
        if conta_contabil and empresa and conta_contabil.empresa_id != empresa.pk:
            self.add_error("conta_contabil", "A conta contábil pertence a outra empresa.")
        if not empresa:
            raise ValidationError("Não foi possível identificar a empresa da categoria financeira.")
        if self.instance.pk and self.instance.empresa_id != empresa.id and self.instance.contas.exists():
            self.add_error("empresa", "Não altere a empresa de uma categoria que j? possui contas financeiras.")
        return cleaned_data

    def save(self, commit=True):
        categoria = super().save(commit=False)
        if "empresa" not in self.fields:
            categoria.empresa_id = self.empresa_id_do_usuario
        if commit:
            categoria.full_clean()
            categoria.save()
        return categoria


class ContaFinanceiraForm(forms.ModelForm):
    class Meta:
        model = ContaFinanceira
        fields = [
            "tipo",
            "descricao",
            "categoria",
            "centro_custo",
            "filial",
            "fornecedor",
            "cliente",
            "valor",
            "vencimento",
            "observacoes",
        ]
        widgets = {
            "vencimento": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        filiais = _filiais_para_usuario(user)
        self.fields["filial"].queryset = filiais
        empresa_id = filiais.values_list("empresa", flat=True).first()
        if user and user.is_superuser:
            self.fields["categoria"].queryset = CategoriaFinanceira.objects.filter(is_active=True)
            self.fields["centro_custo"].queryset = CentroCusto.objects.filter(ativo=True)
        else:
            self.fields["categoria"].queryset = CategoriaFinanceira.objects.filter(empresa_id=empresa_id, is_active=True) if empresa_id else CategoriaFinanceira.objects.none()
            self.fields["centro_custo"].queryset = CentroCusto.objects.filter(empresa_id=empresa_id, ativo=True) if empresa_id else CentroCusto.objects.none()
        self.fields["cliente"].queryset = clientes_para_usuario(user, self.fields["cliente"].queryset)
        self.fields["fornecedor"].queryset = fornecedores_para_usuario(user, self.fields["fornecedor"].queryset)
        aplicar_select2(
            self,
            ["categoria", "centro_custo", "filial", "fornecedor", "cliente"],
            ajax_urls={
                "filial": "/empresas/filiais/busca.json",
                "fornecedor": "/fornecedores/busca.json",
                "cliente": "/clientes/busca.json",
            },
        )

    def clean(self):
        cleaned_data = super().clean()
        fornecedor = cleaned_data.get("fornecedor")
        categoria = cleaned_data.get("categoria")
        filial = cleaned_data.get("filial")
        centro_custo = cleaned_data.get("centro_custo")
        if fornecedor and fornecedor.empresa_id and filial and fornecedor.empresa_id != filial.empresa_id:
            self.add_error("fornecedor", "Fornecedor informado pertence a outra empresa.")
        if categoria and filial and categoria.empresa_id != filial.empresa_id:
            self.add_error("categoria", "Categoria informada pertence a outra empresa.")
        if centro_custo and filial and centro_custo.empresa_id != filial.empresa_id:
            self.add_error("centro_custo", "Centro de custo informado pertence a outra empresa.")
        return cleaned_data


class BaixaContaForm(forms.Form):
    data_pagamento = forms.DateField(label="Data do pagamento", widget=forms.DateInput(attrs={"type": "date"}))
    valor_pago = forms.DecimalField(label="Valor pago/recebido", max_digits=12, decimal_places=2)
    forma_pagamento = forms.CharField(label="Forma", max_length=80, required=False)
    conta_movimento = forms.ModelChoiceField(
        label="Conta de movimento",
        queryset=ContaMovimentoFinanceiro.objects.none(),
        required=False,
        help_text="Selecione para registrar a entrada ou saída no livro financeiro.",
    )

    def __init__(self, *args, filial=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = ContaMovimentoFinanceiro.objects.filter(ativa=True)
        if filial:
            queryset = queryset.filter(filial=filial)
        self.fields["conta_movimento"].queryset = queryset.select_related("filial")
        self.fields["conta_movimento"].widget.attrs["class"] = "select2-field"


class ContaMovimentoFinanceiroForm(forms.ModelForm):
    class Meta:
        model = ContaMovimentoFinanceiro
        fields = ["filial", "nome", "tipo", "saldo_inicial", "ativa"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["filial"].queryset = _filiais_para_usuario(user)
        aplicar_select2(self, ["filial"], ajax_urls={"filial": "/empresas/filiais/busca.json"})


class TransferenciaFinanceiraForm(forms.ModelForm):
    class Meta:
        model = TransferenciaFinanceira
        fields = ["conta_origem", "conta_destino", "valor", "data", "descricao"]
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}),
            "valor": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        contas = ContaMovimentoFinanceiro.objects.filter(
            ativa=True, filial__in=_filiais_para_usuario(user)
        ).select_related("filial", "filial__empresa")
        self.fields["conta_origem"].queryset = contas
        self.fields["conta_destino"].queryset = contas
        self.fields["descricao"].required = False
        aplicar_select2(self, ["conta_origem", "conta_destino"])

    def clean(self):
        cleaned = super().clean()
        origem = cleaned.get("conta_origem")
        destino = cleaned.get("conta_destino")
        if origem and destino and origem.pk == destino.pk:
            raise forms.ValidationError("As contas de origem e destino devem ser diferentes.")
        if origem and destino and origem.filial.empresa_id != destino.filial.empresa_id:
            raise forms.ValidationError("Transferências entre empresas diferentes não são permitidas.")
        return cleaned
class ImportacaoExtratoFinanceiroForm(forms.Form):
    adaptador = forms.ChoiceField(label="Layout do arquivo", required=False, initial="CSV_GENERICO")
    conta = forms.ModelChoiceField(
        queryset=ContaMovimentoFinanceiro.objects.none(),
        label="Conta bancária/adquirente",
    )
    arquivo = forms.FileField(
        label="Arquivo do extrato",
        help_text="CSV genérico e OFX estão disponíveis; layouts privados aparecem quando configurados no servidor.",
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,.ofx,text/csv,application/x-ofx"}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        adaptadores, self.erros_adaptadores = listar_adaptadores_extrato()
        self.fields["adaptador"].choices = [
            (adaptador.codigo, adaptador.nome) for adaptador in adaptadores
        ]
        self.fields["conta"].queryset = ContaMovimentoFinanceiro.objects.filter(
            ativa=True,
            filial__in=_filiais_para_usuario(user),
        ).select_related("filial", "filial__empresa")
        aplicar_select2(self, ["conta"])

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        if arquivo.size > 5 * 1024 * 1024:
            raise ValidationError("O arquivo deve ter no máximo 5 MB.")
        return arquivo

    def clean(self):
        cleaned = super().clean()
        adaptador = cleaned.get("adaptador") or "CSV_GENERICO"
        cleaned["adaptador"] = adaptador
        arquivo = cleaned.get("arquivo")
        if adaptador and arquivo:
            try:
                validar_arquivo_adaptador(codigo=adaptador, arquivo_nome=arquivo.name)
            except (ImproperlyConfigured, ValidationError) as exc:
                self.add_error("arquivo", str(exc))
        return cleaned


class RegraLiquidacaoEletronicaForm(forms.ModelForm):
    class Meta:
        model = RegraLiquidacaoEletronica
        fields = ["filial", "forma_pagamento", "prazo_dias", "taxa_percentual", "taxa_fixa", "ativa"]
        labels = {
            "prazo_dias": "Prazo para liquidação (dias corridos)",
            "taxa_percentual": "Taxa percentual (%)",
            "taxa_fixa": "Taxa fixa por transação (R$)",
        }
        widgets = {
            "prazo_dias": forms.NumberInput(attrs={"min": "0", "max": "365"}),
            "taxa_percentual": forms.NumberInput(attrs={"min": "0", "max": "100", "step": "0.0001"}),
            "taxa_fixa": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.vendas.models import FormaPagamento

        self.fields["filial"].queryset = _filiais_para_usuario(user)
        self.fields["forma_pagamento"].queryset = FormaPagamento.objects.filter(
            ativo=True,
            tipo__in=["PIX", "CARTAO", "DEBITO", "CREDITO", "VALE_ALIMENTACAO", "VALE_REFEICAO"],
        ).order_by("nome")
        aplicar_select2(self, ["filial", "forma_pagamento"], ajax_urls={"filial": "/empresas/filiais/busca.json"})

class AlocacaoRecebivelForm(forms.Form):
    valor_alocado = forms.DecimalField(
        label="Valor a alocar",
        max_digits=14,
        decimal_places=2,
        min_value=0.01,
        localize=True,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "placeholder": "0,00"}),
    )

class ContratoIntegracaoContabilForm(forms.Form):
    empresa = forms.ModelChoiceField(
        queryset=Empresa.objects.none(), label="Empresa"
    )
    software_contabil = forms.CharField(
        label="Software ou escritório destinatário", max_length=160, required=False
    )
    formato_entrega = forms.ChoiceField(
        label="Formato combinado", choices=FormatoEntregaContabil.choices,
        initial=FormatoEntregaContabil.PACOTE_ZIP_V2,
    )
    responsavel_efd_icms_ipi = forms.ChoiceField(
        label="Responsável pela EFD ICMS/IPI",
        choices=ResponsavelEFDICMSIPI.choices,
        initial=ResponsavelEFDICMSIPI.NAO_DEFINIDO,
    )
    responsavel_efd_nome = forms.CharField(
        label="Identificação do responsável pela EFD", max_length=160, required=False
    )
    aceite_referencia = forms.CharField(
        label="Referência do aceite do contador", max_length=160, required=False,
        help_text="Ex.: protocolo interno ou data da validação. Não informe senha, token ou certificado.",
    )
    observacoes = forms.CharField(
        label="Observações técnicas", required=False, widget=forms.Textarea(attrs={"rows": 3})
    )
    confirmar_validacao = forms.BooleanField(
        label="Confirmo que este contrato foi validado com o contador responsável",
        required=False,
    )

    def __init__(self, *args, empresas=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["empresa"].queryset = empresas if empresas is not None else Empresa.objects.none()
        aplicar_select2(self, ["empresa"])

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("confirmar_validacao"):
            return cleaned
        if not (cleaned.get("software_contabil") or "").strip():
            self.add_error("software_contabil", "Informe o destinatário antes de validar.")
        if cleaned.get("responsavel_efd_icms_ipi") == ResponsavelEFDICMSIPI.NAO_DEFINIDO:
            self.add_error("responsavel_efd_icms_ipi", "Defina o responsável externo pela EFD.")
        if not (cleaned.get("responsavel_efd_nome") or "").strip():
            self.add_error("responsavel_efd_nome", "Identifique o responsável pela EFD.")
        if not (cleaned.get("aceite_referencia") or "").strip():
            self.add_error("aceite_referencia", "Registre a referência do aceite do contador.")
        return cleaned

class AmostraContabilForm(forms.Form):
    empresa = forms.ModelChoiceField(queryset=Empresa.objects.none(), label="Empresa")
    competencia = forms.CharField(
        label="Competência",
        max_length=7,
        widget=forms.TextInput(attrs={"type": "month"}),
    )
    referencia_aceite = forms.CharField(
        label="Referência do aceite do contador",
        max_length=160,
        required=False,
        help_text="Obrigatória somente para registrar o aceite. Não informe senha, token ou certificado.",
    )
    registrar_aceite = forms.BooleanField(
        label="Registrar aceite imutável se todos os portões forem aprovados",
        required=False,
    )

    def __init__(self, *args, empresas=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["empresa"].queryset = empresas if empresas is not None else Empresa.objects.none()
        aplicar_select2(self, ["empresa"])

    def clean_competencia(self):
        valor = (self.cleaned_data.get("competencia") or "").strip()
        try:
            ano, mes = (int(parte) for parte in valor.split("-", 1))
            if ano < 2000 or mes < 1 or mes > 12:
                raise ValueError
        except (TypeError, ValueError):
            raise ValidationError("Competência inválida. Informe no formato AAAA-MM.")
        return f"{ano:04d}-{mes:02d}"

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("registrar_aceite") and not (cleaned.get("referencia_aceite") or "").strip():
            self.add_error("referencia_aceite", "Registre a referência do aceite do contador.")
        return cleaned
