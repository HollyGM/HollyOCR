"""Plain-Tk fallback GUI: used on macOS system Tk builds where CustomTkinter
renders unreliably (see is_macos_legacy_tk), or as the simple/no-AI window.
"""

import os
import queue
import sys
import threading
from datetime import datetime
from pathlib import Path

from hollyocr import __build__, __version__
from hollyocr.core.extraction import find_files
from hollyocr.core.ocr import check_ocr_environment
from hollyocr.core.vision_ocr import is_vision_ocr_available
from hollyocr.gui.modern_ctk.logo import get_resource_path
from hollyocr.gui.shared import processing as gui_shared_processing
from hollyocr.utils.logging_setup import LOGGER
from hollyocr.utils.paths import ensure_dir, get_log_path
from hollyocr.utils.platform import open_path_natively, recommended_ocr_workers
from hollyocr.utils.settings import load_settings, save_settings


def choose_input_output_gui_plain_tk(default_poppler=None, default_tesseract=None):
    """Plain Tk fallback for macOS system Tk builds with broken themed rendering."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    user_settings = load_settings()
    try:
        tk_patchlevel = str(tk.Tcl().eval("info patchlevel"))
    except Exception:
        tk_patchlevel = "desconhecida"
    LOGGER.info("Opening plain Tk GUI. platform=%s tk=%s", sys.platform, tk_patchlevel)

    # HollyOCR: identidade tecnológica de leitura documental e processamento local.
    colors = {
        "bg": "#071722",
        "panel": "#0D2533",
        "field": "#091D29",
        "border": "#234455",
        "text": "#F3FAFC",
        "muted": "#92AAB5",
        "primary": "#55D6BE",
        "primary_hover": "#6BE5CE",
        "primary_text": "#05231E",
        "danger": "#FF6B6B",
        "success": "#55D6BE",
        "warning": "#F2B35D",
        "secondary": "#153646",
        "secondary_hover": "#1C475A",
        "disabled": "#24404C",
    }

    root = tk.Tk()
    root.title(f"HollyOCR v{__version__}")
    root.geometry("980x820")
    root.minsize(880, 720)
    root.configure(bg=colors["bg"])
    try:
        root.tk_setPalette(
            background=colors["bg"],
            foreground=colors["text"],
            activeBackground=colors["secondary_hover"],
            activeForeground=colors["text"],
            highlightColor=colors["primary"],
            selectBackground=colors["primary"],
            selectForeground=colors["primary_text"],
        )
    except Exception:
        pass
    # O dropdown do ttk.Combobox usa um Listbox Tk interno que não segue o
    # ttk.Style; sem isso ele abriria branco sobre o tema escuro.
    try:
        root.option_add("*TCombobox*Listbox.background", colors["field"])
        root.option_add("*TCombobox*Listbox.foreground", colors["text"])
        root.option_add("*TCombobox*Listbox.selectBackground", colors["primary"])
        root.option_add("*TCombobox*Listbox.selectForeground", colors["primary_text"])
    except Exception:
        pass

    sel = {
        "input": None,
        "output": user_settings.get("last_output"),
        "processing": False,
        "stop": False,
        "poppler": default_poppler,
        "tesseract": default_tesseract,
        "file_status": {},
    }
    last_input = user_settings.get("last_input")
    if last_input and os.path.exists(last_input):
        sel["input"] = last_input
    if sel["output"] and not os.path.exists(sel["output"]):
        sel["output"] = None

    ui_queue = queue.Queue()

    def post_ui(callback):
        ui_queue.put(callback)

    def drain_ui_queue():
        while True:
            try:
                callback = ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception:
                LOGGER.exception("Plain Tk GUI callback failed")
        try:
            root.after(80, drain_ui_queue)
        except Exception:
            pass

    def font(size=12, weight="normal"):
        return ("Helvetica", size, weight)

    def make_button(parent, text, command, bg=None, fg=None, width=None):
        if bg == colors["primary"]:
            button_style = "Primary.TButton"
        elif bg == colors["danger"]:
            button_style = "Danger.TButton"
        else:
            button_style = "Secondary.TButton"
        return ttk.Button(parent, text=text, command=command, width=width, style=button_style)

    def parse_positive_int_gui(value, field_label, min_value=1, max_value=None):
        try:
            parsed = int(str(value).strip())
        except Exception:
            raise ValueError(f"{field_label} deve ser um número inteiro.")
        if parsed < min_value:
            raise ValueError(f"{field_label} deve ser no mínimo {min_value}.")
        if max_value is not None and parsed > max_value:
            raise ValueError(f"{field_label} deve ser no máximo {max_value}.")
        return parsed

    def display_input():
        if isinstance(sel["input"], list):
            return f"{len(sel['input'])} arquivo(s) selecionado(s)"
        if sel["input"]:
            return str(sel["input"])
        return "(nenhum)"

    def update_path_labels():
        input_var.set(f"Entrada: {display_input()}")
        output_var.set(f"Saída: {sel['output'] or '(nenhuma)'}")

    def append_log(message):
        stamp = datetime.now().strftime("%H:%M:%S")
        txt_log.configure(state="normal")
        txt_log.insert("end", f"[{stamp}] {message}\n")
        try:
            if int(float(txt_log.index("end-1c"))) > 350:
                txt_log.delete("1.0", "50.0")
        except Exception:
            pass
        txt_log.see("end")
        txt_log.configure(state="disabled")

    def update_status(message, color=None):
        status_var.set(message)
        try:
            ent_status.configure(fg=color or colors["muted"])
        except Exception:
            pass
        append_log(message)

    def set_progress(value):
        value = max(0, min(100, int(value)))
        progress_var.set(value)
        percent_var.set(f"{value}%")

    def refresh_file_list():
        file_list.delete(0, "end")
        if not sel.get("file_status"):
            file_list.insert("end", "Nenhum arquivo em processamento.")
            return
        for path_text, status in sel["file_status"].items():
            file_list.insert("end", f"{Path(path_text).name} - {status}")

    def choose_files():
        initial_dir = str(Path.home())
        if isinstance(sel.get("input"), str):
            initial_dir = sel["input"] if os.path.isdir(sel["input"]) else os.path.dirname(sel["input"])
        paths = filedialog.askopenfilenames(
            title="Selecionar arquivos",
            initialdir=initial_dir,
            filetypes=[
                ("Documentos aceitos", "*.pdf *.docx *.md *.markdown *.png *.jpg *.jpeg"),
                ("PDF", "*.pdf"),
                ("Todos", "*.*"),
            ],
        )
        if paths:
            sel["input"] = list(paths)
            sel["file_status"] = {}
            refresh_file_list()
            update_path_labels()

    def choose_folder():
        initial_dir = sel["input"] if isinstance(sel.get("input"), str) and os.path.isdir(sel["input"]) else str(Path.home())
        path = filedialog.askdirectory(title="Selecionar pasta completa", initialdir=initial_dir)
        if path:
            sel["input"] = path
            sel["file_status"] = {}
            refresh_file_list()
            update_path_labels()

    def choose_output():
        path = filedialog.askdirectory(title="Escolher pasta de destino", initialdir=sel["output"] or str(Path.home()))
        if path:
            sel["output"] = path
            update_path_labels()

    def open_output_folder():
        if sel.get("output") and os.path.exists(sel["output"]):
            open_path_natively(sel["output"])
        else:
            messagebox.showwarning("Saída", "Escolha uma pasta de saída primeiro.")

    def open_full_log():
        log_path = get_log_path()
        if os.path.exists(log_path):
            open_path_natively(log_path)
        else:
            messagebox.showinfo("Log", "O log técnico ainda não foi criado.")

    def set_processing_state(processing):
        sel["processing"] = processing
        state = "disabled" if processing else "normal"
        widgets = [
            btn_files,
            btn_folder,
            btn_out,
            btn_clear,
            opt_lang,
            opt_format,
            opt_mode,
            opt_dpi,
            ent_threshold,
            chk_use_ocr,
            chk_force_ocr,
            chk_page_audit,
        ]
        for widget in widgets:
            try:
                widget.configure(state=state)
            except Exception:
                pass
        btn_start.configure(state="disabled" if processing else "normal")
        btn_cancel.configure(state="normal" if processing else "disabled")

    def clear_selection():
        if sel.get("processing"):
            return
        sel["input"] = None
        sel["file_status"] = {}
        set_progress(0)
        status_var.set("Aguardando seleção...")
        txt_log.configure(state="normal")
        txt_log.delete("1.0", "end")
        txt_log.insert("end", "Aguardando processamento.\n")
        txt_log.configure(state="disabled")
        refresh_file_list()
        update_path_labels()

    def cancel_processing():
        if sel.get("processing") and messagebox.askyesno("Cancelar", "Deseja cancelar o processamento atual?"):
            sel["stop"] = True
            update_status("Cancelando... aguarde.", colors["warning"])

    def process_files():
        compiled_file_handle = None
        try:
            input_arg = sel["input"]
            output_arg = sel["output"]
            if isinstance(input_arg, list):
                input_path = input_arg
                input_root = Path(input_arg[0]).parent
                saved_input = str(input_root)
            else:
                input_path = Path(input_arg)
                input_root = input_path if input_path.is_dir() else input_path.parent
                saved_input = str(input_arg)

            out_base = Path(output_arg)
            ensure_dir(out_base)

            file_paths = list(find_files(input_path))
            if not file_paths:
                post_ui(lambda: messagebox.showwarning("Entrada", "Nenhum arquivo compatível foi encontrado."))
                post_ui(lambda: update_status("Nenhum arquivo encontrado.", colors["warning"]))
                return

            output_format = sel.get("output_format", "md")
            mode = sel.get("output_mode", "individual")
            lang_code = sel.get("lang", "por")
            lang_label = sel.get("lang_label", "por (Português)")
            use_ocr = bool(sel.get("use_ocr", True))
            force_ocr = bool(sel.get("force_ocr", False)) and use_ocr
            page_audit_enabled = bool(sel.get("page_audit", False))
            ocr_threshold = int(sel.get("ocr_threshold", 30))
            ocr_dpi = int(sel.get("ocr_dpi", 300))

            save_settings({
                "last_input": saved_input,
                "last_output": str(out_base),
                "use_ocr": use_ocr,
                "force_ocr": force_ocr,
                "ocr_threshold": ocr_threshold,
                "ocr_dpi": str(ocr_dpi),
                "page_audit": page_audit_enabled,
                "lang": lang_label,
                "output_format": f"{output_format} (.{output_format})",
                "appearance_mode": "Light",
                "plain_tk_gui": True,
            })

            total = len(file_paths)
            post_ui(lambda: sel["file_status"].clear())
            for item in file_paths:
                post_ui(lambda p=str(item): sel["file_status"].update({p: "Aguardando"}))
            post_ui(refresh_file_list)
            post_ui(lambda: update_status(f"Processando {total} arquivo(s)..."))

            ocr_backend = "auto"
            worker_backend = "vision" if is_vision_ocr_available() else "tesseract"
            workers = recommended_ocr_workers(backend=worker_backend)
            if mode == "compiled":
                compiled_file_handle = gui_shared_processing.open_compiled_handle(out_base, total, output_format)

            def on_file_status(path, status):
                post_ui(lambda p=str(path), s=status: sel["file_status"].update({p: s}))
                post_ui(refresh_file_list)

            def on_progress(percent):
                post_ui(lambda v=percent: set_progress(v))

            def on_status(message):
                color = colors["warning"] if "cancel" in message.lower() else None
                post_ui(lambda m=message, c=color: update_status(m, c))

            metas = gui_shared_processing.run_conversion_loop(
                file_paths,
                out_base,
                input_root,
                poppler_path=sel["poppler"],
                tesseract_path=sel["tesseract"],
                lang=lang_code,
                ocr_threshold=ocr_threshold,
                ocr_dpi=ocr_dpi,
                use_ocr=use_ocr,
                force_ocr=force_ocr,
                page_audit_enabled=page_audit_enabled,
                output_format=output_format,
                output_mode=mode,
                workers=workers,
                should_stop=lambda: sel.get("stop", False),
                describe_file_progress=lambda i, t, p: f"[{i}/{t}] Processando {p.name}",
                make_status_callback=lambda i, t, p: (
                    lambda message: post_ui(lambda m=message, idx=i, n=p.name: update_status(f"[{idx}/{t}] {n}: {m}"))
                ),
                on_file_status=on_file_status,
                on_progress=on_progress,
                on_status=on_status,
                compiled_handle=compiled_file_handle,
                ocr_backend=ocr_backend,
            )
            compiled_file_handle = None  # already closed by run_conversion_loop

            success_count = sum(1 for meta in metas if meta.get("status") == "ok")
            failed_count = sum(1 for meta in metas if meta.get("status") == "failed")

            def finish_dialog():
                if sel.get("stop"):
                    messagebox.showinfo("Cancelado", "Processamento interrompido pelo usuário.")
                    return
                update_status(
                    "Conversão concluída com falhas. Verifique o log técnico." if failed_count else "Conversão concluída com sucesso.",
                    colors["warning"] if failed_count else colors["success"],
                )
                msg = (
                    f"{success_count} arquivo(s) convertido(s).\n"
                    f"{failed_count} arquivo(s) com falha.\n\n"
                    f"Saída:\n{out_base}\n\n"
                    "Deseja abrir a pasta de saída?"
                )
                if messagebox.askyesno("Resultado", msg):
                    open_output_folder()

            post_ui(finish_dialog)
        except Exception as exc:
            LOGGER.exception("Plain Tk GUI processing failed")
            post_ui(lambda e=exc: messagebox.showerror("Erro", f"Erro durante processamento:\n{e}"))
            post_ui(lambda e=exc: update_status(f"Erro: {e}", colors["danger"]))
        finally:
            try:
                if compiled_file_handle:
                    compiled_file_handle.close()
            except Exception:
                pass
            post_ui(lambda: set_processing_state(False))

    def start_processing():
        if not sel.get("input") or not sel.get("output"):
            messagebox.showwarning("Faltando", "Escolha entrada e pasta de saída antes de iniciar.")
            return
        if sel.get("processing"):
            return
        try:
            selected_threshold = parse_positive_int_gui(threshold_var.get(), "Limiar de OCR", 1, 5000)
            selected_dpi = parse_positive_int_gui(dpi_var.get(), "DPI do OCR", 300, 450)
        except ValueError as exc:
            messagebox.showwarning("Configuração", str(exc))
            return

        selected_lang_label = lang_var.get()
        selected_lang_code = selected_lang_label.split(" ", 1)[0].strip() or "por"
        selected_use_ocr = bool(use_ocr_var.get())
        selected_force_ocr = bool(force_ocr_var.get()) and selected_use_ocr
        if selected_use_ocr:
            issues = check_ocr_environment(sel["poppler"], sel["tesseract"], selected_lang_code)
            if issues:
                msg = (
                    "O programa pode continuar, mas OCR pode falhar em páginas escaneadas ou imagens:\n\n"
                    + "\n".join(f"- {issue}" for issue in issues)
                    + "\n\nDeseja continuar mesmo assim?"
                )
                if not messagebox.askyesno("Atenção ao OCR", msg):
                    return

        sel["output_format"] = format_var.get()
        sel["output_mode"] = mode_var.get()
        sel["lang"] = selected_lang_code
        sel["lang_label"] = selected_lang_label
        sel["use_ocr"] = selected_use_ocr
        sel["force_ocr"] = selected_force_ocr
        sel["page_audit"] = bool(page_audit_var.get())
        sel["ocr_threshold"] = selected_threshold
        sel["ocr_dpi"] = selected_dpi
        sel["stop"] = False
        set_processing_state(True)
        set_progress(0)
        append_log("Processamento iniciado.")
        threading.Thread(target=process_files, daemon=True).start()

    def bind_mousewheel(widget):
        def _wheel(event):
            delta = getattr(event, "delta", 0)
            if delta:
                if sys.platform == "darwin":
                    units = -1 if delta > 0 else 1
                else:
                    units = -int(delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
                widget.yview_scroll(units, "units")
                return "break"
            return None

        widget.bind("<MouseWheel>", _wheel)
        widget.bind("<Button-4>", lambda _event: widget.yview_scroll(-3, "units") or "break")
        widget.bind("<Button-5>", lambda _event: widget.yview_scroll(3, "units") or "break")

    root.geometry("1080x790")
    root.minsize(940, 760)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("App.TFrame", background=colors["bg"])
    style.configure("Card.TFrame", background=colors["panel"])
    style.configure("Title.TLabel", background=colors["bg"], foreground=colors["text"], font=font(23, "bold"))
    style.configure("Subtitle.TLabel", background=colors["bg"], foreground=colors["muted"], font=font(11))
    style.configure("CardTitle.TLabel", background=colors["panel"], foreground=colors["primary"], font=font(13, "bold"))
    style.configure("CardHint.TLabel", background=colors["panel"], foreground=colors["muted"], font=font(10))
    style.configure("FieldLabel.TLabel", background=colors["panel"], foreground=colors["muted"], font=font(10, "bold"))
    style.configure("Footer.TLabel", background=colors["bg"], foreground=colors["muted"], font=font(9))
    style.configure(
        "Progress.TLabel", background=colors["panel"], foreground=colors["primary"], font=font(12, "bold"),
    )
    style.configure(
        "Primary.TButton", background=colors["primary"], foreground=colors["primary_text"],
        bordercolor=colors["primary"], lightcolor=colors["primary"], darkcolor=colors["primary"],
        padding=(16, 8), font=font(11, "bold"), relief="flat",
    )
    style.map(
        "Primary.TButton",
        background=[("disabled", colors["disabled"]), ("active", colors["primary_hover"])],
        foreground=[("disabled", colors["muted"]), ("active", colors["primary_text"])],
    )
    style.configure(
        "Secondary.TButton", background=colors["secondary"], foreground=colors["text"],
        bordercolor=colors["border"], padding=(14, 7), font=font(10, "bold"), relief="flat",
    )
    style.map(
        "Secondary.TButton",
        background=[("active", colors["secondary_hover"]), ("disabled", colors["disabled"])],
    )
    style.configure(
        "Danger.TButton", background="#3A1E24", foreground="#F2A19C",
        bordercolor="#5A2C33", padding=(14, 7), font=font(10, "bold"), relief="flat",
    )
    style.map("Danger.TButton", background=[("active", "#4A242C"), ("disabled", "#25181E")])
    style.configure(
        "App.TCombobox", fieldbackground=colors["field"], background=colors["field"],
        foreground=colors["text"], bordercolor=colors["border"], arrowcolor=colors["muted"],
        padding=(10, 7), font=font(10),
    )
    style.map(
        "App.TCombobox",
        fieldbackground=[("readonly", colors["field"])],
        selectbackground=[("readonly", colors["field"])],
        selectforeground=[("readonly", colors["text"])],
    )
    style.configure(
        "App.TCheckbutton", background=colors["panel"], foreground=colors["text"],
        font=font(10), padding=(0, 4),
    )
    style.map("App.TCheckbutton", background=[("active", colors["panel"])])
    style.configure(
        "App.Horizontal.TProgressbar", troughcolor=colors["field"], background=colors["primary"],
        bordercolor=colors["field"], lightcolor=colors["primary"], darkcolor=colors["primary"], thickness=14,
    )

    lang_options = ["por (Português)", "eng (Inglês)", "spa (Espanhol)", "fra (Francês)", "deu (Alemão)", "ita (Italiano)"]
    saved_lang = user_settings.get("lang", "por (Português)")
    if saved_lang not in lang_options:
        saved_lang = "por (Português)"
    lang_var = tk.StringVar(value=saved_lang)
    format_var = tk.StringVar(value="md" if "md" in str(user_settings.get("output_format", "md")).lower() else "txt")
    mode_var = tk.StringVar(value="individual")
    saved_dpi = str(user_settings.get("ocr_dpi", "300"))
    if saved_dpi not in {"300", "400", "450"}:
        saved_dpi = "300"
    dpi_var = tk.StringVar(value=saved_dpi)
    threshold_var = tk.StringVar(value=str(user_settings.get("ocr_threshold", 30)))
    use_ocr_var = tk.IntVar(value=1 if user_settings.get("use_ocr", 1) else 0)
    force_ocr_var = tk.IntVar(value=1 if user_settings.get("force_ocr", 0) else 0)
    page_audit_var = tk.IntVar(value=1 if user_settings.get("page_audit", False) else 0)
    input_var = tk.StringVar()
    output_var = tk.StringVar()
    status_var = tk.StringVar(value="Aguardando seleção de arquivos")
    progress_var = tk.IntVar(value=0)
    percent_var = tk.StringVar(value="0%")

    app = ttk.Frame(root, style="App.TFrame", padding=(24, 16, 24, 10))
    app.pack(fill="both", expand=True)
    app.columnconfigure(0, weight=1)

    header = ttk.Frame(app, style="App.TFrame")
    header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
    header.columnconfigure(1, weight=1)

    logo_image = None
    try:
        logo_path = get_resource_path("logo_ui.png")
        if os.path.exists(logo_path):
            logo_image = tk.PhotoImage(file=logo_path)
            # O PNG é gerado em 2x para não ficar serrilhado em telas Retina.
            logo_image = logo_image.subsample(2, 2)
            tk.Label(header, image=logo_image, bg=colors["bg"], bd=0).grid(
                row=0, column=0, rowspan=2, sticky="w", padx=(0, 14)
            )
            root.iconphoto(True, logo_image)
    except Exception:
        LOGGER.exception("Failed to load brand logo for the header")
        logo_image = None

    text_column = 1 if logo_image is not None else 0
    ttk.Label(header, text="HollyOCR", style="Title.TLabel").grid(row=0, column=text_column, sticky="w")
    ttk.Label(
        header,
        text="PDFs, imagens e documentos em Markdown ou texto pesquisável • processamento local",
        style="Subtitle.TLabel",
    ).grid(row=1, column=text_column, sticky="w", pady=(4, 0))
    if text_column == 0:
        header.columnconfigure(0, weight=1)
    backend_name = "Apple Vision" if is_vision_ocr_available() else "Tesseract"
    tk.Label(
        header, text=f"  AUTO • {backend_name}  ", bg=colors["secondary"], fg=colors["primary"],
        font=font(9, "bold"), padx=8, pady=5,
    ).grid(row=0, column=2, rowspan=2, sticky="e")

    def card(parent):
        frame = tk.Frame(
            parent, bg=colors["panel"], highlightbackground=colors["border"],
            highlightcolor=colors["border"], highlightthickness=1, bd=0,
        )
        return frame

    def card_heading(parent, title, hint, row=0):
        ttk.Label(parent, text=title, style="CardTitle.TLabel").grid(row=row, column=0, columnspan=3, sticky="w")
        ttk.Label(parent, text=hint, style="CardHint.TLabel").grid(row=row + 1, column=0, columnspan=3, sticky="w", pady=(2, 8))

    paths = ttk.Frame(app, style="App.TFrame")
    paths.grid(row=1, column=0, sticky="ew", pady=(0, 14))
    paths.columnconfigure(0, weight=1, uniform="path")
    paths.columnconfigure(1, weight=1, uniform="path")

    input_card = card(paths)
    input_card.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
    input_card.columnconfigure(0, weight=1)
    input_card.columnconfigure(1, weight=1)
    card_heading(input_card, "1  Entrada", "Selecione PDFs, imagens, DOCX ou Markdown")
    btn_files = make_button(input_card, "Selecionar arquivos", choose_files, bg=colors["primary"], fg="#FFFFFF")
    btn_files.grid(row=2, column=0, sticky="ew", padx=(0, 5))
    btn_folder = make_button(input_card, "Selecionar pasta", choose_folder)
    btn_folder.grid(row=2, column=1, sticky="ew", padx=(5, 0))
    ent_input = tk.Label(
        input_card, textvariable=input_var, bg=colors["field"], fg=colors["muted"],
        anchor="w", padx=11, pady=8, font=font(9),
    )
    ent_input.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 8))
    list_wrap = tk.Frame(input_card, bg=colors["field"])
    list_wrap.grid(row=4, column=0, columnspan=2, sticky="nsew")
    list_wrap.columnconfigure(0, weight=1)
    file_list = tk.Listbox(
        list_wrap, height=2, bg=colors["field"], fg=colors["text"], borderwidth=0,
        highlightthickness=0, selectbackground=colors["primary"], selectforeground="#FFFFFF",
        font=font(9), activestyle="none",
    )
    file_list.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=6)
    file_scroll = ttk.Scrollbar(list_wrap, command=file_list.yview)
    file_scroll.grid(row=0, column=1, sticky="ns", pady=4)
    file_list.configure(yscrollcommand=file_scroll.set)
    bind_mousewheel(file_list)
    for child in input_card.winfo_children():
        info = child.grid_info()
        if int(info.get("row", 0)) < 2:
            child.grid_configure(padx=18)
    btn_files.grid_configure(padx=(18, 5))
    btn_folder.grid_configure(padx=(5, 18))
    ent_input.grid_configure(padx=18)
    list_wrap.grid_configure(padx=18, pady=(0, 18))

    output_card = card(paths)
    output_card.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
    output_card.columnconfigure(0, weight=1)
    card_heading(output_card, "2  Destino", "Escolha onde os arquivos convertidos serão salvos")
    btn_out = make_button(output_card, "Escolher pasta de destino", choose_output, bg=colors["primary"], fg="#FFFFFF")
    btn_out.grid(row=2, column=0, sticky="ew", padx=18)
    btn_open_folder = make_button(output_card, "Abrir pasta no Finder", open_output_folder)
    btn_open_folder.grid(row=3, column=0, sticky="ew", padx=18, pady=(10, 0))
    ent_output = tk.Label(
        output_card, textvariable=output_var, bg=colors["field"], fg=colors["muted"],
        anchor="w", padx=11, pady=8, font=font(9),
    )
    ent_output.grid(row=4, column=0, sticky="ew", padx=18, pady=(10, 0))
    ttk.Label(
        output_card,
        text="Pastas preservadas; conversões anteriores nunca são sobrescritas.",
        style="CardHint.TLabel", wraplength=430, justify="left",
    ).grid(row=5, column=0, sticky="w", padx=18, pady=(10, 14))
    for child in output_card.winfo_children():
        info = child.grid_info()
        if int(info.get("row", 0)) < 2:
            child.grid_configure(padx=18)

    options_card = card(app)
    options_card.grid(row=2, column=0, sticky="ew", pady=(0, 14))
    for column in range(5):
        options_card.columnconfigure(column, weight=1 if column in (0, 1) else 0)
    card_heading(options_card, "3  Extração e saída", "O modo automático já inclui OCR de toda página que contém imagens")

    ttk.Label(options_card, text="Idioma do OCR", style="FieldLabel.TLabel").grid(row=2, column=0, sticky="w", padx=(18, 8))
    ttk.Label(options_card, text="Formato", style="FieldLabel.TLabel").grid(row=2, column=1, sticky="w", padx=8)
    ttk.Label(options_card, text="DPI", style="FieldLabel.TLabel").grid(row=2, column=2, sticky="w", padx=8)
    ttk.Label(options_card, text="Limiar", style="FieldLabel.TLabel").grid(row=2, column=3, sticky="w", padx=8)
    ttk.Label(options_card, text="Agrupamento", style="FieldLabel.TLabel").grid(row=2, column=4, sticky="w", padx=(8, 18))

    opt_lang = ttk.Combobox(options_card, textvariable=lang_var, values=lang_options, state="readonly", style="App.TCombobox")
    opt_lang.grid(row=3, column=0, sticky="ew", padx=(18, 8), pady=(5, 12))
    opt_format = ttk.Combobox(options_card, textvariable=format_var, values=("md", "txt"), state="readonly", width=8, style="App.TCombobox")
    opt_format.grid(row=3, column=1, sticky="ew", padx=8, pady=(5, 12))
    opt_dpi = ttk.Combobox(
        options_card,
        textvariable=dpi_var,
        values=("300", "400", "450"),
        state="readonly",
        width=7,
        style="App.TCombobox",
    )
    opt_dpi.grid(row=3, column=2, sticky="ew", padx=8, pady=(5, 12))
    ent_threshold = tk.Entry(
        options_card, textvariable=threshold_var, bg=colors["field"], fg=colors["text"],
        insertbackground=colors["text"], relief="flat", highlightthickness=1,
        highlightbackground=colors["border"], highlightcolor=colors["primary"], font=font(10),
    )
    ent_threshold.grid(row=3, column=3, sticky="ew", padx=8, pady=(5, 12), ipady=7)
    opt_mode = ttk.Combobox(options_card, textvariable=mode_var, values=("individual", "compiled"), state="readonly", width=12, style="App.TCombobox")
    opt_mode.grid(row=3, column=4, sticky="ew", padx=(8, 18), pady=(5, 12))

    checks = ttk.Frame(options_card, style="Card.TFrame")
    checks.grid(row=4, column=0, columnspan=5, sticky="ew", padx=18, pady=(0, 10))
    checks.columnconfigure((0, 1, 2), weight=1)
    check_options = {
        "bg": colors["panel"], "fg": colors["text"], "activebackground": colors["panel"],
        "activeforeground": colors["text"], "selectcolor": colors["field"],
        "font": font(10), "anchor": "w", "borderwidth": 0, "highlightthickness": 0,
    }
    chk_use_ocr = tk.Checkbutton(checks, text="OCR automático", variable=use_ocr_var, **check_options)
    chk_use_ocr.grid(row=0, column=0, sticky="w")
    chk_force_ocr = tk.Checkbutton(checks, text="Forçar OCR integral", variable=force_ocr_var, **check_options)
    chk_force_ocr.grid(row=0, column=1, sticky="w")
    chk_page_audit = tk.Checkbutton(checks, text="Auditoria por página (.jsonl)", variable=page_audit_var, **check_options)
    chk_page_audit.grid(row=0, column=2, sticky="w")

    lower = ttk.Frame(app, style="App.TFrame")
    lower.grid(row=3, column=0, sticky="nsew", pady=(0, 14))
    lower.columnconfigure(0, weight=2, uniform="lower")
    lower.columnconfigure(1, weight=3, uniform="lower")

    env_card = card(lower)
    env_card.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
    env_card.columnconfigure(0, weight=1)
    card_heading(env_card, "Ambiente", "Dependências locais disponíveis")
    badges = ttk.Frame(env_card, style="Card.TFrame")
    badges.grid(row=2, column=0, sticky="ew", padx=18)
    badges.columnconfigure((0, 1), weight=1)
    tess_status = "Disponível" if default_tesseract else "Não detectado"
    pop_status = "Disponível" if default_poppler else "Não detectado"
    tk.Label(
        badges, text=f"●  Tesseract  {tess_status}", bg="#152F22" if default_tesseract else "#33261C",
        fg=colors["success"] if default_tesseract else colors["warning"], font=font(9, "bold"), padx=10, pady=7,
    ).grid(row=0, column=0, sticky="ew", padx=(0, 5))
    tk.Label(
        badges, text=f"●  Poppler  {pop_status}", bg="#152F22" if default_poppler else "#33261C",
        fg=colors["success"] if default_poppler else colors["warning"], font=font(9, "bold"), padx=10, pady=7,
    ).grid(row=0, column=1, sticky="ew", padx=(5, 0))
    btn_open_log = make_button(env_card, "Abrir log técnico", open_full_log)
    btn_open_log.grid(row=3, column=0, sticky="ew", padx=18, pady=(10, 14))
    for child in env_card.winfo_children():
        info = child.grid_info()
        if int(info.get("row", 0)) < 2:
            child.grid_configure(padx=18)

    progress_card = card(lower)
    progress_card.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
    progress_card.columnconfigure(0, weight=1)
    card_heading(progress_card, "Progresso", "Acompanhe extração, renderização e OCR")
    progress = ttk.Progressbar(
        progress_card, maximum=100, variable=progress_var, mode="determinate", style="App.Horizontal.TProgressbar"
    )
    progress.grid(row=2, column=0, sticky="ew", padx=(18, 8))
    lbl_percent = ttk.Label(progress_card, textvariable=percent_var, style="Progress.TLabel", width=5, anchor="e")
    lbl_percent.grid(row=2, column=1, sticky="e", padx=(0, 18))
    ent_status = tk.Label(
        progress_card, textvariable=status_var, bg=colors["field"], fg=colors["muted"],
        anchor="w", padx=10, pady=7, font=font(9),
    )
    ent_status.grid(row=3, column=0, columnspan=2, sticky="ew", padx=18, pady=(10, 8))
    log_wrap = tk.Frame(progress_card, bg=colors["field"])
    log_wrap.grid(row=4, column=0, columnspan=2, sticky="nsew", padx=18, pady=(0, 18))
    log_wrap.columnconfigure(0, weight=1)
    txt_log = tk.Text(
        log_wrap, height=2, bg=colors["field"], fg=colors["muted"], insertbackground=colors["text"],
        wrap="word", borderwidth=0, highlightthickness=0, font=("Menlo", 9), padx=8, pady=6,
    )
    txt_log.insert("end", "Aguardando processamento.\n")
    txt_log.configure(state="disabled")
    txt_log.grid(row=0, column=0, sticky="nsew")
    log_scroll = ttk.Scrollbar(log_wrap, command=txt_log.yview)
    log_scroll.grid(row=0, column=1, sticky="ns")
    txt_log.configure(yscrollcommand=log_scroll.set)
    bind_mousewheel(txt_log)
    for child in progress_card.winfo_children():
        info = child.grid_info()
        if int(info.get("row", 0)) < 2:
            child.grid_configure(padx=18)

    actions = ttk.Frame(app, style="App.TFrame")
    actions.grid(row=4, column=0, sticky="ew")
    actions.columnconfigure(0, weight=1)
    btn_start = make_button(actions, "Iniciar conversão", start_processing, bg=colors["primary"], fg="#FFFFFF")
    btn_start.grid(row=0, column=0, sticky="ew", padx=(0, 10))
    btn_cancel = make_button(actions, "Cancelar", cancel_processing, bg=colors["danger"], fg="#FFFFFF")
    btn_cancel.configure(state="disabled")
    btn_cancel.grid(row=0, column=1, padx=(0, 8))
    btn_clear = make_button(actions, "Limpar", clear_selection)
    btn_clear.grid(row=0, column=2, padx=(0, 8))
    btn_quit = make_button(actions, "Sair", root.destroy)
    btn_quit.grid(row=0, column=3)
    ttk.Label(
        actions,
        text=f"HollyOCR v{__version__} (build {__build__}) • processamento local",
        style="Footer.TLabel",
    ).grid(row=1, column=0, sticky="w", pady=(7, 0))

    refresh_file_list()
    update_path_labels()
    root.after(80, drain_ui_queue)
    root.mainloop()
    return sel["input"], sel["output"]
