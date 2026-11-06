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

    result = QueryRewriter(client, model="small-model", prompt="REWRITE RULES").rewrite("how do I transfer my copyright")

    assert result == "assignment of copyright under the Copyright Act, 1957"
    assert client.responses.request["model"] == "small-model"
    assert client.responses.request["input"] == "how do I transfer my copyright"
    assert client.responses.request["store"] is False


def test_rewriter_returns_none_when_the_api_fails():
    client = fake_client(error=RuntimeError("network down"))

    assert QueryRewriter(client, model="m", prompt="r").rewrite("question") is None


def test_retriever_searches_both_queries_and_fuses_results():
    base = FakeRetriever()
    retriever = QueryRewritingRetriever(base, QueryRewriter(fake_client(rewrite="legal words"), "m", "r"))

    results = retriever.search("original question", top_k=5)

    assert base.queries == ["original question", "legal words"]
    assert sorted(r.section.section for r in results) == ["1", "2"]


def test_retriever_falls_back_to_original_question_if_rewrite_fails():
    base = FakeRetriever()
    retriever = QueryRewritingRetriever(base, QueryRewriter(fake_client(error=RuntimeError()), "m", "r"))

    results = retriever.search("original question", top_k=5)

    assert base.queries == ["original question"]
    assert [r.section.section for r in results] == ["1"]


# --- domain routing ----------------------------------------------------------------

from app.services.query_rewriter import DomainRoutedRetriever, RoutedSearchQuery, RoutingQueryRewriter  # noqa: E402


class AreaRetriever:
    """Fake index for one area of law: always returns that area's section."""

    def __init__(self, area):
        self.area, self.queries = area, []

    def search(self, question, top_k=5):
        self.queries.append(question)
        return [SearchResult(section=make_section(self.area), score=1.0)]


def routing_client(areas=None, error=None):
    def parse(**kwargs):
        if error:
            raise error
        return SimpleNamespace(output_parsed=RoutedSearchQuery(legal_query="legal words", areas=areas))
    return SimpleNamespace(responses=SimpleNamespace(parse=parse))


def routed(areas=None, error=None):
    indexes = {"ipr": AreaRetriever("ipr"), "criminal": AreaRetriever("criminal")}
    retriever = DomainRoutedRetriever(indexes, RoutingQueryRewriter(routing_client(areas, error), "m", "r"))
    found = [r.section.section for r in retriever.search("original question", top_k=5)]
    return found, indexes


def test_routing_searches_only_the_chosen_area_with_both_queries():
    found, indexes = routed(areas=["ipr"])
    assert found == ["ipr"]
    assert indexes["ipr"].queries == ["original question", "legal words"]
    assert indexes["criminal"].queries == []  # criminal Acts never searched for an IPR question


def test_routing_to_two_areas_merges_both():
    found, _ = routed(areas=["criminal", "ipr"])
    assert sorted(found) == ["criminal", "ipr"]


def test_unknown_or_no_area_searches_everything():
    found, _ = routed(areas=["property"])
    assert sorted(found) == ["criminal", "ipr"]


def test_failed_rewrite_searches_every_area_with_the_original_question():
    found, indexes = routed(error=RuntimeError("API down"))
    assert sorted(found) == ["criminal", "ipr"]
    assert indexes["ipr"].queries == ["original question"]
