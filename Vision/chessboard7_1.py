# Lab 7 - Ex. 7.1 - Chessboard Calibration
# Baseado no código fornecido (Paulo Dias)

import numpy as np
import cv2
import glob

# Board Size (cantos internos)
board_h = 9
board_w = 6

# Critério usado apenas no cornerSubPix (opcional)
subpix_criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

# Arrays to store object points and image points from all the images.
objpoints = []  # 3d point in real world space
imgpoints = []  # 2d points in image plane.


def FindAndDisplayChessboard(img):
    # Find the chess board corners
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    ret, corners = cv2.findChessboardCorners(gray, (board_w, board_h), None)

    # If found, display image with corners
    if ret == True:
        # Opcional: refinar a posição dos cantos (precisão sub-pixel)
        corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), subpix_criteria)
        img = cv2.drawChessboardCorners(img, (board_w, board_h), corners, ret)
        cv2.imshow('img', img)
        cv2.waitKey(500)

    return ret, corners


# prepare object points, like (0,0,0), (1,0,0), (2,0,0) ....,(5,8,0)
# Unidade = 1 quadrado. Para distâncias reais (ex. mm), multiplicar por
# square_size (lado real de um quadrado), ver nota abaixo.
square_size = 1.0
objp = np.zeros((board_w * board_h, 3), np.float32)
objp[:, :2] = np.mgrid[0:board_w, 0:board_h].T.reshape(-1, 2)
objp = objp * square_size

# Read images
images = sorted(glob.glob('./left*.jpg'))
img_size = None

for fname in images:
    img = cv2.imread(fname)
    if img_size is None:
        img_size = (img.shape[1], img.shape[0])  # (largura, altura)
    ret, corners = FindAndDisplayChessboard(img)
    if ret == True:
        objpoints.append(objp)
        imgpoints.append(corners)

cv2.waitKey(-1)
cv2.destroyAllWindows()

# ---------------------------------------------------------------
# Calibração (sem informação prévia e sem critério de paragem)
# ---------------------------------------------------------------
ret, intrinsics, distortion, rvecs, tvecs = cv2.calibrateCamera(
    objpoints, imgpoints, img_size, None, None)

print("Intrinsics: ")
print(intrinsics)
print("Distortion : ")
print(distortion)
for i in range(len(tvecs)):
    print("Translations(%d) : " % i)
    print(tvecs[i])
    print("Rotation(%d) : " % i)
    print(rvecs[i])

# Guardar matriz intrínseca e distorção
np.savez('camera.npz', intrinsics=intrinsics, distortion=distortion)