function plot_poster_3d()
% PLOT_POSTER_3D  Resultados dos testes do poster: poster + posicao e orientacao da camara.
%
% Sistema de coordenadas (o mesmo do programa em Python), em cm:
%   origem = canto inferior esquerdo do poster
%   X = para a direita, Y = para cima, Z = para fora do poster (em direcao a quem o ve)
%
% Para cada teste indica-se:
%   pos   : posicao calculada da camara [X Y Z]
%   yaw   : graus; > 0 = a camara aponta para a direita da normal do poster
%   pitch : graus; > 0 = a camara aponta para cima
%   roll  : graus; rotacao da camara em torno do eixo otico (ver camera_axes)
%   ref   : ponto do poster ate ao qual se mediu a distancia ([0 0 0] = origem)
%
% Nota sobre o roll: nos testes 2 e 4 o roll (-90.7 e -90.2) foi calculado a partir do
% rvec do programa: a foto e guardada em 1920x1080 com o telemovel na vertical, por isso
% o poster aparece rodado 90 graus na imagem. Nos testes 1 e 3 o roll nao esta nos
% resultados e assumiu-se -90. Se tiver o rvec, substitua (roll = ver camera_axes).
%
% Uso:  plot_poster_3d

% ------------------------------------------------------------------ dados
W = 61;  H = 91;                                  % dimensoes do poster (cm)
corners = [0 0 0; W 0 0; W H 0; 0 H 0];           % pontos 1..4 (X, Y, Z)
center  = [W/2 H/2 0];
origin  = [0 0 0];

fx = 1327.7;  imgW = 1920;  imgH = 1080;          % camara do telemovel (para o campo de visao)
frustumDepth = 25;                                % profundidade do tronco desenhado (cm)
axisLen      = 15;                                % comprimento dos eixos da camara (cm)
saveFigs     = false;                             % true = guarda os graficos em PNG

mk = @(name,pos,yaw,pitch,roll,ref,meas,err) struct('name',name,'pos',pos,'yaw',yaw, ...
    'pitch',pitch,'roll',roll,'ref',ref,'measured',meas,'err',err);

tests = { ...
    mk('Teste 1: 121 cm (origem, inclinado)', [ 1.4  1.5 137.5], 10.6, 14.7, -90.0, origin, 121, 3.11), ...
    mk('Teste 2: 121 cm (centro)',            [32.5 53.2 122.7], -1.6, -1.7, -90.7, center, 121, 3.27), ...
    mk('Teste 3: 220 cm (origem, inclinado)', [ 2.4  1.6 231.2],  5.4,  3.8, -90.0, origin, 220, 1.44), ...
    mk('Teste 4: 220 cm (centro)',            [34.6 52.8 215.1], -1.5,  0.0, -90.2, center, 220, 2.30) };

colors = [0.000 0.447 0.741;  0.850 0.325 0.098;  0.929 0.694 0.125;  0.494 0.184 0.556];
nT = numel(tests);

% ------------------------------------------------- figura 1: todos os testes
f1 = figure('Name', 'Todos os testes', 'Color', 'w');
setup_scene(corners, W, H);
hLeg = zeros(1, nT);
for i = 1:nT
    t = tests{i};
    Rc = camera_axes(t.yaw, t.pitch, t.roll);
    hLeg(i) = draw_camera(t.pos, Rc, colors(i,:), fx, imgW, imgH, frustumDepth, axisLen);
    draw_aim(t.pos, Rc, colors(i,:));
end
legend(hLeg, cellfun(@(s) s.name, tests, 'UniformOutput', false), 'Location', 'northeastoutside');
title('Poster e posicao/orientacao calculada da camara (todos os testes)');
view(-60, 18);

if saveFigs
    print(f1, 'poster_todos.png', '-dpng', '-r150');
end
end

% ============================================================ funcoes locais

function R = camera_axes(yawDeg, pitchDeg, rollDeg)
% Devolve R (3x3) cujas COLUNAS sao os eixos da camara escritos no mundo:
%   coluna 1 = x da imagem (direita), coluna 2 = y da imagem (baixo), coluna 3 = eixo otico.
% yaw > 0: aponta para a direita da normal do poster; pitch > 0: aponta para cima.
% roll: rotacao em torno do eixo otico (0 = imagem "direita", -90 = imagem rodada 90 graus).
yaw = yawDeg*pi/180;  pitch = pitchDeg*pi/180;  roll = rollDeg*pi/180;
z = [cos(pitch)*sin(yaw); sin(pitch); -cos(pitch)*cos(yaw)];   % para onde a camara aponta
up0 = [0; 1; 0];
u  = up0 - (up0.'*z)*z;   u = u / norm(u);                     % "cima" do mundo, perpendicular a z
y0 = -u;                                                      % y da imagem aponta para baixo
x0 = cross(y0, z);
x  =  cos(roll)*x0 - sin(roll)*y0;
y  =  sin(roll)*x0 + cos(roll)*y0;
R  = [x, y, z];
end

function setup_scene(corners, W, H)
% Poster (plano Z = 0) com os 4 pontos numerados. Eixos do grafico: (X, Z, Y) com Z invertido,
% para o Y ficar na vertical e o sistema continuar direito.
hold on; grid on; box on;
fill3(pp(corners,1), pp(corners,2), pp(corners,3), [0.9 0.9 0.9], 'FaceAlpha', 0.5, ...
    'EdgeColor', 'k', 'LineWidth', 1.5);
plot3(pp(corners,1), pp(corners,2), pp(corners,3), 'ko', 'MarkerFaceColor', 'k', 'MarkerSize', 6);
lbl = {'1 (origem)', '2', '3', '4'};
for k = 1:4
    txt(corners(k,:), ['  ' lbl{k}], 'k');
end
seg([0 0 0], [20 0 0], 'r-', 'LineWidth', 2);  txt([20 0 0], ' X', 'r');
seg([0 0 0], [0 20 0], 'g-', 'LineWidth', 2);  txt([0 20 0], ' Y', [0 0.6 0]);
seg([0 0 0], [0 0 20], 'b-', 'LineWidth', 2);  txt([0 0 20], ' Z', 'b');
axis equal;
xlabel('X (cm, direita +)'); ylabel('Z (cm, afastamento ao poster)'); zlabel('Y (cm, cima +)');
set(gca, 'YDir', 'reverse');
xlim([-20 W+60]); zlim([-10 H+20]);
end

function h = draw_camera(C, R, col, fx, imgW, imgH, d, axisLen)
% Tronco da camara (piramide ate ao plano da imagem a distancia d), com a aresta de cima
% da imagem a cheio, e os eixos x (vermelho), y (verde) e z (azul) da camara.
xc = R(:,1).';  yc = R(:,2).';  zc = R(:,3).';
hw = (imgW/2)/fx*d;  hh = (imgH/2)/fx*d;
c0 = C + d*zc;
q = [c0 - hw*xc - hh*yc;       % canto superior esquerdo da imagem (y aponta para baixo)
     c0 + hw*xc - hh*yc;       % superior direito
     c0 + hw*xc + hh*yc;       % inferior direito
     c0 - hw*xc + hh*yc];      % inferior esquerdo
for k = 1:4
    seg(C, q(k,:), '-', 'Color', col, 'LineWidth', 1);
end
fill3(pp(q,1), pp(q,2), pp(q,3), col, 'FaceAlpha', 0.25, 'EdgeColor', col);
seg(q(1,:), q(2,:), '-', 'Color', col, 'LineWidth', 3);        % aresta de cima da imagem
h = plot3(pp(C,1), pp(C,2), pp(C,3), 's', 'MarkerSize', 9, 'MarkerFaceColor', col, 'MarkerEdgeColor', 'k');
dirs = {xc, yc, zc};  cc = {'r', [0 0.6 0], 'b'};  nm = {'x', 'y', 'z'};
for k = 1:3
    seg(C, C + axisLen*dirs{k}, '-', 'Color', cc{k}, 'LineWidth', 1.5);
    txt(C + 1.1*axisLen*dirs{k}, nm{k}, cc{k});
end
end

function draw_aim(C, R, col)
% Onde o eixo otico "bate" no plano do poster (Z = 0).
zc = R(:,3).';
if zc(3) < 0
    t = -C(3)/zc(3);
    hit = C + t*zc;
    seg(C, hit, '--', 'Color', col, 'LineWidth', 1);
    plot3(pp(hit,1), pp(hit,2), pp(hit,3), 'x', 'MarkerSize', 10, 'LineWidth', 2, 'Color', col);
end
end

% --- auxiliares: coordenadas do mundo (X,Y,Z) -> eixos do grafico (X, Z, Y)
function v = pp(M, k)
perm = [1 3 2];
v = M(:, perm(k));
end

function seg(p, q, varargin)
plot3([p(1) q(1)], [p(3) q(3)], [p(2) q(2)], varargin{:});
end

function txt(p, s, col)
text(p(1), p(3), p(2), s, 'Color', col, 'FontSize', 9);
end

function txt2(p, s, col)
text(p(1), p(2), s, 'Color', col, 'FontSize', 9);
end
