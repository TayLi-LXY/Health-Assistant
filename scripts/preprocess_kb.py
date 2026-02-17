"""清洗并切分知识库，生成 chunks 文件（stdlib-only 版本）。

为什么不用 LangChain？
- 方便在未安装依赖时也能跑通“任务一：清洗+切分”，生成可检查的 chunks 文件。

输入：backend/data/crawled_knowledge_base.json
输出：backend/data/processed_kb_chunks.json
用法（在仓库根目录）：python scripts/preprocess_kb.py
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


def _remove_control_chars(text: str) -> str:
    return "".join(c for c in text if unicodedata.category(c)[0] != "C" or c in "\n\t")


_REF_MARK_PAT = re.compile(r"[\[\［]\s*\d+(?:\s*-\s*\d+)?\s*[\]\］]?")
_BAIKE_NOISE_PATS = [
    re.compile(r"\b播报\s*编辑\b"),
    re.compile(r"\b参考来源\b[:：]?"),
]


def clean_kb_content(text: str) -> str:
    if not text or not str(text).strip():
        return ""
    t = html.unescape(str(text))
    t = _remove_control_chars(t)
    t = _REF_MARK_PAT.sub("", t)
    for pat in _BAIKE_NOISE_PATS:
        t = pat.sub("", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _split_by_separators(text: str, seps: List[str]) -> List[str]:
    """递归按分隔符切分（从强到弱），避免过大块。"""
    parts = [text]
    for sep in seps:
        next_parts: List[str] = []
        for p in parts:
            if not p:
                continue
            if sep == "":
                next_parts.append(p)
                continue
            if sep in p:
                next_parts.extend([x for x in p.split(sep) if x])
            else:
                next_parts.append(p)
        parts = next_parts
    return parts


def chunk_text(text: str, chunk_size: int, overlap: int, seps: List[str]) -> List[str]:
    """把长文本切成近似 chunk_size 的块，并做 overlap。"""
    text = text.strip()
    if not text:
        return []

    # 先粗切成句/段
    atoms = _split_by_separators(text, seps)
    atoms = [a.strip() for a in atoms if a and a.strip()]

    # 再拼接成块
    chunks: List[str] = []
    buf: List[str] = []
    buf_len = 0

    def flush() -> None:
        nonlocal buf, buf_len
        if not buf:
            return
        chunks.append(" ".join(buf).strip())
        buf = []
        buf_len = 0

    for atom in atoms:
        if not atom:
            continue
        if buf_len + len(atom) + (1 if buf else 0) <= chunk_size:
            buf.append(atom)
            buf_len += len(atom) + (1 if buf_len else 0)
            continue

        # 当前 atom 放不下，先 flush，再决定 atom 本身怎么处理
        flush()

        if len(atom) <= chunk_size:
            buf.append(atom)
            buf_len = len(atom)
        else:
            # 超长 atom，硬切
            start = 0
            while start < len(atom):
                end = min(start + chunk_size, len(atom))
                chunks.append(atom[start:end].strip())
                start = end

    flush()

    if overlap <= 0 or len(chunks) <= 1:
        return [c for c in chunks if c]

    # 应用 overlap：将上一块尾部 overlap 字符拼到下一块前面
    out: List[str] = [chunks[0]]
    for i in range(1, len(chunks)):
        prev = out[-1]
        prefix = prev[-overlap:] if len(prev) > overlap else prev
        out.append((prefix + " " + chunks[i]).strip())
    return [c for c in out if c]


def load_json_list(path: Path) -> List[Dict[str, Any]]:
    if not path.exists() or path.stat().st_size <= 0:
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def main() -> int:
    repo_root = Path(__file__).parent.parent
    kb_path = repo_root / "backend" / "data" / "crawled_knowledge_base.json"
    docs = load_json_list(kb_path)
    if not docs:
        print(f"未加载到任何 KB 文档：{kb_path} 为空或不存在。")
        return 1

    # 与 builder.py 保持一致（字符级 chunk_size/overlap）
    chunk_size = 500
    overlap = 50
    seps = ["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""]

    chunks_out: List[Dict[str, Any]] = []
    skipped = 0
    for doc in docs:
        content = clean_kb_content(doc.get("content", ""))
        if not content:
            skipped += 1
            continue
        source_url = str(doc.get("source_url", "") or "")
        title = str(doc.get("title", "") or "")
        base_key = f"{source_url}||{title}".encode("utf-8", errors="ignore")
        base_hash = hashlib.sha1(base_key).hexdigest()

        pieces = chunk_text(content, chunk_size=chunk_size, overlap=overlap, seps=seps)
        for idx, p in enumerate(pieces):
            if len(p.strip()) < 20:
                continue
            item = {k: v for k, v in doc.items() if k != "content"}
            item.update(
                {
                    "chunk_index": idx,
                    "chunk_id": f"{base_hash}#{idx}",
                    "content": p.strip(),
                }
            )
            chunks_out.append(item)

    out_path = repo_root / "backend" / "data" / "processed_kb_chunks.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(chunks_out, f, ensure_ascii=False, indent=2)

    total_chars = sum(len(c.get("content", "") or "") for c in chunks_out)
    avg_len = (total_chars / len(chunks_out)) if chunks_out else 0.0
    print(f"原始文档数: {len(docs)}")
    print(f"空 content 跳过: {skipped}")
    print(f"生成 chunks: {len(chunks_out)}")
    print(f"平均 chunk 字符数: {avg_len:.1f}")
    print(f"输出文件: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

