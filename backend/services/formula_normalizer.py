"""公式方言规范化层（确定性语法翻译，不猜语义）

预置因子公式抓取自外部因子库（GTJA Alpha191 / WorldQuant Alpha101 等），
夹带大量非 Python 方言：`cond?a:b` 三元、单 `=` 比较、`&&`/`||`、`^` 幂、
MATLAB `./`/`.*`、隐式乘法 `(a)(b)`、偶发括号损坏。本模块把它们确定性地
翻译成等价的 Python 表达式（三元翻译为求值命名空间中已有的 `IF(cond,a,b)`），
供 `factor_operators.eval_factor_formula` 在 eval 前统一调用。

规则只做语法层转换，不改变公式含义；对无法可靠翻译的公式原样返回，
由上层按结构化错误如实归类，绝不静默猜测。
"""

import ast
import re

__all__ = ["normalize_formula"]


# ── 逻辑运算两侧裸比较补括号 ─────────────────────────────────
#
# Python 中 `&`/`|` 优先级高于比较运算符：`ld>0 & ld>hd` 会被解析成
# `ld > (0 & ld) > hd`。Alpha191 方言里 `&`/`|` 连接的比较必须显式加括号。
# 已被括号包裹的比较（如 `(...)<0.05`）不重复包裹（幂等保证）。

_TOKEN = r"[A-Za-z_]\w*|\d+\.?\d*"


def _parenthesize_logic_operands(s: str) -> str:
    out = s
    for op in ("&", "|"):
        i = 0
        while True:
            i = out.find(op, i)
            if i < 0:
                break
            wrapped, new_op_idx = _wrap_comparison_around(out, i)
            if wrapped is None:
                i += 1
                continue
            out = wrapped
            i = new_op_idx + 1
    return out


def _wrap_comparison_around(s: str, op_idx: int):
    """若 op 两侧存在未被单独包裹的裸比较 `A cmp B`，返回包裹后的字符串与 op 新下标"""
    left = _scan_comparison_left(s, op_idx)
    right = _scan_comparison_right(s, op_idx)
    if left is None and right is None:
        return None, op_idx
    result = s
    shift = 0
    if left is not None:
        l_start, l_end = left
        # 已被自己的括号包裹（左邻 ( 且右邻 )）则跳过，保证幂等
        if not (l_start > 0 and result[l_start - 1] == "(" and result[l_end:l_end + 1] == ")"):
            result = result[:l_start] + "(" + result[l_start:l_end] + ")" + result[l_end:]
            shift += 2  # 一次包裹插入两个字符
    if right is not None:
        r_start, r_end = right
        r_start += shift
        r_end += shift
        if not (r_start > 0 and result[r_start - 1] == "(" and result[r_end:r_end + 1] == ")"):
            result = result[:r_start] + "(" + result[r_start:r_end] + ")" + result[r_end:]
    if shift == 0 and result == s:
        return None, op_idx
    return result, op_idx + shift


def _scan_comparison_left(s: str, op_idx: int):
    """从 op 向左找裸比较 `A cmp B`：返回 (表达式起点, 右端开区间)；找不到返回 None"""
    j = op_idx - 1
    while j >= 0 and s[j].isspace():
        j -= 1
    b_end = j + 1
    b_start = b_end
    while b_start > 0 and re.match(r"[\w.]", s[b_start - 1]):
        b_start -= 1
    if b_start == b_end or not re.match(_TOKEN + r"$", s[b_start:b_end]):
        return None
    k = b_start - 1
    while k >= 0 and s[k].isspace():
        k -= 1
    cmp_start = None
    for cmp_len in (2, 1):
        frag = s[k - cmp_len + 1: k + 1]
        if frag in ("==", ">=", "<=", "!=", ">", "<"):
            cmp_start = k - cmp_len + 1
            break
    if cmp_start is None:
        return None
    k = cmp_start - 1
    while k >= 0 and s[k].isspace():
        k -= 1
    a_end = k + 1
    a_start = a_end
    while a_start > 0 and re.match(r"[\w.]", s[a_start - 1]):
        a_start -= 1
    if a_start == a_end or not re.match(_TOKEN + r"$", s[a_start:a_end]):
        return None
    # 左邻守卫：A 之前必须是边界字符（( , ? : 运算符 或串首），否则是更大表达式的一部分
    if a_start > 0 and s[a_start - 1] not in "(,?:&|+-*/<>= " and not s[a_start - 1].isspace():
        return None
    return a_start, b_end


def _scan_comparison_right(s: str, op_idx: int):
    """从 op 向右找裸比较 `A cmp B`：返回 (A 起点, 右端开区间)；找不到返回 None"""
    n = len(s)
    j = op_idx + 1
    while j < n and s[j].isspace():
        j += 1
    m = re.match(_TOKEN, s[j:])
    if not m:
        return None
    a_start, a_end = j, j + m.end()
    k = a_end
    while k < n and s[k].isspace():
        k += 1
    cmp_op = None
    for frag in ("==", ">=", "<=", "!=", ">", "<"):
        if s.startswith(frag, k):
            cmp_op = frag
            break
    if cmp_op is None:
        return None
    k += len(cmp_op)
    while k < n and s[k].isspace():
        k += 1
    m2 = re.match(_TOKEN, s[k:])
    if not m2:
        return None
    b_end = k + m2.end()
    return a_start, b_end


# ── 括号感知的三元替换 cond?a:b → IF(cond,a,b) ──────────────


def _depth_map(s: str) -> list[int]:
    d = 0
    out = []
    for ch in s:
        out.append(d)
        if ch == "(":
            d += 1
        elif ch == ")":
            d -= 1
    return out


def _find_colon(s: str, q_idx: int, q_depth: int) -> int:
    """从 ? 向右找同深度配对冒号；先遇到同深度 ? 视为畸形，返回 -1"""
    depth = q_depth
    for j in range(q_idx + 1, len(s)):
        c = s[j]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif depth == q_depth:
            if c == "?":
                return -1
            if c == ":":
                return j
    return -1


def _ternary_bounds(s: str, q_idx: int, colon: int, q_depth: int) -> tuple[int, int]:
    """三元的左右边界：左 = 同深度 ( / , / 串首之后；右 = 同深度 ) / , / 串尾之前"""
    depth = q_depth
    left = 0
    for j in range(q_idx - 1, -1, -1):
        c = s[j]
        if c == ")":
            depth += 1
        elif c == "(":
            if depth == q_depth:
                left = j + 1
                break
            depth -= 1
        elif c == "," and depth == q_depth:
            left = j + 1
            break
    depth = q_depth
    right = len(s)
    for j in range(colon + 1, len(s)):
        c = s[j]
        if c == "(":
            depth += 1
        elif c == ")":
            if depth == q_depth:
                right = j
                break
            depth -= 1
        elif c == "," and depth == q_depth:
            right = j
            break
    return left, right


def _replace_ternaries(s: str) -> str:
    for _ in range(128):
        if "?" not in s:
            break
        depths = _depth_map(s)
        converted = False
        for i, ch in enumerate(s):
            if ch != "?":
                continue
            q_depth = depths[i]
            colon = _find_colon(s, i, q_depth)
            if colon < 0:
                # 深度错位兜底：冒号在 q_depth+1（缺一个右括号），在冒号前试插 )
                depth = q_depth
                for j in range(i + 1, len(s)):
                    c = s[j]
                    if c == "(":
                        depth += 1
                    elif c == ")":
                        depth -= 1
                    elif c == ":" and depth == q_depth + 1:
                        s = s[:j] + ")" + s[j:]
                        converted = True
                        break
                    elif c == "?" and depth == q_depth:
                        break
                continue
            left, right = _ternary_bounds(s, i, colon, q_depth)
            cond = s[left:i].strip()
            then = s[i + 1:colon].strip()
            els = s[colon + 1:right].strip()
            if not cond or not then or not els:
                continue
            s = s[:left] + f"IF({cond},{then},{els})" + s[right:]
            converted = True
            break
        if not converted:
            break
    return s


# ── 括号配平兜底 ─────────────────────────────────────────────


def _parse_ok(s: str) -> bool:
    try:
        ast.parse(s)
        return True
    except SyntaxError:
        return False


def _replace_colons_outside_strings(s: str) -> str:
    """把引号外的残留冒号替换为逗号；保留字符串字面量内的冒号（如 '14:30'）。"""
    out: list[str] = []
    quote: str | None = None
    prev = ""
    for ch in s:
        if quote is not None:
            out.append(ch)
            if ch == quote and prev != "\\":
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            out.append(ch)
        elif ch == ":":
            out.append(",")
        else:
            out.append(ch)
        prev = ch
    return "".join(out)


_STR_PLACEHOLDER = "\x00S{}\x00"


def _mask_strings(s: str) -> tuple[str, list[str]]:
    """把引号字符串字面量替换为占位符，返回 (掩码后文本, 字面量列表)。

    这样后续所有方言变换（^、&&、: 、括号配平等）都不会误伤字符串内容。
    """
    literals: list[str] = []
    out: list[str] = []
    quote: str | None = None
    start = -1
    prev = ""
    for idx, ch in enumerate(s):
        if quote is not None:
            if ch == quote and prev != "\\":
                literals.append(s[start : idx + 1])
                out.append(_STR_PLACEHOLDER.format(len(literals) - 1))
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            start = idx
        else:
            out.append(ch)
        prev = ch
    if quote is not None:  # 未闭合字符串（源文本损坏）：原样保留剩余部分
        out.append(s[start:])
    return "".join(out), literals


def _unmask_strings(s: str, literals: list[str]) -> str:
    for i, lit in enumerate(literals):
        s = s.replace(_STR_PLACEHOLDER.format(i), lit)
    return s


def _balance_parens(s: str) -> str:
    opens, closes = s.count("("), s.count(")")
    if closes > opens:
        # 从右向左逐个试探删除多余的 )，保留第一个可解析的结果
        for _ in range(closes - opens):
            fixed = False
            for i in range(len(s) - 1, -1, -1):
                if s[i] != ")":
                    continue
                cand = s[:i] + s[i + 1:]
                if _parse_ok(cand) or cand.count("(") == cand.count(")"):
                    s = cand
                    fixed = True
                    break
            if not fixed:
                break
    elif opens > closes:
        s = s + ")" * (opens - closes)
    return s


# ── 主入口 ───────────────────────────────────────────────────


def normalize_formula(src: str) -> str:
    """把因子公式方言确定性翻译为 Python 表达式；无法翻译时原样返回"""
    if not src or not src.strip():
        return src
    s = src.strip()

    # 先掩码字符串字面量，保证后续变换不破坏字符串内容（如 '14:30'）
    s, literals = _mask_strings(s)

    s = s.replace("&&", " & ").replace("||", " | ")
    s = re.sub(r"\./", "/", s)
    s = re.sub(r"\.\*", "*", s)
    s = s.replace("^", "**")
    # 单 = → ==（不动 ==/>=/<=/!=；公式模式不存在赋值语句）
    s = re.sub(r"(?<![=!<>])=(?![=])", "==", s)
    s = _parenthesize_logic_operands(s)
    s = _replace_ternaries(s)
    # 三元消除后残留的冒号只可能是损坏（如 std(close:20)），按逗号修复
    # （字符串已被掩码，此处不会误伤字面量）
    if ":" in s:
        s = _replace_colons_outside_strings(s)
    # 隐式乘法：(a)(b) → (a)*(b)
    s = re.sub(r"\)\s*\(", ")*(", s)
    s = _balance_parens(s)

    return _unmask_strings(s, literals)
