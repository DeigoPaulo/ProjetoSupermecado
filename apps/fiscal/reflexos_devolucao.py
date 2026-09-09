"""Conferência aritmética de impactos declarados; não é motor tributário.

O chamador deve fornecer itens e rateio íntegros, atuais e autorizados.
Este formulário não busca documentos, persiste dados nem autoriza emissão.
Os deltas são assinados e informados pelo responsável: nenhuma incidência,
proporção, redução ou regra de arredondamento é inferida do valor comercial.
"""
from decimal import Decimal

from django import forms

from .devolucao_fornecedor import TRIBUTOS_MEMORIA_CALCULO
from .rateio_devolucao import COMPONENTES


LIMITE = Decimal("9999999999999.99")


class ReflexosBasesDevolucaoForm(forms.Form):
    fundamentacao = forms.CharField(min_length=10, max_length=4000, widget=forms.Textarea)

    def __init__(self, *args, itens, linhas_rateio, **kwargs):
        super().__init__(*args, **kwargs)
        self.itens = list(itens)
        self.rateio = list(linhas_rateio)
        self.resultado = None
        for item in self.itens:
            for tributo, rotulo in TRIBUTOS_MEMORIA_CALCULO:
                prefixo = f"item_{item.pk}_{tributo}"
                for componente in COMPONENTES:
                    self.fields[f"{prefixo}_{componente}"] = forms.DecimalField(
                        label=f"nItem {item.numero_item_xml} · {rotulo} · impacto de {componente}",
                        max_digits=15, decimal_places=2, min_value=-LIMITE,
                        max_value=LIMITE, localize=True,
                    )
                self.fields[f"{prefixo}_base_final"] = forms.DecimalField(
                    label=f"nItem {item.numero_item_xml} · {rotulo} · base final declarada",
                    max_digits=15, decimal_places=2, min_value=0,
                    max_value=LIMITE, localize=True,
                )
        for tributo, rotulo in TRIBUTOS_MEMORIA_CALCULO:
            self.fields[f"total_base_{tributo}"] = forms.DecimalField(
                label=f"Total declarado das bases de {rotulo}", max_digits=15,
                decimal_places=2, min_value=0, max_value=LIMITE, localize=True,
            )

    def clean(self):
        dados = super().clean()
        if self.errors:
            return dados
        ids = [item.pk for item in self.itens]
        rateio_ids = [linha.get("item_memoria_id") for linha in self.rateio]
        if not ids or len(set(ids)) != len(ids) or len(set(rateio_ids)) != len(rateio_ids) or set(ids) != set(rateio_ids):
            raise forms.ValidationError("Os itens da memória e do rateio precisam corresponder integralmente, sem duplicidade.")
        por_id = {linha["item_memoria_id"]: linha for linha in self.rateio}
        totais = {tributo: Decimal("0") for tributo, _ in TRIBUTOS_MEMORIA_CALCULO}
        linhas = []
        for item in self.itens:
            origem = por_id[item.pk]
            if origem.get("item_rascunho_id") != item.item_rascunho_id or str(origem.get("numero_item_xml")) != str(item.numero_item_xml):
                raise forms.ValidationError("O vínculo do item com o rateio divergiu.")
            tributos = {}
            for tributo, rotulo in TRIBUTOS_MEMORIA_CALCULO:
                prefixo = f"item_{item.pk}_{tributo}"
                base = getattr(item, f"base_{tributo}")
                impactos = {campo: dados[f"{prefixo}_{campo}"] for campo in COMPONENTES}
                final = dados[f"{prefixo}_base_final"]
                if base + sum(impactos.values(), Decimal("0")) != final:
                    raise forms.ValidationError(f"nItem {item.numero_item_xml}: base anterior e impactos de {rotulo} não conferem com a base final.")
                totais[tributo] += final
                tributos[tributo] = {
                    "base_anterior": format(base, ".2f"), "base_final": format(final, ".2f"),
                    "impactos": {campo: format(valor, ".2f") for campo, valor in impactos.items()},
                }
            linhas.append({"item_memoria_id": item.pk, "item_rascunho_id": item.item_rascunho_id,
                           "numero_item_xml": item.numero_item_xml, "tributos": tributos})
        for tributo, rotulo in TRIBUTOS_MEMORIA_CALCULO:
            if totais[tributo] != dados[f"total_base_{tributo}"]:
                raise forms.ValidationError(f"O total declarado das bases de {rotulo} diverge dos itens.")
        self.resultado = {
            "contrato": "supplier_return_tax_base_impacts_draft_v1",
            "fundamentacao": dados["fundamentacao"], "itens": linhas,
            "totais_bases": {campo: format(valor, ".2f") for campo, valor in totais.items()},
            "permite_emissao": False,
        }
        return dados
