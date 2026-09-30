COMPRIMENTOS_GTIN = {8, 12, 13, 14}


def gtin_valido(codigo):
    codigo = str(codigo or "").strip()
    if len(codigo) not in COMPRIMENTOS_GTIN or not codigo.isdigit():
        return False
    soma = sum(
        int(digito) * (3 if indice % 2 == 0 else 1)
        for indice, digito in enumerate(reversed(codigo[:-1]))
    )
    digito_verificador = (10 - soma % 10) % 10
    return digito_verificador == int(codigo[-1])


def gtin_fiscal(codigo):
    codigo = str(codigo or "").strip()
    return codigo if gtin_valido(codigo) else "SEM GTIN"
