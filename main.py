import os
import sqlite3
import shutil
from datetime import datetime
from pathlib import Path

from kivy.app import App
from kivy.metrics import dp
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.utils import platform

APP_NAME = "Kasir Offline Pro"

def rupiah(n):
    try:
        return "Rp {:,.0f}".format(float(n)).replace(",", ".")
    except Exception:
        return "Rp 0"

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

class Database:
    def __init__(self, path):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.init_db()

    def init_db(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT UNIQUE, name TEXT NOT NULL,
            cost REAL NOT NULL DEFAULT 0,
            price REAL NOT NULL DEFAULT 0,
            stock INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sales(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            subtotal REAL NOT NULL,
            discount REAL NOT NULL,
            total REAL NOT NULL,
            paid REAL NOT NULL,
            change_due REAL NOT NULL,
            cost_total REAL NOT NULL,
            profit REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sale_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL,
            product_id INTEGER,
            sku TEXT, name TEXT NOT NULL,
            qty INTEGER NOT NULL,
            price REAL NOT NULL,
            cost REAL NOT NULL,
            line_total REAL NOT NULL,
            FOREIGN KEY(sale_id) REFERENCES sales(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS expenses(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY, value TEXT NOT NULL
        );
        INSERT OR IGNORE INTO settings(key,value) VALUES('starting_capital','0');
        """)
        self.conn.commit()

    def all_products(self):
        return self.conn.execute("SELECT * FROM products ORDER BY name").fetchall()

    def save_product(self, sku, name, cost, price, stock, pid=None):
        sku = sku.strip() or None
        name = name.strip()
        if not name:
            raise ValueError("Nama barang wajib diisi.")
        if min(cost, price, stock) < 0:
            raise ValueError("Harga dan stok tidak boleh negatif.")
        if pid:
            self.conn.execute("UPDATE products SET sku=?,name=?,cost=?,price=?,stock=? WHERE id=?",
                              (sku, name, cost, price, stock, pid))
        else:
            self.conn.execute("INSERT INTO products(sku,name,cost,price,stock,created_at) VALUES(?,?,?,?,?,?)",
                              (sku, name, cost, price, stock, now()))
        self.conn.commit()

    def delete_product(self, pid):
        self.conn.execute("DELETE FROM products WHERE id=?", (pid,))
        self.conn.commit()

    def checkout(self, cart, discount_percent, paid):
        if not cart:
            raise ValueError("Keranjang masih kosong.")
        subtotal = sum(x["price"] * x["qty"] for x in cart.values())
        if not 0 <= discount_percent <= 100:
            raise ValueError("Diskon harus 0 sampai 100 persen.")
        discount = subtotal * discount_percent / 100
        total = subtotal - discount
        if paid < total:
            raise ValueError("Uang bayar kurang.")
        cost_total = sum(x["cost"] * x["qty"] for x in cart.values())
        profit = total - cost_total
        cur = self.conn.cursor()
        try:
            cur.execute("BEGIN")
            for x in cart.values():
                row = cur.execute("SELECT stock FROM products WHERE id=?", (x["id"],)).fetchone()
                if row is None or row["stock"] < x["qty"]:
                    raise ValueError("Stok tidak cukup untuk: " + x["name"])
            cur.execute("""INSERT INTO sales(created_at,subtotal,discount,total,paid,change_due,cost_total,profit)
                           VALUES(?,?,?,?,?,?,?,?)""",
                        (now(), subtotal, discount, total, paid, paid-total, cost_total, profit))
            sale_id = cur.lastrowid
            for x in cart.values():
                cur.execute("""INSERT INTO sale_items(sale_id,product_id,sku,name,qty,price,cost,line_total)
                               VALUES(?,?,?,?,?,?,?,?)""",
                            (sale_id,x["id"],x["sku"],x["name"],x["qty"],x["price"],x["cost"],x["price"]*x["qty"]))
                cur.execute("UPDATE products SET stock=stock-? WHERE id=?", (x["qty"],x["id"]))
            self.conn.commit()
            return sale_id, subtotal, discount, total, paid-total, profit
        except Exception:
            self.conn.rollback()
            raise

    def report(self):
        today = datetime.now().strftime("%Y-%m-%d")
        s = self.conn.execute("""SELECT COUNT(*) n, COALESCE(SUM(total),0) omzet,
                    COALESCE(SUM(cost_total),0) modal, COALESCE(SUM(profit),0) laba
                    FROM sales WHERE substr(created_at,1,10)=?""", (today,)).fetchone()
        e = self.conn.execute("SELECT COALESCE(SUM(amount),0) total FROM expenses WHERE substr(created_at,1,10)=?", (today,)).fetchone()
        all_s = self.conn.execute("""SELECT COUNT(*) n, COALESCE(SUM(total),0) omzet,
                    COALESCE(SUM(cost_total),0) modal, COALESCE(SUM(profit),0) laba FROM sales""").fetchone()
        capital = float(self.conn.execute("SELECT value FROM settings WHERE key='starting_capital'").fetchone()[0])
        expenses = float(self.conn.execute("SELECT COALESCE(SUM(amount),0) FROM expenses").fetchone()[0])
        return s, e["total"], all_s, capital, expenses

    def set_capital(self, amount):
        self.conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('starting_capital',?)", (str(amount),))
        self.conn.commit()

    def add_expense(self, desc, amount):
        if not desc.strip() or amount <= 0:
            raise ValueError("Isi keterangan dan jumlah pengeluaran yang benar.")
        self.conn.execute("INSERT INTO expenses(created_at,description,amount) VALUES(?,?,?)",
                          (now(), desc.strip(), amount))
        self.conn.commit()

    def latest_sale(self):
        sale = self.conn.execute("SELECT * FROM sales ORDER BY id DESC LIMIT 1").fetchone()
        if not sale:
            return None, []
        items = self.conn.execute("SELECT * FROM sale_items WHERE sale_id=?", (sale["id"],)).fetchall()
        return sale, items

    def close(self):
        self.conn.close()

class KasirApp(App):
    title = APP_NAME
    def build(self):
        Window.clearcolor = (0.95, 0.96, 0.98, 1)
        self.cart = {}
        self.current_edit_id = None
        self.last_receipt = ""
        self.root_box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        data_dir = self.user_data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = os.path.join(data_dir, "kasir_offline.db")
        self.db = Database(self.db_path)
        self.show_home()
        return self.root_box

    def btn(self, text, fn, height=44):
        b = Button(text=text, size_hint_y=None, height=dp(height), background_normal="")
        b.background_color = (0.10, 0.30, 0.55, 1)
        b.color = (1,1,1,1)
        b.bind(on_release=lambda *_: fn())
        return b

    def label(self, text, size=16, height=None, bold=False):
        return Label(text=text, font_size=sp(size), bold=bold, color=(0.12,0.15,0.20,1),
                     size_hint_y=None, height=dp(height or 30), halign="left", valign="middle")

    def page(self, title):
        self.root_box.clear_widgets()
        self.root_box.add_widget(self.label(title, 22, 42, True))
        body = BoxLayout(orientation="vertical", spacing=dp(7))
        self.root_box.add_widget(body)
        return body

    def add_nav(self, body):
        nav = GridLayout(cols=3, spacing=dp(5), size_hint_y=None, height=dp(90))
        nav.add_widget(self.btn("Beranda", self.show_home, 40))
        nav.add_widget(self.btn("Kasir", self.show_cashier, 40))
        nav.add_widget(self.btn("Barang", self.show_products, 40))
        nav.add_widget(self.btn("Laporan", self.show_report, 40))
        nav.add_widget(self.btn("Modal", self.show_capital, 40))
        nav.add_widget(self.btn("Backup", self.show_backup, 40))
        self.root_box.add_widget(nav)

    def show_home(self):
        body = self.page("KASIR OFFLINE PRO")
        s, exp_today, all_s, capital, expenses = self.db.report()
        body.add_widget(self.label("Hari ini", 18, 34, True))
        body.add_widget(self.label(f"Omzet: {rupiah(s['omzet'])}"))
        body.add_widget(self.label(f"Transaksi: {s['n']}"))
        body.add_widget(self.label(f"Laba kotor: {rupiah(s['laba'])}"))
        body.add_widget(self.label(f"Pengeluaran hari ini: {rupiah(exp_today)}"))
        body.add_widget(self.label("Semua waktu", 18, 34, True))
        body.add_widget(self.label(f"Total omzet: {rupiah(all_s['omzet'])}"))
        body.add_widget(self.label(f"Modal awal: {rupiah(capital)}"))
        body.add_widget(self.label(f"Total pengeluaran: {rupiah(expenses)}"))
        body.add_widget(self.label("Data tersimpan di perangkat ini.", 14, 32))
        self.add_nav(body)

    def show_products(self):
        body = self.page("MANAJEMEN BARANG")
        body.add_widget(self.btn("+ Tambah barang", lambda: self.product_form(), 42))
        scroll = ScrollView()
        rows = GridLayout(cols=1, spacing=dp(5), size_hint_y=None)
        rows.bind(minimum_height=rows.setter("height"))
        for p in self.db.all_products():
            box = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(90), padding=dp(5))
            box.add_widget(self.label(f"{p['name']} | Stok {p['stock']}", 16, 28, True))
            box.add_widget(self.label(f"Jual {rupiah(p['price'])} | Modal {rupiah(p['cost'])}", 13, 24))
            actions = BoxLayout(spacing=dp(5), size_hint_y=None, height=dp(32))
            actions.add_widget(self.btn("Edit", lambda p=p: self.product_form(p), 30))
            actions.add_widget(self.btn("Hapus", lambda p=p: self.confirm_delete(p), 30))
            box.add_widget(actions)
            rows.add_widget(box)
        scroll.add_widget(rows); body.add_widget(scroll)
        self.add_nav(body)

    def confirm_delete(self, p):
        content = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        content.add_widget(self.label(f"Hapus {p['name']}?", 16, 40))
        pop = Popup(title="Konfirmasi", content=content, size_hint=(.85,.35))
        buttons = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        buttons.add_widget(self.btn("Batal", pop.dismiss))
        def do_del():
            self.db.delete_product(p["id"]); pop.dismiss(); self.show_products()
        buttons.add_widget(self.btn("Hapus", do_del))
        content.add_widget(buttons); pop.open()

    def product_form(self, p=None):
        self.current_edit_id = p["id"] if p else None
        content = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(5))
        fields = {}
        values = {
            "Kode/SKU": p["sku"] or "" if p else "",
            "Nama barang": p["name"] if p else "",
            "Harga modal": str(p["cost"]) if p else "0",
            "Harga jual": str(p["price"]) if p else "0",
            "Stok": str(p["stock"]) if p else "0"
        }
        for name, value in values.items():
            content.add_widget(self.label(name, 13, 22))
            inp = TextInput(text=value, multiline=False, size_hint_y=None, height=dp(40))
            fields[name] = inp; content.add_widget(inp)
        buttons = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        pop = Popup(title="Edit barang" if p else "Tambah barang", content=content, size_hint=(.92,.88))
        def save():
            try:
                self.db.save_product(fields["Kode/SKU"].text, fields["Nama barang"].text,
                    float(fields["Harga modal"].text or 0), float(fields["Harga jual"].text or 0),
                    int(fields["Stok"].text or 0), self.current_edit_id)
                pop.dismiss(); self.show_products()
            except sqlite3.IntegrityError:
                self.alert("Kode/SKU sudah dipakai.")
            except Exception as e:
                self.alert(str(e))
        buttons.add_widget(self.btn("Batal", pop.dismiss))
        buttons.add_widget(self.btn("Simpan", save))
        content.add_widget(buttons); pop.open()

    def show_cashier(self):
        body = self.page("KASIR / TRANSAKSI")
        scroll = ScrollView(size_hint_y=.55)
        rows = GridLayout(cols=1, spacing=dp(5), size_hint_y=None)
        rows.bind(minimum_height=rows.setter("height"))
        for p in self.db.all_products():
            row = BoxLayout(size_hint_y=None, height=dp(66), spacing=dp(5))
            info = BoxLayout(orientation="vertical")
            info.add_widget(self.label(f"{p['name']} (stok {p['stock']})", 14, 30, True))
            info.add_widget(self.label(rupiah(p["price"]), 13, 24))
            row.add_widget(info)
            row.add_widget(self.btn("Tambah", lambda p=p: self.add_to_cart(p), 40))
            rows.add_widget(row)
        scroll.add_widget(rows); body.add_widget(scroll)
        body.add_widget(self.label("Keranjang", 17, 30, True))
        self.cart_label = self.label(self.cart_text(), 13, 90)
        body.add_widget(self.cart_label)
        inputs = GridLayout(cols=2, spacing=dp(5), size_hint_y=None, height=dp(88))
        self.discount_input = TextInput(hint_text="Diskon (%)", text="0", multiline=False, input_filter="float")
        self.paid_input = TextInput(hint_text="Uang dibayar (Rp)", text="0", multiline=False, input_filter="float")
        inputs.add_widget(self.discount_input); inputs.add_widget(self.paid_input)
        body.add_widget(inputs)
        buttons = GridLayout(cols=2, spacing=dp(5), size_hint_y=None, height=dp(88))
        buttons.add_widget(self.btn("Kosongkan", self.clear_cart))
        buttons.add_widget(self.btn("Bayar", self.pay))
        buttons.add_widget(self.btn("Lihat struk terakhir", self.show_receipt))
        buttons.add_widget(self.btn("Barang", self.show_products))
        body.add_widget(buttons)
        self.add_nav(body)

    def cart_text(self):
        if not self.cart: return "Belum ada barang di keranjang."
        lines = []
        for x in self.cart.values():
            lines.append(f"{x['name']} x{x['qty']} = {rupiah(x['price']*x['qty'])}")
        subtotal = sum(x["price"]*x["qty"] for x in self.cart.values())
        return "\n".join(lines) + f"\nSubtotal: {rupiah(subtotal)}"

    def add_to_cart(self, p):
        if p["stock"] < 1:
            self.alert("Stok barang habis."); return
        if p["id"] not in self.cart:
            self.cart[p["id"]] = {"id":p["id"],"sku":p["sku"],"name":p["name"],"price":p["price"],"cost":p["cost"],"qty":0}
        if self.cart[p["id"]]["qty"] >= p["stock"]:
            self.alert("Jumlah melebihi stok."); return
        self.cart[p["id"]]["qty"] += 1
        if hasattr(self, "cart_label"): self.cart_label.text = self.cart_text()
        else: self.show_cashier()

    def clear_cart(self):
        self.cart = {}; self.show_cashier()

    def pay(self):
        try:
            discount = float(self.discount_input.text or 0)
            paid = float(self.paid_input.text or 0)
            result = self.db.checkout(self.cart, discount, paid)
            sale_id, subtotal, disc, total, change, profit = result
            self.cart = {}
            self.make_receipt(sale_id)
            self.alert(f"Transaksi berhasil!\nTotal: {rupiah(total)}\nKembalian: {rupiah(change)}\nLaba kotor: {rupiah(profit)}")
            self.show_cashier()
        except Exception as e:
            self.alert(str(e))

    def make_receipt(self, sale_id=None):
        if sale_id:
            sale = self.db.conn.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
            items = self.db.conn.execute("SELECT * FROM sale_items WHERE sale_id=?", (sale_id,)).fetchall()
        else:
            sale, items = self.db.latest_sale()
        if not sale: self.alert("Belum ada transaksi."); return
        lines = [APP_NAME, "STRUK PEMBELIAN", "="*28, f"No: {sale['id']}", sale["created_at"], "-"*28]
        for x in items:
            lines.append(f"{x['name']} x{x['qty']}")
            lines.append(f"  {rupiah(x['price'])} = {rupiah(x['line_total'])}")
        lines += ["-"*28, f"Subtotal: {rupiah(sale['subtotal'])}", f"Diskon: {rupiah(sale['discount'])}",
                  f"TOTAL: {rupiah(sale['total'])}", f"Bayar: {rupiah(sale['paid'])}",
                  f"Kembalian: {rupiah(sale['change_due'])}", "", "Terima kasih."]
        self.last_receipt = "\n".join(lines)
        receipt_dir = os.path.join(self.user_data_dir, "receipts")
        os.makedirs(receipt_dir, exist_ok=True)
        with open(os.path.join(receipt_dir, f"struk_{sale['id']}.txt"), "w", encoding="utf-8") as f:
            f.write(self.last_receipt)

    def show_receipt(self):
        self.make_receipt()
        if self.last_receipt:
            content = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
            text = TextInput(text=self.last_receipt, readonly=True)
            content.add_widget(text)
            content.add_widget(self.btn("Tutup", lambda: pop.dismiss(), 40))
            pop = Popup(title="Struk terakhir", content=content, size_hint=(.92,.85))
            pop.open()

    def show_report(self):
        body = self.page("LAPORAN")
        s, exp_today, a, capital, expenses = self.db.report()
        for line in [
            "LAPORAN HARI INI",
            f"Jumlah transaksi: {s['n']}",
            f"Omzet: {rupiah(s['omzet'])}",
            f"Modal barang terjual: {rupiah(s['modal'])}",
            f"Laba kotor: {rupiah(s['laba'])}",
            f"Pengeluaran hari ini: {rupiah(exp_today)}",
            "",
            "LAPORAN KESELURUHAN",
            f"Total transaksi: {a['n']}",
            f"Total omzet: {rupiah(a['omzet'])}",
            f"Total modal barang terjual: {rupiah(a['modal'])}",
            f"Total laba kotor: {rupiah(a['laba'])}",
            f"Modal awal: {rupiah(capital)}",
            f"Total pengeluaran: {rupiah(expenses)}",
            f"Perkiraan saldo modal + laba - pengeluaran: {rupiah(capital+a['laba']-expenses)}"
        ]:
            body.add_widget(self.label(line, 14, 28))
        body.add_widget(self.btn("Catat pengeluaran", self.expense_form, 42))
        self.add_nav(body)

    def show_capital(self):
        body = self.page("MODAL & PENGELUARAN")
        s, ex, a, capital, expenses = self.db.report()
        body.add_widget(self.label(f"Modal awal saat ini: {rupiah(capital)}", 16, 36, True))
        inp = TextInput(hint_text="Modal awal (Rp)", text=str(capital), multiline=False, input_filter="float",
                        size_hint_y=None, height=dp(44))
        body.add_widget(inp)
        def save():
            try:
                amount = float(inp.text or 0)
                if amount < 0: raise ValueError("Modal tidak boleh negatif.")
                self.db.set_capital(amount); self.alert("Modal awal disimpan."); self.show_capital()
            except Exception as e: self.alert(str(e))
        body.add_widget(self.btn("Simpan modal awal", save, 42))
        body.add_widget(self.label(f"Total pengeluaran: {rupiah(expenses)}", 16, 34))
        body.add_widget(self.btn("+ Catat pengeluaran", self.expense_form, 42))
        self.add_nav(body)

    def expense_form(self):
        content = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(7))
        desc = TextInput(hint_text="Keterangan (contoh: listrik)", multiline=False, size_hint_y=None, height=dp(44))
        amount = TextInput(hint_text="Jumlah (Rp)", multiline=False, input_filter="float", size_hint_y=None, height=dp(44))
        content.add_widget(desc); content.add_widget(amount)
        pop = Popup(title="Catat pengeluaran", content=content, size_hint=(.9,.45))
        buttons = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(5))
        def save():
            try:
                self.db.add_expense(desc.text, float(amount.text or 0))
                pop.dismiss(); self.alert("Pengeluaran disimpan."); self.show_report()
            except Exception as e: self.alert(str(e))
        buttons.add_widget(self.btn("Batal", pop.dismiss))
        buttons.add_widget(self.btn("Simpan", save))
        content.add_widget(buttons); pop.open()

    def show_backup(self):
        body = self.page("BACKUP & RESTORE")
        body.add_widget(self.label("Database aktif tersimpan di ruang data aplikasi.", 14, 40))
        body.add_widget(self.label("Pilih folder untuk mengekspor backup atau memilih file backup untuk restore.", 13, 50))
        body.add_widget(self.btn("Backup database", lambda: self.file_picker("backup"), 46))
        body.add_widget(self.btn("Restore database", lambda: self.file_picker("restore"), 46))
        self.add_nav(body)

    def file_picker(self, mode):
        try:
            from plyer import filechooser
            if mode == "backup":
                self.db.conn.commit()
                filename = "kasir_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".db"
                candidates = []
                if platform == "android":
                    candidates.append("/storage/emulated/0/Download")
                candidates.append(self.user_data_dir)
                dest = None
                for folder in candidates:
                    try:
                        os.makedirs(folder, exist_ok=True)
                        test_dest = os.path.join(folder, filename)
                        shutil.copy2(self.db_path, test_dest)
                        dest = test_dest
                        break
                    except Exception:
                        continue
                if dest:
                    self.alert("Backup berhasil dibuat:\n" + dest)
                else:
                    self.alert("Backup gagal. Periksa izin penyimpanan Android.")
            else:
                filechooser.open_file(on_selection=lambda selection: self.restore_selected(selection))
        except Exception as e:
            self.alert("Fitur pemilih file tidak tersedia di perangkat ini.\n" + str(e))

    def restore_selected(self, selection):
        if not selection: return
        src = selection[0]
        try:
            self.db.conn.commit()
            self.db.close()
            shutil.copy2(src, self.db_path)
            self.db = Database(self.db_path)
            self.alert("Restore berhasil.")
            self.show_home()
        except Exception as e:
            self.db = Database(self.db_path)
            self.alert("Restore gagal: " + str(e))

    def alert(self, message):
        content = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        content.add_widget(Label(text=message, color=(.1,.1,.1,1)))
        pop = Popup(title="Informasi", content=content, size_hint=(.88,.45))
        content.add_widget(self.btn("OK", pop.dismiss, 40))
        pop.open()

    def on_stop(self):
        try: self.db.close()
        except Exception: pass

def sp(size):
    from kivy.metrics import sp as _sp
    return _sp(size)

if __name__ == "__main__":
    KasirApp().run()
