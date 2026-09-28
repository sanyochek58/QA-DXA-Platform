"""СНИЛС: нормализация, проверка контрольного числа, форматирование.

Алгоритм контрольного числа (ПФР):
  сумма = Σ цифра_i × (10 − i) для первых 9 цифр (веса 9..1);
  < 100  → контрольное число = сумма;
  100, 101 → 00;
  > 101  → сумма mod 101 (если вышло 100 → 00).
Проверка обязательна только для номеров больше 001-001-998.
"""

import re

_DIGITS = re.compile(r"\D")


class InvalidSnilsError(ValueError):
    pass


def checksum(first9: str) -> int:
    total = sum(int(d) * (9 - i) for i, d in enumerate(first9))
    if total < 100:
        return total
    if total in (100, 101):
        return 0
    rest = total % 101
    return 0 if rest == 100 else rest


def normalize(value: str) -> str:
    """'123-456-789 64' → '12345678964'. Бросает InvalidSnilsError, если номер невалиден."""
    digits = _DIGITS.sub("", value or "")
    if len(digits) != 11:
        raise InvalidSnilsError("СНИЛС должен содержать 11 цифр")
    body, control = digits[:9], int(digits[9:])
    if int(body) > 1001998 and checksum(body) != control:
        raise InvalidSnilsError("Неверное контрольное число СНИЛС")
    return digits


def format_snils(digits: str) -> str:
    return f"{digits[0:3]}-{digits[3:6]}-{digits[6:9]} {digits[9:11]}"


def mask(digits: str) -> str:
    """Для публичных мест: ***-***-789 64."""
    return f"***-***-{digits[6:9]} {digits[9:11]}"


def make(first9: str) -> str:
    """Собрать валидный СНИЛС из 9 цифр — нужно для тестовых данных."""
    return first9 + f"{checksum(first9):02d}"
