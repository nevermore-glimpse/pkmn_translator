# -*- coding: utf-8 -*-
"""
rmarshal —— Ruby Marshal 格式（v4.8，Ruby 1.8 方言）读写实现。

用途：解析 / 写回 RMXP（RGSS）与 Pokémon Essentials 的 .rxdata 数据，
       例如 Data/Savestates/savestate1.rxdata、PBS 相关的 .rxdata 等。

★ 最关键的一条：对象表（link 表）的登记规则
-------------------------------------------
Marshal 用 `@<n>` 表示「引用第 n 个已经出现过的对象」。要让解析结果正确、
写回后字节一致，登记时机必须和 Ruby 1.8 的 `marshal.c / w_object()` 完全一致：

    st_add_direct(arg->data, obj, arg->data->num_entries);   ← 在处理内容【之前】

也就是说：
    · nil / true / false / Fixnum / Symbol   —— 不登记
      （Symbol 走另一张符号表，用 ';' 链接）
    · 其余一切对象（Float / String / Bignum / Array / Hash / Object /
      Class / Module / Struct / Regexp / userdef 'u' / usrmarshal 'U' / data 'd'）
      —— 全部在处理内容之前登记

这一点踩过坑：Float 也会被登记，而 Object('o') 是在实例变量【之前】登记的。
搞错时不会报错，'@' 会悄悄指向错误的对象 —— 唯一的检验手段是
`dumps(loads(x)) == x`（见本文件末尾 self_test）。

设计取舍
--------
1. **字节级可逆**：Ruby String 用 Python str 表示，读时
   `decode("utf-8", errors="surrogateescape")`，写时
   `encode("utf-8", errors="surrogateescape")`，任意字节序列都能原样回写。
2. **保留对象共享**：载入时把 '@' 还原成 Python 的「同一个对象」，
   写回时按 id() 判断曾否写过，重新编号，共享关系不丢。
3. **保留顺序**：实例变量顺序、Hash key 顺序都用插入顺序保留。

类型对照表
----------
    Marshal            Python
    nil                None
    true/false         True/False
    Fixnum/Bignum      int
    Float              float
    String             str（可能含 surrogate escape）
    Symbol             RSymbol
    Array              list
    Hash               RHash（有序 pair 列表，可带 default）
    Object             RObject（ruby_class + ivars）
    Struct             RStruct
    class/module       RClass
    regexp             RRegexp
    user defined 'u'   RUserDefined
    user marshal 'U'   RUserMarshal / data 'd' 同结构
"""

from __future__ import annotations

import math
import re
import struct
from typing import Any, Dict, List, Optional

# Ruby 1.8（RMXP/RGSS 自带）的 Fixnum 取值范围，超出的部分 Marshal 写成 Bignum('l')
FIXNUM_MIN = -(1 << 30)
FIXNUM_MAX = (1 << 30) - 1

# ---------------------------------------------------------------------------
# ★ Float 的写法（marshal.c: w_float / save_mantissa）
#
# Ruby 1.8 写浮点时先用 "%.*g" 打到 FLOAT_DIG=17 位有效数字，但如果这个 17 位
# 不足以精确还原原来的 double，会在后面**追加一段二进制尾数**：
#
#     "%.*g" 的结果 + \x00标记 + 若干个大端 32 位字（末尾的 0 字节会被裁掉）
#
# 例：62.207176384839649\0\xb1\xe5    ← 存档/动画数据里能见到这种"脏"字符串
# 直接 float() 会抛 ValueError，只解析前缀又会丢精度，两头都不行，
# 必须照 Ruby 的 load_mantissa() 把尾数拼回去。
# ---------------------------------------------------------------------------
FLOAT_DIG = 17            # DBL_DIG + 2
DECIMAL_MANT = 53 - 16    # 37
MANT_BITS = 32
_MANT_BYTES = MANT_BITS // 8

_NUM_PREFIX = re.compile(rb"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")


def _save_mantissa(value: float, buf: bytearray) -> int:
    """照抄 marshal.c 的 save_mantissa：把不够精度的尾数位追加到 buf 后面。"""
    frac, _ = math.modf(math.ldexp(math.frexp(abs(value))[0], DECIMAL_MANT))
    i = 0
    if frac > 0:
        buf.append(0)          # 标记字节
        i += 1
        while True:
            frac, whole = math.modf(math.ldexp(frac, MANT_BITS))
            m = int(whole) & 0xFFFFFFFF
            buf.append((m >> 24) & 0xFF)
            buf.append((m >> 16) & 0xFF)
            buf.append((m >> 8) & 0xFF)
            buf.append(m & 0xFF)
            i += 4
            if not frac > 0:
                break
        while buf[-1] == 0:    # 裁掉尾部 0 字节
            buf.pop()
            i -= 1
    return i


def _load_mantissa(value: float, tail: bytes) -> float:
    """照抄 marshal.c 的 load_mantissa：用追加的尾数位还原精确值。"""
    if not tail:
        return value
    s = value < 0
    mant, e = math.frexp(abs(value))
    # ★ C 源码是 `modf(x, &d);` —— 丢弃返回值，只把**整数部分**写回 d
    #   （save_mantissa 里才是 `d = modf(...)` 取小数部分，两者别搞混）
    _frac, whole = math.modf(math.ldexp(mant, DECIMAL_MANT))
    d = whole
    p, length, dig = 0, len(tail), 0
    while True:
        m = 0
        if length >= 4:
            m = tail[p]
            p += 1
        if length >= 3:
            m = (m << 8) | tail[p]
            p += 1
        if length >= 2:
            m = (m << 8) | tail[p]
            p += 1
        if length >= 1:
            m = (m << 8) | tail[p]
            p += 1
        dig -= 8 * length if length < _MANT_BYTES else MANT_BITS
        d += math.ldexp(float(m), dig)
        length -= _MANT_BYTES
        if length <= 0 or p >= len(tail):
            break
    d = math.ldexp(d, e - DECIMAL_MANT)
    return -d if s else d


def float_to_bytes(value: float) -> bytes:
    """生成 Marshal 里 Float 的文本外观（含可能的追加尾数）。"""
    if math.isinf(value):
        return b"-inf" if value < 0 else b"inf"
    if math.isnan(value):
        return b"nan"
    if value == 0.0:
        return b"-0" if math.copysign(1.0, value) < 0 else b"0"
    buf = bytearray(("%.*g" % (FLOAT_DIG, value)).encode("ascii"))
    _save_mantissa(value, buf)
    return bytes(buf)


def bytes_to_float(raw: bytes) -> float:
    """解析 Marshal 的 Float 文本（前缀 + 可选追加尾数）。"""
    if raw in (b"inf", b"Infinity"):
        return float("inf")
    if raw in (b"-inf", b"-Infinity"):
        return float("-inf")
    if raw.startswith(b"nan") or raw.startswith(b"NaN"):
        return float("nan")
    head, sep, tail = raw.partition(b"\x00")
    core = head if head else b"0"
    try:
        value = float(core)
    except ValueError:                       # 理论上不会有这种写法
        m = _NUM_PREFIX.match(raw)
        value = float(m.group(0)) if m else 0.0
        tail = b""
    if sep:
        value = _load_mantissa(value, tail)
    return value


# --------------------------------------------------------------------------
# 容器类型
# --------------------------------------------------------------------------
class RSymbol:
    """
    Ruby Symbol。必须与 str 区分，否则写回时会把 Symbol 变成 String。

    ★ .enc：符号名的编码标记（Ruby 1.9+）。**符号名含非 ASCII 时 Ruby 一定会
      写**，形式就是 `I :婆婆 1 :E T`：

          I :婆婆  1  :E  T      # :E = true  → UTF-8 符号名

      和 RStr 的编码标记长得一样，只是字符串那份的 `I "…` 里包的是 String、
      这份包的是 Symbol。**符号只登记符号表、不进对象表**，所以写回时这个
      包裹不能占对象表的一格，否则后面所有 '@' 链接号会整体 +1。
    """

    __slots__ = ("name", "enc")

    def __init__(self, name: str, enc: Optional[bool] = None):
        self.name = name
        self.enc = enc            # True=UTF-8 / False=BINARY / None=无标记

    def __repr__(self) -> str:
        return f":{self.name}"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, RSymbol):
            return self.name == other.name
        if isinstance(other, str):
            return self.name == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("RSymbol", self.name))


class RClass:
    """Marshal 里的 class / module 名（Ruby 会解析成真正的类，这里只存名字）。"""

    __slots__ = ("name",)

    def __init__(self, name: str):
        self.name = name

    def __repr__(self) -> str:
        return f"<class {self.name}>"

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, RClass) and self.name == other.name

    def __hash__(self) -> int:
        return hash(("RClass", self.name))


class RObject:
    """普通 Ruby 对象：类名 + 实例变量（保持顺序）。"""

    __slots__ = ("ruby_class", "ivars")

    def __init__(self, ruby_class: str, ivars: Optional[Dict[str, Any]] = None):
        self.ruby_class = ruby_class
        self.ivars: Dict[str, Any] = ivars if ivars is not None else {}

    def __repr__(self) -> str:
        keys = ",".join(list(self.ivars.keys())[:6])
        return f"<{self.ruby_class} {{{keys}}}>"

    def get(self, key: str, default: Any = None) -> Any:
        return self.ivars.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.ivars[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.ivars[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self.ivars


class RStruct:
    """Ruby Struct（Marshal 'S'）：类名 + 有序成员 [name, value]。"""

    __slots__ = ("ruby_class", "members")

    def __init__(self, ruby_class: str, members: Optional[List] = None):
        self.ruby_class = ruby_class
        self.members: List = members or []

    def __repr__(self) -> str:
        keys = ",".join(str(k) for k, _ in self.members[:6])
        return f"<struct {self.ruby_class} {{{keys}}}>"


class RIVar:
    """
    TYPE_IVAR('I')：给任意对象（Array / Hash / Struct / ...）附加实例变量。

    Essentials 的动画数据就是 `I C :PBAnimations <空Array> + @array=...` 这种
    写法 —— 实例变量挂在 Array 上而不是 Object 上，不包一层就会把数据丢掉。
    """

    __slots__ = ("base", "ivars", "uclass")

    def __init__(self, base: Any, ivars: Optional[Dict[str, Any]] = None,
                 uclass: Optional[str] = None):
        self.base = base
        self.ivars: Dict[str, Any] = ivars if ivars is not None else {}
        # TYPE_UCLASS('C')：对象的类不是它那个内建类型的默认类（如 PBAnimations < Array）
        self.uclass = uclass

    def __repr__(self) -> str:
        keys = ",".join(list(self.ivars.keys())[:6])
        return f"<ivar {type(self.base).__name__} {{{keys}}}>"


class RRegexp:
    """Ruby Regexp（'/'）：源码 + 选项标志。"""

    __slots__ = ("source", "options")

    def __init__(self, source: str, options: int = 0):
        self.source = source
        self.options = options

    def __repr__(self) -> str:
        return f"<regexp /{self.source}/>"


class RHash:
    """
    Ruby Hash。

    用「有序 pair 列表」而不是 Python dict 实现：Ruby 的 key 可以是 Array/Hash
    这类不可哈希对象，且 Marshal 里 key 顺序有意义。写回时原样保留 key 对象
    本身（哪怕它是 list），保证字节一致。
    """

    __slots__ = ("pairs", "default")

    def __init__(self, pairs=None, default: Any = None):
        self.pairs: List[tuple] = list(pairs or [])
        self.default = default

    # -- 映射风格 API ----------------------------------------------------
    def __len__(self) -> int:
        return len(self.pairs)

    def __iter__(self):
        return (k for k, _ in self.pairs)

    def keys(self) -> List[Any]:
        return [k for k, _ in self.pairs]

    def values(self) -> List[Any]:
        return [v for _, v in self.pairs]

    def items(self):
        return list(self.pairs)

    def __contains__(self, key: Any) -> bool:
        return any(self._eq(k, key) for k, _ in self.pairs)

    def __getitem__(self, key: Any) -> Any:
        for k, v in self.pairs:
            if self._eq(k, key):
                return v
        return self.default

    def get(self, key: Any, default: Any = None) -> Any:
        for k, v in self.pairs:
            if self._eq(k, key):
                return v
        return default if default is not None else self.default

    def __setitem__(self, key: Any, value: Any) -> None:
        for i, (k, _) in enumerate(self.pairs):
            if self._eq(k, key):
                self.pairs[i] = (key, value)
                return
        self.pairs.append((key, value))

    def pop(self, key: Any, *rest) -> Any:
        for i, (k, v) in enumerate(self.pairs):
            if self._eq(k, key):
                del self.pairs[i]
                return v
        if rest:
            return rest[0]
        return self.default

    def to_dict(self) -> Dict[Any, Any]:
        """尽力转成普通 dict（key 不可哈希时会失败，调用方自行处理）。"""
        return {k: v for k, v in self.pairs}

    @staticmethod
    def _eq(a: Any, b: Any) -> bool:
        """Ruby 的 ==（Symbol 与 String 在 Marshal 里是两个东西，不混同）。"""
        if isinstance(a, RSymbol) or isinstance(b, RSymbol):
            return isinstance(a, RSymbol) and isinstance(b, RSymbol) and a.name == b.name
        if isinstance(a, list) and isinstance(b, list):
            return len(a) == len(b) and all(RHash._eq(x, y) for x, y in zip(a, b))
        try:
            return bool(a == b)
        except Exception:
            return a is b

    def __repr__(self) -> str:
        body = ",".join(f"{k!r}->{v!r}" for k, v in self.pairs[:4])
        if len(self.pairs) > 4:
            body += ",..."
        return f"<Hash {{{body}}}>"


class RFloat(float):
    """
    Ruby Float。

    ★ 为什么用子类而不是裸 float：**不同 Ruby 写浮点的文本外观不一样**。
      Ruby 1.8.7 是 `sprintf("%.17g")` + 可选尾数，而老版 RGSS 内核（以及
      用 ruby_dtoa 的版本）会写成 `1e2` 这种短形式，有时还**完全不带尾数**。
      我们没法猜出每个游戏用的是哪一支 —— 所以读到的原始字节**原样留着**，
      没改过就逐字节写回。否则「打开存档 → 保存」这一步就会把整份存档里的
      浮点全部改写一遍（虽然值还对，但字节全变了，不好核对也不好排查）。
    """

    __slots__ = ("payload",)

    def __new__(cls, value: Any = 0.0, payload: Optional[bytes] = None):
        obj = super().__new__(cls, float(value))
        obj.payload = payload          # 读到的原始字节（含尾数），None = 自己造
        return obj


class RStr(str):
    """
    Ruby String。

    ★ 为什么所有 Ruby 字符串都要用这个 str 子类，而不是裸 str：
      CPython 会把单字节等短字符串驻留（intern）成同一个对象。于是 Marshal 里
      两个各自独立的 "A"，在 Python 里 `id()` 相同，写回时会被误判成共享对象、
      输出多余的 '@' 链接。包一层后每个实例都是独立对象，身份语义才对得上。
      对外仍然完全当作普通 str 用（== 、len、json、格式化都没问题）。

    ★ .enc：Marshal 的字符串编码标记（Ruby 1.9+）

        I " hello : E T     # :E = true  → Encoding::UTF_8
        I " hello : E F     # :E = false → Encoding::BINARY

      只有少量字符串带这个标记，但写回时漏掉就字节不一致。
    """

    enc = None          # True=UTF-8 / False=BINARY / None=无标记

    def __new__(cls, value: str = "", enc: Optional[bool] = None):
        obj = super().__new__(cls, value)
        obj.enc = enc
        return obj


class RUserDefined:
    """实现了 _dump 的类（'u'）：类名 + 字符串负载。"""

    __slots__ = ("ruby_class", "payload")

    def __init__(self, ruby_class: str, payload: str = ""):
        self.ruby_class = ruby_class
        self.payload = payload

    def __repr__(self) -> str:
        return f"<{self.ruby_class} (dump {len(self.payload)}B)>"


class RUserMarshal:
    """实现了 marshal_dump 的类（'U'）或 T_DATA（'d'）：类名 + 任意对象。"""

    __slots__ = ("ruby_class", "data")

    def __init__(self, ruby_class: str, data: Any = None):
        self.ruby_class = ruby_class
        self.data = data

    def __repr__(self) -> str:
        return f"<{self.ruby_class} (marshal_dump)>"


# --------------------------------------------------------------------------
# 载入
# --------------------------------------------------------------------------
class UnmarshalError(Exception):
    pass


def _sym_name(obj: Any) -> str:
    return obj.name if isinstance(obj, RSymbol) else str(obj)


class _Loader:
    def __init__(self, data: bytes, start: int = 0):
        self.data = data
        self.pos = start
        self.start = start
        self.symbols: List[Any] = []     # 符号表（':' 登记 / ';' 引用）
        self.objects: List[Any] = []     # 对象表（'@' 引用）

    @property
    def consumed(self) -> int:
        return self.pos - self.start

    # -- 基础读取 ---------------------------------------------------------
    def _need(self, n: int) -> None:
        if self.pos + n > len(self.data):
            raise UnmarshalError(f"数据意外结束 @0x{self.pos:X}")

    def byte(self) -> int:
        self._need(1)
        b = self.data[self.pos]
        self.pos += 1
        return b

    def signed_byte(self) -> int:
        b = self.byte()
        return b - 256 if b > 127 else b

    def read_bytes(self, n: int) -> bytes:
        self._need(n)
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    # -- 变长整数 / 字符串 ------------------------------------------------
    def read_int(self) -> int:
        """Marshal 的整数编码：-123..122 用单字节 ±5 偏移，其余用多字节补码。"""
        c = self.signed_byte()
        if c == 0:
            return 0
        if 4 < c < 128:            # 正整数小值
            return c - 5
        if -129 < c < -4:          # 负整数小值
            return c + 5
        cnt = abs(c)
        raw = self.read_bytes(cnt)
        val = int.from_bytes(raw, "little", signed=False)
        if c < 0:
            val -= 1 << (cnt * 8)
        return val

    def _dec(self, raw: bytes) -> RStr:
        return RStr(raw.decode("utf-8", errors="surrogateescape"))

    def read_str(self) -> str:
        return self._dec(self.read_bytes(self.read_int()))

    # -- 登记 ------------------------------------------------------------
    def _reg_obj(self, obj: Any) -> Any:
        self.objects.append(obj)
        return obj

    def _reg_sym(self, obj: Any) -> Any:
        self.symbols.append(obj)
        return obj

    # -- 主体 ------------------------------------------------------------
    def load(self) -> Any:
        if self.read_bytes(2) != b"\x04\x08":
            raise UnmarshalError("不是 Ruby Marshal 数据（缺少 04 08 魔数）")
        return self.read_obj()

    def read_obj(self) -> Any:
        code = self.byte()
        handler = getattr(self, f"_t_{code:02x}", None)
        if handler is not None:
            return handler()
        raise UnmarshalError(
            f"不支持的 Marshal 类型 {chr(code)!r} (0x{code:02X}) @0x{self.pos - 1:X}")

    # ---- immediate（不登记）--------------------------------------------
    def _t_30(self) -> None:      return None
    def _t_54(self) -> bool:      return True
    def _t_46(self) -> bool:      return False
    def _t_69(self) -> int:       return self.read_int()

    # ---- 登记型（全部在处理内容【之前】登记）----------------------------
    def _t_6c(self) -> int:       # Bignum 'l'
        sign = self.byte()        # '+' / '-'
        cnt = self.read_int()     # 16bit 位组的个数（Ruby1.8: SHORTLEN(len)）
        val = int.from_bytes(self.read_bytes(cnt * 2), "little", signed=False)
        return self._reg_obj(-val if sign == 45 else val)

    def _t_66(self) -> float:     # Float 'f'
        raw = self.read_bytes(self.read_int())
        return self._reg_obj(RFloat(bytes_to_float(raw), raw))

    def _t_22(self) -> str:       # String '"'
        return self._reg_obj(self._dec(self.read_bytes(self.read_int())))

    def _t_3a(self) -> RSymbol:   # Symbol ':'（符号表，不进对象表）
        return self._reg_sym(RSymbol(self._dec(self.read_bytes(self.read_int()))))

    def _t_3b(self) -> Any:       # Symbol link ';'
        idx = self.read_int()
        if idx >= len(self.symbols):
            raise UnmarshalError(f"符号链接越界 {idx}")
        return self.symbols[idx]

    def _t_40(self) -> Any:       # Object link '@'
        idx = self.read_int()
        if idx >= len(self.objects):
            raise UnmarshalError(f"对象链接越界 {idx}（当前仅 {len(self.objects)} 个）")
        return self.objects[idx]

    def _t_5b(self) -> list:      # Array '['
        n = self.read_int()
        arr: List[Any] = []
        self._reg_obj(arr)
        arr.extend(self.read_obj() for _ in range(n))
        return arr

    def _t_7b(self) -> Any:       # Hash '{'
        n = self.read_int()
        h = RHash()
        self._reg_obj(h)
        for _ in range(n):
            k = self.read_obj()
            h.pairs.append((k, self.read_obj()))
        return h

    def _t_7d(self) -> Any:       # Hash with default '}'
        n = self.read_int()
        h = RHash()
        self._reg_obj(h)
        for _ in range(n):
            k = self.read_obj()
            h.pairs.append((k, self.read_obj()))
        h.default = self.read_obj()
        return h

    def _t_63(self) -> RClass:    # Class 'c'
        return self._reg_obj(RClass(self.read_str()))

    def _t_6d(self) -> RClass:    # Module 'm'
        return self._reg_obj(RClass(self.read_str()))

    def _t_2f(self) -> RRegexp:   # Regexp '/'
        src = self.read_str()
        return self._reg_obj(RRegexp(src, self.byte()))

    def _t_6f(self) -> Any:       # Object 'o'
        cls = _sym_name(self.read_obj())
        obj = RObject(cls)
        self._reg_obj(obj)        # ★ 在实例变量之前登记
        for _ in range(self.read_int()):
            key = _sym_name(self.read_obj())
            obj.ivars[key] = self.read_obj()
        return obj

    def _t_53(self) -> Any:       # Struct 'S'
        cls = _sym_name(self.read_obj())
        st = RStruct(cls)
        self._reg_obj(st)
        for _ in range(self.read_int()):
            key = self.read_obj()
            st.members.append((key, self.read_obj()))
        return st

    def _t_75(self) -> Any:       # user defined 'u'
        cls = _sym_name(self.read_obj())
        obj = RUserDefined(cls)
        self._reg_obj(obj)
        obj.payload = self.read_str()
        return obj

    def _t_55(self) -> Any:       # user marshal 'U'
        cls = _sym_name(self.read_obj())
        obj = RUserMarshal(cls)
        self._reg_obj(obj)
        obj.data = self.read_obj()
        return obj

    def _t_64(self) -> Any:       # T_DATA 'd'
        cls = _sym_name(self.read_obj())
        obj = RUserMarshal(cls)
        self._reg_obj(obj)
        obj.data = self.read_obj()
        return obj

    def _t_49(self) -> Any:       # instance variables 'I'
        base = self.read_obj()
        for _ in range(self.read_int()):
            key = _sym_name(self.read_obj())
            val = self.read_obj()
            if key == "E" and isinstance(base, RStr):
                # Marshal 的字符串编码标记，就地记下来以便原样写回
                base.enc = bool(val)
                return base
            if key == "E" and isinstance(base, RSymbol):
                # 符号名的编码标记（非 ASCII 符号必带），同样就地记下
                base.enc = bool(val)
                return base
            if isinstance(base, RObject):
                base.ivars[key] = val
            elif isinstance(base, RIVar):
                base.ivars[key] = val
            else:
                # 实例变量挂在 Array/Hash 等非 Object 上：包一层，不能丢
                base = RIVar(base, {key: val})
        return base

    def _t_65(self) -> Any:       # extended object 'e'（模块扩展标记）
        obj = self.read_obj()
        for _ in range(self.read_int()):
            mod = _sym_name(self.read_obj())
            if isinstance(obj, RObject):
                obj.ruby_class += f"(+{mod})"
        return obj

    def _t_43(self) -> Any:       # user class 'C'（如 C:PBAnimations [ ... ]）
        cls = _sym_name(self.read_obj())
        obj = self.read_obj()
        if isinstance(obj, RObject):
            obj.ruby_class = cls
            return obj
        if isinstance(obj, RIVar):
            obj.uclass = cls
            return obj
        return RIVar(obj, uclass=cls)


def loads(data: bytes) -> Any:
    """解析 Ruby Marshal 字节串（只取第一个对象）。"""
    return _Loader(data).load()


def load(path: str) -> Any:
    """读取文件的第一个 Marshal 对象。"""
    with open(path, "rb") as f:
        return loads(f.read())


def loads_all(data: bytes) -> List[Any]:
    """
    Essentials 的存档是「多个 Marshal 流首尾相接」——每 dump 一个全局变量就是一个
    独立的 04 08 开头，这里把它们全部解析出来。
    """
    items: List[Any] = []
    pos, total = 0, len(data)
    while pos < total:
        if data[pos:pos + 2] != b"\x04\x08":
            raise UnmarshalError(f"偏移 0x{pos:X} 处不是 Marshal 魔数")
        ld = _Loader(data, pos)
        items.append(ld.load())
        pos = ld.pos
    return items


def load_all(path: str) -> List[Any]:
    """读取文件中全部 Marshal 流（Essentials 存档用）。"""
    with open(path, "rb") as f:
        return loads_all(f.read())


def streams(data: bytes) -> List[tuple]:
    """返回 [(起始偏移, 字节数)，...]，便于按流定位与写回。"""
    ret: List[tuple] = []
    pos, total = 0, len(data)
    while pos < total:
        if data[pos:pos + 2] != b"\x04\x08":
            raise UnmarshalError(f"偏移 0x{pos:X} 处不是 Marshal 魔数")
        ld = _Loader(data, pos)
        ld.load()
        ret.append((pos, ld.consumed))
        pos = ld.pos
    return ret


# --------------------------------------------------------------------------
# 序列化（写回）
# --------------------------------------------------------------------------
# ★ 'I'（TYPE_IVAR）包装 RIVar 只是 Python 侧的壳：Ruby 里占对象表一格的是
#   **被包的对象**（Symbol / Fixnum / nil / true / false 则本来就不占），
#   壳自己永远不占。见 write_obj 里的 RIVar 分支。
class _Dumper:
    def __init__(self):
        self.out = bytearray(b"\x04\x08")
        self.symbols: Dict[str, int] = {}
        self.objects: Dict[int, int] = {}   # id(obj) -> 索引
        self.objects_n = 0
        # id() 会被复用，登记过的对象必须留着引用，否则可能误判成同一个对象
        self.keepalive: List[Any] = []
        self._suppress: set = set()

    def write(self, bs: bytes) -> None:
        self.out += bs

    def _reg(self, obj: Any) -> None:
        if id(obj) in self._suppress:
            return          # 序号已被外层的 TYPE_IVAR 包装占掉，别再占一格
        self.objects[id(obj)] = self.objects_n
        self.objects_n += 1
        self.keepalive.append(obj)

    def write_int(self, n: int) -> None:
        """
        长度 / 下标用的变长整数。严格照抄 Ruby 1.8 的 w_long()：

            n == 0            → \x00
            0 < n < 123       → n + 5
            -124 < n < 0      → (n - 5) & 0xff
            其余              → 计数字节 + cnt 个小端字节

        最后一档的关键是「算术右移到 0（正数）或 -1（负数）就停」——
        所以 -150 只占 1 个字节（\xff\x6a），而不是教科书里常见的 2 字节写法。
        """
        if n == 0:
            self.write(b"\x00")
            return
        if 0 < n < 123:
            self.write(bytes([n + 5]))
            return
        if -124 < n < 0:
            self.write(bytes([(n - 5) & 0xFF]))
            return
        buf = bytearray()
        x = n
        cnt = None
        for i in range(1, 5):
            buf.append(x & 0xFF)
            x >>= 8                      # Python 的 >> 对负数是算术右移
            if x == 0:
                cnt = i
                break
            if x == -1:
                cnt = -i
                break
        if cnt is None:
            raise UnmarshalError(f"整数超出 Marshal 支持范围: {n}")
        self.write(bytes([cnt & 0xFF]))
        self.write(bytes(buf))

    def write_str_raw(self, text: str) -> None:
        raw = text.encode("utf-8", errors="surrogateescape")
        self.write_int(len(raw))
        self.write(raw)

    def write_bignum(self, n: int) -> None:
        self.write(b"l")
        self.write(b"-" if n < 0 else b"+")
        digits = bytearray()
        m = -n if n < 0 else n
        while m > 0:
            digits += struct.pack("<H", m & 0xFFFF)
            m >>= 16
        if not digits:
            digits = struct.pack("<H", 0)
        self.write_int(len(digits) // 2)
        self.write(bytes(digits))

    def write_value_int(self, n: int) -> None:
        if FIXNUM_MIN <= n <= FIXNUM_MAX:
            self.write(b"i")
            self.write_int(n)
            return
        # Bignum 也要登记（Ruby 的 st_add_direct 在 switch 之前）
        self.write_bignum(n)
        self._reg(n)

    def write_obj(self, obj: Any) -> None:
        # 1) immediate 值：既不登记也不参与链接
        if obj is None:
            self.write(b"0")
            return
        if obj is True:
            self.write(b"T")
            return
        if obj is False:
            self.write(b"F")
            return
        if isinstance(obj, int):
            key = id(obj)
            if FIXNUM_MIN <= obj <= FIXNUM_MAX:
                self.write(b"i")
                self.write_int(obj)
            elif key in self.objects:
                self.write(b"@")
                self.write_int(self.objects[key])
            else:
                self.write_bignum(obj)
                self._reg(obj)
            return
        if isinstance(obj, RSymbol):
            # ★ 编码标记只跟着「符号表的定义」走：同一个符号后面再出现时
            #   Ruby 只写 `;link`，**不再带 I/E 包裹**（写回时必须照办，
            #   否则每个引用处都会多出 6 个字节）。
            if obj.enc is not None and obj.name not in self.symbols:
                # I :名字 1 :E T/F
                # ★ 不占对象表（符号只进符号表），所以这里不 _reg
                self.write(b"I")
                self.write_symbol(obj.name)
                self.write_int(1)
                self.write_symbol("E")
                self.write(b"T" if obj.enc else b"F")
                return
            self.write_symbol(obj.name)
            return

        # 2) 其余对象：已写过就出 link，否则登记后再写内容
        key = id(obj)
        if key in self.objects:
            self.write(b"@")
            self.write_int(self.objects[key])
            return

        if isinstance(obj, RStr) and obj.enc is not None:
            # 'I' + 字符串本体 + ivar(:E => true/false)
            self.write(b"I")
            self.write(b'"')
            self.write_str_raw(str(obj))
            self._reg(obj)
            self.write_int(1)
            self.write_symbol("E")
            self.write(b"T" if obj.enc else b"F")
            return
        if isinstance(obj, str):
            self.write(b'"')
            self.write_str_raw(obj)
            self._reg(obj)
            return
        if isinstance(obj, float):
            self.write(b"f")
            # ★ 读进来时原样留着的字节优先（保住各版本 Ruby 的不同写法）；
            #   自己造出来的浮点才用 Ruby 1.8.7 那套 `%.17g` + 尾数。
            payload = obj.payload if isinstance(obj, RFloat) else None
            raw = payload if payload is not None else float_to_bytes(float(obj))
            self.write_int(len(raw))
            self.write(raw)
            self._reg(obj)
            return
        if isinstance(obj, RClass):
            self.write(b"c")
            self.write_str_raw(obj.name)
            self._reg(obj)
            return
        if isinstance(obj, RIVar) and obj.uclass and not obj.ivars:
            # 只有 UCLASS、没有实例变量时，'I' 字节其实是不存在的
            self.write(b"C")
            self.write_symbol(obj.uclass)
            # ★ 包装本身不是 Ruby 对象，**从不**占登记号；占号的是 base
            #   （Symbol / Fixnum / nil / true / false 天然不占）。
            self.write_obj(obj.base)
            return
        if isinstance(obj, RIVar):
            # 'I'（TYPE_IVAR）只是给 base 挂实例变量的标记：
            # 真正的登记发生在 base 身上，包装自己一格都不占。
            # ★ 两处都不能替 base 占号 —— ① base 是 Symbol（只进符号表，
            #   如带编码的 I:\x06E\x06:\x06ET）时会让其后所有 @ 号 +1；
            #   ② base 是别的类型时，同一个 base 第二次出现应该是 '@' 链接，
            #   若登记的是包装那就查不到、会把对象整个重写一遍。
            #   真实存档（宝可梦SA 移植版）两种都踩过。
            bkey = id(obj.base)
            if bkey in self.objects:
                # base 已经写过 → Ruby 这时只会写一个链接，不再带 'I'
                self.write(b"@")
                self.write_int(self.objects[bkey])
                return
            self.write(b"I")
            if obj.uclass:
                self.write(b"C")
                self.write_symbol(obj.uclass)
            self.write_obj(obj.base)
            self.write_int(len(obj.ivars))
            for k, v in obj.ivars.items():
                self.write_symbol(k)
                self.write_obj(v)
            return
        if isinstance(obj, RRegexp):
            self.write(b"/")
            self.write_str_raw(obj.source)
            self.write(bytes([obj.options]))
            self._reg(obj)
            return
        if isinstance(obj, list):
            self.write(b"[")
            self.write_int(len(obj))
            self._reg(obj)
            for it in obj:
                self.write_obj(it)
            return
        if isinstance(obj, RHash):
            has_default = obj.default is not None
            self.write(b"}" if has_default else b"{")
            self.write_int(len(obj))
            self._reg(obj)
            for k, v in obj.pairs:
                self.write_obj(k)
                self.write_obj(v)
            if has_default:
                self.write_obj(obj.default)
            return
        if isinstance(obj, dict):
            self.write(b"{")
            self.write_int(len(obj))
            self._reg(obj)
            for k, v in obj.items():
                self.write_obj(k)
                self.write_obj(v)
            return
        if isinstance(obj, RObject):
            self.write(b"o")
            self.write_symbol(obj.ruby_class)
            self.write_int(len(obj.ivars))
            self._reg(obj)          # ★ 在实例变量之前登记
            for k, v in obj.ivars.items():
                self.write_symbol(k)
                self.write_obj(v)
            return
        if isinstance(obj, RStruct):
            self.write(b"S")
            self.write_symbol(obj.ruby_class)
            self.write_int(len(obj.members))
            self._reg(obj)
            for k, v in obj.members:
                self.write_symbol(_sym_name(k))
                self.write_obj(v)
            return
        if isinstance(obj, RUserDefined):
            self.write(b"u")
            self.write_symbol(obj.ruby_class)
            payload = obj.payload if isinstance(obj.payload, str) else str(obj.payload)
            self._reg(obj)
            self.write_str_raw(payload)
            return
        if isinstance(obj, RUserMarshal):
            self.write(b"U")
            self.write_symbol(obj.ruby_class)
            self._reg(obj)
            self.write_obj(obj.data)
            return

        raise UnmarshalError(f"无法序列化的 Python 对象: {type(obj).__name__}")

    def write_symbol(self, name: str) -> None:
        if name in self.symbols:
            self.write(b";")
            self.write_int(self.symbols[name])
            return
        self.write(b":")
        self.write_str_raw(name)
        self.symbols[name] = len(self.symbols)


def dumps(obj: Any) -> bytes:
    """序列化成 Ruby Marshal 字节串。"""
    d = _Dumper()
    d.write_obj(obj)
    return bytes(d.out)


def dump(obj: Any, path: str) -> None:
    with open(path, "wb") as f:
        f.write(dumps(obj))


def dumps_all(objs) -> bytes:
    """多个对象各自 dump 后首尾相接——Essentials 存档的写法。"""
    return b"".join(dumps(o) for o in objs)


def dump_all(objs, path: str) -> None:
    with open(path, "wb") as f:
        f.write(dumps_all(objs))


# --------------------------------------------------------------------------
# 辅助
# --------------------------------------------------------------------------
def safe_str(text: Any) -> str:
    """把可能含 surrogate escape 的字符串转成可安全打印/写入文件的形式。"""
    if not isinstance(text, str):
        text = str(text)
    return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")


def _self_test(path: str) -> None:
    raw = open(path, "rb").read()
    objs = loads_all(raw)
    out = dumps_all(objs)
    print(f"流数量: {len(objs)}")
    print("round-trip:", "OK" if out == raw else f"FAIL ({len(raw)} -> {len(out)})")
    if out != raw:
        for i in range(min(len(raw), len(out))):
            if raw[i] != out[i]:
                print("首个差异 @", i)
                print("  原始:", raw[max(0, i - 40):i + 40])
                print("  重排:", out[max(0, i - 40):i + 40])
                return


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        _self_test(sys.argv[1])
    else:
        print("用法: python rmarshal.py <文件.rxdata>")
