"""Reusable CustomTkinter widget builders used by the main window.

Each helper takes the colors it needs explicitly (instead of relying on
imported constants) so it can be unit-tested or reused with a different
palette without dragging in the rest of the UI module.
"""

import os

import customtkinter as ctk


def validate_path(path):
    """Return path if it exists on disk, else None.

    Used to clean up stale persisted settings (an input directory that the
    user deleted between sessions) before they confuse the rest of the UI.
    """
    if path and os.path.exists(path):
        return path
    return None


def make_section(parent, title, *, fg_color, border_color, text_color, font):
    """A bordered card with a bold title -- the basic layout block."""
    frame = ctk.CTkFrame(
        parent,
        fg_color=fg_color,
        border_width=1,
        border_color=border_color,
        corner_radius=16,
    )
    frame.pack(fill="x", padx=14, pady=9)
    ctk.CTkLabel(
        frame,
        text=title,
        font=font,
        text_color=text_color,
    ).pack(anchor="w", padx=14, pady=(10, 4))
    return frame


def make_path_label(parent, text, *, fg_color, text_color):
    """A pill-shaped label used to display a chosen file/folder path."""
    label = ctk.CTkLabel(
        parent,
        text=text,
        anchor='w',
        fg_color=fg_color,
        text_color=text_color,
        corner_radius=11,
        height=36,
    )
    label.pack(fill="x", padx=14, pady=(4, 12))
    return label


def make_badge(parent, text, ok=True, *, fg_color, text_color, font):
    """A small status pill ('OK' green or 'WARN' red)."""
    label = ctk.CTkLabel(
        parent,
        text=text,
        fg_color=fg_color,
        text_color=text_color,
        corner_radius=10,
        height=28,
        font=font,
    )
    label.pack(side="left", padx=(0, 8), pady=4)
    return label


def add_tip(parent, text, *, root, fg_color, text_color, secondary_fg,
            secondary_hover, font):
    """An inline 'i' button that pops a tooltip with explanatory text on hover.

    root: the Toplevel/root window used to anchor the tooltip placement.
    """
    btn = ctk.CTkButton(
        parent,
        text="i",
        width=22,
        height=22,
        corner_radius=11,
        font=font,
        fg_color=secondary_fg,
        hover_color=secondary_hover,
    )
    tip = {"win": None}

    def show_tip(_event=None):
        if tip["win"] is not None:
            return
        w = ctk.CTkToplevel(root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        lbl = ctk.CTkLabel(
            w,
            text=text,
            fg_color=fg_color,
            text_color=text_color,
            corner_radius=8,
            padx=8,
            pady=6,
            wraplength=320,
            justify="left",
        )
        lbl.pack()
        x = btn.winfo_rootx() + 26
        y = btn.winfo_rooty() + 22
        w.geometry(f"+{x}+{y}")
        tip["win"] = w

    def hide_tip(_event=None):
        if tip["win"] is not None:
            tip["win"].destroy()
            tip["win"] = None

    btn.bind("<Enter>", show_tip)
    btn.bind("<Leave>", hide_tip)
    return btn


def configure_textbox_scroll_passthrough(textbox_widget, *, main_scroll,
                                          robust_mouse_wheel_all):
    """Bind wheel events on a readonly Textbox so scrolling the log panel
    scrolls the parent CTkScrollableFrame, not the Textbox itself.

    Without this, hovering over the log area 'steals' scroll events and the
    user has to mouse outside the textbox to keep scrolling the UI.

    main_scroll: the parent CTkScrollableFrame (has _mouse_wheel_all).
    robust_mouse_wheel_all: monkey-patched version that handles macOS
        trackpad deltas. Used as a fallback if the stock one fails.
    """
    if textbox_widget is None:
        return

    def _event_has_scroll_payload(event):
        try:
            delta = int(getattr(event, "delta", 0) or 0)
            if delta != 0:
                return True
        except Exception:
            pass
        return getattr(event, "num", None) in (4, 5)

    def _forward_to_main_scroll(event):
        if not _event_has_scroll_payload(event):
            return None
        handled = False
        try:
            main_scroll._mouse_wheel_all(event)
            handled = True
        except Exception:
            try:
                robust_mouse_wheel_all(main_scroll, event)
                handled = True
            except Exception:
                pass
        return "break" if handled else None

    targets = [textbox_widget]
    inner_text = getattr(textbox_widget, "_textbox", None)
    if inner_text is not None and inner_text not in targets:
        targets.append(inner_text)
    for target in targets:
        try:
            target.bind("<MouseWheel>", _forward_to_main_scroll, add="+")
            target.bind("<Button-4>", _forward_to_main_scroll, add="+")
            target.bind("<Button-5>", _forward_to_main_scroll, add="+")
        except Exception:
            pass