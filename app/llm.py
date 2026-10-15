"""Wrapper OpenRouter chat completions dengan tool-calling loop.

Model gratis di OpenRouter (mis. llama-3.3-70b-instruct:free) mendukung
OpenAI-style tool calling. Kita kirim daftar tool, loop sampai model berhenti
memanggil tool, lalu ambil jawaban teksnya.
"""
from __future__ import annotations

import asyncio
import json
import logging

import httpx

from .config import Settings
from .tools import TOOLS_BY_NAME, ToolContext, openai_tool_schemas

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5

SYSTEM_PROMPT = (
    "Kamu adalah asisten DJ Telegram untuk sebuah pemutar Spotify di sebuah grup. "
    "Bantu pengguna mencari lagu, menambahkan ke queue, melihat queue, menghapus "
    "dari queue, dan mengontrol pemutaran. "
    "Gunakan tool yang tersedia untuk melakukan aksi nyata; jangan mengarang hasil. "
    "Selalu jawab dalam Bahasa Indonesia yang santai dan singkat. "
    "Kalau pengguna minta memutar/menambahkan lagu, panggil queue_track. "
    "Kalau menambah banyak lagu, panggil queue_track sekali per lagu. "
    "Setelah aksi selesai, konfirmasi dengan ringkas (judul + artis). "
    "Kalau perlu nomor urut untuk menghapus, panggil list_queue lebih dulu. "
    "Tampilkan judul lagu dengan format *bold* markdown bila relevan.\n\n"
    "MEMORY / ROUTINE:\n"
    "- Kamu punya memory berupa 'routine' (playlist bernama yang disimpan permanen).\n"
    "- Kalau pengguna bilang 'simpan', 'ingat', 'catat', 'bikin routine', simpan "
    "pakai save_routine (kuumpulkan lagu-lagunya dari konteks/pencarian).\n"
    "- Kalau pengguna menyebut nama routine, mis. 'putar morning routine', "
    "panggil play_routine dengan nama itu.\n"
    "- Kalau pengguna tanya routine apa aja yang ada, panggil list_routines.\n"
    "- Untuk menghapus routine, panggil delete_routine.\n\n"
    "MEMORY / CATATAN BEBAS (notes):\n"
    "- Kamu juga bisa mengingat catatan apapun tentang pengguna (bukan playlist): "
    "preferensi musik, fakta tentang teman, pengingat, dll.\n"
    "- Pakai save_note untuk menyimpan, get_note untuk mengambil satu catatan, "
    "list_notes untuk melihat semua, delete_note untuk menghapus.\n"
    "- Contoh: pengguna bilang 'catat ya Roy suka metal' -> save_note(key='preferensi Roy', "
    "content='Suka metal', category='preferensi').\n"
    "- Kalau pengguna tanya 'kamu tau apa soal Roy?' atau 'catatan apa aja yang ada?', "
    "panggil list_notes (atau get_note kalau key spesifik).\n"
    "- Bedakan: ROUTINE = daftar lagu untuk diputar; NOTE = informasi bebas."
)


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = httpx.AsyncClient(timeout=45.0)

    @property
    def enabled(self) -> bool:
        return self.settings.llm_enabled

    async def _chat(self, messages: list[dict], tools: list[dict]) -> dict:
        url = f"{self.settings.openrouter_base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        # header opsional khusus OpenRouter; gateway lain (mis. 9router) bisa
        # menolak header tak dikenal, jadi hanya kirim kalau ke openrouter.ai.
        if "openrouter.ai" in self.settings.openrouter_base_url:
            headers["HTTP-Referer"] = "https://github.com/spotify-tg-bot"
            headers["X-Title"] = "Spotify Telegram Bot"
        payload = {
            "model": self.settings.openrouter_model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.3,
            "stream": False,
        }
        try:
            resp = await self._client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise LLMError(f"Koneksi ke LLM gateway gagal: {exc}") from exc

        if resp.status_code >= 400:
            raise LLMError(f"LLM gateway {resp.status_code}: {resp.text[:300]}")

        ctype = resp.headers.get("content-type", "")
        body = resp.text

        # beberapa gateway (mis. 9router/gemini) selalu balas SSE walau
        # stream=False. Kalau begitu, parsing event-stream.
        if "text/event-stream" in ctype or body.lstrip().startswith("data:"):
            return self._parse_sse(body)

        try:
            data = resp.json()
        except ValueError as exc:
            raise LLMError(
                f"Respons bukan JSON (content-type={ctype!r}): {body[:200]}"
            ) from exc
        if "choices" not in data or not data["choices"]:
            raise LLMError(f"Respons LLM aneh: {str(data)[:300]}")
        return data["choices"][0]["message"]

    @staticmethod
    def _parse_sse(body: str) -> dict:
        """Gabungkan chunk SSE jadi satu 'message' ala OpenAI."""
        content_parts: list[str] = []
        tool_calls: dict[int, dict] = {}
        for line in body.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            if delta.get("content"):
                content_parts.append(delta["content"])
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                slot = tool_calls.setdefault(
                    idx, {"id": tc.get("id", ""), "type": "function",
                          "function": {"name": "", "arguments": ""}}
                )
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["function"]["name"] += fn["name"]
                if fn.get("arguments"):
                    slot["function"]["arguments"] += fn["arguments"]

        message: dict = {"role": "assistant", "content": "".join(content_parts)}
        if tool_calls:
            message["tool_calls"] = [tool_calls[i] for i in sorted(tool_calls)]
        return message

    async def run(
        self,
        user_text: str,
        ctx: ToolContext,
        history: list[dict] | None = None,
        max_rounds: int = MAX_TOOL_ROUNDS,
    ) -> str:
        """Jalankan percakapan + tool calls. Kembalikan teks jawaban final."""
        if not self.enabled:
            raise LLMError("LLM tidak aktif (OPENROUTER_API_KEY kosong).")

        system = SYSTEM_PROMPT
        # suntik daftar routine + catatan yang ada, biar LLM tau konteksnya
        if ctx.memory is not None:
            try:
                routines = ctx.memory.list_all()
                notes = ctx.memory.list_notes()
                if routines or notes:
                    system += "\n\n=== MEMORY SAAT INI ==="
                if routines:
                    system += "\nRoutine tersimpan (nama -> jumlah lagu):"
                    for r in routines:
                        system += f"\n- {r.name} ({len(r.queries)} lagu)"
                if notes:
                    system += "\nCatatan tersimpan (key -> isi):"
                    for n in notes:
                        cat = f" [{n.category}]" if n.category else ""
                        system += f"\n- {n.key}{cat}: {n.content}"
                if routines:
                    system += (
                        "\n\nPENTING: kalau pengguna menyebut salah satu nama routine di atas "
                        "(dengan kata seperti 'putar', 'mainin', atau menyebut namanya saja), "
                        "langsung panggil play_routine dengan nama itu. Jangan tanya balik."
                    )
            except Exception as exc:  # jangan gagalkan request karena memory
                log.warning("Gagal baca memory untuk prompt: %s", exc)

        messages: list[dict] = [{"role": "system", "content": system}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_text})

        tools = openai_tool_schemas()

        for _ in range(max_rounds):
            message = await self._chat(messages, tools)
            tool_calls = message.get("tool_calls")

            # tidak ada tool call -> jawaban final
            if not tool_calls:
                return (message.get("content") or "").strip() or "(kosong)"

            # simpan pesan assistant (berisi tool_calls) ke konteks
            messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content") or "",
                    "tool_calls": tool_calls,
                }
            )

            # eksekusi tiap tool call
            for call in tool_calls:
                fn = call.get("function", {})
                name = fn.get("name", "")
                raw_args = fn.get("args") or fn.get("arguments") or "{}"
                result = await self._exec_tool(name, raw_args, ctx)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", name),
                        "name": name,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        # kehabisan ronde -> minta ringkasan tanpa tool
        messages.append(
            {
                "role": "user",
                "content": "Ringkas hasil aksi di atas dalam satu-dua kalimat.",
            }
        )
        message = await self._chat(messages, tools=[])
        return (message.get("content") or "").strip() or "(selesai)"

    async def _exec_tool(self, name: str, raw_args, ctx: ToolContext) -> dict:
        tool = TOOLS_BY_NAME.get(name)
        if tool is None:
            return {"error": f"Tool tidak dikenal: {name}"}
        try:
            if isinstance(raw_args, str):
                args = json.loads(raw_args) if raw_args.strip() else {}
            elif isinstance(raw_args, dict):
                args = raw_args
            else:
                args = {}
        except json.JSONDecodeError:
            return {"error": f"Argumen tool tidak valid: {raw_args!r}"}

        try:
            return await asyncio.to_thread(tool.runner, ctx, **args)
        except TypeError as exc:
            return {"error": f"Argumen salah untuk {name}: {exc}"}
        except Exception as exc:  # jangan biarkan tool crash mematikan bot
            log.warning("Tool %s error: %s", name, exc)
            return {"error": f"{type(exc).__name__}: {exc}"}

    async def close(self) -> None:
        await self._client.aclose()
