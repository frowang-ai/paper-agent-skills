from __future__ import annotations

from paper_agent.workspace import WorkspaceDirectoryNamingProtocol


def test_naming_protocol_uses_year_authors_title_and_short_id() -> None:
    protocol = WorkspaceDirectoryNamingProtocol()
    result = protocol.generate(
        metadata={
            "publication_year": 2024,
            "authors": [
                {"family": "Smith", "given": "Alice"},
                {"family": "Lee", "given": "Bob"},
                {"family": "Wang", "given": "Carol"},
            ],
            "title": "Inflation: Dynamics / Evidence?",
        },
        paper_id="11111111-1111-1111-1111-111111111111",
        short_id="P-lw",
        revision="task-1",
    )

    assert result.directory == "2024-Smith-et-al-Inflation-Dynamics-Evidence--P-lw"
    assert result.as_dict() == {
        "protocol": "year-author-short-title--short-id-v1",
        "generated_from_revision": "task-1",
    }


def test_naming_protocol_handles_two_string_authors_and_unicode() -> None:
    protocol = WorkspaceDirectoryNamingProtocol()

    western = protocol.generate(
        metadata={
            "year": "2022",
            "authors": ["John Smith", "Jane Doe"],
            "title": "Monetary Policy Shocks",
        },
        paper_id="paper-a",
        short_id="P-a",
        revision="task-a",
    )
    chinese = protocol.generate(
        metadata={
            "publication_date": "2021-05-01",
            "authors": ["张三", "李四"],
            "title": "地方债务与经济增长",
        },
        paper_id="paper-b",
        short_id="P-b",
        revision="task-b",
    )

    assert western.directory == "2022-Smith-Doe-Monetary-Policy-Shocks--P-a"
    assert chinese.directory == "2021-张三-李四-地方债务与经济增长--P-b"


def test_naming_protocol_has_safe_bounded_fallback() -> None:
    protocol = WorkspaceDirectoryNamingProtocol()
    result = protocol.generate(
        metadata={"title": '<>:"/\\|?*' + "Long title " * 30},
        paper_id="11111111-2222-3333-4444-555555555555",
        short_id=None,
        revision="task-fallback",
    )

    assert result.directory.startswith("n.d.-Unknown-")
    assert result.directory.endswith("--id-11111111")
    assert len(result.directory) <= 120
    assert not any(character in result.directory for character in '<>:"/\\|?*')
