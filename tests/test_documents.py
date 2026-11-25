"""Document Analyzer: PDF and TXT extraction, reference detection and entity extraction."""
import pytest

from backend.pdf_service import ExtractionError, analyze, chunk_pages, extract_pdf, extract_text_file
from backend.rag import extractive_summary, select_excerpts
from conftest import SAMPLES


@pytest.fixture(scope="module")
def fir5_pdf():
    return analyze(extract_pdf((SAMPLES / "test_fir_5page.pdf").read_bytes()))


def test_sample_fir_pdf():
    a = analyze(extract_pdf((SAMPLES / "sample_fir.pdf").read_bytes()))
    assert a["stats"]["pages"] == 2
    assert a["doc_type"]["type"] == "FIR"
    assert len(a["references"]) == 13
    assert a["entities"]["amounts"] == ["Rs. 4,75,000", "Rs. 50,000"]
    assert a["entities"]["police_stations"] == ["Hazratganj"]


def test_five_page_fir_pdf(fir5_pdf):
    a = fir5_pdf
    assert a["stats"]["pages"] == 5
    assert a["doc_type"]["type"] == "FIR"
    assert len(a["references"]) == 24
    old = [r for r in a["references"] if r["era"] == "old"]
    assert len(old) == 11 and all(r["converted"] for r in old)
    e = a["entities"]
    assert e["fir_numbers"] == ["0738/2025", "0215/2022", "0098/2023"]
    assert set(e["police_stations"]) == {"Shivajinagar", "Hadapsar", "Kondhwa"}
    assert len(e["amounts"]) == 7 and "Rs. 18,45,000" in e["amounts"]
    assert all("7000054321" not in x for x in e["amounts"])  # a phone number is not an amount


def test_five_page_fir_txt_matches_pdf(fir5_pdf):
    a = analyze(extract_text_file((SAMPLES / "test_fir_5page.txt").read_bytes()))
    assert a["stats"]["pages"] == 5
    assert {r["section_id"] for r in a["references"]} == {r["section_id"] for r in fir5_pdf["references"]}


def test_txt_page_markers_and_encodings():
    assert extract_text_file(b"===== Page 1 =====\nIPC 420\n===== Page 2 =====\nCrPC 154\n")["page_count"] == 2
    assert extract_text_file(b"page one\fpage two\fpage three")["page_count"] == 3
    utf16 = "Section 420 IPC".encode("utf-16")
    assert "420" in extract_text_file(utf16)["pages"][0]["text"]


def test_bad_pdf_raises():
    with pytest.raises(ExtractionError):
        extract_pdf(b"%PDF-1.4 not really a pdf")


def test_chunks_and_summaries():
    ex = extract_pdf((SAMPLES / "test_fir_5page.pdf").read_bytes())
    assert len(chunk_pages(ex["pages"])) >= 5
    full = "\n".join(p["text"] for p in ex["pages"])
    assert extractive_summary(full)["summary"]
    short, coverage = select_excerpts("short text")
    assert short == "short text" and coverage == "complete"
    long_text = "Opening facts. " * 500 + "Section 154 matters here. " * 50 + "We hold the appeal is allowed. " * 200
    excerpt, coverage = select_excerpts(long_text)
    assert len(excerpt) <= 13000 and "We hold" in excerpt and "long document" in coverage
