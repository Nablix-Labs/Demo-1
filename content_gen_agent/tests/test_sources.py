

def test_an_empty_directory_with_the_right_name_is_not_the_sources_dir(tmp_path, monkeypatch):
    """A stray empty "Content Gen- Agent" folder closer to the package than
    the real one used to win the search. Every test needing an input then
    skipped, and a suite reporting 279 skips still says green.
    """
    import sources

    decoy = tmp_path / sources.SOURCES_DIR_NAME
    decoy.mkdir()
    monkeypatch.setattr(sources.Path, "resolve", lambda self: tmp_path / "pkg" / "x.py")
    monkeypatch.delenv(sources.ENV_VAR, raising=False)
    assert sources._holds_sources(decoy) is False


def test_a_directory_holding_topic_documents_counts(tmp_path):
    import sources

    real = tmp_path / sources.SOURCES_DIR_NAME
    real.mkdir()
    (real / "Topic_1_Formatted.docx").write_bytes(b"")
    assert sources._holds_sources(real) is True


def test_a_directory_holding_only_the_template_counts(tmp_path):
    import sources

    real = tmp_path / sources.SOURCES_DIR_NAME
    real.mkdir()
    (real / sources.SCHEMA_TEMPLATE_NAME).write_bytes(b"")
    assert sources._holds_sources(real) is True
