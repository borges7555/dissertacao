# Lab 7 - Ex. 7.4 - Calibração externa (solvePnP)
#
# Dados: parâmetros intrínsecos/distorção (camera_phone.npz) e uma imagem (dep5.jpg).
# Resultado: pose da câmara -> posição de onde a foto foi tirada.
#
# MODE   = 'points'     -> 4 (ou mais) pontos 3D conhecidos + a sua posição na imagem
# MODE   = 'chessboard' -> usa o tabuleiro de xadrez visível na imagem
# COORDS = 'geo'        -> POINTS_3D = [latitude, longitude, altura(m)]  (graus, graus, metros)
# COORDS = 'local'      -> POINTS_3D já em coordenadas métricas locais (x, y, z)

import numpy as np
import cv2

# ---------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------
IMAGE_FILE = './targets/anfs.jpg'
PARAMS_FILE = 'camera_phone_best.npz'
OUTPUT_IMAGE = './targets/anfs_pose.jpg'
CALIB_SIZE = (1280, 720)     # usado só se o .npz não tiver 'image_size'

# Rodar a imagem depois de a ler: None, cv2.ROTATE_90_CLOCKWISE,
# cv2.ROTATE_90_COUNTERCLOCKWISE ou cv2.ROTATE_180
# (foto em pé 1080x1920 -> horizontal 1920x1080)
ROTATE = None

# Fator aplicado a fx e fy (1.0 = focal da calibração). A calibração com o tabuleiro
# a curta distância pode sobrestimar a focal para cenas distantes (foco no infinito).
# Só alterar depois de validar com fotos de posição conhecida.
FOCAL_SCALE = 1.0

# Varrimento opcional da escala da focal: (mínimo, máximo, passo), ex. (0.85, 1.05, 0.01).
# Imprime, para cada escala, o erro de reprojeção e a posição calculada. Com pontos NÃO
# coplanares a escala com menor erro de reprojeção indica a focal que melhor encaixa a foto.
# None = desligado.
SCALE_SWEEP = None

MODE = 'points'              # 'points' ou 'chessboard'
COORDS = 'geo'               # 'geo' ou 'local' (só para MODE='points')

# --- MODE = 'points' ---
POINTS_3D = np.array([
    [40.631278, -8.659628, 22.25],       # ponto 1
    [40.631542, -8.659981, 21.12],       # ponto 2
    [40.631278, -8.659628, 5.05],        # ponto 3
    [40.631542, -8.659981, 3.92],        # ponto 4
    [40.632175, -8.659642, 5.775875],
], dtype=np.float64)

# Posição dos mesmos pontos na imagem JÁ RODADA, em pixéis (x, y), mesma ordem.
# Se None, abre-se a imagem e clica-se nos pontos pela ordem de POINTS_3D.
# (O script imprime os pixéis clicados: copiar para aqui evita voltar a clicar.)
POINTS_2D = None
# POINTS_2D = np.array([[645.12, 837.12], [689.28, 228.48],
#                       [942.72, 840.96], [935.04, 224.64]], dtype=np.float64)

# --- MODE = 'chessboard' ---
board_w = 6                  # cantos internos
board_h = 9
square_size = 2.15           # cm

FONT = cv2.FONT_HERSHEY_SIMPLEX


# ---------------------------------------------------------------
# Conversão lat/lon/altura <-> coordenadas métricas locais (E, N, Up)
# ---------------------------------------------------------------
def meters_per_degree(lat_deg):
    p = np.radians(lat_deg)
    m_lat = 111132.92 - 559.82 * np.cos(2 * p) + 1.175 * np.cos(4 * p)
    m_lon = 111412.84 * np.cos(p) - 93.5 * np.cos(3 * p) + 0.118 * np.cos(5 * p)
    return m_lat, m_lon


def geo_to_local(geo, origin):
    """[lat, lon, h] -> [Este, Norte, Cima] em metros, relativo a 'origin'."""
    m_lat, m_lon = meters_per_degree(origin[0])
    return np.column_stack([(geo[:, 1] - origin[1]) * m_lon,
                            (geo[:, 0] - origin[0]) * m_lat,
                            geo[:, 2] - origin[2]])


def local_to_geo(enu, origin):
    m_lat, m_lon = meters_per_degree(origin[0])
    return np.array([origin[0] + enu[1] / m_lat,
                     origin[1] + enu[0] / m_lon,
                     origin[2] + enu[2]])


# ---------------------------------------------------------------
# Ler parâmetros da câmara e imagem
# ---------------------------------------------------------------
with np.load(PARAMS_FILE) as data:
    intrinsics = data['intrinsics'].astype(np.float64)
    distortion = data['distortion'].astype(np.float64)
    if 'image_size' in data.files:      # guardado pelo chessboard_camera.py
        CALIB_SIZE = tuple(int(v) for v in data['image_size'])
print('Resolução da calibração: %dx%d' % CALIB_SIZE)
print('Intrinsics:\n', intrinsics)
print('Distortion:\n', distortion)

img = cv2.imread(IMAGE_FILE)
if img is None:
    raise SystemExit('Não foi possível abrir ' + IMAGE_FILE)
print('Imagem lida: %dx%d (largura x altura)' % (img.shape[1], img.shape[0]))
if ROTATE is not None:
    img = cv2.rotate(img, ROTATE)
h, w = img.shape[:2]

# Se a imagem tiver outra resolução (mesmo rácio), escalar a matriz intrínseca.
sx = w / CALIB_SIZE[0]
sy = h / CALIB_SIZE[1]
if abs(sx - sy) > 1e-3:
    raise SystemExit('A imagem (%dx%d) tem rácio diferente da calibração (%dx%d): '
                     'os parâmetros não são válidos.' % (w, h, CALIB_SIZE[0], CALIB_SIZE[1]))
if abs(sx - 1.0) > 1e-6:
    print('Aviso: imagem %dx%d; intrínsecos escalados por %.3f' % (w, h, sx))
    intrinsics[0, :] *= sx   # fx, cx
    intrinsics[1, :] *= sy   # fy, cy
if FOCAL_SCALE != 1.0:
    print('Aviso: focal multiplicada por FOCAL_SCALE = %.3f' % FOCAL_SCALE)
    intrinsics[0, 0] *= FOCAL_SCALE
    intrinsics[1, 1] *= FOCAL_SCALE


# ---------------------------------------------------------------
# Obter pontos 3D / 2D
# ---------------------------------------------------------------
def pick_points(image, n):
    """Clicar nos n pontos pela ordem de POINTS_3D (ESC cancela)."""
    scale = min(1.0, 1000.0 / image.shape[1])
    disp = cv2.resize(image, None, fx=scale, fy=scale) if scale < 1 else image.copy()
    pts = []
    win = 'clicar nos pontos (ESC sai)'

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(pts) < n:
            pts.append((x / scale, y / scale))
            cv2.circle(disp, (x, y), 5, (0, 0, 255), -1)
            cv2.putText(disp, str(len(pts)), (x + 8, y - 8), FONT, 0.7, (0, 0, 255), 2)

    cv2.namedWindow(win)
    cv2.setMouseCallback(win, on_mouse)
    while len(pts) < n:
        cv2.imshow(win, disp)
        if cv2.waitKey(20) & 0xFF == 27:
            raise SystemExit('Cancelado')
    cv2.imshow(win, disp)
    cv2.waitKey(400)
    cv2.destroyAllWindows()
    return np.array(pts, dtype=np.float64)


geo_origin = None
if MODE == 'chessboard':
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    found, corners = cv2.findChessboardCorners(gray, (board_w, board_h), None)
    if not found:
        raise SystemExit('Tabuleiro não encontrado na imagem')
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
    obj_pts = np.zeros((board_w * board_h, 3), np.float64)
    obj_pts[:, :2] = np.mgrid[0:board_w, 0:board_h].T.reshape(-1, 2) * square_size
    img_pts = corners.reshape(-1, 2).astype(np.float64)
else:
    if COORDS == 'geo':
        # Graus não são metros: converter para coordenadas métricas locais
        # (Este, Norte, Cima) com origem no 1.º ponto.
        geo_origin = POINTS_3D[0].copy()
        obj_pts = geo_to_local(POINTS_3D, geo_origin)
        print('\nPontos 3D em metros (Este, Norte, Cima) relativos ao ponto 1:\n',
              np.round(obj_pts, 2))
    else:
        obj_pts = POINTS_3D.astype(np.float64)
    img_pts = POINTS_2D if POINTS_2D is not None else pick_points(img, len(obj_pts))
    img_pts = np.asarray(img_pts, dtype=np.float64).reshape(-1, 2)
    print('Pontos 2D usados (px):\n', np.round(img_pts, 2))

n = len(obj_pts)
if n < 4:
    raise SystemExit('São necessários pelo menos 4 pontos')


# ---------------------------------------------------------------
# Calibração externa: pose do mundo relativamente à câmara
#   X_cam = R * X_mundo + t
# ---------------------------------------------------------------
def reproj_error(rv, tv):
    pr, _ = cv2.projectPoints(obj_pts, rv, tv, intrinsics, distortion)
    return np.linalg.norm(pr.reshape(-1, 2) - img_pts, axis=1)


def solve_pose():
    """Devolve lista de candidatos (rvec, tvec, erro médio), do melhor para o pior."""
    sv = np.linalg.svd(obj_pts - obj_pts.mean(axis=0), compute_uv=False)
    planar = sv[2] / sv[0] < 1e-4
    cands = []
    if planar:
        # Pontos coplanares: IPPE devolve as 2 soluções possíveis
        print('\nPontos coplanares -> solvePnP IPPE (2 soluções possíveis)')
        k, rvs, tvs, _ = cv2.solvePnPGeneric(obj_pts, img_pts, intrinsics, distortion,
                                             flags=cv2.SOLVEPNP_IPPE)
        pairs = list(zip(rvs, tvs)) if k > 0 else []
    else:
        # ITERATIVE usa DLT sem uma estimativa inicial e exige pelo menos
        # 6 correspondências não coplanares. SQPNP suporta 3 ou mais.
        flags = cv2.SOLVEPNP_AP3P if n == 4 else cv2.SOLVEPNP_SQPNP
        ok, rv, tv = cv2.solvePnP(obj_pts, img_pts, intrinsics, distortion, flags=flags)
        pairs = [(rv, tv)] if ok else []
    for rv, tv in pairs:
        rv, tv = cv2.solvePnPRefineLM(obj_pts, img_pts, intrinsics, distortion, rv, tv)
        R_ = cv2.Rodrigues(rv)[0]
        if np.any((R_ @ obj_pts.T + tv).T[:, 2] <= 0):
            continue                     # pontos atrás da câmara -> inválida
        cands.append((rv, tv, reproj_error(rv, tv).mean()))
    cands.sort(key=lambda c: c[2])
    # O refinamento pode levar as 2 soluções IPPE ao mesmo mínimo: remover duplicados
    unique = []
    for rv, tv, e in cands:
        c = (-cv2.Rodrigues(rv)[0].T @ tv).ravel()
        if all(np.linalg.norm(c - u[3]) > 0.01 * np.linalg.norm(tv) for u in unique):
            unique.append((rv, tv, e, c))
    return [(rv, tv, e) for rv, tv, e, _ in unique]


cands = solve_pose()
if not cands:
    raise SystemExit('solvePnP falhou (nenhuma solução válida). Verifique a ordem '
                     'e as unidades dos pontos 3D e os pontos 2D.')


def describe(rv, tv):
    R = cv2.Rodrigues(rv)[0]
    cam = (-R.T @ tv).ravel()                       # C = -R^T t
    view = (R.T @ np.array([[0.0], [0.0], [1.0]])).ravel()
    return R, cam, view


def print_camera(cam, view):
    if geo_origin is not None:
        g = local_to_geo(cam, geo_origin)
        print('   Latitude : %.6f' % g[0])
        print('   Longitude: %.6f' % g[1])
        print('   Altura   : %.2f m' % g[2])
        print('   (Este, Norte, Cima) rel. ao ponto 1: (%.1f, %.1f, %.1f) m' % tuple(cam))
        print('   https://www.google.com/maps?q=%.6f,%.6f' % (g[0], g[1]))
    else:
        print('   X = %.2f   Y = %.2f   Z = %.2f' % tuple(cam))
    print('   Direção do eixo ótico (mundo):', np.round(view, 3))


if SCALE_SWEEP is not None:
    import io
    import contextlib
    base_K = intrinsics.copy()
    print('\n=== Varrimento de FOCAL_SCALE (relativo ao valor atual) ===')
    print('  escala   erro px   latitude    longitude   altura')
    rows = []
    for sc in np.arange(SCALE_SWEEP[0], SCALE_SWEEP[1] + 1e-9, SCALE_SWEEP[2]):
        intrinsics[0, 0] = base_K[0, 0] * sc
        intrinsics[1, 1] = base_K[1, 1] * sc
        with contextlib.redirect_stdout(io.StringIO()):
            cs = solve_pose()
        if not cs:
            print('  %.3f    (sem solução válida)' % sc)
            continue
        rv_, tv_, e_ = cs[0]
        cam_ = describe(rv_, tv_)[1]
        g_ = local_to_geo(cam_, geo_origin) if geo_origin is not None else cam_
        rows.append((e_, sc))
        print('  %.3f    %6.2f    %s' % (sc, e_, '  '.join('%.6f' % v for v in g_[:2]) +
                                         '   %.2f' % g_[2] if geo_origin is not None
                                         else '  '.join('%.2f' % v for v in g_)))
    intrinsics[:] = base_K
    if rows:
        print('  -> menor erro de reprojeção em escala %.3f (%.2f px)' % (min(rows)[1], min(rows)[0]))

rvec, tvec, best_err = cands[0]
R, cam_pos, view_dir = describe(rvec, tvec)

print('\nRotation vector (rvec):', rvec.ravel())
print('Translation vector (tvec):', tvec.ravel())
print('\n=== POSIÇÃO DA CÂMARA (melhor solução, erro médio %.2f px) ===' % best_err)
print_camera(cam_pos, view_dir)

if len(cands) > 1:
    rv2, tv2, err2 = cands[1]
    _, cam2, view2 = describe(rv2, tv2)
    print('\n--- Solução alternativa (erro médio %.2f px) ---' % err2)
    print_camera(cam2, view2)
    if err2 < 3 * best_err:
        print('ATENÇÃO: as duas soluções têm erros parecidos -> posição ambígua.')

errs = reproj_error(rvec, tvec)
print('\nErro de reprojeção por ponto (px):', np.round(errs, 2))
print('Erro médio: %.2f px' % errs.mean())

# Imagem de verificação: verde = pontos dados, vermelho = reprojetados
proj, _ = cv2.projectPoints(obj_pts, rvec, tvec, intrinsics, distortion)
proj = proj.reshape(-1, 2)
out = img.copy()
for i in range(n):
    p = tuple(int(round(v)) for v in img_pts[i])
    q = tuple(int(round(v)) for v in proj[i])
    cv2.circle(out, p, 6, (0, 255, 0), 2)
    cv2.circle(out, q, 3, (0, 0, 255), -1)
    cv2.putText(out, str(i + 1), (p[0] + 8, p[1] - 8), FONT, 0.7, (0, 255, 0), 2)
cv2.imwrite(OUTPUT_IMAGE, out)
print('Imagem de verificação guardada em', OUTPUT_IMAGE)

scale = min(1.0, 1000.0 / w)
cv2.imshow('verde = pontos dados | vermelho = reprojecao',
           cv2.resize(out, None, fx=scale, fy=scale) if scale < 1 else out)
cv2.waitKey(-1)
cv2.destroyAllWindows()