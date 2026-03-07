"""Calculo de entropy de Shannon para detectar secrets reales vs placeholders.

La entropy mide la aleatoriedad/complejidad de un string:
  - Entropy < 3.0 bits/char: probablemente placeholder o string generico
    (ej: "changeme", "password123", "TODO")
  - Entropy 3.0 - 4.0: zona gris, podria ser un valor simple o un secret debil
  - Entropy > 4.5: probablemente un secret real hardcodeado
    (ej: "a3f8b2c1d9e0", API keys reales)

Se usa como filtro para distinguir entre placeholders (que son un error de copy-paste
del AI agent) y secrets reales (que no deberian estar en el codigo).
"""

import math
from collections import Counter


def shannon_entropy(text: str) -> float:
    """Calcula la entropy de Shannon de un string.

    Args:
        text: String a analizar.

    Returns:
        Entropy en bits por caracter. 0.0 para strings vacios.
    """
    if not text:
        return 0.0

    length = len(text)
    counts = Counter(text)
    entropy = 0.0

    for count in counts.values():
        probability = count / length
        if probability > 0:
            entropy -= probability * math.log2(probability)

    return entropy


def is_high_entropy_secret(value: str, min_entropy: float = 3.0) -> bool:
    """Determina si un valor tiene entropy suficiente para ser un secret real.

    Args:
        value: Valor a analizar.
        min_entropy: Umbral minimo de entropy.

    Returns:
        True si la entropy supera el umbral.
    """
    if len(value) < 8:
        return False
    return shannon_entropy(value) >= min_entropy


def is_low_entropy_secret(value: str, max_entropy: float = 3.0) -> bool:
    """Determina si un valor tiene entropy baja (placeholder o secret debil).

    Args:
        value: Valor a analizar.
        max_entropy: Umbral maximo de entropy.

    Returns:
        True si la entropy es menor al umbral.
    """
    if len(value) < 3:
        return False
    return shannon_entropy(value) < max_entropy
