import re


def recursive_chunk(text: str, chunk_size: int = 150, overlap: int = 15) -> list[str]:
    """递归分块：优先按段落、句子、逗号切分，最后才按字符硬切"""
    if len(text) <= chunk_size:
        return [text]

    separators = ["\n\n", "\n", "。", "，", " "]

    for sep in separators:
        if sep in text:
            parts = text.split(sep)
            chunks = []
            current = ""

            for part in parts:
                if not part.strip():
                    continue
                test = current + sep + part if current else part
                if len(test) <= chunk_size:
                    current = test
                else:
                    if current:
                        chunks.append(current)
                    if len(part) > chunk_size:
                        chunks.extend(recursive_chunk(part, chunk_size, overlap))
                        current = ""
                    else:
                        current = part

            if current:
                chunks.append(current)

            if overlap > 0 and len(chunks) > 1:
                overlapped = []
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        overlapped.append(chunk)
                    else:
                        prev_tail = chunks[i - 1][-overlap:]
                        overlapped.append(prev_tail + chunk)
                return overlapped
            return chunks

    # 所有分隔符都不存在时，按 chunk_size 硬切
    chunks = []
    for i in range(0, len(text), chunk_size - overlap):
        chunks.append(text[i:i + chunk_size])
    return chunks


def extract_keywords(text: str, max_keywords: int = 5) -> list[str]:
    """简单关键词提取：去停用词、取高频词"""
    stopwords = {
        "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好", "自己", "这", "请", "通知", "关于"
    }

    tokens = re.findall(r"[一-龥]+", text)
    word_freq = {}
    for token in tokens:
        if len(token) >= 2 and token not in stopwords:
            word_freq[token] = word_freq.get(token, 0) + 1

    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    return [word for word, _ in sorted_words[:max_keywords]]
