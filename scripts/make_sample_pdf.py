"""Generates frontend/samples/sample_fir.pdf: a FICTIONAL First Information Report for demos.

Uses a tiny hand-written PDF writer (standard library only) so no extra dependency is needed.
"""
from pathlib import Path
import textwrap

OUT = Path(__file__).resolve().parent.parent / "frontend" / "samples" / "sample_fir.pdf"

PAGES = [
    [
        ("H", "FIRST INFORMATION REPORT (Under Section 154 Cr.P.C.)"),
        ("S", "SAMPLE DOCUMENT - FICTIONAL - FOR DEMONSTRATION ONLY"),
        ("", ""),
        ("", "District: Lucknow    P.S. Hazratganj    Year: 2024    FIR No. 0412/2024    Date: 18/06/2024"),
        ("", "Acts & Sections: u/s 420/406/120B IPC and Section 34 of the Indian Penal Code"),
        ("", ""),
        ("B", "1. Occurrence of offence"),
        ("", "Date of occurrence: from 02 March 2024 to 15 May 2024. Information received at police station on 18/06/2024 at 11:30 hrs."),
        ("", "Place of occurrence: Office No. 7, Sapru Marg, approximately 2 km east of the police station."),
        ("", ""),
        ("B", "2. Complainant / Informant"),
        ("", "Name: Ramesh Kumar Verma, S/o Late Shri Om Prakash Verma, Age 46, Occupation: Shopkeeper."),
        ("", "Address: 21, Aliganj, Lucknow. Mobile: 9876543210. Email: ramesh.verma@example.com"),
        ("", ""),
        ("B", "3. Details of accused"),
        ("", "(i) Suresh Malhotra, proprietor of 'Sunrise Investments'; (ii) Neha Malhotra; (iii) one unknown associate."),
        ("", ""),
        ("B", "4. Particulars of property involved"),
        ("", "Cash and bank transfers totalling Rs. 4,75,000 and a cheque of Rs. 50,000 dated 10.04.2024."),
        ("", ""),
        ("B", "5. Brief facts"),
        ("", "The complainant states that the accused persons induced him to invest money in a scheme promising "
             "monthly returns of 8 percent. Relying on their representations he transferred Rs. 4,75,000 between "
             "02 March 2024 and 15 May 2024. The accused issued fake receipts and stopped answering calls after "
             "15 May 2024. When the complainant visited the office it was found locked. The accused acted in "
             "furtherance of a common intention and entered into a criminal conspiracy to cheat the complainant and "
             "dishonestly misappropriate the money entrusted to them. They also threatened him on WhatsApp, which "
             "amounts to criminal intimidation under section 506 IPC."),
    ],
    [
        ("B", "6. Evidence collected"),
        ("", "Bank statements, the WhatsApp chat and CCTV footage from the office building were collected. A certificate "
             "under Section 65B of the Indian Evidence Act has been requested for the electronic records."),
        ("", ""),
        ("B", "7. Action taken"),
        ("", "Since the information discloses commission of cognizable offences, the case is registered and taken up for "
             "investigation. Statements of witnesses will be recorded under Section 161 Cr.P.C. The accused are "
             "absconding; one accused has applied for anticipatory bail under section 438 CrPC before the Sessions Court."),
        ("", ""),
        ("B", "8. Note on the new criminal laws"),
        ("", "Offences committed on or after 1 July 2024 are registered under the Bharatiya Nyaya Sanhita, 2023. For "
             "reference, cheating is now punishable under BNS 318(4), criminal breach of trust under BNS 316, and "
             "criminal conspiracy under BNS 61. FIRs are now registered under section 173 of the BNSS."),
        ("", ""),
        ("", "Signature of the Officer in Charge: SI Anil Yadav, P.S. Hazratganj    Date of dispatch to court: 19/06/2024"),
        ("", ""),
        ("S", "This is a fictional sample created for the NyayaSetu project. All names and numbers are invented."),
    ],
]


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def page_stream(lines) -> bytes:
    out = ["BT", "50 790 Td"]
    for style, text in lines:
        font, size, lead = {"H": ("F2", 15, 22), "B": ("F2", 11.5, 17), "S": ("F1", 9, 14)}.get(style, ("F1", 10.5, 14.5))
        wrapped = textwrap.wrap(text, 95 if size <= 10.5 else 80) or [""]
        for w in wrapped:
            out.append(f"/{font} {size} Tf {lead} TL T* ({esc(w)}) Tj")
    out.append("ET")
    return "\n".join(out).encode("latin-1")


def build() -> bytes:
    objs: list[bytes] = []
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{5 + i * 2} 0 R" for i in range(len(PAGES)))
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(PAGES)} >>".encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    for i, lines in enumerate(PAGES):
        content = page_stream(lines)
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {6 + i * 2} 0 R >>".encode())
        objs.append(b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream")
    info_id = len(objs) + 1
    objs.append(b"<< /Title (Sample FIR - NyayaSetu demo) /Producer (NyayaSetu sample generator) >>")
    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for n, body in enumerate(objs, 1):
        offsets.append(len(pdf))
        pdf += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(pdf)
    pdf += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        pdf += f"{off:010d} 00000 n \n".encode()
    pdf += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R /Info {info_id} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(pdf)


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(build())
    print("wrote", OUT)
