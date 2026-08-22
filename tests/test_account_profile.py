from moolias.review_settings import _mailbox_first_name


def test_mailbox_first_name_uses_first_given_name() -> None:
    assert _mailbox_first_name({"name": "Philipp Kreis"}, "pk@example.org") == "Philipp"


def test_mailbox_first_name_supports_last_name_first_format() -> None:
    assert _mailbox_first_name({"name": "Kreis, Philipp"}, "pk@example.org") == "Philipp"


def test_mailbox_first_name_skips_common_titles() -> None:
    assert _mailbox_first_name({"name": "Dr. Philipp Kreis"}, "pk@example.org") == "Philipp"


def test_mailbox_first_name_uses_first_given_name_for_long_names() -> None:
    assert (
        _mailbox_first_name({"name": "Lisey Johanna Quimbayo Ospina"}, "user@example.org")
        == "Lisey"
    )


def test_mailbox_first_name_falls_back_to_mailbox() -> None:
    assert _mailbox_first_name({"name": ""}, "pk@example.org") == "pk@example.org"
