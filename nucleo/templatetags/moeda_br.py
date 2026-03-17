from django import template

register = template.Library()


@register.filter(name="moeda_br")
def moeda_br(valor):
    try:
        valor = float(valor)
    except (TypeError, ValueError):
        return "R$ 0,00"

    texto = f"{valor:,.2f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"