# -*- coding: utf-8 -*-
import random, re

_BOLD_DIGITS = {
    '0': '𝟎', '1': '𝟏', '2': '𝟐', '3': '𝟑', '4': '𝟒',
    '5': '𝟓', '6': '𝟔', '7': '𝟕', '8': '𝟖', '9': '𝟗',
}

_HOMOGLYPHS = {
    'ع': ['ﻋ', 'ﻌ', 'ع'], 'ا': ['ا', 'ﺍ', 'ا'], 'و': ['و', 'ﻭ', 'و'],
    'ي': ['ي', 'ﻳ', 'ﻴ'], 'ن': ['ن', 'ﻥ', 'ﻦ'], 'م': ['م', 'ﻡ', 'ﻢ'],
    'ت': ['ت', 'ﺕ', 'ﺖ'], 'ه': ['ه', 'ﻫ', 'ﻬ'], 'ل': ['ل', 'ﻝ', 'ﻞ'],
    'ك': ['ك', 'ﻙ', 'ﻚ'], 'ر': ['ر', 'ﺭ', 'ر'], 'س': ['س', 'ﺱ', 'ﺲ'],
    'ح': ['ح', 'ﺡ', 'ﺢ'], 'ب': ['ب', 'ﺏ', 'ﺐ'], 'ف': ['ف', 'ﻑ', 'ﻒ'],
}

_INVISIBLES = ['\u200b', '\u200c', '\u200d', '\u2060', '\u00ad', '\ufeff', '\u034f', '\u180e']

_SENSITIVE = [
    'واتساب', 'واتس', 'تواصل', 'اتصال', 'إعلان', 'إعلانات', 'عرض', 'عروض',
    'خصم', 'ارسل', 'أرسل', 'رسالة', 'اشتري', 'اطلب', 'طلب', 'يومي', 'مجاني',
    'حصري', 'للبيع', 'للإيجار', 'متوفر', 'متاح',
]

class AdProtector:
    @staticmethod
    def ghost_numbers(text: str) -> str:
        result = []
        i = 0
        while i < len(text):
            c = text[i]
            if c.isdigit():
                j = i
                while j < len(text) and text[j].isdigit():
                    j += 1
                num_str = text[i:j]
                if len(num_str) >= 3:
                    result.append(''.join(_BOLD_DIGITS.get(d, d) for d in num_str))
                else:
                    result.append(num_str)
                i = j
            else:
                result.append(c)
                i += 1
        return ''.join(result)

    @staticmethod
    def fragment_words(text: str) -> str:
        for word in _SENSITIVE:
            if word in text:
                mid = len(word) // 2
                broken = word[:mid] + '\u200c' + word[mid:]
                text = text.replace(word, broken, 1)
        return text

    @staticmethod
    def apply_homoglyphs(text: str, intensity: float = 0.4) -> str:
        result = []
        for ch in text:
            if ch in _HOMOGLYPHS and random.random() < intensity:
                result.append(random.choice(_HOMOGLYPHS[ch]))
            else:
                result.append(ch)
        return ''.join(result)

    @staticmethod
    def add_hash_breaker(text: str, count: int = 5) -> str:
        return text + ''.join(random.choices(_INVISIBLES, k=count))

    @staticmethod
    def inject_invisibles(text: str, rate: float = 0.08) -> str:
        result = []
        for ch in text:
            result.append(ch)
            if ch == ' ' and random.random() < rate:
                result.append(random.choice(_INVISIBLES[:4]))
        return ''.join(result)

    @classmethod
    def protect(cls, text: str, level: int = 2) -> str:
        if level >= 1:
            text = cls.add_hash_breaker(text)
        if level >= 2:
            text = cls.fragment_words(text)
            text = cls.ghost_numbers(text)
        if level >= 3:
            text = cls.apply_homoglyphs(text)
            text = cls.inject_invisibles(text)
        return text

    @classmethod
    def generate_variants(cls, text: str, count: int = 5, level: int = 2) -> list:
        return [cls.protect(text, level) for _ in range(count)]

    @classmethod
    def preview(cls, text: str) -> str:
        protected = cls.protect(text, level=2)
        lines = [
            "🛡️ **الإعلان المحمي:**",
            "━━━━━━━━━━━━━━━━━━━━━━",
            protected,
            "━━━━━━━━━━━━━━━━━━━━━━",
            "✅ **التقنيات المُطبَّقة:**",
            "• 🔢 أرقام الهاتف → أرقام شبح",
            "• ✂️ كسر الكلمات الحساسة",
            "• 👻 رموز غير مرئية في النهاية",
        ]
        return '\n'.join(lines)
