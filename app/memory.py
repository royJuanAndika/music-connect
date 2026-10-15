"""Memory sederhana berbasis file Markdown.

Ada 2 jenis memory:

1. ROUTINE (playlist bernama) -> data/memory/<slug>.md
   Format file routine:
       # Morning Routine
       slipknot, nirvana

       ---
       - dibuat: 2026-10-15T09:00:00
       - oleh: Roy
       - deskripsi: lagu buat pagi
       - lagu:
         - slipknot
         - nirvana

2. NOTES (catatan bebas: preferensi, fakta, apapun) -> data/memory/notes/<slug>.md
   Format file note:
       # Preferensi Roy
       ---
       - diperbarui: 2026-10-15T09:00:00
       - oleh: Roy
       - kategori: preferensi

       Suka metal & rock. Gak suka lagu galau.

Semua file plain-text markdown: gampang dibaca manusia, gampang di-edit manual,
tanpa database. data/memory/MEMORY.md merangkum routine + notes.
"""
from __future__ import annotations

import datetime as _dt
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    s = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    return s or "untitled"


@dataclass
class Routine:
    name: str
    slug: str
    queries: list[str] = field(default_factory=list)
    description: str = ""
    created_by: str = ""
    created_at: str = ""
    path: Path | None = None


@dataclass
class Note:
    key: str
    slug: str
    content: str = ""
    category: str = ""
    updated_by: str = ""
    updated_at: str = ""
    path: Path | None = None


class MemoryStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.notes_dir = self.root / "notes"
        self.notes_dir.mkdir(parents=True, exist_ok=True)

    # ---------- write ----------
    def save(
        self,
        name: str,
        queries: list[str],
        description: str = "",
        created_by: str = "",
    ) -> Routine:
        slug = slugify(name)
        now = _dt.datetime.now().isoformat(timespec="seconds")
        path = self.root / f"{slug}.md"
        r = Routine(
            name=name.strip(),
            slug=slug,
            queries=[q.strip() for q in queries if q and q.strip()],
            description=description.strip(),
            created_by=created_by,
            created_at=now,
            path=path,
        )
        path.write_text(self._render(r), encoding="utf-8")
        self.write_index()
        log.info("Routine disimpan: %s (%d lagu)", slug, len(r.queries))
        return r

    def delete(self, name: str) -> bool:
        slug = slugify(name)
        path = self.root / f"{slug}.md"
        if path.exists():
            path.unlink()
            self.write_index()
            return True
        return False

    # ---------- read ----------
    def get(self, name: str) -> Routine | None:
        slug = slugify(name)
        path = self.root / f"{slug}.md"
        if not path.exists():
            return None
        return self._parse(path)

    def list_all(self) -> list[Routine]:
        out: list[Routine] = []
        for p in sorted(self.root.glob("*.md")):
            if p.name.lower() == "memory.md":
                continue
            try:
                out.append(self._parse(p))
            except Exception as exc:
                log.warning("Gagal parse routine %s: %s", p.name, exc)
        return out

    # ---------- internal ----------
    def _render(self, r: Routine) -> str:
        lines = [f"# {r.name}", ""]
        if r.description:
            lines.append(f"_{r.description}_")
            lines.append("")
        if r.queries:
            lines.append(", ".join(r.queries))
            lines.append("")
        lines.append("---")
        lines.append(f"- dibuat: {r.created_at}")
        lines.append(f"- oleh: {r.created_by}")
        lines.append(f"- deskripsi: {r.description}")
        lines.append("- lagu:")
        for q in r.queries:
            lines.append(f"  - {q}")
        lines.append("")
        return "\n".join(lines)

    def _parse(self, path: Path) -> Routine:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        name = path.stem.replace("-", " ").title()
        queries: list[str] = []
        description = ""
        created_by = ""
        created_at = ""

        if lines and lines[0].startswith("# "):
            name = lines[0][2:].strip()

        in_songs = False
        for ln in lines:
            low = ln.strip().lower()
            if low.startswith("- dibuat:"):
                created_at = ln.split(":", 1)[1].strip()
            elif low.startswith("- oleh:"):
                created_by = ln.split(":", 1)[1].strip()
            elif low.startswith("- deskripsi:"):
                description = ln.split(":", 1)[1].strip()
            elif low.startswith("- lagu:"):
                in_songs = True
            elif in_songs and ln.strip().startswith("- "):
                queries.append(ln.strip()[2:].strip())
            elif in_songs and ln.strip() and not ln.startswith(" "):
                in_songs = False

        # fallback: baris sebelum '---' yang berisi koma
        if not queries and "---" in text:
            head = text.split("---", 1)[0]
            for ln in head.splitlines():
                ln = ln.strip()
                if ln and not ln.startswith("#") and not ln.startswith("_") and "," in ln:
                    queries = [x.strip() for x in ln.split(",") if x.strip()]
                    break

        return Routine(
            name=name,
            slug=path.stem,
            queries=queries,
            description=description,
            created_by=created_by,
            created_at=created_at,
            path=path,
        )

    def write_index(self) -> None:
        """Tulis data/memory/MEMORY.md yang merangkum semua routine + notes."""
        routines = self.list_all()
        notes = self.list_notes()
        lines = [
            "# MEMORY",
            "",
            f"_Total: {len(routines)} routine, {len(notes)} catatan_",
            "",
            "## ROUTINE (playlist)",
            "",
        ]
        if not routines:
            lines.append("_(belum ada)_")
            lines.append("")
        for r in routines:
            lines.append(f"### {r.name}")
            if r.description:
                lines.append(f"{r.description}")
            lines.append(f"- lagu ({len(r.queries)}): {', '.join(r.queries)}")
            if r.created_at:
                lines.append(f"- dibuat: {r.created_at} oleh {r.created_by}")
            lines.append("")

        lines.append("## CATATAN")
        lines.append("")
        if not notes:
            lines.append("_(belum ada)_")
            lines.append("")
        for n in notes:
            head = f"### {n.key}"
            if n.category:
                head += f"  _(kategori: {n.category})_"
            lines.append(head)
            lines.append(n.content.strip() or "_(kosong)_")
            if n.updated_at:
                lines.append(f"- diperbarui: {n.updated_at} oleh {n.updated_by}")
            lines.append("")

        (self.root / "MEMORY.md").write_text("\n".join(lines), encoding="utf-8")

    # ================= NOTES =================
    def save_note(
        self,
        key: str,
        content: str,
        category: str = "",
        updated_by: str = "",
    ) -> Note:
        slug = slugify(key)
        now = _dt.datetime.now().isoformat(timespec="seconds")
        path = self.notes_dir / f"{slug}.md"
        n = Note(
            key=key.strip(),
            slug=slug,
            content=content.strip(),
            category=category.strip(),
            updated_by=updated_by,
            updated_at=now,
            path=path,
        )
        path.write_text(self._render_note(n), encoding="utf-8")
        self.write_index()
        log.info("Note disimpan: %s", slug)
        return n

    def get_note(self, key: str) -> Note | None:
        path = self.notes_dir / f"{slugify(key)}.md"
        if not path.exists():
            return None
        return self._parse_note(path)

    def list_notes(self) -> list[Note]:
        out: list[Note] = []
        for p in sorted(self.notes_dir.glob("*.md")):
            try:
                out.append(self._parse_note(p))
            except Exception as exc:
                log.warning("Gagal parse note %s: %s", p.name, exc)
        return out

    def delete_note(self, key: str) -> bool:
        path = self.notes_dir / f"{slugify(key)}.md"
        if path.exists():
            path.unlink()
            self.write_index()
            return True
        return False

    def _render_note(self, n: Note) -> str:
        lines = [f"# {n.key}", "---"]
        lines.append(f"- diperbarui: {n.updated_at}")
        lines.append(f"- oleh: {n.updated_by}")
        if n.category:
            lines.append(f"- kategori: {n.category}")
        lines.append("")
        lines.append(n.content)
        lines.append("")
        return "\n".join(lines)

    def _parse_note(self, path: Path) -> Note:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        key = path.stem.replace("-", " ").title()
        updated_by = ""
        updated_at = ""
        category = ""

        if lines and lines[0].startswith("# "):
            key = lines[0][2:].strip()

        # konten = setelah baris '---' dan blok metadata '- ...'
        content_lines: list[str] = []
        seen_sep = False
        for ln in lines[1:]:
            low = ln.strip().lower()
            if not seen_sep and low == "---":
                seen_sep = True
                continue
            if seen_sep and low.startswith("- diperbarui:"):
                updated_at = ln.split(":", 1)[1].strip()
            elif seen_sep and low.startswith("- oleh:"):
                updated_by = ln.split(":", 1)[1].strip()
            elif seen_sep and low.startswith("- kategori:"):
                category = ln.split(":", 1)[1].strip()
            elif seen_sep and low and not (low.startswith("- ") and ":" in ln and len(content_lines) == 0):
                content_lines.append(ln)
            elif seen_sep and content_lines:
                content_lines.append(ln)

        return Note(
            key=key,
            slug=path.stem,
            content="\n".join(content_lines).strip(),
            category=category,
            updated_by=updated_by,
            updated_at=updated_at,
            path=path,
        )
