import ctypes
import win32gui
import win32ui
import win32con
from PIL import Image
import numpy as np
import time
from threading import Thread, Lock
import logging
from queue import Queue
import os
from plyer import notification
import pyautogui
import win32clipboard
import io

# ======================================
# CONFIGURAÇÕES GLOBAIS
# ======================================
logging.basicConfig(filename='monitor.log', level=logging.INFO,
                    format='%(asctime)s - %(message)s')

fila_notificacoes = Queue()

CONFIG = {
    'cor_alvo_min': (200, 0, 0),     # Vermelho mínimo (R alto, G e B baixos)
    'cor_alvo_max': (255, 80, 80),   # Vermelho máximo
    'limite_pixels': 5,
    'intervalo': 5,
    'alerta_cooldown': 5
}

REGIAO_ICONE = (15, 2, 30, 30)

# ======================================
# FUNÇÕES DE CAPTURA
# ======================================
def send_to_clipboard(image):
    output = io.BytesIO()
    image.convert("RGB").save(output, "BMP")
    data = output.getvalue()[14:]
    output.close()
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
    win32clipboard.CloseClipboard()

def capturar_janela_background(nome_janela):
    try:
        def callback(hwnd, hwnds):
            if win32gui.IsWindowVisible(hwnd) and nome_janela.lower() in win32gui.GetWindowText(hwnd).lower():
                hwnds.append(hwnd)
            return True

        hwnds = []
        win32gui.EnumWindows(callback, hwnds)
        if not hwnds:
            logging.warning(f"Janela '{nome_janela}' não encontrada")
            return None

        hwnd = hwnds[0]
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width = right - left
        height = bottom - top

        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        saveBitMap = win32ui.CreateBitmap()
        saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
        saveDC.SelectObject(saveBitMap)
        result = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 2)

        if result != 1:
            logging.warning(f"Falha ao capturar janela '{nome_janela}'")
            return None

        bmpinfo = saveBitMap.GetInfo()
        bmpstr = saveBitMap.GetBitmapBits(True)
        imagem = Image.frombuffer('RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                                  bmpstr, 'raw', 'BGRX', 0, 1)
        return imagem

    except Exception as e:
        logging.error(f"Erro ao capturar janela '{nome_janela}': {str(e)}")
        return None

    finally:
        if 'saveBitMap' in locals() and saveBitMap:
            win32gui.DeleteObject(saveBitMap.GetHandle())
        if 'saveDC' in locals() and saveDC:
            saveDC.DeleteDC()
        if 'mfcDC' in locals() and mfcDC:
            mfcDC.DeleteDC()
        if 'hwndDC' in locals() and hwndDC:
            win32gui.ReleaseDC(hwnd, hwndDC)

def extrair_regiao_icone(imagem_janela, regiao):
    try:
        if (regiao[0] + regiao[2] > imagem_janela.width or
            regiao[1] + regiao[3] > imagem_janela.height):
            logging.error("Região do ícone fora dos limites da janela")
            return None

        return imagem_janela.crop((
            regiao[0], regiao[1],
            regiao[0] + regiao[2],
            regiao[1] + regiao[3]
        ))
    except Exception as e:
        logging.error(f"Erro ao extrair região do ícone: {str(e)}")
        return None

# ======================================
# FUNÇÕES DE DETECÇÃO
# ======================================
def detectar_cor_alvo(imagem):
    try:
        img_array = np.array(imagem)
        mask = ( # vermelho porra!
    (img_array[:, :, 0] >= CONFIG['cor_alvo_min'][0]) & (img_array[:, :, 0] <= CONFIG['cor_alvo_max'][0]) &
    (img_array[:, :, 1] >= CONFIG['cor_alvo_min'][1]) & (img_array[:, :, 1] <= CONFIG['cor_alvo_max'][1]) &
    (img_array[:, :, 2] >= CONFIG['cor_alvo_min'][2]) & (img_array[:, :, 2] <= CONFIG['cor_alvo_max'][2])
)

        return np.sum(mask) >= CONFIG['limite_pixels']
    except Exception as e:
        logging.error(f"Erro ao detectar cor-alvo: {str(e)}")
        return False

def gerenciador_notificacoes():
    while True:
        nome_janela = fila_notificacoes.get()
        mensagem = f"Irregularidade detectada em {nome_janela[24:]}!"

        notification.notify(
            title="ALERTA DE CMS",
            message=mensagem,
            timeout=3
        )
        print(f"\a{mensagem}")
        fila_notificacoes.task_done()

def monitorar_janela(nome_janela):
    ultimo_alerta = 0
    while True:
        try:
            imagem_janela = capturar_janela_background(nome_janela)
            if not imagem_janela:
                time.sleep(CONFIG['intervalo'])
                continue

            icone = extrair_regiao_icone(imagem_janela, REGIAO_ICONE)
            send_to_clipboard(icone)
            if not icone:
                time.sleep(CONFIG['intervalo'])
                continue

            if detectar_cor_alvo(icone):
                agora = time.time()
                if agora - ultimo_alerta > CONFIG['alerta_cooldown']:
                    fila_notificacoes.put(nome_janela)
                    logging.info(f"Alerta de verde em {nome_janela}")
                    ultimo_alerta = agora

            time.sleep(CONFIG['intervalo'])

        except Exception as e:
            logging.error(f"Erro no monitoramento de {nome_janela}: {str(e)}")
            time.sleep(CONFIG['intervalo'])

# ======================================
# FUNÇÕES DE CONTROLE
# ======================================
def listar_janelas_estado():
    def callback(hwnd, hwnds):
        if win32gui.IsWindowVisible(hwnd) and 'E' in win32gui.GetWindowText(hwnd):
            hwnds.append(win32gui.GetWindowText(hwnd))
        return True

    hwnds = []
    win32gui.EnumWindows(callback, hwnds)
    return hwnds

def iniciar_monitoramento():
    janelas = listar_janelas_estado()

    if not janelas:
        print("Nenhuma janela 'Estado' encontrada!")
        return

    print("Janelas disponíveis para monitoramento:")
    for i, janela in enumerate(janelas, 1):
        print(f"{i} - {janela}")

    selecao = input("Digite os números das janelas (separados por vírgula) ou '0' para todas: ")

    if selecao == '0':
        janelas_monitorar = janelas
    else:
        indices = [int(i.strip()) - 1 for i in selecao.split(',')]
        janelas_monitorar = [janelas[i] for i in indices]

    Thread(target=gerenciador_notificacoes, daemon=True).start()

    for nome_janela in janelas_monitorar:
        Thread(target=monitorar_janela, args=(nome_janela,), daemon=True).start()

    print("\nMonitoramento iniciado em segundo plano...")
    print("Pressione Ctrl+C para encerrar.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nEncerrando monitoramento...")

if __name__ == "__main__":
    iniciar_monitoramento()
