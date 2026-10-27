"""Run an opt-in, real-gateway comparison inside the configured app container.

This script reads the existing class material and never modifies stored indexes.
Invoke from PowerShell: Get-Content -Raw tests/manual_qa_comparison.py |
    docker compose exec -T app python -
"""

import json
import os

import httpx

import app.retrieval as retrieval
from app.retrieval import InMemoryChunkStore, InMemoryVectorStore, OpenAIChatClient, OpenAIEmbedder, RetrievalService


def run():
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=60) as api:
        login = api.post("/api/auth/login", json={"username": "teacher_a", "password": os.environ["SEED_PASSWORD"]})
        login.raise_for_status()
        api.headers["Authorization"] = "Bearer " + login.json()["access_token"]
        class_id = api.get("/api/me/classes").json()["classes"][0]["id"]
        materials = api.get(f"/api/classes/{class_id}/materials").json()["materials"]
        material = next(item for item in materials if "守则" in item["filename"])
        source = api.get(f"/api/materials/{material['material_id']}").json()
        baseline = RetrievalService(
            InMemoryChunkStore(), InMemoryVectorStore(),
            OpenAIEmbedder(os.environ["EMBEDDING_API_KEY"], os.environ["EMBEDDING_MODEL"], os.environ["EMBEDDING_BASE_URL"]),
        )
        previous_size, previous_overlap = retrieval.DEFAULT_CHUNK_SIZE, retrieval.DEFAULT_CHUNK_OVERLAP
        try:
            retrieval.DEFAULT_CHUNK_SIZE, retrieval.DEFAULT_CHUNK_OVERLAP = 800, 100
            baseline.index_material({
                "id": source["id"], "class_id": class_id, "filename": source["filename"],
                "content_text": source["content_text"],
            }, "window")
        finally:
            retrieval.DEFAULT_CHUNK_SIZE, retrieval.DEFAULT_CHUNK_OVERLAP = previous_size, previous_overlap
        # Retain the previous whole-question hybrid lookup for the baseline.
        baseline._select_ai_evidence = lambda target_class, question: baseline.search(target_class, question, "hybrid")[:5]
        chat = OpenAIChatClient(os.environ["EMBEDDING_API_KEY"], os.environ["CHAT_MODEL"], os.environ["EMBEDDING_BASE_URL"])
        cases = [
            ("考试和作业中应该如何保持诚实守信？", ["不抄袭", "不作弊"]),
            ("遇到校园欺凌时应该怎么办？", ["老师", "求助"]),
            ("使用网络和电子设备应该注意什么？", ["不良信息", "网络游戏"]),
        ]
        for question, expected in cases:
            old = baseline.answer_ai_question(class_id, question, chat)
            response = api.post(f"/api/classes/{class_id}/ai-questions", json={"question": question})
            response.raise_for_status()
            current = response.json()
            checks = {}
            for label, answer in (("old_window", old), ("semantic", current)):
                checks[label] = {
                    "answer": answer["answer"],
                    "expected_facts_present": all(word in answer["answer"] for word in expected),
                    "citation_ranges": [item["char_range"] for item in answer["citations"]],
                }
            checks["current_citations_openable"] = all(api.get(item["material_url"]).status_code == 200 for item in current["citations"])
            print(json.dumps({"question": question, **checks}, ensure_ascii=False), flush=True)
        unrelated = api.post(f"/api/classes/{class_id}/ai-questions", json={"question": "量子引力波星际航行如何设计？"})
        assert unrelated.status_code == 200
        assert unrelated.json() == {"answer": "资料中未找到相关内容", "citations": []}
        api.post("/api/auth/logout")
        student_login = api.post("/api/auth/login", json={"username": "student_b", "password": os.environ["SEED_PASSWORD"]})
        student_login.raise_for_status()
        api.headers["Authorization"] = "Bearer " + student_login.json()["access_token"]
        denied = api.post(f"/api/classes/{class_id}/ai-questions", json={"question": "考试和作业中应该如何保持诚实守信？"})
        assert denied.status_code == 403
        print(json.dumps({"unrelated": unrelated.json(), "cross_class_status": denied.status_code}, ensure_ascii=False), flush=True)
        api.post("/api/auth/logout")


if __name__ == "__main__":
    run()
