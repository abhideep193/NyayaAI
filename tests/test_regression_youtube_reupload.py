"""Regression: "my YouTube video was re-uploaded and monetised" (owner's test, 2026-11-07).

Diagnosis: the Copyright Act sections are all in the corpus, and the rewritten query ranks
s.55 (civil remedies: injunction, damages, accounts) #1. But s.55 is NOT in the original
question's top 30, so after fusing the two rankings (RRF) it gets only one vote and falls to
#17, outside the 15 sections the answer model sees. The model then (correctly, given its
sources) says it cannot explain the civil remedies.

This test uses the real IPR search index and a FIXED rewrite logged from a live run, so it
needs no API call and is deterministic. It is expected to FAIL until the fusion is fixed;
strict=True makes pytest report it when it starts passing, so the marker gets removed then.
"""

import pytest

QUESTION = (
    "Someone uploaded my entire YouTube video on their channel without my permission. "
    "They have also monetised it. What legal action can I take in India, and can I get the video removed?"
)
# Logged from gpt-6-luna on 2026-11-07 (run 3 of the diagnosis), with areas == ["ipr"].
LOGGED_REWRITE = (
    "Under the Copyright Act, 1957, what remedies are available for infringement where a person has uploaded "
    "and monetised a video without the copyright owner's permission, including whether the infringing copy may "
    "be removed and what civil or criminal action may be taken?"
)
# s.51 infringement, s.55 civil remedies (injunction, damages, accounts), s.63 offence.
MUST_REACH_MODEL = ["copyright_act_1957:51", "copyright_act_1957:55", "copyright_act_1957:63"]
CONTEXT_SECTIONS = 15  # app/config.py ANSWER_CONTEXT_SECTIONS default


class LoggedRewriter:
    def route(self, question):
        return LOGGED_REWRITE, ["ipr"]


@pytest.fixture(scope="module")
def ipr_retriever():
    pytest.importorskip("sentence_transformers")
    from scripts.search import build_domain_retrievers

    try:
        return build_domain_retrievers()["ipr"]
    except Exception as error:  # no processed data / embedding model on this machine
        pytest.skip(f"real search index not available: {error}")


@pytest.mark.xfail(strict=True, reason="s.55 ranks #1 for the rewrite but is lost in RRF fusion (diagnosis 2026-11-07)")
def test_copyright_remedy_sections_reach_the_answer_model(ipr_retriever):
    from app.services.citation_verifier import section_id
    from app.services.query_rewriter import DomainRoutedRetriever

    retriever = DomainRoutedRetriever({"ipr": ipr_retriever}, LoggedRewriter())
    given_to_model = [section_id(r.section) for r in retriever.search(QUESTION, top_k=CONTEXT_SECTIONS)]

    missing = [s for s in MUST_REACH_MODEL if s not in given_to_model]
    assert not missing, f"not in the model's {CONTEXT_SECTIONS} sections: {missing}"
