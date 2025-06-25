import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from threading import Thread
import time
import numpy as np
from cmsing import (
    listar_janelas_estado,
    capturar_janela_background,
    extrair_regiao_icone,
    gerenciador_notificacoes,
    CONFIG,
    REGIAO_ICONE,
    fila_notificacoes
)

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Monitor de Janelas - Leonardo Barros")
        self.geometry("620x580")
        self.minsize(500, 500)
        self.maxsize(800, 800)

        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.label_title = ctk.CTkLabel(self, text="Selecione as Janelas para Monitorar",
                                        font=("Segoe UI", 20, "bold"))
        self.label_title.pack(pady=(20, 10))

        self.janela_listbox = ctk.CTkScrollableFrame(self, width=500, height=200)
        self.janela_listbox.pack(pady=10)

        self.check_vars = {}
        self.monitorando_flags = {}
        self.preencher_janelas()

        self.pixel_slider_label = ctk.CTkLabel(self, text="Quantidade mínima de pixels detectados:",
                                               font=("Segoe UI", 14))
        self.pixel_slider_label.pack(pady=(20, 5))

        self.slider_value_label = ctk.CTkLabel(self, text=f"{int(CONFIG['limite_pixels'])} px",
                                               font=("Segoe UI", 12))
        self.slider_value_label.pack()

        self.pixel_slider = ctk.CTkSlider(self, from_=1, to=100, number_of_steps=99, width=400,
                                          command=self.atualizar_valor_slider)
        self.pixel_slider.set(CONFIG['limite_pixels'])
        self.pixel_slider.pack(pady=5)

        self.toggle_button = ctk.CTkButton(self, text="Iniciar Monitoramento", font=("Segoe UI", 15),
                                           command=self.iniciar_monitoramento)
        self.toggle_button.pack(pady=10)

        self.stop_button = ctk.CTkButton(self, text="Parar Monitoramento", font=("Segoe UI", 15),
                                         command=self.parar_monitoramento, fg_color="red", hover_color="#b22222")
        self.stop_button.pack(pady=10)
        self.stop_button.configure(state="disabled")

        self.criador = ctk.CTkLabel(self, text="Criado por Leonardo Barros", font=("Segoe UI", 12))
        self.criador.pack(side="bottom", pady=10)

    def atualizar_valor_slider(self, value):
        CONFIG['limite_pixels'] = int(value)
        self.slider_value_label.configure(text=f"{int(value)} px")

    def preencher_janelas(self):
        janelas = listar_janelas_estado()
        if not janelas:
            label = ctk.CTkLabel(self.janela_listbox, text="Nenhuma janela encontrada.", font=("Segoe UI", 13))
            label.pack()
        else:
            for janela in janelas:
                var = tk.BooleanVar()
                cb = ctk.CTkCheckBox(self.janela_listbox, text=janela, variable=var, font=("Segoe UI", 13))
                cb.pack(anchor="w", pady=5)
                self.check_vars[janela] = var

    def iniciar_monitoramento(self):
        selecionadas = [nome for nome, var in self.check_vars.items() if var.get()]
        if not selecionadas:
            messagebox.showwarning("Aviso", "Selecione ao menos uma janela.")
            return

        self.toggle_button.configure(state="disabled", text="Monitorando...")
        self.stop_button.configure(state="normal")

        self.monitorando_flags = {janela: True for janela in selecionadas}

        Thread(target=gerenciador_notificacoes, daemon=True).start()

        for janela in selecionadas:
            Thread(target=self.thread_monitoramento, args=(janela,), daemon=True).start()

        messagebox.showinfo("Monitoramento", "Monitoramento iniciado com sucesso!")

    def parar_monitoramento(self):
        for janela in self.monitorando_flags:
            self.monitorando_flags[janela] = False

        self.toggle_button.configure(state="normal", text="Iniciar Monitoramento")
        self.stop_button.configure(state="disabled")
        messagebox.showinfo("Parado", "Monitoramento cancelado.")

    def thread_monitoramento(self, nome_janela):
        ultimo_alerta = 0

        while self.monitorando_flags.get(nome_janela, False):
            imagem_janela = capturar_janela_background(nome_janela)
            if not imagem_janela:
                time.sleep(CONFIG['intervalo'])
                continue

            icone = extrair_regiao_icone(imagem_janela, REGIAO_ICONE)
            if not icone:
                time.sleep(CONFIG['intervalo'])
                continue

            try:
                img_array = np.array(icone)
                r, g, b = img_array[:, :, 0], img_array[:, :, 1], img_array[:, :, 2]
                mask = (
                    (r >= CONFIG['cor_alvo_min'][0]) & (r <= CONFIG['cor_alvo_max'][0]) &
                    (g >= CONFIG['cor_alvo_min'][1]) & (g <= CONFIG['cor_alvo_max'][1]) &
                    (b >= CONFIG['cor_alvo_min'][2]) & (b <= CONFIG['cor_alvo_max'][2])
                )

                total_pixels = int(np.sum(mask))

                if total_pixels >= CONFIG['limite_pixels']:
                    agora = time.time()
                    if agora - ultimo_alerta > CONFIG['alerta_cooldown']:
                        fila_notificacoes.put(nome_janela)
                        ultimo_alerta = agora

                time.sleep(CONFIG['intervalo'])
            except Exception as e:
                print(f"[ERRO]: {e}")
                time.sleep(CONFIG['intervalo'])


if __name__ == "__main__":
    app = App()
    app.mainloop()
