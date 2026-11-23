"""Contraste WCAG entre dos colores. Uso: python tools/contraste.py "#4A5361" "#DADFE3" """
import sys


def lum(h: str) -> float:
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a: str, b: str) -> float:
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


if __name__ == "__main__":
    r = ratio(sys.argv[1], sys.argv[2])
    print(f"{r:.2f}:1  texto {'OK' if r >= 4.5 else 'NO'} (4,5)  bordes {'OK' if r >= 3 else 'NO'} (3)")
