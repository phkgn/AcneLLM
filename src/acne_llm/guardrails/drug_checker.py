"""Drug interaction checker -- YAML primary + OpenFDA API fallback.

Su dung:
    checker = DrugChecker("config/drugs_acne.yaml")
    warnings = checker.check(["isotretinoin", "doxycycline"], context)
    for w in warnings:
        print(w.warning_vi)
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from loguru import logger


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class DrugWarning:
    drug_name: str                    # ten thuoc nguoi dung nhap
    matched_drug: str                 # ten chuan trong DB
    category: str                     # loai thuoc
    pregnancy_category: str           # A/B/C/D/X/N
    contraindications_triggered: list[str] = field(default_factory=list)
    interactions_triggered: list[str] = field(default_factory=list)
    warning_vi: str = ""
    source: str = "local"             # "local" | "openfda"
    severity: str = "moderate"        # "high" | "moderate" | "low"

    @property
    def is_critical(self) -> bool:
        return self.severity == "high" or self.pregnancy_category == "X"


# ── DrugChecker ───────────────────────────────────────────────────────────────

_PREGNANT_FLAGS = {"pregnant", "is_pregnant"}
_BREASTFEEDING_FLAGS = {"breastfeeding", "is_breastfeeding"}


class DrugChecker:
    """Kiem tra tuong tac thuoc va chong chi dinh cho benh nhan mun.

    Flow:
      1. Normalize ten thuoc nguoi dung nhap
      2. Tim trong YAML local (fast path)
      3. Neu khong co -> goi OpenFDA API (fallback, cached 24h)
      4. Tra ve list DrugWarning
    """

    def __init__(self, yaml_path: str) -> None:
        self._path = yaml_path
        self._db: list[dict] = []
        self._load_yaml()

    # -- Loading & normalization -----------------------------------------------

    def _load_yaml(self) -> None:
        path = Path(self._path)
        if not path.exists():
            logger.warning(f"[DrugChecker] YAML not found: {path}")
            return
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self._db = data.get("drugs", [])
        logger.info(f"[DrugChecker] Loaded {len(self._db)} drug entries from {path}")

    @staticmethod
    def _normalize(name: str) -> str:
        """Lowercase, strip dau, xoa ky tu dac biet."""
        n = name.lower().strip()
        # Xoa dau tieng Viet don gian
        for src, dst in [
            ("kem", "kem"), ("ke m", "kem"),
        ]:
            n = n.replace(src, dst)
        n = re.sub(r"[^\w\s-]", "", n)
        n = re.sub(r"\s+", " ", n).strip()
        return n

    def _find_in_db(self, drug_input: str) -> Optional[dict]:
        """Tim entry trong YAML khop voi ten thuoc."""
        normalized = self._normalize(drug_input)
        for entry in self._db:
            for name in entry.get("names", []):
                if self._normalize(name) in normalized or normalized in self._normalize(name):
                    return entry
        return None

    # -- Context flags ---------------------------------------------------------

    @staticmethod
    def _context_flags(context) -> set[str]:
        """Chuyen UserContext thanh tap flags de match voi contraindications."""
        flags: set[str] = set()
        if context is None:
            return flags
        # Support both dict and object
        get = (lambda k: context.get(k)) if isinstance(context, dict) else (lambda k: getattr(context, k, None))

        if get("is_pregnant"):
            flags.add("pregnant")
        if get("is_breastfeeding"):
            flags.add("breastfeeding")
        age = get("age")
        if age is not None:
            if age < 8:
                flags.add("age_under_8")
            if age < 12:
                flags.add("age_under_12")
        sex = (get("sex") or "").lower()
        if sex == "male":
            flags.add("male_patient_acne_use")
        return flags

    # -- OpenFDA fallback ------------------------------------------------------

    def _query_openfda(self, drug_name: str) -> Optional[str]:
        """Goi OpenFDA label API, tra ve warning text hoac None.
        Ket qua duoc cache 24h boi diskcache (neu co).
        """
        from ..cache import get_cache, _make_key
        import pickle

        CACHE_KEY = f"openfda_v1:{self._normalize(drug_name)}"
        cache = get_cache()
        if cache is not None:
            try:
                hit = cache.get(CACHE_KEY)
                if hit is not None:
                    logger.debug(f"[DrugChecker] OpenFDA cache HIT: {drug_name}")
                    return pickle.loads(hit)
            except Exception:
                pass

        result = self._fetch_openfda(drug_name)

        if cache is not None:
            try:
                cache.set(CACHE_KEY, pickle.dumps(result), expire=86400)  # 24h
            except Exception:
                pass
        return result

    @staticmethod
    def _fetch_openfda(drug_name: str) -> Optional[str]:
        """HTTP call toi OpenFDA drug label API."""
        try:
            import httpx
            url = "https://api.fda.gov/drug/label.json"
            params = {
                "search": f'openfda.generic_name:"{drug_name}"',
                "limit": 1,
            }
            r = httpx.get(url, params=params, timeout=5.0)
            if r.status_code != 200:
                return None
            results = r.json().get("results", [])
            if not results:
                return None
            label = results[0]
            # Lay cac section quan trong nhat
            parts = []
            for section in ["warnings", "contraindications", "drug_interactions", "pregnancy"]:
                text = label.get(section)
                if isinstance(text, list) and text:
                    parts.append(text[0][:500])
            return " | ".join(parts) if parts else None
        except Exception as e:
            logger.debug(f"[DrugChecker] OpenFDA fetch failed for '{drug_name}': {e}")
            return None

    # -- Main check method -----------------------------------------------------

    def check(
        self,
        medications: list[str],
        context=None,
    ) -> list[DrugWarning]:
        """Kiem tra danh sach thuoc vs context, tra ve list DrugWarning.

        Args:
            medications: ten thuoc nguoi dung nhap (co the viet tat, khong dau)
            context: UserContext object hoac dict voi is_pregnant, is_breastfeeding, age, sex
        """
        if not medications:
            return []

        ctx_flags = self._context_flags(context)
        warnings: list[DrugWarning] = []
        checked_drugs = set()

        for med in medications:
            normalized = self._normalize(med)
            if normalized in checked_drugs:
                continue
            checked_drugs.add(normalized)

            entry = self._find_in_db(med)
            if entry is not None:
                w = self._build_warning_from_entry(entry, med, ctx_flags, medications)
                if w is not None:
                    warnings.append(w)
            else:
                # Fallback OpenFDA
                logger.debug(f"[DrugChecker] '{med}' not in local DB, trying OpenFDA")
                fda_text = self._query_openfda(med)
                if fda_text:
                    w = self._build_warning_from_fda(med, fda_text, ctx_flags)
                    if w is not None:
                        warnings.append(w)

        # Kiem tra tuong tac giua cac thuoc trong danh sach
        interaction_warnings = self._check_cross_interactions(medications, warnings)
        warnings.extend(interaction_warnings)

        return warnings

    def _build_warning_from_entry(
        self,
        entry: dict,
        drug_input: str,
        ctx_flags: set[str],
        all_meds: list[str],
    ) -> Optional[DrugWarning]:
        """Tao DrugWarning tu YAML entry neu co vi pham."""
        contraindications = entry.get("contraindications", [])
        interactions = entry.get("interactions", [])
        preg_cat = entry.get("pregnancy_category", "N")

        triggered_contra = [c for c in contraindications if c in ctx_flags]
        # Kiem tra tuong tac voi cac thuoc khac trong danh sach
        triggered_inter = []
        for inter in interactions:
            for other_med in all_meds:
                if self._normalize(inter) in self._normalize(other_med) or \
                   self._normalize(other_med) in self._normalize(inter):
                    triggered_inter.append(f"{drug_input} + {other_med}")

        if not triggered_contra and not triggered_inter:
            # Khong co gi dac biet nhung van warn cho thuoc pregnancy X
            if preg_cat != "X" or "pregnant" not in ctx_flags:
                return None

        # Severity
        severity = "low"
        if preg_cat == "X" or "pregnant" in triggered_contra:
            severity = "high"
        elif "breastfeeding" in triggered_contra or triggered_inter:
            severity = "moderate"

        matched_name = entry["names"][0] if entry.get("names") else drug_input

        return DrugWarning(
            drug_name=drug_input,
            matched_drug=matched_name,
            category=entry.get("category", "unknown"),
            pregnancy_category=preg_cat,
            contraindications_triggered=triggered_contra,
            interactions_triggered=triggered_inter,
            warning_vi=entry.get("warnings_vi", "").strip(),
            source="local",
            severity=severity,
        )

    @staticmethod
    def _build_warning_from_fda(
        drug_name: str,
        fda_text: str,
        ctx_flags: set[str],
    ) -> Optional[DrugWarning]:
        """Tao DrugWarning tu OpenFDA text khi co keyword nguy hiem."""
        text_lower = fda_text.lower()
        # Chi warn neu co keyword lien quan den context hien tai
        should_warn = False
        if "pregnant" in ctx_flags and any(
            kw in text_lower for kw in ["pregnan", "fetal", "embryo", "teratog"]
        ):
            should_warn = True
        if "breastfeeding" in ctx_flags and any(
            kw in text_lower for kw in ["breast", "lactat", "nursing", "milk"]
        ):
            should_warn = True

        if not should_warn:
            return None

        # Trich xuat phan ngan nhat de hien thi
        warning_vi = (
            f"[FDA] Canh bao voi {drug_name}: {fda_text[:300]}..."
        )
        return DrugWarning(
            drug_name=drug_name,
            matched_drug=drug_name,
            category="unknown",
            pregnancy_category="N",
            contraindications_triggered=list(ctx_flags),
            warning_vi=warning_vi,
            source="openfda",
            severity="moderate",
        )

    def _check_cross_interactions(
        self,
        medications: list[str],
        existing_warnings: list[DrugWarning],
    ) -> list[DrugWarning]:
        """Kiem tra cac tuong tac thuoc-thuoc chua duoc bat o buoc truoc."""
        extra: list[DrugWarning] = []
        already_flagged = {
            inter
            for w in existing_warnings
            for inter in w.interactions_triggered
        }
        # Tranh dup: kiem tra cap (A,B) khong lap lai (B,A)
        meds = list(medications)
        for i, med_a in enumerate(meds):
            entry_a = self._find_in_db(med_a)
            if entry_a is None:
                continue
            for med_b in meds[i + 1:]:
                flag = f"{med_a} + {med_b}"
                flag_rev = f"{med_b} + {med_a}"
                if flag in already_flagged or flag_rev in already_flagged:
                    continue
                for inter in entry_a.get("interactions", []):
                    if self._normalize(inter) in self._normalize(med_b) or \
                       self._normalize(med_b) in self._normalize(inter):
                        matched = entry_a["names"][0] if entry_a.get("names") else med_a
                        extra.append(DrugWarning(
                            drug_name=med_a,
                            matched_drug=matched,
                            category=entry_a.get("category", "unknown"),
                            pregnancy_category=entry_a.get("pregnancy_category", "N"),
                            interactions_triggered=[flag],
                            warning_vi=(
                                f"Canh bao tuong tac: {med_a} + {med_b}. "
                                + entry_a.get("warnings_vi", "").strip()
                            ),
                            source="local",
                            severity="moderate",
                        ))
                        break
        return extra

    def format_warnings_for_prompt(self, warnings: list[DrugWarning]) -> str:
        """Dinh dang list DrugWarning thanh text inject vao system prompt."""
        if not warnings:
            return ""
        lines = ["[CANH BAO THUOC]"]
        for w in warnings:
            prefix = "NGUY HIEM CAO" if w.is_critical else "Chu y"
            lines.append(f"- [{prefix}] {w.warning_vi}")
        return "\n".join(lines)
