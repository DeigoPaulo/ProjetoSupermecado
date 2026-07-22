from django import forms

from apps.core_forms import aplicar_select2
from apps.pdv.models import TerminalPdv
from apps.vendas.models import FormaPagamento

from .models import ConfiguracaoImpressao, ModeloEtiqueta, TipoDocumentoImpressao


class ConfiguracaoImpressaoForm(forms.ModelForm):
    class Meta:
        model = ConfiguracaoImpressao
        fields = [
            "empresa",
            "filial",
            "tipo_documento",
            "modelo_papel",
            "exibir_logo",
            "tamanho_fonte",
            "margem_superior_mm",
            "margem_inferior_mm",
            "margem_esquerda_mm",
            "margem_direita_mm",
            "mensagem_rodape",
            "impressora_padrao",
            "impressao_automatica",
            "gaveta_automatica",
            "abrir_gaveta_em_dinheiro",
            "abrir_gaveta_em_movimento_caixa",
            "numero_vias",
            "largura_etiqueta_mm",
            "altura_etiqueta_mm",
            "gap_horizontal_mm",
            "gap_vertical_mm",
            "colunas_etiqueta",
            "dpi_impressora",
            "densidade_impressao",
            "velocidade_impressao",
            "tipo_midia_etiqueta",
            "linguagem_impressora",
            "is_active",
        ]
        widgets = {
            "mensagem_rodape": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aplicar_select2(self, ["empresa", "filial"], ajax_urls={"filial": "/empresas/filiais/busca.json"})
        self.fields["impressora_padrao"].widget.attrs.update(
            {
                "list": "printer-suggestions",
                "placeholder": "Ex.: Caixa 01, EPSON TM-T20, PDF",
            }
        )

    def clean_tamanho_fonte(self):
        tamanho = self.cleaned_data["tamanho_fonte"]
        if tamanho < 8 or tamanho > 18:
            raise forms.ValidationError("Use fonte entre 8 e 18.")
        return tamanho

    def clean_numero_vias(self):
        vias = self.cleaned_data["numero_vias"]
        if vias < 1 or vias > 5:
            raise forms.ValidationError("Informe de 1 a 5 vias.")
        return vias

    def clean(self):
        cleaned = super().clean()
        usa_gaveta = cleaned.get("gaveta_automatica")
        tipo_documento = cleaned.get("tipo_documento")
        tipos_caixa = {
            TipoDocumentoImpressao.CUPOM_NAO_FISCAL,
            TipoDocumentoImpressao.CUPOM_FISCAL,
            TipoDocumentoImpressao.FECHAMENTO_CAIXA,
        }
        if usa_gaveta and tipo_documento not in tipos_caixa:
            self.add_error("gaveta_automatica", "Gaveta automatica deve ser configurada apenas para documentos de caixa.")
        if not usa_gaveta:
            cleaned["abrir_gaveta_em_dinheiro"] = False
            cleaned["abrir_gaveta_em_movimento_caixa"] = False
        if tipo_documento == TipoDocumentoImpressao.ETIQUETA:
            limites = {
                "largura_etiqueta_mm": (20, 300, "largura"),
                "altura_etiqueta_mm": (10, 300, "altura"),
                "gap_horizontal_mm": (0, 30, "gap horizontal"),
                "gap_vertical_mm": (0, 30, "gap vertical"),
                "colunas_etiqueta": (1, 8, "colunas"),
                "dpi_impressora": (100, 1200, "DPI"),
                "densidade_impressao": (0, 30, "densidade"),
                "velocidade_impressao": (1, 14, "velocidade"),
            }
            for campo, (minimo, maximo, nome) in limites.items():
                valor = cleaned.get(campo)
                if valor is not None and not minimo <= valor <= maximo:
                    self.add_error(campo, f"Informe {nome} entre {minimo} e {maximo}.")
        return cleaned


class ModeloEtiquetaForm(forms.ModelForm):
    class Meta:
        model = ModeloEtiqueta
        fields = [
            "configuracao",
            "terminal",
            "nome",
            "largura_mm",
            "altura_mm",
            "gap_horizontal_mm",
            "gap_vertical_mm",
            "colunas",
            "orientacao",
            "padrao",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["configuracao"].queryset = ConfiguracaoImpressao.objects.filter(
            tipo_documento=TipoDocumentoImpressao.ETIQUETA
        ).select_related("empresa", "filial")
        aplicar_select2(self, ["configuracao", "terminal"])

    def clean(self):
        cleaned = super().clean()
        limites = {
            "largura_mm": (20, 300, "largura"),
            "altura_mm": (10, 300, "altura"),
            "gap_horizontal_mm": (0, 30, "gap horizontal"),
            "gap_vertical_mm": (0, 30, "gap vertical"),
            "colunas": (1, 8, "colunas"),
        }
        for campo, (minimo, maximo, nome) in limites.items():
            valor = cleaned.get(campo)
            if valor is not None and not minimo <= valor <= maximo:
                self.add_error(campo, f"Informe {nome} entre {minimo} e {maximo}.")
        configuracao = cleaned.get("configuracao")
        terminal = cleaned.get("terminal")
        if terminal and configuracao:
            filial_incompativel = configuracao.filial_id and terminal.filial_id != configuracao.filial_id
            empresa_incompativel = not configuracao.filial_id and terminal.filial.empresa_id != configuracao.empresa_id
            if filial_incompativel or empresa_incompativel:
                self.add_error("terminal", "O terminal deve pertencer ao escopo da configuracao selecionada.")
        return cleaned


class FormaPagamentoForm(forms.ModelForm):
    TIPOS = [
        ("DINHEIRO", "Dinheiro"),
        ("PIX", "PIX"),
        ("CARTAO", "Cartao / TEF"),
        ("CREDIARIO", "Crediario"),
        ("VALE", "Vale / convenio"),
        ("OUTRO", "Outro"),
    ]
    tipo = forms.ChoiceField(choices=TIPOS)

    class Meta:
        model = FormaPagamento
        fields = ["nome", "tipo", "conta_movimento_padrao", "permite_troco", "exige_autorizacao", "ativo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aplicar_select2(self, ["conta_movimento_padrao"])

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("permite_troco") and cleaned.get("tipo") != "DINHEIRO":
            self.add_error("permite_troco", "Troco deve ser habilitado somente para pagamentos em dinheiro.")
        return cleaned


class TerminalPdvForm(forms.ModelForm):
    class Meta:
        model = TerminalPdv
        fields = [
            "filial",
            "nome",
            "descricao",
            "provedor_tef",
            "modo_integracao_tef",
            "usa_balanca",
            "protocolo_balanca",
            "porta_balanca",
            "modelo_balanca",
            "status_licenca",
            "observacao_licenca",
            "permite_modo_offline",
            "emite_documento_fiscal",
            "ativo",
        ]
        widgets = {
            "descricao": forms.TextInput(attrs={"placeholder": "Ex.: Balcao principal, frente de loja, caixa rapido"}),
            "porta_balanca": forms.TextInput(attrs={"placeholder": "Ex.: COM3, /dev/ttyUSB0, 192.168.1.50:9000"}),
            "modelo_balanca": forms.TextInput(attrs={"placeholder": "Ex.: Toledo, Filizola, Urano, outro"}),
            "observacao_licenca": forms.TextInput(attrs={"placeholder": "Ex.: Caixa contratado no plano da loja, aguardando instalacao"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aplicar_select2(self, ["filial"], ajax_urls={"filial": "/empresas/filiais/busca.json"})
        self.fields["protocolo_balanca"].required = False

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("usa_balanca"):
            if cleaned.get("protocolo_balanca") == "NAO_CONFIGURADO":
                self.add_error("protocolo_balanca", "Informe o protocolo da balanca.")
            if not cleaned.get("porta_balanca"):
                self.add_error("porta_balanca", "Informe a porta, caminho ou endereco da balanca.")
        return cleaned
