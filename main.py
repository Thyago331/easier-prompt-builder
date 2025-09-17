# main.py
# =============================================================================
# easier-prompt-builder
# =============================================================================
# Aplicativo desktop para montar um prompt concatenando:
# 1) Texto do usuário
# 2) File tree textual das pastas adicionadas (itens não removidos)
# 3) Conteúdo dos arquivos selecionados
#
# Somente standard library. GUI com tkinter.
#
# Empacotamento em .exe (Windows):
#   pip install pyinstaller
#   pyinstaller --noconsole --onefile --name easier-prompt-builder main.py
# O executável ficará em dist/
# =============================================================================

import os
import sys
import time
import threading
import queue
import fnmatch
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter import scrolledtext

APP_TITLE = "easier-prompt-builder"

DEFAULT_EXTS = ".txt,.md,.py,.json,.csv,.yml,.yaml,.ini,.log,.xml,.html,.css,.js,.ts"
DEFAULT_MAX_MB = 2

REPLACEMENT_CHAR = "\ufffd"
REPLACEMENT_RATIO_THRESHOLD = 0.01
REPLACEMENT_ABS_THRESHOLD = 100

SKIP_DIRS = {
    "node_modules", ".pnpm", ".yarn", ".turbo",
    "venv", ".venv", "env", ".env", ".tox", ".mypy_cache", "__pycache__",
    ".git", ".hg", ".svn", ".idea", ".vscode", "dist", "build"
}



def rp(p):
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, p)
    return p


def now_hhmmss():
    return time.strftime("%H:%M:%S")


def norm_case_path(p):
    try:
        return os.path.normcase(os.path.abspath(os.path.normpath(p)))
    except Exception:
        return os.path.abspath(p)


def is_subpath(child, parent):
    child = norm_case_path(child)
    parent = norm_case_path(parent)
    if child == parent:
        return True
    try:
        common = os.path.commonpath([child, parent])
    except Exception:
        return False
    return common == parent


class GitIgnore:
    # Interpretador simplificado de .gitignore por raiz
    def __init__(self, root):
        self.root = root
        self.rules = []

    def load(self):
        path = os.path.join(self.root, ".gitignore")
        try:
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.rstrip("\n")
                        if not line or line.lstrip().startswith("#"):
                            continue
                        self._add_rule(line)
        except Exception:
            pass

    def _add_rule(self, line):
        neg = False
        if line.startswith("!"):
            neg = True
            line = line[1:]
        anchored = line.startswith("/")
        if anchored:
            line = line[1:]
        dir_only = line.endswith("/")
        if dir_only:
            line = line[:-1]
        patt = line.replace("\\", "/").strip()
        if not patt:
            return
        self.rules.append({
            "neg": neg,
            "pattern": patt,
            "dir_only": dir_only,
            "anchored": anchored
        })

    def match(self, relpath, is_dir):
        # Verifica se relpath (posix) é ignorado. Última regra válida vence.
        path = relpath.replace("\\", "/").strip("/")
        result = None
        for r in self.rules:
            patt = r["pattern"]
            matched = False
            if r["anchored"]:
                target = path
                if r["dir_only"]:
                    if target == patt or target.startswith(patt + "/"):
                        matched = True
                else:
                    if fnmatch.fnmatch(target, patt):
                        matched = True
            else:
                if "/" in patt:
                    if path == patt or path.startswith(patt + "/") or fnmatch.fnmatch(path, f"*{patt}*"):
                        matched = True
                else:
                    base = os.path.basename(path)
                    if fnmatch.fnmatch(base, patt):
                        matched = True
                    elif r["dir_only"]:
                        if ("/" + patt + "/") in ("/" + path + "/"):
                            matched = True
            if matched:
                result = not r["neg"]
        return bool(result)


class App(tk.Tk):
    def __init__(self):
        tk.Tk.__init__(self)
        self.title(APP_TITLE)
        
        try:
            self.iconbitmap(rp("assets/app.ico"))         
        except Exception:
            try:
                self.iconphoto(False, tk.PhotoImage(file=rp("assets/app-32x32.png")))  #
            except Exception:
                pass

        self.geometry("1200x700")
        self.minsize(1000, 600)

        self.roots = []
        self.removed_paths = set()
        self.node_path = {}
        self.node_is_dir = {}
        self.populated_nodes = set()
        self.selected_files = []
        self.selected_files_set = set()
        self.last_output = None
        self.gitignores = {}

        self.log_queue = queue.Queue()
        self.result_queue = queue.Queue()

        self._build_ui()
        self.after(100, self._process_queues)

    # ---------------------------------------------------------------------
    # UI
    # ---------------------------------------------------------------------
    def _build_ui(self):
        self.main_paned = ttk.Panedwindow(self, orient="horizontal")
        self.main_paned.pack(fill="both", expand=True)

        left_frame = ttk.Frame(self.main_paned)
        self.main_paned.add(left_frame, weight=1)

        left_buttons = ttk.Frame(left_frame)
        left_buttons.pack(fill="x", padx=6, pady=(6, 3))

        self.btn_add_folder = ttk.Button(left_buttons, text="Adicionar pasta…", command=self._on_add_folder)
        self.btn_add_folder.pack(side="left", padx=(0, 6))

        self.btn_remove_selected = ttk.Button(left_buttons, text="Remover selecionados", command=self._on_remove_selected_nodes)
        self.btn_remove_selected.pack(side="left")

        # Menu de contexto do tree
        self.tree_menu = tk.Menu(self, tearoff=0)

        tree_frame = ttk.Frame(left_frame)
        tree_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        self.tree = ttk.Treeview(tree_frame, columns=("fullpath",), displaycolumns=())
        self.tree.heading("#0", text="Arquivos e pastas")
        self.tree["selectmode"] = "extended"

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=vsb.set, xscroll=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self.tree.bind("<<TreeviewOpen>>", self._on_tree_open)
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.tree.bind("<Button-3>", self._on_tree_right_click)

        right_frame = ttk.Frame(self.main_paned)
        self.main_paned.add(right_frame, weight=2)

        top_frame = ttk.Frame(right_frame)
        top_frame.pack(fill="both", expand=True, padx=6, pady=(6, 3))

        cfg_frame = ttk.Frame(top_frame)
        cfg_frame.pack(fill="x", pady=(0, 6))

        ttk.Label(cfg_frame, text="Extensões permitidas (separadas por vírgula):").pack(side="left")
        self.entry_exts = ttk.Entry(cfg_frame)
        self.entry_exts.insert(0, DEFAULT_EXTS)
        self.entry_exts.pack(side="left", fill="x", expand=True, padx=6)

        ttk.Label(cfg_frame, text="Tamanho máx. (MB):").pack(side="left", padx=(6, 0))
        self.entry_max_mb = ttk.Entry(cfg_frame, width=6)
        self.entry_max_mb.insert(0, str(DEFAULT_MAX_MB))
        self.entry_max_mb.pack(side="left")

        ttk.Label(top_frame, text="Texto do usuário:").pack(anchor="w")
        self.user_text = scrolledtext.ScrolledText(top_frame, wrap="word", height=8)  # reduzido p/ dar espaço aos botões
        self.user_text.pack(fill="both", expand=True)

        mid_frame = ttk.Frame(right_frame)
        mid_frame.pack(fill="both", expand=True, padx=6, pady=3)

        mid_buttons = ttk.Frame(mid_frame)
        mid_buttons.pack(fill="x", pady=(0, 6))

        self.btn_add_selected_from_tree = ttk.Button(mid_buttons, text="Adicionar selecionados do tree", command=self._on_add_selected_from_tree)
        self.btn_add_selected_from_tree.pack(side="left")

        self.btn_refresh_files = ttk.Button(mid_buttons, text="Atualizar selecionados", command=self._on_refresh_selected_files)
        self.btn_refresh_files.pack(side="left", padx=6)

        self.btn_clear_list = ttk.Button(mid_buttons, text="Limpar lista", command=self._on_clear_selected_list)
        self.btn_clear_list.pack(side="left", padx=6)

        ttk.Label(mid_frame, text="Arquivos a concatenar:").pack(anchor="w")

        files_view_frame = ttk.Frame(mid_frame)
        files_view_frame.pack(fill="both", expand=True)

        self.files_view = ttk.Treeview(files_view_frame, columns=("name", "path"), show="headings", selectmode="extended")
        self.files_view.heading("name", text="Nome")
        self.files_view.heading("path", text="Caminho")
        self.files_view.column("name", width=220, anchor="w")
        self.files_view.column("path", anchor="w")

        files_vsb = ttk.Scrollbar(files_view_frame, orient="vertical", command=self.files_view.yview)
        files_hsb = ttk.Scrollbar(files_view_frame, orient="horizontal", command=self.files_view.xview)
        self.files_view.configure(yscroll=files_vsb.set, xscroll=files_hsb.set)

        self.files_view.grid(row=0, column=0, sticky="nsew")
        files_vsb.grid(row=0, column=1, sticky="ns")
        files_hsb.grid(row=1, column=0, sticky="ew")
        files_view_frame.rowconfigure(0, weight=1)
        files_view_frame.columnconfigure(0, weight=1)

        bottom_frame = ttk.Frame(right_frame)
        bottom_frame.pack(fill="both", expand=True, padx=6, pady=(3, 6))

        ttk.Label(bottom_frame, text="Log:").pack(anchor="w")
        self.log_text = scrolledtext.ScrolledText(bottom_frame, wrap="word", height=5, state="disabled")  # reduzido
        self.log_text.pack(fill="both", expand=True)

        footer = ttk.Frame(self)
        footer.pack(fill="x", padx=6, pady=6)

        self.btn_generate_copy = ttk.Button(footer, text="Gerar e copiar", command=self._on_generate_and_copy)
        self.btn_generate_copy.pack(side="left")

        self.btn_save_file = ttk.Button(footer, text="Salvar em arquivo…", command=self._on_save_to_file)
        self.btn_save_file.pack(side="left", padx=6)

        self.btn_reset_all = ttk.Button(footer, text="Limpar tudo", command=self._on_reset_all)
        self.btn_reset_all.pack(side="left", padx=6)

        self.btn_exit = ttk.Button(footer, text="Sair", command=self.destroy)
        self.btn_exit.pack(side="right")

        self.user_text.focus_set()

    # ---------------------------------------------------------------------
    # Log e filas
    # ---------------------------------------------------------------------
    def log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{now_hhmmss()}] {msg}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def tlog(self, msg):
        self.log_queue.put(("log", msg))

    def _process_queues(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                if item[0] == "log":
                    self.log(item[1])
        except queue.Empty:
            pass

        try:
            while True:
                mode, payload = self.result_queue.get_nowait()
                if mode == "copy_done":
                    content = payload
                    try:
                        norm = self._normalize_for_clipboard(content)
                        self.clipboard_clear()
                        self.clipboard_append(norm)
                        self.update()
                        self.log("Conteúdo copiado para a área de transferência.")
                    except Exception as e:
                        messagebox.showerror(APP_TITLE, f"Falha ao copiar para a área de transferência: {e}")
                elif mode == "save_done":
                    content = payload
                    file_path = filedialog.asksaveasfilename(
                        title="Salvar em arquivo",
                        defaultextension=".txt",
                        filetypes=[("Texto", "*.txt"), ("Todos os arquivos", "*.*")]
                    )
                    if file_path:
                        try:
                            with open(file_path, "w", encoding="utf-8") as f:
                                f.write(content)
                            self.log(f"Conteúdo salvo em: {file_path}")
                        except Exception as e:
                            messagebox.showerror(APP_TITLE, f"Falha ao salvar o arquivo: {e}")
                    else:
                        self.log("Salvar cancelado pelo usuário.")
                elif mode == "done_cleanup":
                    self._set_busy(False)
        except queue.Empty:
            pass

        self.after(100, self._process_queues)

    # ---------------------------------------------------------------------
    # Ações do tree
    # ---------------------------------------------------------------------
    def _on_add_folder(self):
        folder = filedialog.askdirectory(title="Selecionar pasta")
        if not folder:
            return
        folder = norm_case_path(folder)

        for root in self.roots:
            if folder == root or is_subpath(folder, root) or is_subpath(root, folder):
                self.log("Pasta ignorada por duplicidade ou sobreposição.")
                return

        if not os.path.isdir(folder):
            messagebox.showerror(APP_TITLE, "Caminho inválido.")
            return

        self.roots.append(folder)
        self._insert_root(folder)
        self._load_gitignore_for_root(folder)
        self.log(f"Pasta adicionada: {folder}")

    def _insert_root(self, root_path):
        # Mostra apenas o nome da pasta no tree; guarda caminho completo no mapa
        base = os.path.basename(root_path.rstrip("\\/")) or root_path
        node_id = self.tree.insert("", "end", text=base, open=False)
        self.node_path[node_id] = root_path
        self.node_is_dir[node_id] = True
        self._add_placeholder(node_id)

    def _add_placeholder(self, node_id):
        placeholder = self.tree.insert(node_id, "end", text="…")
        self.node_path[placeholder] = None
        self.node_is_dir[placeholder] = False

    def _on_tree_open(self, event):
        node_id = self.tree.focus()
        if not node_id:
            return
        if node_id in self.populated_nodes:
            return
        path = self.node_path.get(node_id)
        if not path or not os.path.isdir(path):
            return

        children = self.tree.get_children(node_id)
        for c in children:
            if self.node_path.get(c) is None:
                self.tree.delete(c)

        try:
            entries = []
            with os.scandir(path) as it:
                for e in it:
                    name = e.name
                    full = os.path.join(path, name)
                    try:
                        is_dir = e.is_dir(follow_symlinks=False)
                    except Exception:
                        is_dir = False
                    if self._should_skip_path(full, is_dir):
                        continue
                    entries.append((name, full, is_dir))
        except PermissionError:
            self.log("Acesso negado ao abrir diretório.")
            return
        except FileNotFoundError:
            self.log("Caminho não encontrado ao abrir diretório.")
            return
        except Exception as e:
            self.log(f"Erro ao listar diretório: {e}")
            return

        entries.sort(key=lambda x: (not x[2], x[0].lower()))

        for name, full, is_dir in entries:
            child_id = self.tree.insert(node_id, "end", text=name, open=False)
            self.node_path[child_id] = full
            self.node_is_dir[child_id] = is_dir
            if is_dir:
                self._add_placeholder(child_id)

        self.populated_nodes.add(node_id)

    def _on_tree_double_click(self, event):
        # Adiciona arquivo ao painel ao dar duplo clique
        item = self.tree.identify_row(event.y)
        if not item:
            return
        path = self.node_path.get(item)
        if not path or not os.path.isfile(path):
            return
        if self._is_removed(path):
            return
        if self._is_gitignored(path, is_dir=False):
            return
        allow_exts = self._get_allowed_exts()
        if not self._ext_allowed(path, allow_exts):
            return
        added = self._add_selected_file(path)
        if added:
            self._refresh_files_view()
            self._select_file_in_files_view(path)
            self.log(f"Arquivo adicionado: {path}")

    def _on_tree_right_click(self, event):
        # Mostra menu contextual
        item = self.tree.identify_row(event.y)
        if not item:
            return
        self.tree.selection_set(item)
        self.tree.focus(item)
        self.tree_menu.delete(0, "end")
        path = self.node_path.get(item)
        parent = self.tree.parent(item)
        is_dir = self.node_is_dir.get(item, False)

        if parent == "":  # raiz
            self.tree_menu.add_command(label="Recarregar pasta", command=lambda i=item: self._reload_node(i))
            self.tree_menu.add_command(label="Resetar itens removidos desta pasta", command=lambda i=item: self._reset_removed_for_root(i))
            self.tree_menu.add_separator()
            self.tree_menu.add_command(label="Remover pasta", command=lambda i=item: self._remove_root(i))
        else:
            if is_dir:
                self.tree_menu.add_command(label="Recarregar pasta", command=lambda i=item: self._reload_node(i))
            self.tree_menu.add_command(label="Remover do tree", command=lambda i=item: self._remove_node_only(i))

        try:
            self.tree_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.tree_menu.grab_release()

    def _reload_node(self, node_id):
        # Recarrega o conteúdo de um diretório
        if not self.node_is_dir.get(node_id, False):
            return
        for c in self.tree.get_children(node_id):
            self._delete_node_recursive(c)
        self.populated_nodes.discard(node_id)
        self._add_placeholder(node_id)
        self.tree.item(node_id, open=True)
        self.tree.focus(node_id)
        self._on_tree_open(None)
        self.log("Nó recarregado.")

    def _reset_removed_for_root(self, node_id):
        # Limpa todos os removidos pertencentes à raiz e recarrega
        root_path = self.node_path.get(node_id)
        if not root_path:
            return
        to_keep = set()
        for r in self.removed_paths:
            if not is_subpath(r, root_path):
                to_keep.add(r)
        self.removed_paths = to_keep
        self._reload_node(node_id)
        self.log("Itens removidos resetados para esta pasta.")

    def _remove_root(self, node_id):
        # Remove raiz corretamente permitindo adicioná-la novamente
        root_path = self.node_path.get(node_id)
        if not root_path:
            return
        try:
            self.roots = [r for r in self.roots if norm_case_path(r) != norm_case_path(root_path)]
            self.gitignores.pop(root_path, None)
        except Exception:
            pass
        # Remove flags de removidos sob essa raiz
        to_keep = set()
        for r in self.removed_paths:
            if not is_subpath(r, root_path):
                to_keep.add(r)
        self.removed_paths = to_keep
        # Remove nó visual
        self._delete_node_recursive(node_id)
        self.log(f"Pasta removida: {root_path}")

    def _remove_node_only(self, node_id):
        # Remove apenas do tree (marca como removido)
        path = self.node_path.get(node_id)
        if not path:
            return
        self.removed_paths.add(norm_case_path(path))
        self._delete_node_recursive(node_id)
        self.log("Item removido do tree.")

    def _on_remove_selected_nodes(self):
        # Ignora raízes aqui; usar menu de contexto
        sel = self.tree.selection()
        if not sel:
            return
        removed = 0
        roots_ignored = 0
        for node_id in sel:
            if self.tree.parent(node_id) == "":  # raiz
                roots_ignored += 1
                continue
            path = self.node_path.get(node_id)
            if not path:
                continue
            self.removed_paths.add(norm_case_path(path))
            self._delete_node_recursive(node_id)
            removed += 1
        if removed > 0:
            self.log(f"Removidos do tree: {removed}")
        if roots_ignored > 0:
            self.log("Raízes não removidas aqui. Use o menu de contexto da pasta.")

    def _delete_node_recursive(self, node_id):
        for child in self.tree.get_children(node_id):
            self._delete_node_recursive(child)
        try:
            del self.node_path[node_id]
        except Exception:
            pass
        try:
            del self.node_is_dir[node_id]
        except Exception:
            pass
        self.populated_nodes.discard(node_id)
        try:
            self.tree.delete(node_id)
        except Exception:
            pass

    # ---------------------------------------------------------------------
    # Lista de arquivos selecionados
    # ---------------------------------------------------------------------
    def _on_add_selected_from_tree(self):
        sel = self.tree.selection()
        if not sel:
            return

        added = 0
        last_added_path = None
        start = time.time()
        allow_exts = self._get_allowed_exts()

        for node_id in sel:
            path = self.node_path.get(node_id)
            if not path or self._is_removed(path):
                continue
            if os.path.isdir(path):
                for f in self._iter_files(path):
                    if self._is_removed(f):
                        continue
                    if self._is_gitignored(f, is_dir=False):
                        continue
                    if self._ext_allowed(f, allow_exts):
                        added += self._add_selected_file(f)
                        last_added_path = f
            else:
                if self._is_gitignored(path, is_dir=False):
                    continue
                if self._ext_allowed(path, allow_exts):
                    added += self._add_selected_file(path)
                    last_added_path = path

        if added > 0:
            self._refresh_files_view()
            if last_added_path:
                self._select_file_in_files_view(last_added_path)
        elapsed = time.time() - start
        self.log(f"Arquivos adicionados: {added} em {elapsed:.2f}s")

    def _on_refresh_selected_files(self):
        # Atualiza arquivos selecionados na lista (revalida existência e força releitura futura)
        items = self.files_view.selection()
        if not items:
            self.log("Selecione pelo menos um arquivo na lista.")
            return
        refreshed = 0
        missing = 0
        for iid in items:
            vals = self.files_view.item(iid, "values")
            if not vals:
                continue
            path = vals[1]
            if os.path.isfile(path):
                refreshed += 1
            else:
                missing += 1
        self.log(f"Arquivos atualizados: {refreshed} | Inexistentes: {missing}. O conteúdo será recarregado na geração.")

    def _on_clear_selected_list(self):
        self.selected_files = []
        self.selected_files_set = set()
        for iid in self.files_view.get_children():
            self.files_view.delete(iid)
        self.log("Lista de arquivos limpa.")

    def _iter_files(self, root_path):
        for dirpath, dirnames, filenames in os.walk(root_path):
            kept = []
            for d in list(dirnames):
                full = os.path.join(dirpath, d)
                if self._should_skip_path(full, True):
                    continue
                kept.append(d)
            dirnames[:] = kept
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                if self._should_skip_path(full, False):
                    continue
                yield full

    def _add_selected_file(self, path):
        p = norm_case_path(path)
        if p in self.selected_files_set:
            return 0
        self.selected_files.append(p)
        self.selected_files_set.add(p)
        return 1

    def _refresh_files_view(self):
        for iid in self.files_view.get_children():
            self.files_view.delete(iid)
        for p in self.selected_files:
            name = os.path.basename(p)
            self.files_view.insert("", "end", values=(name, p))

    def _select_file_in_files_view(self, path):
        # Seleciona e foca o item recém-adicionado na lista
        for iid in self.files_view.get_children():
            vals = self.files_view.item(iid, "values")
            if vals and vals[1] == path:
                self.files_view.selection_set(iid)
                self.files_view.focus(iid)
                self.files_view.see(iid)
                break

    # ---------------------------------------------------------------------
    # Rodapé: gerar, salvar, reset
    # ---------------------------------------------------------------------
    def _on_generate_and_copy(self):
        if not self.roots and not self.selected_files and not self.user_text.get("1.0", "end-1c").strip():
            messagebox.showinfo(APP_TITLE, "Nada a gerar.")
            return
        self._set_busy(True)
        t = threading.Thread(target=self._worker_generate, args=("copy",), daemon=True)
        t.start()

    def _on_save_to_file(self):
        if not self.roots and not self.selected_files and not self.user_text.get("1.0", "end-1c").strip():
            messagebox.showinfo(APP_TITLE, "Nada a salvar.")
            return
        self._set_busy(True)
        t = threading.Thread(target=self._worker_generate, args=("save",), daemon=True)
        t.start()

    def _on_reset_all(self):
        # Reseta todo o estado do app
        self.roots = []
        self.removed_paths = set()
        self.node_path = {}
        self.node_is_dir = {}
        self.populated_nodes = set()
        self.gitignores = {}
        for iid in self.tree.get_children(""):
            self._delete_node_recursive(iid)
        self.selected_files = []
        self.selected_files_set = set()
        for iid in self.files_view.get_children():
            self.files_view.delete(iid)
        self.user_text.delete("1.0", "end")
        self.last_output = None
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.log("Estado reiniciado.")

    def _worker_generate(self, mode):
        start = time.time()
        try:
            content = self._build_output()
            self.last_output = content
            if mode == "copy":
                self.result_queue.put(("copy_done", content))
            else:
                self.result_queue.put(("save_done", content))
            elapsed = time.time() - start
            self.tlog(f"Geração concluída em {elapsed:.2f}s")
        except Exception as e:
            self.tlog(f"Erro na geração: {e}")
            messagebox.showerror(APP_TITLE, f"Erro ao gerar conteúdo: {e}")
        finally:
            self.result_queue.put(("done_cleanup", None))

    def _set_busy(self, busy):
        state = "disabled" if busy else "normal"
        for b in (
            self.btn_add_folder,
            self.btn_remove_selected,
            self.btn_add_selected_from_tree,
            self.btn_refresh_files,
            self.btn_clear_list,
            self.btn_generate_copy,
            self.btn_save_file,
            self.btn_reset_all,
        ):
            b.configure(state=state)
        self.config(cursor="watch" if busy else "")
        self.update_idletasks()

    # ---------------------------------------------------------------------
    # Filtros e .gitignore
    # ---------------------------------------------------------------------
    def _get_allowed_exts(self):
        raw = self.entry_exts.get().strip()
        if not raw:
            return set()
        items = [x.strip().lower() for x in raw.split(",") if x.strip()]
        norm = set()
        for it in items:
            if not it.startswith("."):
                it = "." + it
            norm.add(it)
        return norm

    def _get_max_size_bytes(self):
        raw = self.entry_max_mb.get().strip()
        try:
            mb = float(raw.replace(",", "."))
        except Exception:
            mb = DEFAULT_MAX_MB
        if mb <= 0:
            mb = DEFAULT_MAX_MB
        return int(mb * 1024 * 1024)

    def _ext_allowed(self, path, allowed_exts):
        ext = os.path.splitext(path)[1].lower()
        return ext in allowed_exts if allowed_exts else True

    def _load_gitignore_for_root(self, root):
        gi = GitIgnore(root)
        gi.load()
        self.gitignores[root] = gi

    def _get_root_for_path(self, path):
        best = None
        for r in self.roots:
            if is_subpath(path, r):
                if best is None or len(r) > len(best):
                    best = r
        return best

    def _is_gitignored(self, path, is_dir):
        root = self._get_root_for_path(path)
        if not root:
            return False
        gi = self.gitignores.get(root)
        if not gi:
            return False
        rel = os.path.relpath(path, root)
        if rel == ".":
            return False
        try:
            return gi.match(rel, is_dir)
        except Exception:
            return False

    def _should_skip_name(self, name, is_dir):
        if is_dir and name in SKIP_DIRS:
            return True
        if name.startswith("."):
            return True
        return False

    def _is_removed(self, path):
        p = norm_case_path(path)
        for r in self.removed_paths:
            if is_subpath(p, r):
                return True
        return False

    def _should_skip_path(self, path, is_dir):
        name = os.path.basename(path)
        if self._is_removed(path):
            return True
        if self._should_skip_name(name, is_dir):
            return True
        if self._is_gitignored(path, is_dir):
            return True
        return False

    # ---------------------------------------------------------------------
    # File tree textual
    # ---------------------------------------------------------------------
    def _build_file_tree_text(self):
        lines = []
        for root in self.roots:
            if self._is_removed(root):
                continue
            lines.append(root)
            lines.extend(self._tree_lines_for_dir(root, prefix=""))
        return "\n".join(lines)

    def _tree_lines_for_dir(self, dir_path, prefix):
        lines = []
        try:
            entries = []
            with os.scandir(dir_path) as it:
                for e in it:
                    name = e.name
                    full = os.path.join(dir_path, name)
                    try:
                        is_dir = e.is_dir(follow_symlinks=False)
                    except Exception:
                        is_dir = False
                    if self._should_skip_path(full, is_dir):
                        continue
                    entries.append((name, full, is_dir))
        except Exception:
            return lines

        entries.sort(key=lambda x: (not x[2], x[0].lower()))
        count = len(entries)
        for i, (name, full, is_dir) in enumerate(entries):
            last = i == count - 1
            connector = "└── " if last else "├── "
            lines.append(prefix + connector + name)
            if is_dir:
                child_prefix = prefix + ("    " if last else "│   ")
                lines.extend(self._tree_lines_for_dir(full, child_prefix))
        return lines

    # ---------------------------------------------------------------------
    # Leitura de arquivos
    # ---------------------------------------------------------------------
    def _read_text_file(self, path, max_bytes):
        try:
            st = os.stat(path)
        except FileNotFoundError:
            return None, "not_found"
        except PermissionError:
            return None, "no_perm"
        except Exception:
            return None, "stat_error"

        if st.st_size > max_bytes:
            return None, "too_large"

        try:
            with open(path, "rb") as f:
                data = f.read()
        except Exception:
            return None, "read_error"

        if b"\x00" in data:
            return None, "binary_nul"

        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            return None, "decode_error"

        rep = text.count(REPLACEMENT_CHAR)
        ratio = rep / max(1, len(text))
        if rep > REPLACEMENT_ABS_THRESHOLD and ratio > REPLACEMENT_RATIO_THRESHOLD:
            return None, "binary_ratio"

        return text, "ok"

    # ---------------------------------------------------------------------
    # Concatenação
    # ---------------------------------------------------------------------
    def _build_output(self):
        start = time.time()
        user_text = self._normalize_newlines(self.user_text.get("1.0", "end-1c"))

        t0 = time.time()
        tree_text = self._build_file_tree_text()
        t1 = time.time()
        self.tlog(f"FILE TREE gerado em {(t1 - t0):.2f}s")

        allow_exts = self._get_allowed_exts()
        max_bytes = self._get_max_size_bytes()

        files_to_process = list(self.selected_files)
        total = len(files_to_process)
        ok = 0
        skipped = 0

        parts = []
        for path in files_to_process:
            if self._is_removed(path):
                skipped += 1
                self.tlog(f"Ignorado (removido): {path}")
                continue
            if self._is_gitignored(path, is_dir=False):
                skipped += 1
                self.tlog(f"Ignorado (.gitignore): {path}")
                continue
            if not self._ext_allowed(path, allow_exts):
                skipped += 1
                self.tlog(f"Ignorado (extensão não permitida): {path}")
                continue

            text, status = self._read_text_file(path, max_bytes)
            if status == "ok":
                ok += 1
                body = self._normalize_newlines(text)
                block = (
                    "\n" +
                    "=" * 80 + "\n" +
                    f" ARQUIVO: {path}\n" +
                    "=" * 80 + "\n" +
                    body
                )
                parts.append(block)
            else:
                skipped += 1
                if status == "too_large":
                    self.tlog(f"Ignorado (maior que o limite): {path}")
                elif status in ("binary_nul", "binary_ratio"):
                    self.tlog(f"Ignorado (provável binário): {path}")
                elif status == "not_found":
                    self.tlog(f"Ignorado (não encontrado): {path}")
                elif status == "no_perm":
                    self.tlog(f"Ignorado (sem permissão): {path}")
                else:
                    self.tlog(f"Ignorado ({status}): {path}")

        self.tlog(f"Arquivos processados: {ok} | Ignorados: {skipped} | Total selecionados: {total}")

        out = []
        out.append("===== TEXTO DO USUÁRIO =====")
        out.append("")
        out.append(user_text)
        out.append("")
        out.append("===== FILE TREE =====")
        out.append("")
        out.append(tree_text)
        out.append("")
        out.append("===== CONTEÚDO DE ARQUIVOS =====")
        out.append("")
        out.extend(parts)

        final_text = "\n".join(out)

        elapsed = time.time() - start
        self.tlog(f"Tamanho final: {len(final_text)} caracteres")
        self.tlog(f"Concatenação concluída em {elapsed:.2f}s")

        return final_text

    # ---------------------------------------------------------------------
    # Normalização de quebras de linha
    # ---------------------------------------------------------------------
    def _normalize_newlines(self, s):
        if s is None:
            return ""
        s = s.replace("\r\n", "\n").replace("\r", "\n")
        return s

    def _normalize_for_clipboard(self, s):
        return self._normalize_newlines(s)


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
