"""Tests for app/services/query_rewriter.py, using fakes (no API calls)."""

from types import SimpleNamespace

from app.services.query_rewriter import QueryRewriter, QueryRewritingRetriever, SearchQuery
from app.services.retriever import SearchResult
from app.services.section_splitter import Section


def make_section(number: str) -> Section:
    return Section("example_act", "The Example Act", number, f"Heading {number}", "in_force",
                   None, 1, 1, "text", f"Section {number}, The Example Act")


class FakeResponses:
    def __init__(self, rewrite: str | None = None, error: Exception | None = None):
        self.rewrite, self.error, self.request = rewrite, error, None

    def parse(self, **kwargs):
        self.request = kwargs
        if self.error:
            raise self.error
        return SimpleNamespace(output_parsed=SearchQuery(legal_query=self.rewrite))


def fake_client(rewrite=None, error=None):
    return SimpleNamespace(responses=FakeResponses(rewrite, error))


class FakeRetriever:
    """Returns section "1" for the original question and section "2" for anything else."""

    def __init__(self):
        self.queries = []

    def search(self, question, top_k=5):
        self.queries.append(question)
        number = "1" if question == "original question" else "2"
        return [SearchResult(section=make_section(number), score=1.0)]


def test_rewriter_sends_question_and_returns_rewrite():
    client = fake_client(rewrite="assignment of copyright under the Copyright Act, 1957")

    result = QueryRewriter(client, model="small-model").rewrite("how do I transfer my copyright")

    assert result == "assignment of copyright under the Copyright Act, 1957"
    assert client.responses.request["model"] == "small-model"
    assert client.responses.request["input"] == "how do I transfer my copyright"
    assert client.responses.request["store"] is False


def test_rewriter_returns_none_when_the_api_fails():
    client = fake_client(error=RuntimeError("network down"))

    assert QueryRewriter(client, model="m").rewrite("question") is None


def test_retriever_searches_both_queries_and_fuses_results():
    base = FakeRetriever()
    retriever = QueryRewritingRetriever(base, QueryRewriter(fake_client(rewrite="legal words"), "m"))

    results = retriever.search("original question", top_k=5)

    assert base.queries == ["original question", "legal words"]
    assert sorted(r.section.section for r in results) == ["1", "2"]


def test_retriever_falls_back_to_original_question_if_rewrite_fails():
    base = FakeRetriever()
    retriever = QueryRewritingRetriever(base, QueryRewriter(fake_client(error=RuntimeError()), "m"))

    results = retriever.search("original question", top_k=5)

    assert base.queries == ["original question"]
    assert [r.section.section for r in results] == ["1"]
