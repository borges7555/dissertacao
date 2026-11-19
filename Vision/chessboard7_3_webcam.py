# Lab 7 - Ex. 7.3 - Calibração com a câmara (DroidCam)
#
# Teclas (na janela de vídeo):
#   ESPAÇO -> guarda a vista atual (só se o tabuleiro estiver detetado)
#   q      -> termina a captura (e calibra se houver vistas suficientes)
#   l      -> bloqueia o autofocus no foco atual (recomendado antes de capturar)
#   [ / ]  -> diminui / aumenta o foco (em passos de 5) com o autofocus bloqueado

import os
import numpy as np
import cv2
import glob

# ---------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------
USE_CAMERA = False        # True -> câmara (webcam USB / DroidCam); False -> fotos (IMAGE_GROUPS)

# Só com USE_CAMERA = False: lista de grupos de fotos (um padrão glob por grupo).
# Cada grupo é calibrado em separado para comparar; depois calibra-se com todos juntos.
IMAGE_GROUPS = ['./logitech_camara_app/*.jpg']

# Fonte de vídeo:
#  - webcam USB: índice 0, 1, 2... (0 costuma ser a webcam integrada do portátil;
#    a USB externa costuma ser 1 ou 2). Experimente até aparecer a imagem certa.
#  - DroidCam: o cliente no PC aparece como webcam; ou "http://<IP>:4747/video" por Wi-Fi
CAMERA_SOURCE = 2

# Backend de captura. No Windows, cv2.CAP_DSHOW abre mais depressa e respeita melhor a
# resolução e o foco pedidos. Noutros sistemas deixe cv2.CAP_ANY.
CAMERA_BACKEND = cv2.CAP_DSHOW

# Muitas webcams só entregam 1920x1080 em MJPG. True = pede MJPG antes da resolução.
USE_MJPG = True

# Foco (muito importante na calibração: a focal muda com o foco!)
#   None = não mexer (autofocus como está)
#   0..255 = desliga o autofocus e fixa o foco nesse valor (ex.: 0 = infinito, valores
#            maiores = mais perto; depende da webcam). Use o mesmo valor ao usar a câmara.
LOCK_FOCUS = None

# Exposição manual (reduz o desfoque de movimento; precisa de mais luz).
#   None = automática. No Windows (DirectShow) o valor é log2 do tempo em segundos:
#   -5 = 1/32 s, -6 = 1/64 s, -7 = 1/128 s. Depende do driver/câmara.
MANUAL_EXPOSURE = None

# Resolução pedida à câmara (largura, altura). O OpenCV pode ignorar o que está
# definido na app do DroidCam, por isso pede-se aqui e confirma-se no fim.
# Usar None para a resolução por defeito.
CAPTURE_SIZE = (1920, 1080)

# Guarda cada vista capturada (sem desenhos, em PNG sem perdas) nesta pasta, para poder
# recalibrar depois com USE_CAMERA = False e comparar modelos nos MESMOS dados:
#   IMAGE_GROUPS = ['./webcam_frames/frame_*.png']
# None = não guardar.
SAVE_FRAMES_DIR = 'webcam_frames'

NUM_IMAGES = 20         # nº de vistas a capturar
OUTPUT_FILE = 'camera_logitech_f18.npz'   # mudar o nome para não sobrescrever calibrações anteriores

# Flags do calibrateCamera. 0 = modelo completo (k1,k2,p1,p2,k3).
# Se k2/k3 saírem absurdos (|k3| > ~1), tentar cv2.CALIB_FIX_K3 ou
# cv2.CALIB_FIX_K2 + cv2.CALIB_FIX_K3 para estabilizar a distância focal.
CALIB_FLAGS = 0

# Remove as vistas cujo erro de reprojeção seja > PRUNE_OUTLIERS x a mediana e recalibra
# (costumam ser imagens tremidas/desfocadas). None = desligado. Mantém pelo menos 10 vistas.
PRUNE_OUTLIERS = 2.0

# Cantos INTERNOS do tabuleiro (confirmar contando no vosso padrão!)
board_h = 9
board_w = 6

# Lado de cada quadrado, em cm -> translações em cm
square_size = 2.15

subpix_criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

# Pontos 3D do tabuleiro: (0,0,0), (2.15,0,0), ... em cm
objp = np.zeros((board_w * board_h, 3), np.float32)
objp[:, :2] = np.mgrid[0:board_w, 0:board_h].T.reshape(-1, 2)
objp = objp * square_size

objpoints = []  # pontos 3D
imgpoints = []  # pontos 2D
img_size = None


def refine(gray, corners):
    return cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), subpix_criteria)


def calib_summary(name, objs, imgs, size):
    """Calibra com vários modelos e imprime fx, fy, cx, cy, RMS e os coeficientes."""
    print('\n%s (%d vistas)' % (name, len(objs)))
    F = cv2
    models = [('completo (k1 k2 p1 p2 k3)', 0),
              ('k3 fixo', F.CALIB_FIX_K3),
              ('k2 e k3 fixos', F.CALIB_FIX_K2 + F.CALIB_FIX_K3),
              ('k3 fixo + tangencial 0', F.CALIB_FIX_K3 + F.CALIB_ZERO_TANGENT_DIST),
              ('k2,k3 fixos + tang. 0', F.CALIB_FIX_K2 + F.CALIB_FIX_K3 + F.CALIB_ZERO_TANGENT_DIST),
              ('k3 fixo + tang. 0 + ponto principal fixo',
               F.CALIB_FIX_K3 + F.CALIB_ZERO_TANGENT_DIST + F.CALIB_FIX_PRINCIPAL_POINT),
              ('k3 fixo + fx=fy (pixeis quadrados)', F.CALIB_FIX_K3 + F.CALIB_FIX_ASPECT_RATIO),
              ('k2,k3 fixos + fx=fy + tang. 0 + pp fixo',
               F.CALIB_FIX_K2 + F.CALIB_FIX_K3 + F.CALIB_FIX_ASPECT_RATIO + F.CALIB_ZERO_TANGENT_DIST
               + F.CALIB_FIX_PRINCIPAL_POINT)]
    for label, fl in models:
        r, K, d, _, _ = cv2.calibrateCamera(objs, imgs, size, None, None, flags=fl)
        print('  %-42s fx=%7.1f fy=%7.1f cx=%6.1f cy=%6.1f RMS=%.3f  k1,k2,k3=%s p1,p2=%s'
              % (label, K[0, 0], K[1, 1], K[0, 2], K[1, 2], r,
                 np.round(d.ravel()[[0, 1, 4]], 3), np.round(d.ravel()[[2, 3]], 4)))


# ---------------------------------------------------------------
# Aquisição
# ---------------------------------------------------------------
if USE_CAMERA:
    capture = cv2.VideoCapture(CAMERA_SOURCE, CAMERA_BACKEND)
    if not capture.isOpened():
        raise SystemExit('Não foi possível abrir a fonte de vídeo: %s (tente outro índice '
                         'ou CAMERA_BACKEND = cv2.CAP_ANY)' % str(CAMERA_SOURCE))

    # A ordem importa: formato -> resolução -> foco
    if USE_MJPG:
        capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    if CAPTURE_SIZE is not None:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_SIZE[0])
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_SIZE[1])
    if LOCK_FOCUS is not None:
        capture.set(cv2.CAP_PROP_AUTOFOCUS, 0)
        capture.set(cv2.CAP_PROP_FOCUS, LOCK_FOCUS)
    if MANUAL_EXPOSURE is not None:
        capture.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)      # DirectShow: 0.25 = manual
        capture.set(cv2.CAP_PROP_EXPOSURE, MANUAL_EXPOSURE)
        print('Exposição manual pedida: %s | lida: %s'
              % (MANUAL_EXPOSURE, capture.get(cv2.CAP_PROP_EXPOSURE)))
    print('Câmara aberta: %dx%d | autofocus=%s | foco=%s'
          % (capture.get(cv2.CAP_PROP_FRAME_WIDTH), capture.get(cv2.CAP_PROP_FRAME_HEIGHT),
             capture.get(cv2.CAP_PROP_AUTOFOCUS), capture.get(cv2.CAP_PROP_FOCUS)))

    # Descarta alguns frames iniciais (exposição e foco a estabilizar)
    for _ in range(15):
        capture.read()

    flags = (cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE
             + cv2.CALIB_CB_FAST_CHECK)

    while len(objpoints) < NUM_IMAGES:
        ret, frame = capture.read()
        if not ret:
            print('Falha a ler frame')
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if img_size is None:
            img_size = (gray.shape[1], gray.shape[0])  # (largura, altura)

        found, corners = cv2.findChessboardCorners(gray, (board_w, board_h), flags)

        display = frame.copy()
        if found:
            corners = refine(gray, corners)
            cv2.drawChessboardCorners(display, (board_w, board_h), corners, found)

        cv2.putText(display, 'Vistas: %d/%d | ESPACO=guardar  q=sair'
                    % (len(objpoints), NUM_IMAGES), (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (0, 255, 0) if found else (0, 0, 255), 2)
        af = capture.get(cv2.CAP_PROP_AUTOFOCUS)
        fv = capture.get(cv2.CAP_PROP_FOCUS)
        cv2.putText(display, 'autofocus=%s foco=%d | l=bloquear foco  [ ]=foco -/+'
                    % ('ON' if af else 'OFF', fv), (10, 52),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        cv2.imshow('video', display)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        if key == ord('l'):              # fixa o foco no valor atual
            capture.set(cv2.CAP_PROP_AUTOFOCUS, 0)
            capture.set(cv2.CAP_PROP_FOCUS, fv)
            print('Autofocus desligado; foco fixo em %d (LOCK_FOCUS = %d)' % (fv, fv))
        if key in (ord('['), ord(']')):  # ajuste manual do foco
            capture.set(cv2.CAP_PROP_AUTOFOCUS, 0)
            capture.set(cv2.CAP_PROP_FOCUS, max(0, fv + (5 if key == ord(']') else -5)))
        if key == ord(' ') and found:
            objpoints.append(objp)
            imgpoints.append(corners)
            print('Vista %d guardada' % len(objpoints))
            if SAVE_FRAMES_DIR:
                os.makedirs(SAVE_FRAMES_DIR, exist_ok=True)
                cv2.imwrite(os.path.join(SAVE_FRAMES_DIR, 'frame_%02d.png' % len(objpoints)), frame)
            cv2.imshow('video', 255 - display)  # "flash" de confirmação
            cv2.waitKey(300)

    capture.release()
    cv2.destroyAllWindows()

else:
    groups = []   # (nome, objpoints, imgpoints)
    for pattern in IMAGE_GROUPS:
        g_obj, g_img = [], []
        for fname in sorted(glob.glob(pattern)):
            img = cv2.imread(fname)
            if img is None:
                continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            size = (gray.shape[1], gray.shape[0])
            if img_size is None:
                img_size = size
            if size != img_size:
                print('Ignorada (resolução %dx%d diferente): %s' % (size + (fname,)))
                continue
            found, corners = cv2.findChessboardCorners(gray, (board_w, board_h), None)
            if found:
                corners = refine(gray, corners)
                g_obj.append(objp)
                g_img.append(corners)
                cv2.drawChessboardCorners(img, (board_w, board_h), corners, found)
                cv2.imshow('img', cv2.resize(img, None, fx=0.5, fy=0.5)
                           if img.shape[1] > 1400 else img)
                cv2.waitKey(200)
            else:
                print('Tabuleiro NÃO encontrado em', fname)
        groups.append((pattern, g_obj, g_img))
        objpoints += g_obj
        imgpoints += g_img
    cv2.destroyAllWindows()

    # Comparação da estabilidade da focal entre grupos e modelos de distorção
    print('\n=== Comparação (fx, fy devem ser parecidos entre grupos) ===')
    for name, g_obj, g_img in groups:
        if len(g_obj) >= 3:
            calib_summary(name, g_obj, g_img, img_size)
    if len(groups) > 1 and len(objpoints) >= 3:
        calib_summary('TODOS JUNTOS', objpoints, imgpoints, img_size)
    print('\n(A calibração final abaixo usa CALIB_FLAGS = %s)' % str(CALIB_FLAGS))

# ---------------------------------------------------------------
# Calibração
# ---------------------------------------------------------------
if len(objpoints) < 3:
    raise SystemExit('Vistas insuficientes (%d) para calibrar.' % len(objpoints))

ret, intrinsics, distortion, rvecs, tvecs = cv2.calibrateCamera(
    objpoints, imgpoints, img_size, None, None, flags=CALIB_FLAGS)


def view_errors(objs, imgs, rvs, tvs, K, d):
    """RMS do erro de reprojeção (px) de cada vista."""
    out = []
    for o, im, rv, tv in zip(objs, imgs, rvs, tvs):
        pr, _ = cv2.projectPoints(o, rv, tv, K, d)
        dd = im.reshape(-1, 2) - pr.reshape(-1, 2)
        out.append(float(np.sqrt(np.mean(np.sum(dd ** 2, axis=1)))))
    return out


if PRUNE_OUTLIERS:
    ve = view_errors(objpoints, imgpoints, rvecs, tvecs, intrinsics, distortion)
    thr = PRUNE_OUTLIERS * float(np.median(ve))
    keep = [i for i, e in enumerate(ve) if e <= thr]
    if len(keep) < len(ve) and len(keep) >= 10:
        print('Removidas %d vistas com erro > %.2f px (%.1f x mediana): %s'
              % (len(ve) - len(keep), thr, PRUNE_OUTLIERS,
                 ', '.join('#%d=%.2f' % (i, ve[i]) for i in range(len(ve)) if i not in keep)))
        objpoints = [objpoints[i] for i in keep]
        imgpoints = [imgpoints[i] for i in keep]
        ret, intrinsics, distortion, rvecs, tvecs = cv2.calibrateCamera(
            objpoints, imgpoints, img_size, None, None, flags=CALIB_FLAGS)

print('\nResolução: %dx%d' % img_size)
if USE_CAMERA and CAPTURE_SIZE is not None and tuple(img_size) != tuple(CAPTURE_SIZE):
    print('ATENÇÃO: pedida %dx%d mas a câmara entregou %dx%d. '
          'Estes parâmetros são válidos só para %dx%d.'
          % (CAPTURE_SIZE + tuple(img_size) + tuple(img_size)))
print('RMS (erro de reprojeção): %.4f px' % ret)

# Erro de reprojeção (RMS) de cada vista: vistas muito acima das outras costumam ser
# imagens desfocadas/tremidas ou com o tabuleiro dobrado -> repetir ou remover.
view_err = []
for i in range(len(objpoints)):
    pr, _ = cv2.projectPoints(objpoints[i], rvecs[i], tvecs[i], intrinsics, distortion)
    d = imgpoints[i].reshape(-1, 2) - pr.reshape(-1, 2)
    view_err.append(float(np.sqrt(np.mean(np.sum(d ** 2, axis=1)))))
worst = sorted(range(len(view_err)), key=lambda i: -view_err[i])[:5]
print('Pior erro por vista: ' + ', '.join('#%d=%.2f px (a %.0f cm)' % (i, view_err[i], float(np.linalg.norm(tvecs[i])))
                                         for i in worst)
      + ' | mediana %.2f px' % float(np.median(view_err)))
print('Distância do tabuleiro à câmara nas vistas: %.0f a %.0f cm (se as piores forem as mais perto/longe, pode ser desfoque)'
      % (min(float(np.linalg.norm(t)) for t in tvecs), max(float(np.linalg.norm(t)) for t in tvecs)))

# Resíduos por zona da imagem: se o erro cresce para as bordas, o modelo de distorção é
# insuficiente (ou a lente está desfocada nas bordas); se é uniforme, é ruído/planicidade.
all_pos, all_res = [], []
for o, im, rv, tv in zip(objpoints, imgpoints, rvecs, tvecs):
    pr, _ = cv2.projectPoints(o, rv, tv, intrinsics, distortion)
    all_pos.append(im.reshape(-1, 2))
    all_res.append(im.reshape(-1, 2) - pr.reshape(-1, 2))
all_pos = np.vstack(all_pos)
all_res = np.vstack(all_res)
half = np.array([img_size[0] / 2.0, img_size[1] / 2.0])
rad = np.hypot(all_pos[:, 0] - half[0], all_pos[:, 1] - half[1]) / np.hypot(*half)
print('Erro RMS por zona da imagem (0 = centro, 1 = canto):')
for lo, hi in [(0.0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.01)]:
    m = (rad >= lo) & (rad < hi)
    if m.any():
        print('   r %.2f-%.2f: %.2f px (%d cantos)'
              % (lo, min(hi, 1.0), float(np.sqrt(np.mean(np.sum(all_res[m] ** 2, axis=1)))), int(m.sum())))
print('RMS em x: %.2f px | RMS em y: %.2f px | viés médio (x, y): (%+.2f, %+.2f) px'
      % (float(np.sqrt(np.mean(all_res[:, 0] ** 2))), float(np.sqrt(np.mean(all_res[:, 1] ** 2))),
         float(all_res[:, 0].mean()), float(all_res[:, 1].mean())))
frac_edge = float(np.mean(rad > 0.5))
print('Cobertura: %.1f %% dos cantos detetados têm r > 0.5 (ideal: > 30 %%)' % (100 * frac_edge))
if frac_edge < 0.2:
    print('ATENÇÃO: o tabuleiro quase só apareceu ao centro da imagem. Faça vistas com o '
          'tabuleiro encostado aos lados e aos cantos: sem isso a distorção e o ponto '
          'principal ficam mal determinados.')
canvas = np.full((img_size[1] // 2, img_size[0] // 2, 3), 255, np.uint8)
for (x, y), (dx, dy) in zip(all_pos / 2.0, all_res):
    cv2.line(canvas, (int(x), int(y)), (int(x + 30 * dx / 2.0), int(y + 30 * dy / 2.0)), (200, 80, 0), 1)
    cv2.circle(canvas, (int(x), int(y)), 1, (0, 0, 0), -1)
cv2.imwrite('residuos.png', canvas)
print('Mapa de resíduos (setas x30) guardado em residuos.png')
print('Intrinsics: ')
print(intrinsics)
print('Distortion (k1, k2, p1, p2, k3): ')
print(distortion)
for i in range(len(tvecs)):
    print('Translations(%d) [cm]: ' % i)
    print(tvecs[i])
    print('Rotation(%d) : ' % i)
    print(rvecs[i])

np.savez(OUTPUT_FILE, intrinsics=intrinsics, distortion=distortion,
         image_size=np.array(img_size))
print('\nParâmetros guardados em', OUTPUT_FILE)