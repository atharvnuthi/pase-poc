"""Meses como intervalos de datas.

Orçamentos, filtros e a visão mensal falam em "mês" (`YYYY-MM`). Este módulo é o único
lugar que converte isso em datas, para os três concordarem sobre onde um mês começa e
termina.
"""

from datetime import date


def parse_month(value: str) -> tuple[date, date]:
    """`YYYY-MM` vira `(primeiro dia do mês, primeiro dia do mês seguinte)`.

    O fim é **exclusivo**: assim o último dia do mês nunca fica de fora, qualquer que
    seja o comprimento dele.
    """
    try:
        ano_texto, mes_texto = value.split("-")
        ano, mes = int(ano_texto), int(mes_texto)
        inicio = date(ano, mes, 1)
    except (ValueError, TypeError) as exc:
        raise ValueError("o mês deve estar no formato AAAA-MM") from exc
    fim = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
    return inicio, fim


def current_month() -> str:
    hoje = date.today()
    return f"{hoje.year:04d}-{hoje.month:02d}"


def month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"
