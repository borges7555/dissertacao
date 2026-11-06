# Lab 7 - Ex. 7.3 - Calibração com a câmara (DroidCam)
#
# Teclas (na janela de vídeo):
#   ESPAÇO -> guarda a vista atual (só se o tabuleiro estiver detetado)
#   q      -> termina a captura (e calibra se houver vistas suficientes)

import numpy as np
import cv2
import glob

# ---------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------
USE_CAMERA = False       # False -> usa fotos (IMAGE_GROUPS) em vez da câmara

# Só com USE_CAMERA = False: lista de grupos de fotos (um padrão glob por grupo).
# Cada grupo é calibrado em separado para comparar; depois calibra-se com todos juntos.
# Ex.: ['./set1/*.jpg', './set2/*.jpg']  (todas as fotos com a mesma resolução/orientação)
IMAGE_GROUPS = ['./unity1/unity*.jpg', './unity2/unity*.jpg']

# Fonte de vídeo do DroidCam:
#  - com o DroidCam Client no PC aparece como webcam: tentar 1, 2, ...
#  - alternativa por Wi-Fi: "http://<IP_DO_TELEMOVEL>:4747/video"
CAMERA_SOURCE = 1

# Resolução pedida à câmara (largura, altura). O OpenCV pode ignorar o que está
# definido na app do DroidCam, por isso pede-se aqui e confirma-se no fim.
# Usar None para a resolução por defeito.
CAPTURE_SIZE = (1280, 720)

NUM_IMAGES = 20         # nº de vistas a capturar
OUTPUT_FILE = 'camera_phone.npz'   # mudar o nome para não sobrescrever calibrações anteriores

# Flags do calibrateCamera. 0 = modelo completo (k1,k2,p1,p2,k3).
# Se k2/k3 saírem absurdos (|k3| > ~1), tentar cv2.CALIB_FIX_K3 ou
# cv2.CALIB_FIX_K2 + cv2.CALIB_FIX_K3 para estabilizar a distância focal.
CALIB_FLAGS = 0

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
    """Calibra com 3 modelos de distorção e imprime fx, fy, cx, cy e RMS."""
    print('\n%s (%d vistas)' % (name, len(objs)))
    for label, fl in [('modelo completo      ', 0),
                      ('k3 fixo              ', cv2.CALIB_FIX_K3),
                      ('k2 e k3 fixos        ', cv2.CALIB_FIX_K2 + cv2.CALIB_FIX_K3)]:
        r, K, d, _, _ = cv2.calibrateCamera(objs, imgs, size, None, None, flags=fl)
        print('  %s fx=%7.1f fy=%7.1f cx=%6.1f cy=%6.1f RMS=%.3f  k=%s'
              % (label, K[0, 0], K[1, 1], K[0, 2], K[1, 2], r,
                 np.round(d.ravel()[[0, 1, 4]], 2)))


# ---------------------------------------------------------------
# Aquisição
# ---------------------------------------------------------------
if USE_CAMERA:
    capture = cv2.VideoCapture(CAMERA_SOURCE)
    if not capture.isOpened():
        raise SystemExit('Não foi possível abrir a fonte de vídeo: %s' % str(CAMERA_SOURCE))

    if CAPTURE_SIZE is not None:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_SIZE[0])
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_SIZE[1])

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
        cv2.imshow('video', display)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        if key == ord(' ') and found:
            objpoints.append(objp)
            imgpoints.append(corners)
            print('Vista %d guardada' % len(objpoints))
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

print('\nResolução: %dx%d' % img_size)
if USE_CAMERA and CAPTURE_SIZE is not None and tuple(img_size) != tuple(CAPTURE_SIZE):
    print('ATENÇÃO: pedida %dx%d mas a câmara entregou %dx%d. '
          'Estes parâmetros são válidos só para %dx%d.'
          % (CAPTURE_SIZE + tuple(img_size) + tuple(img_size)))
print('RMS (erro de reprojeção): %.4f px' % ret)
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