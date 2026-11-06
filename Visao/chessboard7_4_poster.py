# Lab 7 - Ex. 7.4 (versão "poster") - Distância da câmara a um ponto de referência (solvePnP)
#
# Os pontos 3D são medidos no plano do poster, em cm, relativamente à ORIGEM
# (por exemplo, o canto inferior esquerdo):
#     x > 0 para a DIREITA da origem,  y > 0 para CIMA da origem.
# O programa calcula onde estava a câmara (o telemóvel) em relação à origem:
#     X = deslocamento para a direita, Y = para cima, Z = afastamento perpendicular ao poster.
# Depois calcula a distância da câmara ao ponto onde mediu a distância (MEASURED_REF).
#
# Sistema de coordenadas do mundo (direto): X direita, Y cima, Z para fora do poster, em
# direção a quem o vê. A câmara fica, portanto, em Z > 0.
#
# MODE = 'poster'     -> 4 (ou mais) pontos medidos por si (POINTS_CM) + cliques na imagem
# MODE = 'chessboard' -> usa o tabuleiro de xadrez visível na imagem (54 cantos detetados
#                        automaticamente, com sub-pixel): ideal para validar a calibração

import numpy as np
import cv2

# ---------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------
IMAGE_FILE = 'poster.jpg'
PARAMS_FILE = 'camera_phone_best.npz'
OUTPUT_IMAGE = 'poster_pose.jpg'
CALIB_SIZE = (1920, 1080)    # usado só se o .npz não tiver 'image_size'

# Rodar a imagem depois de a ler: None, cv2.ROTATE_90_CLOCKWISE,
# cv2.ROTATE_90_COUNTERCLOCKWISE ou cv2.ROTATE_180
# (foto em pé 1080x1920 -> horizontal 1920x1080)
ROTATE = None

MODE = 'poster'              # 'poster' ou 'chessboard'

# Fator aplicado a fx e fy (1.0 = focal da calibração). Só alterar depois de validar
# com medições reais em várias distâncias.
FOCAL_SCALE = 1.0

# Varrimento opcional da escala da focal: (mínimo, máximo, passo), ex. (0.90, 1.10, 0.02).
# Mostra como a posição calculada varia com a focal. None = desligado.
SCALE_SWEEP = None

# Distância que mediu no terreno (cm), da lente do telemóvel ao ponto MEASURED_REF.
# None = não comparar.
MEASURED_CM = None

# Ponto do poster ao qual a distância medida se refere:
#   'origin' = origem (ponto 1) | 'center' = centro dos pontos | (x, y) em cm
MEASURED_REF = 'center'

# --- MODE = 'poster': dimensões medidas (cm). SUBSTITUIR pelos valores reais! ---
POSTER_W_CM = 61.0
POSTER_H_CM = 91.0

# Pontos 3D, em cm, relativos à origem: [x (direita), y (cima)] ou [x, y, z]
# z (opcional) = afastamento do ponto à superfície do poster, para fora (cm).
# A ordem tem de ser a mesma dos pontos 2D (cliques).
POINTS_CM = np.array([
    [0.0,         0.0],           # ponto 1: canto inferior esquerdo = ORIGEM
    [POSTER_W_CM, 0.0],           # ponto 2: canto inferior direito
    [POSTER_W_CM, POSTER_H_CM],   # ponto 3: canto superior direito
    [0.0,         POSTER_H_CM],   # ponto 4: canto superior esquerdo
], dtype=np.float64)

# Posição dos mesmos pontos na imagem JÁ RODADA, em pixéis (x, y), mesma ordem.
# Se None, abre-se a imagem e clica-se nos pontos pela ordem de POINTS_CM.
# (O script imprime os pixéis clicados: copiar para aqui evita voltar a clicar.)
POINTS_2D = None
# POINTS_2D = np.array([[645.1, 837.1], [942.7, 840.9], [935.0, 224.6], [689.3, 228.5]])

# --- MODE = 'chessboard' ---
board_w = 6                  # cantos internos
board_h = 9
square_size = 2.15           # cm

FONT = cv2.FONT_HERSHEY_SIMPLEX

# ---------------------------------------------------------------
# Ler parâmetros da câmara e imagem
# ---------------------------------------------------------------
with np.load(PARAMS_FILE) as data:
    intrinsics = data['intrinsics'].astype(np.float64)
    distortion = data['distortion'].astype(np.float64)
    if 'image_size' in data.files:      # guardado pelo chessboard7_3.py
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
# Pontos 3D / 2D
# ---------------------------------------------------------------
def pick_points(image, n):
    """Clicar nos n pontos pela ordem de POINTS_CM (ESC cancela)."""
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


if MODE == 'chessboard':
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    found, corners = cv2.findChessboardCorners(gray, (board_w, board_h), None)
    if not found:
        raise SystemExit('Tabuleiro não encontrado na imagem')
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
    img_pts = corners.reshape(-1, 2).astype(np.float64)
    # Cantos (coluna i, linha j) -> x = i * lado (direita), y = -j * lado (cima), z = 0.
    # (a linha cresce "para baixo", por isso y = -linha mantém o sistema X direita, Y cima, Z para fora)
    obj_pts = np.zeros((board_w * board_h, 3), np.float64)
    ij = np.mgrid[0:board_w, 0:board_h].T.reshape(-1, 2)
    obj_pts[:, 0] = ij[:, 0] * square_size
    obj_pts[:, 1] = -ij[:, 1] * square_size
    print('\nTabuleiro: %d cantos detetados (lado do quadrado %.2f cm)' % (len(obj_pts), square_size))
else:
    pts_cm = np.asarray(POINTS_CM, dtype=np.float64)
    if pts_cm.shape[1] == 2:                   # só (x, y): pontos no plano do poster (z = 0)
        pts_cm = np.column_stack([pts_cm, np.zeros(len(pts_cm))])
    obj_pts = pts_cm                           # (X direita, Y cima, Z para fora), em cm
    print('\nPontos 3D (cm; X direita, Y cima, Z para fora do poster):\n', np.round(obj_pts, 1))
    img_pts = POINTS_2D if POINTS_2D is not None else pick_points(img, len(obj_pts))
    img_pts = np.asarray(img_pts, dtype=np.float64).reshape(-1, 2)
    print('Pontos 2D usados (px):\n', np.round(img_pts, 2))

n = len(obj_pts)
if n < 4 or len(img_pts) != n:
    raise SystemExit('São necessários pelo menos 4 pontos 3D e o mesmo número de pontos 2D')

# Ponto de referência da distância medida
if isinstance(MEASURED_REF, str) and MEASURED_REF == 'center':
    ref_xy = (obj_pts[:, :2].min(axis=0) + obj_pts[:, :2].max(axis=0)) / 2.0
    ref_name = 'centro'
elif isinstance(MEASURED_REF, str) and MEASURED_REF == 'origin':
    ref_xy = np.array([0.0, 0.0])
    ref_name = 'origem'
else:
    ref_xy = np.asarray(MEASURED_REF, dtype=np.float64)
    ref_name = 'ponto (%.1f, %.1f)' % tuple(ref_xy)
ref_pt = np.array([ref_xy[0], ref_xy[1], 0.0])
print('Ponto de referência da distância: %s = (%.1f, %.1f) cm' % (ref_name, ref_xy[0], ref_xy[1]))


# ---------------------------------------------------------------
# Calibração externa: pose do mundo relativamente à câmara
#   X_cam = R * X_mundo + t        e a câmara está em  C = -R^T t
# ---------------------------------------------------------------
def reproj_error(rv, tv):
    pr, _ = cv2.projectPoints(obj_pts, rv, tv, intrinsics, distortion)
    return np.linalg.norm(pr.reshape(-1, 2) - img_pts, axis=1)


def solve_pose():
    """Devolve candidatos (rvec, tvec, erro médio, posição da câmara), do melhor para o pior."""
    sv = np.linalg.svd(obj_pts - obj_pts.mean(axis=0), compute_uv=False)
    planar = sv[2] / sv[0] < 1e-4
    if planar:
        # Pontos coplanares: IPPE devolve as 2 soluções possíveis
        k, rvs, tvs, _ = cv2.solvePnPGeneric(obj_pts, img_pts, intrinsics, distortion,
                                             flags=cv2.SOLVEPNP_IPPE)
        pairs = list(zip(rvs, tvs)) if k > 0 else []
    else:
        flags = cv2.SOLVEPNP_AP3P if n == 4 else cv2.SOLVEPNP_SQPNP
        ok, rv, tv = cv2.solvePnP(obj_pts, img_pts, intrinsics, distortion, flags=flags)
        pairs = [(rv, tv)] if ok else []

    cands = []
    for rv, tv in pairs:
        rv, tv = cv2.solvePnPRefineLM(obj_pts, img_pts, intrinsics, distortion, rv, tv)
        R_ = cv2.Rodrigues(rv)[0]
        if np.any((R_ @ obj_pts.T + tv).T[:, 2] <= 0):
            continue                                  # pontos atrás da câmara -> inválida
        cam = (-R_.T @ tv).ravel()
        cands.append((rv, tv, reproj_error(rv, tv).mean(), cam))

    # Remove duplicados (o refinamento pode levar as 2 soluções ao mesmo mínimo)
    unique = []
    for c in sorted(cands, key=lambda c: c[2]):
        if all(np.linalg.norm(c[3] - u[3]) > 0.01 * np.linalg.norm(c[1]) for u in unique):
            unique.append(c)

    # A câmara tem de estar do lado de quem vê o poster (Z > 0)
    front = [c for c in unique if c[3][2] > 0]
    return front if front else unique


cands = solve_pose()
if not cands:
    raise SystemExit('solvePnP falhou (nenhuma solução válida). Verifique a ordem '
                     'e as unidades dos pontos 3D e os pontos 2D.')


def describe(rv):
    R = cv2.Rodrigues(rv)[0]
    view = R.T @ np.array([0.0, 0.0, 1.0])            # eixo ótico (para onde a câmara aponta)
    # yaw > 0: aponta para a direita da normal do poster; pitch > 0: aponta para cima
    yaw = np.degrees(np.arctan2(view[0], -view[2]))
    pitch = np.degrees(np.arctan2(view[1], np.hypot(view[0], view[2])))
    return view, yaw, pitch


def dists(cam):
    d = cam - ref_pt
    return np.linalg.norm(d), np.hypot(d[0], d[2]), cam[2]


def print_camera(cam, rv):
    view, yaw, pitch = describe(rv)
    X, Y, Z = cam
    d3, dh, dz = dists(cam)
    print('   Posição da câmara relativa à origem (cm):')
    print('     X (direita +)             = %8.1f' % X)
    print('     Y (cima +)                = %8.1f' % Y)
    print('     Z (afastamento ao poster) = %8.1f' % Z)
    print('   Distâncias ao ponto de referência (%s):' % ref_name)
    print('     3D                  : %.1f cm' % d3)
    print('     horizontal (sem Y)  : %.1f cm' % dh)
    print('     perpendicular (Z)   : %.1f cm' % dz)
    print('   A câmara aponta %.1f° %s e %.1f° %s relativamente à normal do poster'
          % (abs(yaw), 'para a direita' if yaw >= 0 else 'para a esquerda',
             abs(pitch), 'para cima' if pitch >= 0 else 'para baixo'))


if SCALE_SWEEP is not None:
    import io
    import contextlib
    base_K = intrinsics.copy()
    print('\n=== Varrimento de FOCAL_SCALE (relativo ao valor atual) ===')
    print('  escala   erro px      X        Y        Z     dist 3D à ref. (cm)')
    for sc in np.arange(SCALE_SWEEP[0], SCALE_SWEEP[1] + 1e-9, SCALE_SWEEP[2]):
        intrinsics[0, 0] = base_K[0, 0] * sc
        intrinsics[1, 1] = base_K[1, 1] * sc
        with contextlib.redirect_stdout(io.StringIO()):
            cs = solve_pose()
        if not cs:
            print('  %.3f    (sem solução válida)' % sc)
            continue
        c = cs[0]
        print('  %.3f   %6.2f  %7.1f  %7.1f  %7.1f   %7.1f'
              % (sc, c[2], c[3][0], c[3][1], c[3][2], dists(c[3])[0]))
    intrinsics[:] = base_K

rvec, tvec, best_err, cam_pos = cands[0]

print('\nRotation vector (rvec):', rvec.ravel())
print('Translation vector (tvec):', tvec.ravel())
print('\n=== POSIÇÃO DA CÂMARA (melhor solução, erro médio %.2f px) ===' % best_err)
print_camera(cam_pos, rvec)

if cam_pos[2] <= 0:
    print('ATENÇÃO: a câmara ficou atrás do plano do poster (Z <= 0). Verifique a ordem dos '
          'pontos e se x cresce para a direita e y para cima.')

if len(cands) > 1:
    rv2, tv2, err2, cam2 = cands[1]
    print('\n--- Solução alternativa (erro médio %.2f px) ---' % err2)
    print_camera(cam2, rv2)
    if err2 < 3 * best_err:
        print('ATENÇÃO: as duas soluções têm erros parecidos -> posição ambígua.')

if MEASURED_CM is not None:
    d3, dh, dz = dists(cam_pos)
    print('\n=== Comparação com a distância medida (%.1f cm, até %s) ===' % (MEASURED_CM, ref_name))
    for name, val in [('3D ao ponto de referência', d3), ('horizontal', dh),
                      ('perpendicular ao poster', dz)]:
        print('   %-26s calculada %.1f cm | diferença %+.1f cm (%+.1f %%)'
              % (name, val, val - MEASURED_CM, 100.0 * (val - MEASURED_CM) / MEASURED_CM))
    print('   Uma diferença só é sistemática se se repetir no mesmo sentido em várias fotos; '
          'a distância calculada é proporcional à focal e ao tamanho real dos pontos.')

errs = reproj_error(rvec, tvec)
print('\nErro de reprojeção por ponto (px):', np.round(errs, 2) if n <= 8 else
      'média %.2f, máximo %.2f' % (errs.mean(), errs.max()))
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
    if n <= 8:
        cv2.putText(out, str(i + 1), (p[0] + 8, p[1] - 8), FONT, 0.7, (0, 255, 0), 2)
cv2.imwrite(OUTPUT_IMAGE, out)
print('Imagem de verificação guardada em', OUTPUT_IMAGE)

scale = min(1.0, 1000.0 / w)
cv2.imshow('verde = pontos dados | vermelho = reprojecao',
           cv2.resize(out, None, fx=scale, fy=scale) if scale < 1 else out)
cv2.waitKey(-1)
cv2.destroyAllWindows()