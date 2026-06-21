import json
import re
import argparse
from typing import Any, Dict, List, Optional, Tuple

# ---------------- helpers ----------------

def norm_spaces(s: Any) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()

def clean_unit(u: str) -> str:
    u = norm_spaces(u)
    # common OCR cleanups
    u = u.replace("Tcu mm", "/cu mm").replace("-/cu mm", "/cu mm")
    u = u.replace("/cu' mm", "/cu mm").replace("' /cur mm", "/cu mm").replace("I /cu mm", "/cu mm")
    u = u.replace("gm/dL", "gm/dL").replace("g/dL", "gm/dL")
    return u

def is_method_token(s: str) -> bool:
    s = s.strip()
    return (s.startswith("(") and s.endswith(")")) or s.startswith("(")

def looks_like_header_row(r: str) -> bool:
    # common lab table header variants
    r_low = r.lower()
    return (
        ("investigation" in r_low or "test" in r_low) and
        ("result" in r_low) and
        ("reference" in r_low or "range" in r_low)
    )

# comma-aware number: 1,50,000 or 4,000 or 12.8
NUM_TOKEN_RE = re.compile(r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?")
# range: 12.0 - 15.0 / 4,000 - 11,000 / 0-2
RANGE_RE = re.compile(
    r"(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*[-–]\s*(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
)

def parse_number(token: str) -> Optional[float]:
    token = token.strip().replace(",", "")
    try:
        return float(token)
    except:
        return None

def extract_numbers(text: str) -> List[str]:
    return NUM_TOKEN_RE.findall(text)

def parse_range(text: str) -> Tuple[Optional[float], Optional[float]]:
    m = RANGE_RE.search(text.replace("—", "-").replace("–", "-"))
    if not m:
        return None, None
    low = parse_number(m.group(1))
    high = parse_number(m.group(2))
    return low, high

def is_flag_token(p: str) -> bool:
    p = p.strip()
    return p in ("H", "L") or p in (": H", ": L")

def extract_flag(parts: List[str]) -> Optional[str]:
    for p in parts:
        p2 = p.strip()
        if p2 in ("H", "L"):
            return p2
        if p2 in (": H", ": L"):
            return p2.replace(":", "").strip()
    return None

def has_unit_hint(p: str) -> bool:
    pl = p.lower()
    return any(x in pl for x in [
        "gm/dl", "g/dl", "mg/dl", "mmol", "iu/l", "u/l", "ng/ml", "pg", "fl", "%", "/cu", "ratio", "cells", "miu/ml",
        "mill/cu", "umol", "meq", "g/l"
    ])

def looks_like_test_name(s: str) -> bool:
    s = s.strip()
    if not s:
        return False
    if is_method_token(s):
        return False
    # must contain letters
    return bool(re.search(r"[A-Za-z]", s))

def looks_like_footer(r: str) -> bool:
    rl = r.lower()
    return rl.startswith("print.date") or "laboratory accred" in rl or "page " in rl and "of" in rl

def choose_best_result(nums: List[str], ref_low: Optional[float], ref_high: Optional[float]) -> Optional[float]:
    """
    OCR often injects junk single digits like '1' before the real result.
    Strategy:
      - If multiple numbers exist, drop single-digit integers (e.g., '1') when others exist.
      - Prefer decimals if present (often real values like 28.80, 12.8).
      - Prefer a value that lies within the reference range.
      - Otherwise choose the largest value (often correct vs tiny artifacts).
    """
    if not nums:
        return None

    cleaned = nums[:]
    if len(cleaned) > 1:
        cleaned2 = []
        for n in cleaned:
            raw = n.replace(",", "")
            if len(raw) == 1 and "." not in raw:  # single digit
                continue
            cleaned2.append(n)
        if cleaned2:
            cleaned = cleaned2

    # prefer decimals
    decimals = [n for n in cleaned if "." in n.replace(",", "")]
    if decimals:
        return parse_number(decimals[-1])

    vals = [parse_number(n) for n in cleaned]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None

    if ref_low is not None and ref_high is not None:
        for v in vals:
            if ref_low <= v <= ref_high:
                return v

    return max(vals)


def format_number(v: Any) -> str:
    if v is None:
        return ""
    try:
        fv = float(v)
        if fv.is_integer():
            return str(int(fv))
        return f"{fv:.2f}".rstrip("0").rstrip(".")
    except Exception:
        return norm_spaces(str(v))


def build_reference_range(low: Optional[float], high: Optional[float]) -> str:
    low_s = format_number(low)
    high_s = format_number(high)
    if low_s and high_s:
        return f"{low_s} - {high_s}"
    if low_s:
        return f">= {low_s}"
    if high_s:
        return f"<= {high_s}"
    return ""


def estimate_confidence(test: Dict[str, Any]) -> float:
    # Heuristic confidence score based on completeness of extracted fields.
    score = 0.55
    if test.get("result") is not None:
        score += 0.20
    if norm_spaces(test.get("unit", "")):
        score += 0.10
    if test.get("ref_low") is not None and test.get("ref_high") is not None:
        score += 0.10
    if test.get("flag") in ("H", "L"):
        score += 0.05
    return round(min(score, 0.99), 2)


def build_structured_tests(raw_tests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    structured: List[Dict[str, Any]] = []

    for t in raw_tests:
        test_name = norm_spaces(t.get("name", ""))
        if not test_name:
            continue

        structured.append(
            {
                "test_name": test_name,
                "value": format_number(t.get("result")),
                "unit": clean_unit(t.get("unit") or ""),
                "reference_range": build_reference_range(t.get("ref_low"), t.get("ref_high")),
                "confidence": estimate_confidence(t),
            }
        )

    return structured


def build_abnormal_summary(raw_tests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    abnormal: List[Dict[str, Any]] = []

    for t in raw_tests:
        flag = t.get("flag")
        res = t.get("result")
        lo = t.get("ref_low")
        hi = t.get("ref_high")

        if flag not in ("H", "L") and res is not None and lo is not None and hi is not None:
            if res < lo:
                flag = "L"
            elif res > hi:
                flag = "H"

        if flag in ("H", "L"):
            abnormal.append(
                {
                    "name": norm_spaces(t.get("name", "")),
                    "result": format_number(res),
                    "unit": clean_unit(t.get("unit") or ""),
                    "flag": flag,
                    "ref_low": format_number(lo),
                    "ref_high": format_number(hi),
                }
            )

    return abnormal


def derive_report_id(ocr: Dict[str, Any]) -> str:
    report_id = (
        ocr.get("report_id")
        or ocr.get("ocr_doc_id")
        or ocr.get("source")
        or ocr.get("input")
        or ocr.get("input_path")
        or "unknown"
    )
    return str(report_id)

# ---------------- patient info extraction ----------------

def extract_patient_info(rows: List[str]) -> Dict[str, Any]:
    info: Dict[str, Any] = {}
    joined = "\n".join(rows)

    # Patient name: try explicit, else fallback MR/MRS/MS pattern
    m = re.search(r"Patient Name.*?(\bMR\b|\bMRS\b|\bMS\b)?\s*([A-Z][A-Z\s]{5,})", joined, flags=re.IGNORECASE)
    if m:
        name = norm_spaces((m.group(1) or "").strip() + " " + m.group(2).strip())
        info["name"] = name.strip()
    else:
        m2 = re.search(r"\b(MR|MRS|MS)\s+[A-Z][A-Z ]{5,}", joined)
        if m2:
            info["name"] = norm_spaces(m2.group(0))

    # Age/Gender: fix "$1" -> "31" style
    m = re.search(r"(\$?\d{1,3})\s*Yrs?\s*/\s*(Male|Female)", joined, flags=re.IGNORECASE)
    if m:
        age_raw = m.group(1).replace("$", "3")
        gender = m.group(2).title()
        info["age_gender_raw"] = f"{age_raw} Yrs/ {gender}"
        if age_raw.isdigit():
            info["age_years"] = int(age_raw)
        info["gender"] = gender

    # Registration date
    m = re.search(r"Registration\.Date\s*:\s*([0-9]{2}[-/][0-9]{2}[-/][0-9]{4})", joined, flags=re.IGNORECASE)
    if m:
        info["registration_date"] = m.group(1)

    # Report date/time
    m = re.search(r"Report Date/Time\s*(?:\|\s*:\s*)?([0-9]{2}[-/][0-9]{2}[-/][0-9]{4}\s*[0-9]{1,2}:[0-9]{2}\s*(?:am|pm)?)",
                  joined, flags=re.IGNORECASE)
    if m:
        info["report_datetime"] = norm_spaces(m.group(1))

    return info

# ---------------- report type detection ----------------

def detect_report_type(rows: List[str]) -> str:
    joined = " ".join(rows)
    # pick common patterns like "HAEMOGRAM (CBC)" / "LIVER FUNCTION TEST" etc.
    # Heuristic: find a line that looks like a title (ALL CAPS, length reasonable)
    candidates = []
    for r in rows:
        rr = norm_spaces(r)
        if len(rr) < 5 or len(rr) > 60:
            continue
        # accept if contains parentheses or is uppercase-ish and not "Investigation | Result..."
        if looks_like_header_row(rr):
            continue
        if re.search(r"\b(CBC|HAEMOGRAM|HEMOGRAM|LFT|KFT|LIPID|THYROID|URINE|SUGAR|GLUCOSE)\b", rr, re.IGNORECASE):
            candidates.append(rr)
        elif rr.upper() == rr and re.search(r"[A-Z]", rr):
            # avoid noisy address lines by requiring medical-ish token
            if re.search(r"(test|profile|panel|haemo|hemo|count|function|serum|urine|blood)", rr, re.IGNORECASE):
                candidates.append(rr)

    # prefer the earliest strong candidate
    if candidates:
        # normalize common CBC naming
        for c in candidates:
            if re.search(r"haemogram.*cbc|cbc", c, re.IGNORECASE):
                return "HAEMOGRAM (CBC)"
        return candidates[0]

    # fallback
    if "cbc" in joined.lower():
        return "HAEMOGRAM (CBC)"
    return "UNKNOWN"

# ---------------- table parser ----------------

def extract_tests(rows: List[str]) -> List[Dict[str, Any]]:
    tests: List[Dict[str, Any]] = []
    in_table = False
    pending_method: Optional[str] = None
    current: Optional[Dict[str, Any]] = None

    for raw in rows:
        r = norm_spaces(raw)
        if not r:
            continue

        # detect table header
        if looks_like_header_row(r):
            in_table = True
            continue

        if not in_table:
            continue

        # stop at footer
        if looks_like_footer(r):
            break

        parts = [norm_spaces(p) for p in r.split("|") if norm_spaces(p)]
        if not parts:
            continue

        # Handle a row that starts with a method token then has the test name
        # Example: "(Fluroscence...)" | "Total WBC..." | ":" | "8370" | "/cu mm" | "4,000 - 11,000"
        if is_method_token(parts[0]) and len(parts) >= 2:
            pending_method = parts[0]
            # If the second token looks like a test name, treat it as such
            if looks_like_test_name(parts[1]):
                # create a new current test here
                current = {
                    "name": parts[1],
                    "result": None,
                    "unit": None,
                    "ref_low": None,
                    "ref_high": None,
                    "flag": None,
                    "method": pending_method
                }
                tests.append(current)
                pending_method = None
                # fill from the entire row (including tokens after name)
                _fill_test_from_parts(current, parts[2:])
                continue
            else:
                # method line alone, keep it for next test
                continue

        # If row itself is a method token like "(Calculated)" etc. and we have a current test => continuation
        if is_method_token(parts[0]) and current is not None:
            current["method"] = (current.get("method") + "; " if current.get("method") else "") + parts[0]
            _fill_test_from_parts(current, parts[1:])
            continue

        # Normal: first part is test name OR continuation line
        if looks_like_test_name(parts[0]):
            # Start new test if this line has any evidence of numeric data or range or unit,
            # OR if it's clearly a test row by having multiple columns.
            start_new = len(parts) >= 2

            if start_new:
                current = {
                    "name": parts[0],
                    "result": None,
                    "unit": None,
                    "ref_low": None,
                    "ref_high": None,
                    "flag": None,
                    "method": pending_method
                }
                pending_method = None
                tests.append(current)
                _fill_test_from_parts(current, parts[1:])
                continue

        # Continuation: attach to current
        if current is not None:
            _fill_test_from_parts(current, parts)
        # else ignore noise

    # Post-pass: merge weird “name became (Calculated)” cases by fixing names if needed
    # If a test name is "(Calculated)" and the previous test exists without a result -> merge.
    merged: List[Dict[str, Any]] = []
    i = 0
    while i < len(tests):
        t = tests[i]
        if t["name"].strip().lower() in ("(calculated)", "(derived)") and merged:
            prev = merged[-1]
            # only merge if prev doesn't have a result yet
            if prev.get("result") is None and t.get("result") is not None:
                prev["result"] = t["result"]
                prev["unit"] = prev["unit"] or t["unit"]
                prev["ref_low"] = prev["ref_low"] if prev["ref_low"] is not None else t["ref_low"]
                prev["ref_high"] = prev["ref_high"] if prev["ref_high"] is not None else t["ref_high"]
                prev["flag"] = prev["flag"] or t["flag"]
                prev["method"] = (prev.get("method") + "; " if prev.get("method") else "") + (t.get("method") or "")
                i += 1
                continue
        merged.append(t)
        i += 1

    # Remove pure garbage tests with no useful data
    cleaned = []
    for t in merged:
        if not t.get("name"):
            continue
        if t.get("result") is None and t.get("ref_low") is None and t.get("unit") is None and not t.get("method"):
            continue
        cleaned.append(t)

    return cleaned

def _fill_test_from_parts(test: Dict[str, Any], parts: List[str]) -> None:
    # flag
    f = extract_flag(parts)
    if f and not test.get("flag"):
        test["flag"] = f

    # unit + range candidates
    for p in parts:
        low, high = parse_range(p)
        if low is not None and high is not None:
            test["ref_low"], test["ref_high"] = low, high

    for p in parts:
        if has_unit_hint(p):
            candidate = clean_unit(p)
            # don't accept if it's purely numeric
            if not NUM_TOKEN_RE.fullmatch(candidate.replace(",", "")):
                test["unit"] = candidate

    # pick result
    joined = " ".join(parts)

    # remove range endpoints from candidate numbers to avoid selecting ref_low/ref_high as result
    nums = extract_numbers(joined)

    if test.get("ref_low") is not None and test.get("ref_high") is not None:
        low = test["ref_low"]
        high = test["ref_high"]

        def not_endpoint(n: str) -> bool:
            v = parse_number(n)
            if v is None:
                return True
            return abs(v - low) > 1e-9 and abs(v - high) > 1e-9

        filtered = [n for n in nums if not_endpoint(n)]
        if filtered:
            nums = filtered

    result_val = choose_best_result(nums, test.get("ref_low"), test.get("ref_high"))
    if result_val is not None:
        test["result"] = result_val


# ---------------- main ----------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to OCR JSON (blood_report_ocr.json)")
    ap.add_argument("--out", default="lab_structured.json", help="Output structured JSON")
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        ocr = json.load(f)

    # Collect all rows across pages
    rows: List[str] = []
    pages = ocr.get("pages", [])
    if isinstance(pages, list):
        for p in pages:
            if not isinstance(p, dict):
                continue
            page_rows = p.get("rows", [])
            if isinstance(page_rows, list):
                rows.extend([str(r) for r in page_rows if isinstance(r, str)])

    patient_info = extract_patient_info(rows)
    raw_tests = extract_tests(rows)
    tests = build_structured_tests(raw_tests)
    report_type = detect_report_type(rows)
    abnormal = build_abnormal_summary(raw_tests)

    output = {
        "report_id": derive_report_id(ocr),
        "source": ocr.get("input") or ocr.get("input_path"),
        "patient_info": patient_info,
        "report_type": report_type,
        "tests": tests,
        "abnormal": abnormal
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Saved structured JSON to: {args.out}")
    print(f"Extracted tests: {len(tests)} | Abnormal: {len(abnormal)}")

if __name__ == "__main__":
    main()
