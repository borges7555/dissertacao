# Lab 7 - Optional (após o 7.4) - Calibração externa em tempo real e projeção de um cubo
#
# Em cada frame do live feed (DroidCam):
#   1) deteta o tabuleiro
#   2) calcula a pose (rvec, tvec) com solvePnP, usando os parâmetros da câmara guardados
#   3) projeta com cv2.projectPoints um cubo, a normal e os eixos sobre o tabuleiro
#
# Teclas: q / ESC = sair | c = cubo on/off | n = normal on/off | a = eixos on/off
#         s = guardar o frame atual (live_XXXX.png)

import time
import numpy as np
import cv2

# ---------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------
# Fonte de vídeo do DroidCam:
#  - com o DroidCam Client no PC aparece como webcam: 1, 2, ... (0 costuma ser a do portátil)
#  - alternativa por Wi-Fi: "http://<IP_DO_TELEMOVEL>:4747/video"
CAMERA_SOURCE = 2

# Resolução pedida à câmara (largura, altura). None = por defeito.
CAPTURE_SIZE = (1920, 1080)

# Opções para webcam USB (usar as MESMAS da calibração, incluindo o foco):
CAMERA_BACKEND = cv2.CAP_DSHOW   # Windows: cv2.CAP_DSHOW
USE_MJPG = True               # True = pede MJPG (muitas webcams só dão 1080p assim)
LOCK_FOCUS = 45              # None = não mexer; 0..255 = desliga o autofocus e fixa o foco

# Parâmetros da câmara. O ideal é uma calibração feita com ESTE live feed
# (chessboard7_3.py com USE_CAMERA = True e a mesma resolução). Se o ficheiro tiver
# 'image_size' com o mesmo rácio mas outra resolução, a matriz K é escalada.
PARAMS_FILE = 'camera_logitech_f45.npz'

# Cantos INTERNOS do tabuleiro
board_w = 6
board_h = 9

# Lado de cada quadrado: 1.0 = unidades de quadrados; 2.15 = cm (a distância sai em cm)
square_size = 2.15
UNIT = 'cm'

# Deteção mais rápida: o tabuleiro é procurado numa imagem reduzida (0.5 = metade).
# 1.0 = resolução total (mais preciso, mais lento).
DETECT_SCALE = 1.0

# Erro de reprojeção (px) acima do qual a pose é considerada pouco fiável
MAX_REPROJ_ERR = 4.0

subpix_criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
FONT = cv2.FONT_HERSHEY_SIMPLEX

# ---------------------------------------------------------------
# Modelo 3D do tabuleiro e dos objetos a projetar
# ---------------------------------------------------------------
objp = np.zeros((board_w * board_h, 3), np.float32)
objp[:, :2] = np.mgrid[0:board_w, 0:board_h].T.reshape(-1, 2)
objp = objp * square_size

# No OpenCV o eixo Z do padrão aponta para dentro do tabuleiro: Z negativo = em direção
# à câmara (o cubo "sai" do tabuleiro).
cube_side = 2 * square_size
cube = np.float32([[0, 0, 0], [0, 1, 0], [1, 1, 0], [1, 0, 0],
                   [0, 0, -1], [0, 1, -1], [1, 1, -1], [1, 0, -1]]) * cube_side

center = np.float32([(board_w - 1) / 2.0, (board_h - 1) / 2.0, 0]) * square_size
normal = np.float32([center, center + np.float32([0, 0, -4 * square_size])])

axes = np.float32([[0, 0, 0], [3, 0, 0], [0, 3, 0], [0, 0, -3]]) * square_size


def put_text(img, text, org, scale, color, thick):
    """Texto com contorno preto, legível sobre qualquer fundo."""
    cv2.putText(img, text, org, FONT, scale, (0, 0, 0), thick + 3, cv2.LINE_AA)
    cv2.putText(img, text, org, FONT, scale, color, thick, cv2.LINE_AA)


def draw_cube(img, pts):
    t = max(2, img.shape[1] // 400)
    pts = np.int32(np.round(pts)).reshape(-1, 2)
    cv2.polylines(img, [pts[:4]], True, (0, 255, 0), t)              # base  (verde)
    for i, j in zip(range(4), range(4, 8)):
        cv2.line(img, tuple(pts[i]), tuple(pts[j]), (255, 0, 0), t)   # arestas (azul)
    cv2.polylines(img, [pts[4:]], True, (0, 0, 255), t)              # topo  (vermelho)


def draw_normal(img, pts):
    t = max(3, img.shape[1] // 300)
    pts = np.int32(np.round(pts)).reshape(-1, 2)
    cv2.arrowedLine(img, tuple(pts[0]), tuple(pts[1]), (0, 255, 255), t, tipLength=0.15)


def draw_axes(img, pts):
    t = max(2, img.shape[1] // 400)
    pts = np.int32(np.round(pts)).reshape(-1, 2)
    o = tuple(pts[0])
    cv2.line(img, o, tuple(pts[1]), (0, 0, 255), t)    # X vermelho
    cv2.line(img, o, tuple(pts[2]), (0, 255, 0), t)    # Y verde
    cv2.line(img, o, tuple(pts[3]), (255, 0, 0), t)    # Z azul


# ---------------------------------------------------------------
# Parâmetros da câmara e live feed
# ---------------------------------------------------------------
with np.load(PARAMS_FILE) as data:
    K_file = data['intrinsics'].astype(np.float64)
    distortion = data['distortion'].astype(np.float64)
    calib_size = tuple(int(v) for v in data['image_size']) if 'image_size' in data.files else None
print('Parâmetros lidos de %s (resolução da calibração: %s)' % (PARAMS_FILE, calib_size))
print('Intrinsics:\n', K_file)
print('Distortion:\n', distortion)

capture = cv2.VideoCapture(CAMERA_SOURCE, CAMERA_BACKEND)
if not capture.isOpened():
    raise SystemExit('Não foi possível abrir a fonte de vídeo: %s' % str(CAMERA_SOURCE))
# A ordem importa: formato -> resolução -> foco
if USE_MJPG:
    capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
if CAPTURE_SIZE is not None:
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_SIZE[0])
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_SIZE[1])
if LOCK_FOCUS is not None:
    capture.set(cv2.CAP_PROP_AUTOFOCUS, 0)
    capture.set(cv2.CAP_PROP_FOCUS, LOCK_FOCUS)
print('Câmara aberta: %dx%d | foco=%s' % (capture.get(cv2.CAP_PROP_FRAME_WIDTH),
                                         capture.get(cv2.CAP_PROP_FRAME_HEIGHT),
                                         capture.get(cv2.CAP_PROP_FOCUS)))
for _ in range(10):      # descarta frames iniciais (exposição e foco a estabilizar)
    capture.read()

ok, frame = capture.read()
if not ok:
    raise SystemExit('Não foi possível ler o primeiro frame')
h, w = frame.shape[:2]
print('Resolução do live feed: %dx%d' % (w, h))

# Escalar K se a resolução do feed for diferente da da calibração (mesmo rácio)
K = K_file.copy()
if calib_size is not None and (w, h) != calib_size:
    sx, sy = w / calib_size[0], h / calib_size[1]
    if abs(sx - sy) > 1e-3:
        raise SystemExit('O live feed (%dx%d) tem rácio diferente da calibração (%dx%d): '
                         'os parâmetros não são válidos. Calibre com este feed.'
                         % (w, h, calib_size[0], calib_size[1]))
    print('Aviso: K escalada por %.3f (feed %dx%d, calibração %dx%d)'
          % (sx, w, h, calib_size[0], calib_size[1]))
    K[0, :] *= sx
    K[1, :] *= sy

detect_flags = (cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE
                + cv2.CALIB_CB_FAST_CHECK)

show_cube, show_normal, show_axes = True, True, True
prev_pose = None
frames = detected = saved = 0
t0 = time.time()

while ok:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    frames += 1

    # 1) Deteção do tabuleiro (opcionalmente numa imagem reduzida)
    if DETECT_SCALE < 1.0:
        small = cv2.resize(gray, None, fx=DETECT_SCALE, fy=DETECT_SCALE)
        found, corners = cv2.findChessboardCorners(small, (board_w, board_h), detect_flags)
        if found:
            corners = corners / DETECT_SCALE
    else:
        found, corners = cv2.findChessboardCorners(gray, (board_w, board_h), detect_flags)

    status, color = 'Tabuleiro nao detetado', (0, 0, 255)
    if found:
        corners = cv2.cornerSubPix(gray, corners.astype(np.float32), (11, 11), (-1, -1),
                                   subpix_criteria)

        # 2) Calibração externa: pose do tabuleiro em relação à câmara
        if prev_pose is None:
            good, rvec, tvec = cv2.solvePnP(objp, corners, K, distortion,
                                            flags=cv2.SOLVEPNP_IPPE)
        else:   # usa a pose anterior como estimativa inicial (mais estável entre frames)
            good, rvec, tvec = cv2.solvePnP(objp, corners, K, distortion,
                                            prev_pose[0].copy(), prev_pose[1].copy(), True,
                                            cv2.SOLVEPNP_ITERATIVE)
        if good:
            proj, _ = cv2.projectPoints(objp, rvec, tvec, K, distortion)
            err = np.linalg.norm(proj.reshape(-1, 2) - corners.reshape(-1, 2), axis=1).mean()
            if err > MAX_REPROJ_ERR:
                prev_pose = None            # pose duvidosa: recomeça no próximo frame
                status, color = 'Pose pouco fiavel (erro %.1f px)' % err, (0, 165, 255)
            else:
                prev_pose = (rvec, tvec)
                detected += 1

                # 3) Projeção dos pontos 3D com a pose calculada
                if show_cube:
                    pts, _ = cv2.projectPoints(cube, rvec, tvec, K, distortion)
                    draw_cube(frame, pts)
                if show_normal:
                    pts, _ = cv2.projectPoints(normal, rvec, tvec, K, distortion)
                    draw_normal(frame, pts)
                if show_axes:
                    pts, _ = cv2.projectPoints(axes, rvec, tvec, K, distortion)
                    draw_axes(frame, pts)

                R, _ = cv2.Rodrigues(rvec)
                cam = (-R.T @ tvec).ravel()          # posição da câmara no referencial do tabuleiro
                status = 'dist. %.1f %s | camara em (%.1f, %.1f, %.1f) %s | erro %.2f px' % (
                    np.linalg.norm(tvec), UNIT, cam[0], cam[1], cam[2], UNIT, err)
                color = (0, 255, 0)
        else:
            prev_pose = None
    else:
        prev_pose = None

    put_text(frame, status, (10, 28), 0.7, color, 2)
    fps = frames / max(time.time() - t0, 1e-6)
    put_text(frame, '%.1f fps | q=sair c=cubo n=normal a=eixos s=guardar' % fps,
             (10, h - 12), 0.55, (255, 255, 255), 1)
    cv2.imshow('Live - cubo no tabuleiro', frame)

    key = cv2.waitKey(1) & 0xFF
    if key in (ord('q'), 27):
        break
    elif key == ord('c'):
        show_cube = not show_cube
    elif key == ord('n'):
        show_normal = not show_normal
    elif key == ord('a'):
        show_axes = not show_axes
    elif key == ord('s'):
        saved += 1
        cv2.imwrite('live_%04d.png' % saved, frame)
        print('Frame guardado em live_%04d.png' % saved)

    ok, frame = capture.read()

capture.release()
cv2.destroyAllWindows()
print('Frames: %d | tabuleiro e pose válidos em %d (%.0f %%)'
      % (frames, detected, 100.0 * detected / max(frames, 1)))
