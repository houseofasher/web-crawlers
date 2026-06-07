from omnispider.topic.profile import TopicProfile
from omnispider.topic.scorer import score_link, score_page, score_text


def test_topic_profile_parses_terms():
    profile = TopicProfile.parse("Asher Shepherd Newton Cape Coral Florida")
    assert "asher" in profile.terms
    assert "newton" in profile.terms
    assert "florida" in profile.terms
    assert any("asher" in p for p in profile.phrases)


def test_score_text_matches_name():
    profile = TopicProfile.parse("Asher Newton")
    assert score_text("Asher Newton lives in Cape Coral", profile) > 0.3


def test_score_link_github_profile():
    profile = TopicProfile.parse("Asher Newton")
    score = score_link("https://github.com/shep95", "Asher Newton", profile)
    assert score > 0.2


def test_score_page_github_html():
    profile = TopicProfile.parse("Asher Newton Cape Coral")
    html = "<html><title>shep95 (Asher Newton)</title><body>Asher Newton Cape Coral Florida</body></html>"
    assert score_page(url="https://github.com/shep95", title="shep95 (Asher Newton)", body=html, profile=profile) > 0.2
