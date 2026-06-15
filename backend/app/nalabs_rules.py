"""
NALABS-Regeln (Lightweight-Version)
====================================

Akademisch fundierte Requirement-Bad-Smell-Detection basierend auf:
- NALABS (Natural LAnguage Bad Smells Detector) von Rajkovic & Enoiu
- ISO/IEC/IEEE 29148:2018 - Section 5.2 (Quality of Requirements)

Erkennt folgende Smell-Kategorien:
- Ambiguous Words (mehrdeutige Begriffe)
- Vagueness (Unbestimmtheit)
- Optionality (Optionalitaet: kann, mag, optional)
- Subjectivity (subjektive Wertungen)
- Weakness (schwache Formulierungen)
- Readability (Lesbarkeit, Flesch Score)
- Missing Keywords (shall/must/should fehlt)
- Multiple Conjunctions (zu viele Bedingungen)
- Security Keywords (Hinweis auf Security-Anforderungen)

Original-Quelle: https://github.com/eduardenoiu/NALABS
Lizenz: MIT
"""

from typing import List, Dict, Any
import re

# NALABS-Woerterbuecher (uebernommen aus nalabs_rules.py, MIT-Lizenz)
AMBIGUOUS_WORDS = {
    "may", "could", "has to", "have to", "might", "will", "should have",
    "must have", "all the other", "all other", "based on", "some",
    "appropriate", "as a", "as an", "a minimum", "up to", "adequate",
    "as applicable", "be able to", "be capable", "but not limited to",
    "capability of", "capability to", "effective", "normal",
}

REQUIREMENT_KEYWORDS = {
    "shall", "must", "should", "will", "requires", "necessitates",
    "needs to", "is required to",
}

SECURITY_KEYWORDS = {
    "security", "secure", "confidentiality", "integrity", "availability",
    "authentication", "authorization", "encryption", "access control",
    "audit", "firewall", "intrusion detection", "vulnerability",
    "patching", "secure communication", "privacy", "compliance",
    "risk assessment", "incident response", "disaster recovery",
    "secure coding", "dsgvo", "gdpr",
}

OPTIONALITY_KEYWORDS = {"can", "may", "optionally"}

CONJUNCTION_KEYWORDS = {
    "and", "after", "although", "as long as", "before", "but", "else",
    "if", "in order", "in case", "nor", "or", "otherwise", "once",
    "since", "then", "though", "till", "unless", "until", "when",
    "whenever", "where", "whereas", "wherever", "while", "yet",
}

CONTINUANCES_KEYWORDS = {"below", "as follows", "following", "listed", "in particular", "support"}

SUBJECTIVITY_KEYWORDS = {
    "similar", "better", "similarly", "worse", "having in mind",
    "take into account", "take into consideration", "as possible",
    "good", "smart", "clever", "schlau", "gut", "schnell", "einfach",
    "moeglichst", "sinnvoll", "zweckmaessig", "robust", "flexibel",
}

WEAKNESS_KEYWORDS = {
    "adequate", "as appropriate", "be able to", "be capable of",
    "capability", "effective", "as required", "normal", "provide for",
    "timely", "easy to", "ausreichend", "angemessen", "zweckmaessig",
}

REFERENCES_KEYWORDS = {"e.g.", "i.e.", "for example", "for instance", "figure", "table", "note", "z.B.", "siehe"}

# NALABS-Defaults
DEFAULT_MIN_READING_SCORE = 30  # Flesch Reading Ease (hoeher = besser)
DEFAULT_MAX_SUBJECTIVITY = 0.5
DEFAULT_MAX_CONJUNCTIONS = 3
DEFAULT_MAX_WORDS = 50  # Empfehlung: nicht laenger als 50 Worte pro Requirement


def _count_keywords(text: str, keywords: set) -> int:
    """Zaehlt Vorkommen von keywords in text (case-insensitive, Word-Boundary)."""
    t = text.lower()
    count = 0
    for kw in keywords:
        # Word-Boundary-Suche (vermeidet Substring-Treffer)
        if re.search(r"\b" + re.escape(kw) + r"\b", t):
            count += 1
    return count


def _count_word_occurrences(text: str, keywords: set) -> List[str]:
    """Gibt die gefundenen keywords zurueck (case-insensitive)."""
    t = text.lower()
    found = []
    for kw in keywords:
        if re.search(r"\b" + re.escape(kw) + r"\b", t):
            found.append(kw)
    return found


def _flesch_reading_ease_de(text: str) -> float:
    """Flesch Reading Ease fuer deutsche Texte (textstat)."""
    try:
        from textstat import flesch_reading_ease
        return float(flesch_reading_ease(text))
    except Exception:
        return 100.0  # Fallback: keine Beanstandung


def _word_count(text: str) -> int:
    return len([w for w in re.split(r"\s+", text.strip()) if w])


def check_requirement_quality(text: str) -> Dict[str, Any]:
    """
    Prueft ein einzelnes Requirement auf Bad Smells (NALABS-Methode).

    Returns: {
        "text": str,
        "issues": [{"severity", "category", "message", "found_terms"}],
        "stats": {...}
    }
    """
    if not text or not text.strip():
        return {
            "text": text,
            "issues": [{
                "severity": "high",
                "category": "empty",
                "message": "Requirement ist leer",
                "found_terms": [],
            }],
            "stats": {"word_count": 0, "flesch": 0},
        }

    issues: List[Dict[str, Any]] = []
    text_lower = text.lower()

    # 1. AMBIGUOUS_WORDS
    found = _count_word_occurrences(text, AMBIGUOUS_WORDS)
    if found:
        issues.append({
            "severity": "medium" if len(found) <= 2 else "high",
            "category": "ambiguous",
            "message": f"Mehrdeutige Begriffe gefunden: {', '.join(found[:5])}. "
                       f"Diese sollten praezisiert werden.",
            "found_terms": found,
        })

    # 2. VAGUENESS_WORDS (Subset von AMBIGUOUS, aber speziell)
    vagueness_found = [w for w in found if w in {
        "some", "appropriate", "adequate", "as applicable",
        "be able to", "be capable", "effective", "normal",
    }]
    if vagueness_found:
        issues.append({
            "severity": "high",
            "category": "vagueness",
            "message": f"Unbestimmte Begriffe: {', '.join(vagueness_found)}. "
                       f"Besser: konkrete Zahlen oder Bedingungen angeben.",
            "found_terms": vagueness_found,
        })

    # 3. OPTIONALITY (can/may/optionally)
    opt_found = _count_word_occurrences(text, OPTIONALITY_KEYWORDS)
    if opt_found:
        issues.append({
            "severity": "high",
            "category": "optionality",
            "message": f"Optionalitaets-Woerter: {', '.join(opt_found)}. "
                       f"Optionale Anforderungen sind schwer testbar. "
                       f"Entweder als MUSS oder als NICE-TO-HAVE markieren.",
            "found_terms": opt_found,
        })

    # 4. WEAKNESS_WORDS
    weakness_found = _count_word_occurrences(text, WEAKNESS_KEYWORDS)
    if weakness_found:
        issues.append({
            "severity": "medium",
            "category": "weakness",
            "message": f"Schwache Formulierungen: {', '.join(weakness_found)}. "
                       f"Diese sind nicht messbar/verifizierbar.",
            "found_terms": weakness_found,
        })

    # 5. SUBJECTIVITY
    subj_found = _count_word_occurrences(text, SUBJECTIVITY_KEYWORDS)
    if subj_found:
        issues.append({
            "severity": "high",
            "category": "subjectivity",
            "message": f"Subjektive Wertungen: {', '.join(subj_found)}. "
                       f"Besser: messbare GROESSEN verwenden (z.B. '< 200ms' statt 'schnell').",
            "found_terms": subj_found,
        })

    # 6. MISSING REQUIREMENT KEYWORD (shall/must/should)
    req_kw_found = _count_word_occurrences(text, REQUIREMENT_KEYWORDS)
    if req_kw_found == 0:
        issues.append({
            "severity": "medium",
            "category": "missing_keyword",
            "message": "Kein Modalverb (shall/must/should/will) gefunden. "
                       f"IEEE 29148 verlangt eine klare Verbindlichkeit. "
                       f"Beispiel: 'Das System SOLL ...' oder 'Das System MUSS ...'",
            "found_terms": [],
        })

    # 7. ZU VIELE CONJUNCTIONS (mehrere Bedingungen)
    conj_found = _count_word_occurrences(text, CONJUNCTION_KEYWORDS)
    if len(conj_found) > DEFAULT_MAX_CONJUNCTIONS:
        issues.append({
            "severity": "high",
            "category": "multiple_conditions",
            "message": f"{len(conj_found)} Konjunktionen gefunden ({', '.join(conj_found[:3])}...). "
                       f"Empfehlung: max. {DEFAULT_MAX_CONJUNCTIONS} Konjunktionen pro Requirement. "
                       f"Sonst aufteilen.",
            "found_terms": conj_found,
        })

    # 8. WORD COUNT
    wc = _word_count(text)
    if wc > DEFAULT_MAX_WORDS:
        issues.append({
            "severity": "low",
            "category": "length",
            "message": f"Requirement hat {wc} Woerter. Empfehlung: max. {DEFAULT_MAX_WORDS}. "
                       f"Lange Requirements sind schwer zu verstehen und zu testen.",
            "found_terms": [],
        })

    # 9. READABILITY (Flesch)
    flesch = _flesch_reading_ease_de(text)
    if flesch < DEFAULT_MIN_READING_SCORE:
        issues.append({
            "severity": "low",
            "category": "readability",
            "message": f"Flesch Reading Ease = {flesch:.1f} (Schwelle: {DEFAULT_MIN_READING_SCORE}). "
                       f"Schwer lesbar. Empfehlung: kuerzere Saetze, einfache Woerter.",
            "found_terms": [],
        })

    # 10. SECURITY HINT (positiv: wenn Security-Keywords vorhanden, ggf. NFR erstellen)
    sec_found = _count_word_occurrences(text, SECURITY_KEYWORDS)
    security_hint = bool(sec_found)

    return {
        "text": text,
        "word_count": wc,
        "flesch_score": round(flesch, 1),
        "security_hint": security_hint,
        "security_terms": sec_found,
        "issues": issues,
    }


def check_requirements_batch(texts: List[str]) -> Dict[str, Any]:
    """
    Prueft eine Liste von Requirements als Batch.

    Returns: {
        "total": int,
        "with_issues": int,
        "high": int, "medium": int, "low": int,
        "results": [check_requirement_quality resultate],
        "summary": {...}
    }
    """
    results = []
    high = medium = low = 0
    for text in texts:
        r = check_requirement_quality(text)
        results.append(r)
        for issue in r["issues"]:
            if issue["severity"] == "high":
                high += 1
            elif issue["severity"] == "medium":
                medium += 1
            else:
                low += 1
    return {
        "total": len(texts),
        "with_issues": sum(1 for r in results if r["issues"]),
        "issue_counts": {"high": high, "medium": medium, "low": low},
        "results": results,
        "summary": {
            "avg_flesch": round(sum(r["flesch_score"] for r in results) / max(len(results), 1), 1),
            "avg_word_count": round(sum(r["word_count"] for r in results) / max(len(results), 1), 1),
            "security_related": sum(1 for r in results if r["security_hint"]),
        },
    }
