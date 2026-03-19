"""
记忆系统

两层存储:
    - MEMORY.md = 长期事实 (手动维护)
    - daily/{date}.jsonl = 每日日志 (通过 agent 工具自动写入)

搜索算法:
    - TF-IDF + 余弦相似度 (关键词搜索)
    - 基于哈希的向量模拟 (向量搜索)
    - 时间衰减 (越近的记忆得分越高)
    - MMR 重排序 (保证多样性)
"""

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from coder.settings import settings


class MemoryStore:
    """
    记忆存储和搜索类

    实现双层存储和混合搜索管道。

    用法:
        store = MemoryStore()

        # 写入记忆
        store.write_memory("User prefers Python", category="preference")

        # 搜索记忆
        results = store.search_memory("python", top_k=5)

        # 混合搜索 (TF-IDF + 向量 + MMR)
        results = store.hybrid_search("python programming", top_k=5)
    """

    def __init__(self, workspace_dir: Optional[Path] = None) -> None:
        """
        初始化记忆存储

        Args:
            workspace_dir: 工作区目录, 默认从配置读取
        """
        if workspace_dir is None:
            self.workspace_dir = Path(settings.workspace_dir)
        else:
            self.workspace_dir = workspace_dir

        self.memory_dir = self.workspace_dir / "memory" / "daily"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        # 从配置读取参数
        self.decay_rate = settings.memory_decay_rate
        self.mmr_lambda = settings.mmr_lambda

    def write_memory(self, content: str, category: str = "general") -> str:
        """
        写入记忆到每日 JSONL 文件

        Args:
            content: 记忆内容
            category: 记忆分类

        Returns:
            操作结果信息
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self.memory_dir / f"{today}.jsonl"

        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "category": category,
            "content": content,
        }

        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            return f"Memory saved to {today}.jsonl ({category})"
        except Exception as exc:
            return f"Error writing memory: {exc}"

    def load_evergreen(self) -> str:
        """
        加载长期记忆 (MEMORY.md)

        Returns:
            长期记忆内容
        """
        path = self.workspace_dir / "MEMORY.md"
        if not path.is_file():
            return ""
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    def _load_all_chunks(self) -> List[Dict[str, str]]:
        """
        加载所有记忆并拆分为块

        Returns:
            记忆块列表, 每个块包含 path 和 text
        """
        chunks: List[Dict[str, str]] = []

        # 按段落拆分长期记忆
        evergreen = self.load_evergreen()
        if evergreen:
            for para in evergreen.split("\n\n"):
                para = para.strip()
                if para:
                    chunks.append({"path": "MEMORY.md", "text": para})

        # 每日记忆: 每条 JSONL 记录作为一个块
        if self.memory_dir.is_dir():
            for jf in sorted(self.memory_dir.glob("*.jsonl")):
                try:
                    for line in jf.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        entry = json.loads(line)
                        text = entry.get("content", "")
                        if text:
                            cat = entry.get("category", "")
                            label = f"{jf.name} [{cat}]" if cat else jf.name
                            chunks.append({"path": label, "text": text})
                except Exception:
                    continue

        return chunks

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """
        分词

        支持小写英文 + 单个 CJK 字符, 过滤短 token。

        Args:
            text: 要分词的文本

        Returns:
            token 列表
        """
        tokens = re.findall(r"[a-z0-9\u4e00-\u9fff]+", text.lower())
        return [t for t in tokens if len(t) > 1 or "\u4e00" <= t <= "\u9fff"]

    def search_memory(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        TF-IDF + 余弦相似度搜索

        纯 Python 实现, 不需要外部向量数据库。

        Args:
            query: 搜索查询
            top_k: 返回结果数量, 默认从配置读取

        Returns:
            搜索结果列表, 每个结果包含 path, score, snippet
        """
        if top_k is None:
            top_k = settings.memory_top_k

        chunks = self._load_all_chunks()
        if not chunks:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        chunk_tokens = [self._tokenize(c["text"]) for c in chunks]

        # 文档频率
        df: Dict[str, int] = {}
        for tokens in chunk_tokens:
            for t in set(tokens):
                df[t] = df.get(t, 0) + 1
        n = len(chunks)

        def tfidf(tokens: List[str]) -> Dict[str, float]:
            tf: Dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            return {t: c * (math.log((n + 1) / (df.get(t, 0) + 1)) + 1) for t, c in tf.items()}

        def cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
            common = set(a) & set(b)
            if not common:
                return 0.0
            dot = sum(a[k] * b[k] for k in common)
            na = math.sqrt(sum(v * v for v in a.values()))
            nb = math.sqrt(sum(v * v for v in b.values()))
            return dot / (na * nb) if na and nb else 0.0

        qvec = tfidf(query_tokens)
        scored: List[Dict[str, Any]] = []

        for i, tokens in enumerate(chunk_tokens):
            if not tokens:
                continue
            score = cosine(qvec, tfidf(tokens))
            if score > 0.0:
                snippet = chunks[i]["text"]
                if len(snippet) > 200:
                    snippet = snippet[:200] + "..."
                scored.append(
                    {
                        "path": chunks[i]["path"],
                        "score": round(score, 4),
                        "snippet": snippet,
                    }
                )

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    # --- Hybrid Memory Search Enhancement ---

    @staticmethod
    def _hash_vector(text: str, dim: int = 64) -> List[float]:
        """
        模拟向量嵌入

        使用基于哈希的随机投影, 不需要外部 API。
        展示双通道搜索的模式。

        Args:
            text: 要编码的文本
            dim: 向量维度

        Returns:
            模拟的向量嵌入
        """
        tokens = MemoryStore._tokenize(text)
        vec = [0.0] * dim
        for token in tokens:
            h = hash(token)
            for i in range(dim):
                bit = (h >> (i % 62)) & 1
                vec[i] += 1.0 if bit else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    @staticmethod
    def _vector_cosine(a: List[float], b: List[float]) -> float:
        """
        计算两个向量的余弦相似度

        Args:
            a: 向量 a
            b: 向量 b

        Returns:
            余弦相似度
        """
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        return dot / (na * nb) if na and nb else 0.0

    @staticmethod
    def _jaccard_similarity(tokens_a: List[str], tokens_b: List[str]) -> float:
        """
        计算 Jaccard 相似度

        Args:
            tokens_a: token 集合 a
            tokens_b: token 集合 b

        Returns:
            Jaccard 相似度
        """
        set_a, set_b = set(tokens_a), set(tokens_b)
        inter = len(set_a & set_b)
        union = len(set_a | set_b)
        return inter / union if union else 0.0

    def _vector_search(
        self, query: str, chunks: List[Dict[str, str]], top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        向量搜索

        Args:
            query: 搜索查询
            chunks: 记忆块列表
            top_k: 返回结果数量

        Returns:
            搜索结果列表
        """
        q_vec = self._hash_vector(query)
        scored = []
        for chunk in chunks:
            c_vec = self._hash_vector(chunk["text"])
            score = self._vector_cosine(q_vec, c_vec)
            if score > 0.0:
                scored.append({"chunk": chunk, "score": score})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def _keyword_search(
        self, query: str, chunks: List[Dict[str, str]], top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        关键词搜索 (复用 TF-IDF)

        Args:
            query: 搜索查询
            chunks: 记忆块列表
            top_k: 返回结果数量

        Returns:
            搜索结果列表
        """
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        chunk_tokens = [self._tokenize(c["text"]) for c in chunks]
        n = len(chunks)
        df: Dict[str, int] = {}
        for tokens in chunk_tokens:
            for t in set(tokens):
                df[t] = df.get(t, 0) + 1

        def tfidf(tokens: List[str]) -> Dict[str, float]:
            tf: Dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            return {t: c * (math.log((n + 1) / (df.get(t, 0) + 1)) + 1) for t, c in tf.items()}

        def cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
            common = set(a) & set(b)
            if not common:
                return 0.0
            dot = sum(a[k] * b[k] for k in common)
            na = math.sqrt(sum(v * v for v in a.values()))
            nb = math.sqrt(sum(v * v for v in b.values()))
            return dot / (na * nb) if na and nb else 0.0

        qvec = tfidf(query_tokens)
        scored = []
        for i, tokens in enumerate(chunk_tokens):
            if not tokens:
                continue
            score = cosine(qvec, tfidf(tokens))
            if score > 0.0:
                scored.append({"chunk": chunks[i], "score": score})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    @staticmethod
    def _merge_hybrid_results(
        vector_results: List[Dict[str, Any]],
        keyword_results: List[Dict[str, Any]],
        vector_weight: float = 0.7,
        text_weight: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """
        合并向量和关键词搜索结果

        Args:
            vector_results: 向量搜索结果
            keyword_results: 关键词搜索结果
            vector_weight: 向量搜索权重
            text_weight: 关键词搜索权重

        Returns:
            合并后的结果列表
        """
        merged: Dict[str, Dict[str, Any]] = {}
        for r in vector_results:
            key = r["chunk"]["text"][:100]
            merged[key] = {"chunk": r["chunk"], "score": r["score"] * vector_weight}
        for r in keyword_results:
            key = r["chunk"]["text"][:100]
            if key in merged:
                merged[key]["score"] += r["score"] * text_weight
            else:
                merged[key] = {"chunk": r["chunk"], "score": r["score"] * text_weight}
        result = list(merged.values())
        result.sort(key=lambda x: x["score"], reverse=True)
        return result

    @staticmethod
    def _temporal_decay(
        results: List[Dict[str, Any]], decay_rate: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        应用时间衰减

        越近的记忆得分越高。

        Args:
            results: 搜索结果列表
            decay_rate: 衰减率, 默认从配置读取

        Returns:
            应用衰减后的结果列表
        """
        if decay_rate is None:
            decay_rate = settings.memory_decay_rate

        now = datetime.now(timezone.utc)
        for r in results:
            path = r["chunk"].get("path", "")
            age_days = 0.0
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", path)
            if date_match:
                try:
                    chunk_date = datetime.strptime(date_match.group(1), "%Y-%m-%d").replace(
                        tzinfo=timezone.utc
                    )
                    age_days = (now - chunk_date).total_seconds() / 86400.0
                except ValueError:
                    pass
            r["score"] *= math.exp(-decay_rate * age_days)
        return results

    @staticmethod
    def _mmr_rerank(
        results: List[Dict[str, Any]], lambda_param: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        MMR 重排序

        Maximal Marginal Relevance, 保证结果多样性。
        MMR = lambda * relevance - (1-lambda) * max_similarity_to_selected

        Args:
            results: 搜索结果列表
            lambda_param: MMR lambda 参数, 默认从配置读取

        Returns:
            重排序后的结果列表
        """
        if lambda_param is None:
            lambda_param = settings.mmr_lambda

        if len(results) <= 1:
            return results

        tokenized = [MemoryStore._tokenize(r["chunk"]["text"]) for r in results]
        selected: List[int] = []
        remaining = list(range(len(results)))
        reranked: List[Dict[str, Any]] = []

        while remaining:
            best_idx = -1
            best_mmr = float("-inf")
            for idx in remaining:
                relevance = results[idx]["score"]
                max_sim = 0.0
                for sel_idx in selected:
                    sim = MemoryStore._jaccard_similarity(tokenized[idx], tokenized[sel_idx])
                    if sim > max_sim:
                        max_sim = sim
                mmr = lambda_param * relevance - (1 - lambda_param) * max_sim
                if mmr > best_mmr:
                    best_mmr = mmr
                    best_idx = idx
            selected.append(best_idx)
            remaining.remove(best_idx)
            reranked.append(results[best_idx])

        return reranked

    def hybrid_search(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        完整混合搜索管道

        关键词 -> 向量 -> 合并 -> 衰减 -> MMR -> top_k

        Args:
            query: 搜索查询
            top_k: 返回结果数量, 默认从配置读取

        Returns:
            搜索结果列表
        """
        if top_k is None:
            top_k = settings.memory_top_k

        chunks = self._load_all_chunks()
        if not chunks:
            return []

        keyword_results = self._keyword_search(query, chunks, top_k=10)
        vector_results = self._vector_search(query, chunks, top_k=10)
        merged = self._merge_hybrid_results(vector_results, keyword_results)
        decayed = self._temporal_decay(merged)
        reranked = self._mmr_rerank(decayed)

        result = []
        for r in reranked[:top_k]:
            snippet = r["chunk"]["text"]
            if len(snippet) > 200:
                snippet = snippet[:200] + "..."
            result.append(
                {
                    "path": r["chunk"]["path"],
                    "score": round(r["score"], 4),
                    "snippet": snippet,
                }
            )
        return result

    def get_stats(self) -> Dict[str, Any]:
        """
        获取记忆存储统计信息

        Returns:
            统计信息字典
        """
        evergreen = self.load_evergreen()
        daily_files = (
            list(self.memory_dir.glob("*.jsonl")) if self.memory_dir.is_dir() else []
        )
        total_entries = 0
        for f in daily_files:
            try:
                total_entries += sum(
                    1 for line in f.read_text(encoding="utf-8").splitlines() if line.strip()
                )
            except Exception:
                pass
        return {
            "evergreen_chars": len(evergreen),
            "daily_files": len(daily_files),
            "daily_entries": total_entries,
        }


__all__ = [
    "MemoryStore",
]
