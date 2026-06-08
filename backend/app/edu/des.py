"""
DES 加密复刻自 cas.jlu.edu.cn/tpass/comm/js/des.js 的 strEnc 函数。

约束：
- 不是标准 DES：每个字符按 16 位 unicode 处理（charCodeAt），
  4 字符 = 64 bit 一个 block；密钥也按相同方式分组。
- 多密钥时按 firstKey -> secondKey -> thirdKey 顺序，每个 key 内部按其
  分组数依次 enc。

仅用于吉大 CAS 登录的密码加密复现，不要拿去做通用加密。
"""

from __future__ import annotations

# ============== 数据/位转换 ==============

def _str_to_bt(s: str) -> list[int]:
    """对应 JS strToBt：4 字符 → 64 bit。不足 4 字符末尾用 0 填充。"""
    bt = [0] * 64
    leng = len(s)
    fill = min(leng, 4)
    for i in range(fill):
        k = ord(s[i])
        for j in range(16):
            pow_v = 1 << (15 - j)
            bt[16 * i + j] = (k // pow_v) % 2
    return bt


def _byte_to_string(byte_data: list[int]) -> str:
    out = []
    for i in range(4):
        count = 0
        for j in range(16):
            count += byte_data[16 * i + j] * (1 << (15 - j))
        if count != 0:
            out.append(chr(count))
    return "".join(out)


def _bt64_to_hex(byte_data: list[int]) -> str:
    out = []
    for i in range(16):
        v = (byte_data[i * 4] << 3) | (byte_data[i * 4 + 1] << 2) | (byte_data[i * 4 + 2] << 1) | byte_data[i * 4 + 3]
        out.append("{:X}".format(v))
    return "".join(out)


def _hex_to_bt64(hex_str: str) -> list[int]:
    bits: list[int] = []
    for ch in hex_str[:16]:
        v = int(ch, 16)
        bits.append((v >> 3) & 1)
        bits.append((v >> 2) & 1)
        bits.append((v >> 1) & 1)
        bits.append(v & 1)
    return bits


def _get_key_bytes(key: str) -> list[list[int]]:
    """把 key 按每 4 字符切成 64 bit 块。剩余不足 4 也补一块（0 填充）。"""
    blocks: list[list[int]] = []
    leng = len(key)
    iterator = leng // 4
    remainder = leng % 4
    for i in range(iterator):
        blocks.append(_str_to_bt(key[i * 4 : i * 4 + 4]))
    if remainder > 0:
        blocks.append(_str_to_bt(key[iterator * 4 :]))
    return blocks


# ============== DES 内部置换 ==============

def _initial_permute(data: list[int]) -> list[int]:
    ip = [0] * 64
    for i, m, n in zip(range(4), range(1, 8, 2), range(0, 8, 2)):
        for j, k in zip(range(7, -1, -1), range(8)):
            ip[i * 8 + k] = data[j * 8 + m]
            ip[i * 8 + k + 32] = data[j * 8 + n]
    return ip


def _expand_permute(right: list[int]) -> list[int]:
    ep = [0] * 48
    for i in range(8):
        ep[i * 6 + 0] = right[31] if i == 0 else right[i * 4 - 1]
        ep[i * 6 + 1] = right[i * 4 + 0]
        ep[i * 6 + 2] = right[i * 4 + 1]
        ep[i * 6 + 3] = right[i * 4 + 2]
        ep[i * 6 + 4] = right[i * 4 + 3]
        ep[i * 6 + 5] = right[0] if i == 7 else right[i * 4 + 4]
    return ep


def _xor(a: list[int], b: list[int]) -> list[int]:
    return [x ^ y for x, y in zip(a, b)]


_S_BOXES = [
    # s1
    [
        [14, 4, 13, 1, 2, 15, 11, 8, 3, 10, 6, 12, 5, 9, 0, 7],
        [0, 15, 7, 4, 14, 2, 13, 1, 10, 6, 12, 11, 9, 5, 3, 8],
        [4, 1, 14, 8, 13, 6, 2, 11, 15, 12, 9, 7, 3, 10, 5, 0],
        [15, 12, 8, 2, 4, 9, 1, 7, 5, 11, 3, 14, 10, 0, 6, 13],
    ],
    # s2
    [
        [15, 1, 8, 14, 6, 11, 3, 4, 9, 7, 2, 13, 12, 0, 5, 10],
        [3, 13, 4, 7, 15, 2, 8, 14, 12, 0, 1, 10, 6, 9, 11, 5],
        [0, 14, 7, 11, 10, 4, 13, 1, 5, 8, 12, 6, 9, 3, 2, 15],
        [13, 8, 10, 1, 3, 15, 4, 2, 11, 6, 7, 12, 0, 5, 14, 9],
    ],
    # s3
    [
        [10, 0, 9, 14, 6, 3, 15, 5, 1, 13, 12, 7, 11, 4, 2, 8],
        [13, 7, 0, 9, 3, 4, 6, 10, 2, 8, 5, 14, 12, 11, 15, 1],
        [13, 6, 4, 9, 8, 15, 3, 0, 11, 1, 2, 12, 5, 10, 14, 7],
        [1, 10, 13, 0, 6, 9, 8, 7, 4, 15, 14, 3, 11, 5, 2, 12],
    ],
    # s4
    [
        [7, 13, 14, 3, 0, 6, 9, 10, 1, 2, 8, 5, 11, 12, 4, 15],
        [13, 8, 11, 5, 6, 15, 0, 3, 4, 7, 2, 12, 1, 10, 14, 9],
        [10, 6, 9, 0, 12, 11, 7, 13, 15, 1, 3, 14, 5, 2, 8, 4],
        [3, 15, 0, 6, 10, 1, 13, 8, 9, 4, 5, 11, 12, 7, 2, 14],
    ],
    # s5
    [
        [2, 12, 4, 1, 7, 10, 11, 6, 8, 5, 3, 15, 13, 0, 14, 9],
        [14, 11, 2, 12, 4, 7, 13, 1, 5, 0, 15, 10, 3, 9, 8, 6],
        [4, 2, 1, 11, 10, 13, 7, 8, 15, 9, 12, 5, 6, 3, 0, 14],
        [11, 8, 12, 7, 1, 14, 2, 13, 6, 15, 0, 9, 10, 4, 5, 3],
    ],
    # s6
    [
        [12, 1, 10, 15, 9, 2, 6, 8, 0, 13, 3, 4, 14, 7, 5, 11],
        [10, 15, 4, 2, 7, 12, 9, 5, 6, 1, 13, 14, 0, 11, 3, 8],
        [9, 14, 15, 5, 2, 8, 12, 3, 7, 0, 4, 10, 1, 13, 11, 6],
        [4, 3, 2, 12, 9, 5, 15, 10, 11, 14, 1, 7, 6, 0, 8, 13],
    ],
    # s7
    [
        [4, 11, 2, 14, 15, 0, 8, 13, 3, 12, 9, 7, 5, 10, 6, 1],
        [13, 0, 11, 7, 4, 9, 1, 10, 14, 3, 5, 12, 2, 15, 8, 6],
        [1, 4, 11, 13, 12, 3, 7, 14, 10, 15, 6, 8, 0, 5, 9, 2],
        [6, 11, 13, 8, 1, 4, 10, 7, 9, 5, 0, 15, 14, 2, 3, 12],
    ],
    # s8
    [
        [13, 2, 8, 4, 6, 15, 11, 1, 10, 9, 3, 14, 5, 0, 12, 7],
        [1, 15, 13, 8, 10, 3, 7, 4, 12, 5, 6, 11, 0, 14, 9, 2],
        [7, 11, 4, 1, 9, 12, 14, 2, 0, 6, 10, 13, 15, 3, 5, 8],
        [2, 1, 14, 7, 4, 10, 8, 13, 15, 12, 9, 0, 3, 5, 6, 11],
    ],
]


def _s_box_permute(expand_byte: list[int]) -> list[int]:
    out = [0] * 32
    for m in range(8):
        i = expand_byte[m * 6] * 2 + expand_byte[m * 6 + 5]
        j = (
            expand_byte[m * 6 + 1] * 8
            + expand_byte[m * 6 + 2] * 4
            + expand_byte[m * 6 + 3] * 2
            + expand_byte[m * 6 + 4]
        )
        v = _S_BOXES[m][i][j]
        out[m * 4 + 0] = (v >> 3) & 1
        out[m * 4 + 1] = (v >> 2) & 1
        out[m * 4 + 2] = (v >> 1) & 1
        out[m * 4 + 3] = v & 1
    return out


_P_TABLE = [
    15, 6, 19, 20, 28, 11, 27, 16,
    0, 14, 22, 25, 4, 17, 30, 9,
    1, 7, 23, 13, 31, 26, 2, 8,
    18, 12, 29, 5, 21, 10, 3, 24,
]


def _p_permute(s_box_byte: list[int]) -> list[int]:
    return [s_box_byte[idx] for idx in _P_TABLE]


_FP_TABLE = [
    39, 7, 47, 15, 55, 23, 63, 31,
    38, 6, 46, 14, 54, 22, 62, 30,
    37, 5, 45, 13, 53, 21, 61, 29,
    36, 4, 44, 12, 52, 20, 60, 28,
    35, 3, 43, 11, 51, 19, 59, 27,
    34, 2, 42, 10, 50, 18, 58, 26,
    33, 1, 41, 9, 49, 17, 57, 25,
    32, 0, 40, 8, 48, 16, 56, 24,
]


def _final_permute(end_byte: list[int]) -> list[int]:
    return [end_byte[idx] for idx in _FP_TABLE]


_KEY_LOOP = [1, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1]
_KEY_PERMUTE = [
    13, 16, 10, 23, 0, 4, 2, 27, 14, 5, 20, 9, 22, 18, 11, 3,
    25, 7, 15, 6, 26, 19, 12, 1, 40, 51, 30, 36, 46, 54, 29, 39,
    50, 44, 32, 47, 43, 48, 38, 55, 33, 52, 45, 41, 49, 35, 28, 31,
]


def _generate_keys(key_byte: list[int]) -> list[list[int]]:
    key = [0] * 56
    for i in range(7):
        for j in range(8):
            k = 7 - j
            key[i * 8 + j] = key_byte[8 * k + i]
    keys: list[list[int]] = []
    for i in range(16):
        for _ in range(_KEY_LOOP[i]):
            t_left = key[0]
            t_right = key[28]
            for k in range(27):
                key[k] = key[k + 1]
                key[28 + k] = key[29 + k]
            key[27] = t_left
            key[55] = t_right
        keys.append([key[idx] for idx in _KEY_PERMUTE])
    return keys


def _enc_block(data_byte: list[int], key_byte: list[int]) -> list[int]:
    keys = _generate_keys(key_byte)
    ip = _initial_permute(data_byte)
    left = ip[:32]
    right = ip[32:64]
    for i in range(16):
        temp_left = left[:]
        left = right[:]
        new_right = _xor(_p_permute(_s_box_permute(_xor(_expand_permute(right), keys[i]))), temp_left)
        right = new_right
    final = right + left
    return _final_permute(final)


def _dec_block(data_byte: list[int], key_byte: list[int]) -> list[int]:
    keys = _generate_keys(key_byte)
    ip = _initial_permute(data_byte)
    left = ip[:32]
    right = ip[32:64]
    for i in range(15, -1, -1):
        temp_left = left[:]
        left = right[:]
        new_right = _xor(_p_permute(_s_box_permute(_xor(_expand_permute(right), keys[i]))), temp_left)
        right = new_right
    final = right + left
    return _final_permute(final)


# ============== 对外接口 ==============

def str_enc(data: str, first_key: str | None, second_key: str | None = None, third_key: str | None = None) -> str:
    if not data:
        return ""

    keys: list[list[list[int]]] = []
    if first_key:
        keys.append(_get_key_bytes(first_key))
    if second_key:
        keys.append(_get_key_bytes(second_key))
    if third_key:
        keys.append(_get_key_bytes(third_key))

    parts: list[str] = []
    leng = len(data)
    iterator = leng // 4
    remainder = leng % 4
    blocks: list[str] = []
    if leng < 4:
        blocks.append(data)
    else:
        for i in range(iterator):
            blocks.append(data[i * 4 : i * 4 + 4])
        if remainder > 0:
            blocks.append(data[iterator * 4 :])

    for blk in blocks:
        bt = _str_to_bt(blk)
        for key_set in keys:
            for k in key_set:
                bt = _enc_block(bt, k)
        parts.append(_bt64_to_hex(bt))

    return "".join(parts)


def str_dec(data: str, first_key: str | None, second_key: str | None = None, third_key: str | None = None) -> str:
    keys: list[list[list[int]]] = []
    if first_key:
        keys.append(_get_key_bytes(first_key))
    if second_key:
        keys.append(_get_key_bytes(second_key))
    if third_key:
        keys.append(_get_key_bytes(third_key))

    out: list[str] = []
    leng = len(data) // 16
    for i in range(leng):
        chunk = data[i * 16 : i * 16 + 16]
        bt = _hex_to_bt64(chunk)
        for key_set in reversed(keys):
            for k in reversed(key_set):
                bt = _dec_block(bt, k)
        out.append(_byte_to_string(bt))
    return "".join(out)
