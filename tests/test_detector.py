"""Section-reference detection and old -> new conversion."""
import pytest

from backend.detector import convert, convert_text, detect_references, infer_code_act, reverse


def ids(refs):
    return {r["section_id"] for r in refs}


@pytest.mark.parametrize("text, expected", [
    ("booked u/s 420/406/34 IPC", {"IPC-420", "IPC-406", "IPC-34"}),
    ("Section 120B of the Indian Penal Code", {"IPC-120B"}),
    ("statement under S. 161 Cr.P.C.", {"CrPC-161"}),
    ("certificate under Section 65B of the Indian Evidence Act", {"IEA-65B"}),
    ("IPC 498A and 154 CrPC", {"IPC-498A", "CrPC-154"}),
    ("IPC 420, 406 and 154 CrPC", {"IPC-420", "IPC-406", "CrPC-154"}),
    ("धारा 302 आईपीसी", {"IPC-302"}),
    ("BNS 318(4) applies", {"BNS-318"}),
])
def test_detects_references(text, expected):
    assert expected <= ids(detect_references(text))


def test_ignores_other_acts():
    assert ids(detect_references("Section 4 of the Dowry Prohibition Act")) == set()


def test_number_before_another_act_is_not_misread():
    found = ids(detect_references("IPC 498A and 154 CrPC"))
    assert "IPC-154" not in found


@pytest.mark.parametrize("act, number, expected", [
    ("IPC", "420", {"BNS-318"}),
    ("IPC", "302", {"BNS-103"}),
    ("IPC", "498A", {"BNS-85", "BNS-86"}),
    ("IPC", "120B", {"BNS-61"}),
    ("CrPC", "154", {"BNSS-173"}),
    ("CrPC", "438", {"BNSS-482"}),
    ("CrPC", "41A", {"BNSS-35"}),   # curated mapping
    ("IEA", "65B", {"BSA-63"}),
])
def test_old_to_new(act, number, expected):
    assert {c["id"] for c in convert(act, number)} == expected


def test_new_to_old_and_new_offences():
    assert {p["id"] for p in reverse("BNS", "318")} >= {"IPC-415", "IPC-420"}
    assert reverse("BNS", "111") == []  # organised crime: no IPC predecessor


def test_convert_text_annotates_passage():
    out = convert_text("booked u/s 302/34 IPC and 154 CrPC")
    assert "[→ BNS 103, BNS 3]" in out["converted_text"]
    assert "[→ BNSS 173]" in out["converted_text"]
    assert out["converted_count"] == 3


def test_of_the_code_in_judgments():
    text = ("Section 154 of the Code of Criminal Procedure, 1973 (in short 'the Code'). "
            "Sections 156 and 157 of the Code also apply.")
    act = infer_code_act(text, detect_references(text))
    assert act == "CrPC"
    found = detect_references(text, code_act=act)
    assert {"CrPC-154", "CrPC-156", "CrPC-157"} <= ids(found)
    assert any(r["inferred"] for r in found)
    assert ids(detect_references("Section 154 of the Code")) == set()  # unknown code: no guess
