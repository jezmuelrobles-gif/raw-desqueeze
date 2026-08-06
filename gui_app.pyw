"""Desktop GUI for the desqueeze tool: pick a folder, it desqueezes everything
in it automatically to a "desqueezed" subfolder. No console window (.pyw).
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from desqueeze.pipeline import process_file
from desqueeze.raw_io import find_raw_files

SQUEEZE_FACTOR = 1.33
FORMATS = {"tiff"}


class DesqueezeApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("RAW Desqueeze")
        root.geometry("640x420")
        root.minsize(480, 320)

        self._events: queue.Queue = queue.Queue()
        self._running = False

        top = tk.Frame(root, padx=12, pady=12)
        top.pack(fill="x")

        self.select_btn = tk.Button(
            top, text="Select Shoot Folder...", command=self.on_select_folder,
            font=("Segoe UI", 11), padx=10, pady=6,
        )
        self.select_btn.pack(side="left")

        self.overwrite_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            top, text="Overwrite existing outputs", variable=self.overwrite_var,
        ).pack(side="left", padx=(16, 0))

        self.recursive_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            top, text="Include subfolders", variable=self.recursive_var,
        ).pack(side="left", padx=(16, 0))

        self.dng_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            top, text="Also export DNG", variable=self.dng_var,
        ).pack(side="left", padx=(16, 0))

        self.folder_label = tk.Label(root, text="No folder selected.", anchor="w", padx=12)
        self.folder_label.pack(fill="x")

        self.progress = ttk.Progressbar(root, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", padx=12, pady=(6, 0))

        self.status_label = tk.Label(root, text="", anchor="w", padx=12)
        self.status_label.pack(fill="x", pady=(2, 6))

        log_frame = tk.Frame(root)
        log_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        scrollbar = tk.Scrollbar(log_frame)
        scrollbar.pack(side="right", fill="y")
        self.log = tk.Text(
            log_frame, wrap="none", yscrollcommand=scrollbar.set,
            font=("Consolas", 9), state="disabled", bg="#111", fg="#ddd",
        )
        self.log.pack(fill="both", expand=True)
        scrollbar.config(command=self.log.yview)

        self.open_folder_btn = tk.Button(
            root, text="Open Output Folder", command=self.on_open_output,
            state="disabled",
        )
        self.open_folder_btn.pack(pady=(0, 12))

        self._out_dir: Path | None = None
        self.root.after(100, self._poll_events)

    def _append_log(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def on_select_folder(self) -> None:
        if self._running:
            return
        folder = filedialog.askdirectory(title="Select folder with RAW files")
        if not folder:
            return
        self.start_batch(Path(folder))

    def on_open_output(self) -> None:
        if self._out_dir and self._out_dir.exists():
            os.startfile(str(self._out_dir))

    def start_batch(self, folder: Path) -> None:
        self._running = True
        self.select_btn.config(state="disabled")
        self.open_folder_btn.config(state="disabled")
        self.folder_label.config(text=f"Folder: {folder}")
        self.status_label.config(text="Scanning for RAW files...")
        self.progress.config(value=0)
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

        formats = set(FORMATS)
        if self.dng_var.get():
            formats.add("dng")

        thread = threading.Thread(
            target=self._run_batch,
            args=(folder, self.overwrite_var.get(), self.recursive_var.get(), formats),
            daemon=True,
        )
        thread.start()

    def _run_batch(self, folder: Path, overwrite: bool, recursive: bool, formats: set) -> None:
        out_dir = folder / "desqueezed"
        out_dir.mkdir(parents=True, exist_ok=True)
        supported, skipped = find_raw_files(folder, recursive=recursive)
        total = len(supported)
        self._events.put(("log", f"Found {total} RAW file(s), {len(skipped)} skipped (unsupported)."))
        self._events.put(("total", total))

        succeeded = failed = skip_existing = 0
        for i, path in enumerate(supported, 1):
            result = process_file(path, out_dir, SQUEEZE_FACTOR, formats, overwrite)
            if result.status == "success":
                succeeded += 1
                orig = f"{result.original_size[0]}x{result.original_size[1]}" if result.original_size else "?"
                out = f"{result.output_size[0]}x{result.output_size[1]}" if result.output_size else "?"
                self._events.put(("log", f"[{i}/{total}] OK    {path.name}  {orig} -> {out}"))
            elif result.status == "skipped":
                skip_existing += 1
                self._events.put(("log", f"[{i}/{total}] SKIP  {path.name}  already exists"))
            else:
                failed += 1
                self._events.put(("log", f"[{i}/{total}] FAIL  {path.name}  {result.error}"))
            for warning in result.warnings:
                self._events.put(("log", f"          WARN  {warning}"))
            self._events.put(("progress", i))

        summary = (
            f"Done: {succeeded} succeeded, {failed} failed, "
            f"{skip_existing + len(skipped)} skipped."
        )
        self._events.put(("log", summary))
        self._events.put(("done", (out_dir, summary)))

    def _poll_events(self) -> None:
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "total":
                    self.progress.config(maximum=max(payload, 1))
                elif kind == "progress":
                    self.progress.config(value=payload)
                    self.status_label.config(text=f"Processing {payload}/{int(self.progress['maximum'])}...")
                elif kind == "done":
                    out_dir, summary = payload
                    self._out_dir = out_dir
                    self._running = False
                    self.select_btn.config(state="normal")
                    self.open_folder_btn.config(state="normal")
                    self.status_label.config(text=summary)
                    messagebox.showinfo("Desqueeze complete", f"{summary}\n\nOutput folder:\n{out_dir}")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)


def main() -> None:
    root = tk.Tk()
    DesqueezeApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
