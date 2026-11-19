# Lab 7 - Ex. 7.2 - Projeção de pontos 3D na imagem (cubo e normal ao tabuleiro)
# Baseado no código do 7.1 (Paulo Dias)
#
# Desenha, em cada imagem com o tabuleiro detetado,
#   - uma linha normal ao tabuleiro (a partir do centro do padrão)
#   - um cubo em arame com um canto na origem do padrão
# usando cv2.projectPoints com a pose (rvec, tvec) de cada imagem.
#
# USE_SAVED_PARAMS = True : lê intrinsics/distortion do ficheiro do 7.3 (câmara do telemóvel)
#                           e calcula a pose de cada imagem com solvePnP (como no 7.4).
# USE_SAVED_PARAMS = False: calibra aqui (como no enunciado do 7.2) e usa os rvecs/tvecs
#                           da calibração.
#
# Teclas na janela: qualquer tecla = próxima imagem; q ou ESC = terminar.

import os
import numpy as np
import cv2
import glob

# ---------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------
IMAGE_PATTERNS = ['./unity1/unity*.jpg', './unity2/unity*.jpg']

USE_SAVED_PARAMS = False
PARAMS_FILE = 'camera_phone_best.npz'    # gerado pelo chessboard7_3.py

VIEWS = None            # None = todas as imagens com tabuleiro; ou lista de índices, ex. [0]
SAVE_DIR = 'cubes'      # pasta onde guardar as imagens com o cubo (None = não guardar)
SHOW_MS = 0             # 0 = esperar por uma tecla; >0 = avança sozinho após esse nº de ms

# Board Size (cantos internos)
board_h = 9
board_w = 6

# Unidade do padrão: 1.0 = lado de um quadrado. Para cm usar 2.15 (o lado real).
square_size = 1.0

# Critério usado apenas no cornerSubPix (opcional)
subpix_criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

# Pontos 3D do tabuleiro: (0,0,0), (1,0,0), ..., (5,8,0), em unidades de square_size
objp = np.zeros((board_w * board_h, 3), np.float32)
objp[:, :2] = np.mgrid[0:board_w, 0:board_h].T.reshape(-1, 2)
objp = objp * square_size


def show(img):
    """Reduz imagens grandes para caberem no ecrã (só para visualização)."""
    return cv2.resize(img, None, fx=0.5, fy=0.5) if img.shape[1] > 1400 else img


# ---------------------------------------------------------------
# 1) Deteção do tabuleiro em todas as imagens
# ---------------------------------------------------------------
images = []
for pattern in IMAGE_PATTERNS:
    images += sorted(glob.glob(pattern))     # glob.glob recebe um padrão (string) de cada vez
print('Imagens encontradas: %d' % len(images))
if not images:
    raise SystemExit('Nenhuma imagem encontrada para os padrões: %s' % IMAGE_PATTERNS)

used_files = []     # ficheiros com tabuleiro detetado
imgpoints = []      # cantos 2D de cada um
sizes = []          # (largura, altura) de cada um

for fname in images:
    img = cv2.imread(fname)
    if img is None:
        continue
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    found, corners = cv2.findChessboardCorners(gray, (board_w, board_h), None)
    if not found:
        print('Tabuleiro NÃO encontrado em', fname)
        continue
    corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), subpix_criteria)
    used_files.append(fname)
    imgpoints.append(corners)
    sizes.append((gray.shape[1], gray.shape[0]))
print('Imagens com tabuleiro detetado: %d' % len(used_files))
if not used_files:
    raise SystemExit('Tabuleiro não detetado em nenhuma imagem.')

# ---------------------------------------------------------------
# 2) Parâmetros da câmara e pose de cada imagem
# ---------------------------------------------------------------
poses = []          # (rvec, tvec, K, erro de reprojeção médio) por imagem

if USE_SAVED_PARAMS:
    with np.load(PARAMS_FILE) as data:
        K0 = data['intrinsics'].astype(np.float64)
        distortion = data['distortion'].astype(np.float64)
        calib_size = tuple(int(v) for v in data['image_size']) if 'image_size' in data.files else None
    print('Parâmetros lidos de %s (resolução da calibração: %s)' % (PARAMS_FILE, calib_size))
    print('Intrinsics:\n', K0)
    print('Distortion:\n', distortion)

    keep = []
    for idx, (fname, corners, size) in enumerate(zip(used_files, imgpoints, sizes)):
        K = K0.copy()
        if calib_size is not None and size != calib_size:
            sx, sy = size[0] / calib_size[0], size[1] / calib_size[1]
            if abs(sx - sy) > 1e-3:
                print('Ignorada (rácio %dx%d diferente da calibração): %s' % (size + (fname,)))
                continue
            K[0, :] *= sx
            K[1, :] *= sy
        # Pose do tabuleiro nesta imagem (padrão plano -> IPPE) + refinamento
        ok, rv, tv = cv2.solvePnP(objp, corners, K, distortion, flags=cv2.SOLVEPNP_IPPE)
        if not ok:
            print('solvePnP falhou em', fname)
            continue
        rv, tv = cv2.solvePnPRefineLM(objp, corners, K, distortion, rv, tv)
        proj, _ = cv2.projectPoints(objp, rv, tv, K, distortion)
        err = np.linalg.norm(proj.reshape(-1, 2) - corners.reshape(-1, 2), axis=1).mean()
        poses.append((rv, tv, K, err))
        keep.append(idx)
    used_files = [used_files[i] for i in keep]

else:
    # Calibração aqui, como no enunciado (precisa de imagens com a mesma resolução)
    ref_size = sizes[0]
    keep = [i for i, s in enumerate(sizes) if s == ref_size]
    if len(keep) < len(sizes):
        print('Aviso: %d imagens ignoradas por terem resolução diferente de %dx%d'
              % (len(sizes) - len(keep), ref_size[0], ref_size[1]))
    used_files = [used_files[i] for i in keep]
    imgpoints = [imgpoints[i] for i in keep]
    objpoints = [objp] * len(imgpoints)

    ret, K, distortion, rvecs, tvecs = cv2.calibrateCamera(
        objpoints, imgpoints, ref_size, None, None)
    print('RMS da calibração: %.4f px' % ret)
    print("Intrinsics: ")
    print(K)
    print("Distortion : ")
    print(distortion)
    for rv, tv, corners in zip(rvecs, tvecs, imgpoints):
        proj, _ = cv2.projectPoints(objp, rv, tv, K, distortion)
        err = np.linalg.norm(proj.reshape(-1, 2) - corners.reshape(-1, 2), axis=1).mean()
        poses.append((rv, tv, K, err))

if not poses:
    raise SystemExit('Sem poses válidas.')

# ---------------------------------------------------------------
# 3) Pontos 3D a projetar (7.2)
# ---------------------------------------------------------------
# No OpenCV o eixo Z do padrão aponta para dentro do tabuleiro; por isso, para o
# cubo e a normal "saírem" do tabuleiro em direção à câmara usa-se Z negativo.

# Cubo de lado = 2 quadrados com um canto na origem do padrão
cube_side = 2 * square_size
cube = np.float32([[0, 0, 0], [0, 1, 0], [1, 1, 0], [1, 0, 0],      # base (em Z = 0)
                   [0, 0, -1], [0, 1, -1], [1, 1, -1], [1, 0, -1]   # topo
                   ]) * cube_side

# Linha normal ao tabuleiro: do centro do padrão para fora, com comprimento de 4 quadrados
center = np.float32([(board_w - 1) / 2.0, (board_h - 1) / 2.0, 0]) * square_size
normal = np.float32([center, center + np.float32([0, 0, -4 * square_size])])


def draw_cube(img, pts):
    t = max(2, img.shape[1] // 400)   # espessura proporcional à resolução
    pts = np.int32(np.round(pts)).reshape(-1, 2)
    cv2.polylines(img, [pts[:4]], True, (0, 255, 0), t)             # base  (verde)
    for i, j in zip(range(4), range(4, 8)):
        cv2.line(img, tuple(pts[i]), tuple(pts[j]), (255, 0, 0), t)  # arestas (azul)
    cv2.polylines(img, [pts[4:]], True, (0, 0, 255), t)             # topo  (vermelho)
    return img


def draw_normal(img, pts):
    t = max(3, img.shape[1] // 300)
    pts = np.int32(np.round(pts)).reshape(-1, 2)
    cv2.arrowedLine(img, tuple(pts[0]), tuple(pts[1]), (0, 255, 255), t, tipLength=0.15)
    return img


# ---------------------------------------------------------------
# 4) Projeção e desenho em cada imagem
# ---------------------------------------------------------------
if SAVE_DIR:
    os.makedirs(SAVE_DIR, exist_ok=True)

views = range(len(used_files)) if VIEWS is None else VIEWS
for i in views:
    fname = used_files[i]
    rvec, tvec, K, err = poses[i]
    img = cv2.imread(fname)

    # Projeção dos pontos 3D com a pose (rvec, tvec) desta imagem e os parâmetros da câmara
    cube_2d, _ = cv2.projectPoints(cube, rvec, tvec, K, distortion)
    normal_2d, _ = cv2.projectPoints(normal, rvec, tvec, K, distortion)

    img = draw_cube(img, cube_2d)
    img = draw_normal(img, normal_2d)

    # Nome de saída com a pasta (unity1/unity1.jpg != unity2/unity1.jpg)
    parts = fname.replace('\\', '/').split('/')
    tag = '_'.join(q for q in parts[-2:] if q not in ('.', '')).rsplit('.', 1)[0]
    if SAVE_DIR:
        cv2.imwrite(os.path.join(SAVE_DIR, 'cube_%s.png' % tag), img)
    print('[%d/%d] %s  (erro de reprojeção do tabuleiro: %.2f px)'
          % (i + 1, len(used_files), fname, err))

    cv2.imshow('7.2 - cubo e normal', show(img))
    key = cv2.waitKey(SHOW_MS if SHOW_MS > 0 else -1) & 0xFF
    if key in (ord('q'), 27):
        break

cv2.destroyAllWindows()