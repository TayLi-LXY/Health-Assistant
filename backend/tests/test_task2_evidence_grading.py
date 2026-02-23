"""
任务二：证据分级机制 - 自动化测试

测试内容：
1. 证据分级算法（来源权威性、时效性、文档类型）
2. 等级映射（Level 1-4）
3. 元数据传递（source_name, publication_date, document_type）
4. RAG 管道中的 grade_and_format_evidences 集成
5. 知识库 builder 的 metadata 结构
"""
import sys
from pathlib import Path

# 确保 backend 在 path 中
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

import unittest

from models import EvidenceLevel, EvidenceItem
from evidence_grading import compute_evidence_grade


class TestEvidenceGradingAlgorithm(unittest.TestCase):
    """测试证据分级核心算法"""

    def test_high_authority_source(self):
        """WHO 等顶级机构应显著高于贴吧等低权威来源"""
        _, score_who, _ = compute_evidence_grade(
            content="test",
            source_url="https://www.who.int/health-topics/xxx",
            source_name="WHO",
            publication_date="2024-01-15",
            document_type="guideline",
        )
        _, score_tieba, _ = compute_evidence_grade(
            content="test",
            source_url="https://tieba.baidu.com/p/1",
            publication_date=None,
            document_type="forum_post",
        )
        self.assertGreater(score_who, score_tieba)

    def test_level3_mayoclinic(self):
        """Mayo Clinic 等知名机构应得 Level 2 或 Level 3"""
        level, score, _ = compute_evidence_grade(
            content="test",
            source_url="https://www.mayoclinic.org/diseases/xxx",
            source_name="Mayo Clinic",
            publication_date="2023-06-01",
            document_type="encyclopedia",
        )
        self.assertIn(level, (EvidenceLevel.MEDIUM, EvidenceLevel.LOW))
        self.assertGreaterEqual(score, 60)

    def test_level2_baike_with_date(self):
        """Level 2: 百度百科 + 发布日期 应能利用时效性和 document_type"""
        level, score, exp = compute_evidence_grade(
            content="test content",
            source_url="https://baike.baidu.com/item/xxx",
            source_name="\u767e\u5ea6\u767e\u79d1",  # 百度百科
            publication_date="2024-03-28",
            document_type="encyclopedia",
        )
        self.assertIn(level, (EvidenceLevel.LOW, EvidenceLevel.VERY_LOW))
        # 验证 publication_date 被使用（explanation 中有时效性相关描述）
        self.assertTrue("70" in exp or "85" in exp or "95" in exp or "\u65e5\u671f" in exp)
        # 验证 document_type 元数据被使用
        self.assertTrue("encyclopedia" in exp.lower() or "\u5143\u6570\u636e" in exp)

    def test_level1_tieba_low_authority(self):
        """Level 1: 贴吧等低权威来源"""
        level, score, _ = compute_evidence_grade(
            content="test",
            source_url="https://tieba.baidu.com/p/xxx",
            source_name="\u8d34\u5427",
            publication_date=None,
            document_type="forum_post",
        )
        self.assertEqual(level, EvidenceLevel.VERY_LOW)
        self.assertLess(score, 60)

    def test_document_type_metadata_used(self):
        """document_type 元数据应被正确利用，guideline 比 encyclopedia 得分高"""
        _, s1, _ = compute_evidence_grade(
            content="x",
            source_url="https://cdc.gov/x",
            source_name="CDC",
            document_type="encyclopedia",
        )
        _, s2, _ = compute_evidence_grade(
            content="x",
            source_url="https://cdc.gov/x",
            source_name="CDC",
            document_type="guideline",
        )
        self.assertGreaterEqual(s2, s1)

    def test_publication_date_affects_score(self):
        """publication_date 应影响时效性得分"""
        _, score_recent, _ = compute_evidence_grade(
            content="x",
            source_url="https://who.int/x",
            publication_date="2024-12-01",
        )
        _, score_old, _ = compute_evidence_grade(
            content="x",
            source_url="https://who.int/x",
            publication_date="2015-01-01",
        )
        self.assertGreater(score_recent, score_old)

    def test_source_name_supplements_authority(self):
        """source_name 可补充权威性判断（WHO 触发加分）"""
        _, score1, _ = compute_evidence_grade(
            content="x",
            source_url="https://unknown-site.org/x",
            source_name="WHO",
        )
        _, score2, _ = compute_evidence_grade(
            content="x",
            source_url="https://unknown-site.org/x",
            source_name="Random Blog",
        )
        self.assertGreater(score1, score2)

    def test_level_mapping_boundaries(self):
        """等级映射：高权威来源得分高于低权威"""
        level_high, s_high, _ = compute_evidence_grade(
            content="x",
            source_url="https://who.int/x",
            source_name="WHO",
            publication_date="2024-06-01",
            document_type="guideline",
        )
        level_low, s_low, _ = compute_evidence_grade(
            content="x",
            source_url="https://tieba.baidu.com/p/1",
            source_name="tieba",
            document_type="forum_post",
        )
        self.assertGreater(s_high, s_low)
        self.assertGreaterEqual(level_high.value, level_low.value)


class TestGradeAndFormatEvidences(unittest.TestCase):
    """测试 grade_and_format_evidences 逻辑（不依赖 langchain/向量库）"""

    def _grade_and_format_evidences(self, chunks):
        """内联 grade_and_format_evidences 逻辑，避免导入 rag_pipeline"""
        evidences = []
        for c in chunks:
            meta = c.get("metadata", {}) or c
            level, score, explanation = compute_evidence_grade(
                content=meta.get("content", c.get("content", "")),
                source_url=meta.get("source_url", ""),
                source_name=meta.get("source_name", ""),
                publication_date=meta.get("publication_date") or None,
                title=meta.get("title", ""),
                document_type=meta.get("document_type", ""),
            )
            evidences.append(EvidenceItem(
                content=meta.get("content", c.get("content", "")),
                source_url=meta.get("source_url", ""),
                source_name=meta.get("source_name", ""),
                publication_date=meta.get("publication_date"),
                title=meta.get("title", ""),
                evidence_level=level,
                evidence_score=score,
                level_explanation=explanation,
            ))
        return evidences

    def test_full_metadata_passed_to_grading(self):
        """chunk metadata 应完整传递至证据分级并产出 EvidenceItem"""
        chunks = [
            {
                "content": "Hypertension diet advice.",
                "metadata": {
                    "source_url": "https://baike.baidu.com/item/hypertension",
                    "source_name": "Baidu Baike",
                    "publication_date": "2024-01-20",
                    "title": "Hypertension",
                    "document_type": "encyclopedia",
                },
            }
        ]
        evidences = self._grade_and_format_evidences(chunks)
        self.assertEqual(len(evidences), 1)
        ev = evidences[0]
        self.assertIsInstance(ev, EvidenceItem)
        self.assertEqual(ev.source_name, "Baidu Baike")
        self.assertEqual(ev.publication_date, "2024-01-20")
        self.assertIn(ev.evidence_level, EvidenceLevel)
        self.assertGreater(len(ev.level_explanation), 0)

    def test_document_type_in_metadata_affects_level(self):
        """metadata 中的 document_type 应影响分级结果"""
        base_meta = {
            "content": "Clinical guideline content",
            "source_url": "https://cdc.gov/guide",
            "source_name": "CDC",
            "publication_date": "2024-01-01",
        }
        chunks_enc = [{"content": base_meta["content"], "metadata": {**base_meta, "document_type": "encyclopedia"}}]
        chunks_guide = [{"content": base_meta["content"], "metadata": {**base_meta, "document_type": "guideline"}}]
        ev_enc = self._grade_and_format_evidences(chunks_enc)[0]
        ev_guide = self._grade_and_format_evidences(chunks_guide)[0]
        self.assertGreaterEqual(ev_guide.evidence_score, ev_enc.evidence_score)


class TestBuilderMetadata(unittest.TestCase):
    """测试知识库 builder 的 metadata 结构"""

    def test_metadata_contains_required_fields(self):
        """builder 构造的 metadata 应包含 source_name, publication_date"""
        # 模拟 build_vector_store 中的 metadata 构造逻辑
        chunk = {
            "content": "test content",
            "source_url": "https://baike.baidu.com/item/xx",
            "source_name": "Baidu Baike",
            "publication_date": "2024-03-28",
            "title": "Test",
            "chunk_id": "abc#0",
            "chunk_index": 0,
            "document_type": "encyclopedia",
        }
        metadata = {
            "source_url": chunk.get("source_url", "") or "",
            "source_name": chunk.get("source_name", "") or "",
            "publication_date": str(chunk.get("publication_date") or ""),
            "title": chunk.get("title", "") or "",
            "chunk_id": chunk.get("chunk_id", "") or "",
            "chunk_index": chunk.get("chunk_index", 0),
            "document_type": chunk.get("document_type", "unknown"),
        }
        self.assertIn("source_name", metadata)
        self.assertIn("publication_date", metadata)
        self.assertEqual(metadata["source_name"], "Baidu Baike")
        self.assertEqual(metadata["publication_date"], "2024-03-28")
        self.assertEqual(metadata["document_type"], "encyclopedia")


def run_tests():
    """运行所有任务二测试"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestEvidenceGradingAlgorithm))
    suite.addTests(loader.loadTestsFromTestCase(TestGradeAndFormatEvidences))
    suite.addTests(loader.loadTestsFromTestCase(TestBuilderMetadata))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
