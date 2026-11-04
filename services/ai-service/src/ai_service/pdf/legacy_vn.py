"""Vietnamese text printed in a legacy font encoding (TCVN3 / ABC, ".Vn" fonts) comes out of a PDF
as Latin-1 look-alikes ("Ch­¬ng" for "Chương"). `fix_tcvn3` detects it by the rate of
characters only that encoding uses and converts the lowercase letters, and Đ, to Unicode.

Limits: capital letters with a tone mark are not in the table, and a glyph the PDF has no
Unicode mapping for is already missing from the extracted text, so it cannot come back.
VNI-Windows (a different table) is not handled.
"""

import re

# TCVN3 byte -> Unicode, bytes 0xA1..0xFE (the PDF text holds them as U+00xx).
_TCVN3 = (
    "¡Ă¢Â£Ê¤Ô¥Ơ¦Ư§Đ"
    "¨ă©âªê«ô¬ơ­ư®đ"
    "µà¶ả·ã¸á¹ạ"
    "»ằ¼ẳ½ẵ¾ắÆặ"
    "ÇầÈẩÉẫÊấËậ"
    "ÌèÎẻÏẽÐéÑẹ"
    "ÒềÓểÔễÕếÖệ"
    "×ìØỉÜĩÝíÞị"
    "ßòáỏâõãóäọ"
    "åồæổçỗèốéộ"
    "êờëởìỡíớîợ"
    "ïùñủòũóúôụ"
    "õừöử÷ữøứùự"
    "úỳûỷüỹýýþỵ"
)
_MAP: dict[int, str] = {ord(_TCVN3[i]): _TCVN3[i + 1] for i in range(0, len(_TCVN3), 2)}

# Characters that, in this quantity, say the text is TCVN3: the vowels with a hat, horn or
# breve (a-circumflex, e-circumflex, o-circumflex, o-horn, u-horn, a-breve, d-stroke) and a few
# tone marks that real Latin text almost never holds (soft hyphen, pilcrow, micro sign, ...).
_MARKERS = frozenset(map(ord, "¨©ª«¬­®µ¶·¸¹¾"))
_MIN_MARKERS = 6
_MIN_SHARE = 0.01


def looks_tcvn3(text: str) -> bool:
    letters = sum(1 for c in text if not c.isspace())
    if letters == 0:
        return False
    markers = sum(1 for c in text if ord(c) in _MARKERS)
    return markers >= _MIN_MARKERS and markers / letters >= _MIN_SHARE


# In the fonts seen so far the glyphs of "c", "e-acute" and "u-dot" have no Unicode mapping and come
# out as control characters: a lone CR (not a CR LF line break), U+001C and U+001D.
_LONE_CR = re.compile(r"\r(?!\n)")
_CONTROL = {0x1C: "é", 0x1D: "ụ"}
_MIN_LONE_CR = 5


def fix_tcvn3(text: str) -> str:
    """The text in Unicode when it is TCVN3, else unchanged."""
    if not looks_tcvn3(text):
        return text
    if len(_LONE_CR.findall(text)) >= _MIN_LONE_CR:
        text = _LONE_CR.sub("c", text)
        # _CONTROL after _MAP: the e-acute it writes is itself a TCVN3 key.
        return text.translate(_MAP).translate(_CONTROL)
    return text.translate(_MAP)
