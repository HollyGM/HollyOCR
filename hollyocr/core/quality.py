"""Heuristics to score extracted page text and decide native vs. OCR text."""

import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher

PAGE_TEXT_QUALITY_MIN_SCORE = 55
PAGE_TEXT_LONG_TOKEN_THRESHOLD = 45


def analyze_page_text_quality(text, min_chars=30):
    """Score page text quality to decide whether OCR should replace native extraction."""
    raw_text = text or ""
    stripped = raw_text.strip()
    tokens = re.findall(r"\S+", stripped)
    char_count = len(stripped)
    word_count = len(tokens)
    whitespace_count = sum(1 for ch in raw_text if ch.isspace())
    alpha_count = sum(1 for ch in raw_text if ch.isalpha())
    digit_count = sum(1 for ch in raw_text if ch.isdigit())
    suspicious_count = 0
    for ch in raw_text:
        code = ord(ch)
        if (0xE000 <= code <= 0xF8FF) or (code == 0xFFFD) or (code < 32 and code not in (9, 10, 13)):
            suspicious_count += 1

    suspicious_ratio = (suspicious_count / char_count) if char_count else 0.0
    whitespace_ratio = (whitespace_count / len(raw_text)) if raw_text else 0.0
    longest_token = max((len(token) for token in tokens), default=0)
    avg_word_len = (sum(len(token) for token in tokens) / word_count) if word_count else 0.0

    score = 100
    flags = []
    if char_count == 0:
        flags.append("sem-texto")
        score = 0
    elif char_count < max(1, int(min_chars or 30)):
        flags.append("texto-curto")
        score -= 45

    if suspicious_ratio > 0.05:
        flags.append("caracteres-suspeitos")
        score -= 55
    elif suspicious_ratio > 0.02:
        flags.append("caracteres-suspeitos")
        score -= 25

    if char_count >= 180 and word_count <= 4:
        flags.append("poucas-palavras")
        score -= 35

    if char_count >= 180 and whitespace_ratio < 0.02:
        flags.append("baixa-separacao")
        score -= 30

    if longest_token >= PAGE_TEXT_LONG_TOKEN_THRESHOLD and word_count <= 8:
        flags.append("token-muito-longo")
        score -= 25

    if avg_word_len >= 18 and word_count >= 4:
        flags.append("palavras-coladas")
        score -= 18

    if alpha_count == 0 and digit_count > 0 and char_count > 50:
        flags.append("quase-so-numeros")
        score -= 12

    score = max(0, min(100, int(score)))
    return {
        "char_count": char_count,
        "word_count": word_count,
        "whitespace_ratio": whitespace_ratio,
        "suspicious_ratio": suspicious_ratio,
        "longest_token": longest_token,
        "avg_word_len": avg_word_len,
        "quality_score": score,
        "flags": flags,
        "needs_ocr": bool(char_count == 0 or score < PAGE_TEXT_QUALITY_MIN_SCORE),
    }


def detect_structure_hints(text):
    """Infer coarse structures useful for organizing extracted documents."""
    raw_text = text or ""
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    hints = []
    table_like_lines = sum(1 for line in lines if ("\t" in line) or (line.count(" | ") >= 2))
    timestamp_lines = sum(1 for line in lines if re.search(r"\b\d{1,2}:\d{2}\b", line))
    attachment_lines = sum(1 for line in lines if re.search(r"\b(anexo|anexa|foto|imagem|print|captura|evid[eê]ncia)\b", line, re.IGNORECASE))
    numbered_lines = sum(1 for line in lines if re.match(r"^\d+[.)-]\s+\S+", line))

    if table_like_lines >= 2:
        hints.append("table-like")
    if timestamp_lines >= 2:
        hints.append("chat-like")
    if attachment_lines >= 1:
        hints.append("attachment-mention")
    if numbered_lines >= 3:
        hints.append("list-like")
    return hints


def _normalized_line(text):
    text = unicodedata.normalize("NFKD", text or "").casefold()
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^\w]+", " ", text).strip()


def _is_ocr_line_already_native(normalized, native_flat, native_compact, native_lines, native_tokens):
    if normalized == native_flat or (len(normalized) >= 8 and normalized in native_flat):
        return True
    compact = normalized.replace(" ", "")
    if len(compact) >= 12 and compact in native_compact:
        return True

    tokens = normalized.split()
    if len(tokens) >= 4 and native_tokens:
        match = SequenceMatcher(None, tokens, native_tokens, autojunk=False).find_longest_match()
        if (match.size / len(tokens)) >= 0.82:
            return True

    for existing in native_lines:
        if normalized == existing or (len(normalized) >= 12 and normalized in existing):
            return True
        if min(len(normalized), len(existing)) >= 12:
            shorter = min(len(normalized), len(existing))
            longer = max(len(normalized), len(existing))
            if (shorter / longer) >= 0.55 and SequenceMatcher(None, normalized, existing).ratio() >= 0.90:
                return True
    return False


def merge_native_and_ocr_text(native_text, ocr_text):
    """Preserve native text and append only OCR lines that add information."""
    native_text = (native_text or "").strip()
    ocr_text = (ocr_text or "").strip()
    if not native_text:
        return ocr_text
    if not ocr_text:
        return native_text

    native_flat = _normalized_line(native_text)
    native_compact = native_flat.replace(" ", "")
    native_tokens = native_flat.split()
    native_lines = [_normalized_line(line) for line in native_text.splitlines() if _normalized_line(line)]
    additional = []
    additional_seen = set()
    for line in ocr_text.splitlines():
        cleaned = line.strip()
        normalized = _normalized_line(cleaned)
        if not normalized or normalized in additional_seen:
            continue
        if not _is_ocr_line_already_native(
            normalized, native_flat, native_compact, native_lines, native_tokens
        ):
            additional.append(cleaned)
            additional_seen.add(normalized)

    if not additional:
        return native_text

    additional_tokens = _normalized_line(" ".join(additional)).split()
    if len(additional_tokens) >= 8:
        native_counts = Counter(native_tokens)
        additional_counts = Counter(additional_tokens)
        overlap = sum(
            min(count, native_counts.get(token, 0))
            for token, count in additional_counts.items()
        )
        if overlap / len(additional_tokens) >= 0.90:
            return native_text
    return native_text + "\n\n### Conteúdo adicional detectado por OCR\n\n" + "\n".join(additional)


def choose_best_page_text(native_text, native_analysis, ocr_text, ocr_analysis, force_ocr=False, preserve_both=False):
    """Pick the best page text between native extraction and OCR output."""
    native_text = native_text or ""
    ocr_text = ocr_text or ""
    native_has_text = bool(native_text.strip())
    ocr_has_text = bool(ocr_text.strip())

    if (force_ocr or preserve_both) and native_has_text and ocr_has_text:
        merged = merge_native_and_ocr_text(native_text, ocr_text)
        return merged, "nativo+ocr", analyze_page_text_quality(merged)

    if force_ocr:
        if ocr_has_text:
            return ocr_text, "ocr", ocr_analysis
        return native_text, "nativo", native_analysis

    if not native_has_text and ocr_has_text:
        return ocr_text, "ocr", ocr_analysis
    if native_has_text and not ocr_has_text:
        return native_text, "nativo", native_analysis
    if not native_has_text and not ocr_has_text:
        return native_text, "sem-texto", native_analysis

    native_score = int((native_analysis or {}).get("quality_score", 0))
    ocr_score = int((ocr_analysis or {}).get("quality_score", 0))
    native_chars = int((native_analysis or {}).get("char_count", len(native_text.strip())))
    ocr_chars = int((ocr_analysis or {}).get("char_count", len(ocr_text.strip())))

    if (native_analysis or {}).get("needs_ocr") and ocr_has_text:
        return ocr_text, "ocr", ocr_analysis
    if ocr_score >= native_score + 10 and ocr_chars >= max(20, int(native_chars * 0.55)):
        return ocr_text, "ocr", ocr_analysis
    if ocr_chars > int(native_chars * 1.35) and ocr_score + 3 >= native_score:
        return ocr_text, "ocr", ocr_analysis
    return native_text, "nativo", native_analysis


def humanize_page_source(source):
    mapping = {
        "nativo": "Texto nativo",
        "ocr": "OCR",
        "nativo+ocr": "Texto nativo + OCR de imagens",
        "imagem-ocr": "Imagem + OCR",
        "docx": "DOCX",
        "markdown": "Markdown",
        "sem-texto": "Sem texto",
    }
    return mapping.get(source, source or "Desconhecido")


def humanize_page_flags(flags):
    flag_map = {
        "sem-texto": "sem texto",
        "texto-curto": "texto curto",
        "caracteres-suspeitos": "caracteres suspeitos",
        "poucas-palavras": "poucas palavras",
        "baixa-separacao": "baixa separacao",
        "token-muito-longo": "token muito longo",
        "palavras-coladas": "palavras coladas",
        "quase-so-numeros": "quase so numeros",
        "camada-nativa-incompleta": "camada nativa incompleta",
    }
    result = []
    for flag in flags or []:
        result.append(flag_map.get(flag, flag))
    return result


def humanize_structure_hints(hints):
    hint_map = {
        "table-like": "tabela provavel",
        "chat-like": "conversa ou print com horario",
        "attachment-mention": "mencao a anexo ou imagem",
        "list-like": "lista ou enumeracao",
    }
    result = []
    for hint in hints or []:
        result.append(hint_map.get(hint, hint))
    return result


def build_page_detail(
    page_number,
    text,
    source,
    analysis=None,
    structure_hints=None,
    image_count=0,
    image_coverage=0.0,
    ocr_image_candidate=False,
    extraction_issue=None,
    ocr_reason=None,
):
    analysis = analysis or analyze_page_text_quality(text)
    detected_hints = list(structure_hints if structure_hints is not None else detect_structure_hints(text))
    return {
        "page": page_number,
        "source": source,
        "char_count": int(analysis.get("char_count", len((text or "").strip()))),
        "quality_score": int(analysis.get("quality_score", 0)),
        "quality_flags": list(analysis.get("flags", [])),
        "needs_ocr": bool(analysis.get("needs_ocr", False)),
        "structure_hints": detected_hints,
        "image_count": int(image_count or 0),
        "image_coverage": round(float(image_coverage or 0.0), 6),
        "ocr_image_candidate": bool(ocr_image_candidate),
        "extraction_issue": extraction_issue,
        "ocr_reason": ocr_reason,
    }


def describe_page_detail(page_detail):
    if not page_detail:
        return ""
    source_label = humanize_page_source(page_detail.get("source"))
    quality_score = page_detail.get("quality_score")
    char_count = page_detail.get("char_count")
    flags = humanize_page_flags(page_detail.get("quality_flags"))
    parts = [f"Origem: {source_label}"]
    if quality_score is not None:
        parts.append(f"Qualidade: {quality_score}/100")
    if char_count is not None:
        parts.append(f"Caracteres: {char_count}")
    if flags:
        parts.append(f"Alertas: {', '.join(flags)}")
    image_count = int(page_detail.get("image_count", 0) or 0)
    if image_count:
        parts.append(f"Imagens detectadas: {image_count}")
        coverage = float(page_detail.get("image_coverage", 0.0) or 0.0)
        if coverage:
            parts.append(f"Maior imagem: {coverage * 100:.1f}% da página")
    if page_detail.get("ocr_reason"):
        parts.append(f"Motivo do OCR: {page_detail['ocr_reason']}")
    if page_detail.get("extraction_issue"):
        parts.append("Camada nativa sinalizada como incompleta")
    hints = humanize_structure_hints(page_detail.get("structure_hints"))
    if hints:
        parts.append(f"Estrutura: {', '.join(hints)}")
    return " | ".join(parts)
