import json
import re

_BARE = re.compile(r"[A-Za-z0-9_-]+")


def _key(k: str) -> str:
    return k if _BARE.fullmatch(k) else json.dumps(k, ensure_ascii=False)


def _value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(_value(x) for x in v) + "]"
    return json.dumps(v, ensure_ascii=False)  # JSON string escapes are valid TOML basic-string escapes


def _is_table_array(v) -> bool:
    return isinstance(v, list) and bool(v) and all(isinstance(x, dict) for x in v)


def _body(d: dict, path: tuple) -> list[str]:
    lines = ["%s = %s" % (_key(k), _value(v)) for k, v in d.items() if not isinstance(v, dict) and not _is_table_array(v)]
    for k, v in d.items():
        dotted = ".".join(_key(x) for x in path + (k,))
        if isinstance(v, dict):
            lines += ["", "[%s]" % dotted] + _body(v, path + (k,))
        elif _is_table_array(v):
            for item in v:
                lines += ["", "[[%s]]" % dotted] + _body(item, path + (k,))
    return lines


def dumps(d: dict) -> str:
    """TOML for the profile shape only: scalars, lists of scalars, nested tables, arrays of tables."""
    return "\n".join(_body(d, ())).lstrip("\n") + "\n"
