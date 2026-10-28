"""Conservative hints for explicit English/Chinese reply directives only."""
import re

_QUOTED = re.compile(r"""“[^”]*”|"[^"\n]*"|「[^」]*」|『[^』]*』|‘[^’]*’|`[^`]*`|(?<!\w)'[^'\n]*'(?!\w)""")
_ZH = re.compile(
    r'(?:用|以|使用|采用|请)\s*(英语|英文|中文|汉语|简体中文|繁体中文)'
    r'\s*(?:来|进行)?\s*(?:回答|作答|回复|答复|输出|撰写|答)'
)
_EN = re.compile(
    r'\b(?:answer|reply|respond|write)\b(?:\s+[a-z]+){0,3}?\s+in\s+(english|chinese|mandarin)\b'
    r'|\bin\s+(english|chinese|mandarin)\s*,?\s*please\b', re.I
)
_CLAUSE_END = re.compile(r'[，。；：！？,.;:!?\n]')
_BLOCK = re.compile(
    r"不要|别|不用|勿|不必|无需|不能|不得|禁止|如何|怎么|怎样|为什么|什么意思|解释|解读|是否|"
    r"\b(?:don['’]?t|do\s+not|never|not|no|how|why|explain|does|did|whether|phrase)\b", re.I
)
_EN_PREFIX = re.compile(r'(?:(?:please|kindly)|(?:can|could|would|will) you(?: please)?|you (?:must|should)|i (?:want|need) you to)?', re.I)


def resolve_explicit_language(question: str) -> str | None:
    """Leave ambiguous, quoted and unsupported directives to the model."""
    if not isinstance(question, str) or not question:
        return None
    text = _QUOTED.sub(lambda match: ' ' * len(match.group()), question)
    found = []
    for pattern in (_ZH, _EN):
        for match in pattern.finditer(text):
            boundaries = list(_CLAUSE_END.finditer(text, 0, match.start()))
            start = boundaries[-1].end() if boundaries else 0
            if pattern is _EN and not _EN_PREFIX.fullmatch(text[start:match.start()].strip()):
                continue
            if _BLOCK.search(text[start:match.end()]):
                continue
            if re.match(r'\s*(?:or|或者|或|/)\s*(?:English|Chinese|英语|英文|中文|汉语)\b', text[match.end():], re.I):
                continue
            language = next(value for value in match.groups() if value).lower()
            found.append((match.start(), 'English' if language in ('英语', '英文', 'english') else 'Chinese'))
    return max(found)[1] if found else None
