function plot_poster_3d()
% PLOT_POSTER_3D  Poster + posicao e orientacao calculada das cameras + planos de distancia.
% Compara o telemovel e a webcam Logitech nos mesmos testes.
%
% Sistema de coordenadas (o mesmo do programa em Python), em cm:
%   origem = canto inferior esquerdo do poster
%   X = para a direita, Y = para cima, Z = para fora do poster (em direcao a quem o ve)
%
% Para cada teste indica-se:
%   dev      : 'Telemovel' ou 'Logitech'
%   pos      : posicao calculada da camara [X Y Z]
%   yaw      : graus; > 0 = a camara aponta para a direita da normal do poster
%   pitch    : graus; > 0 = a camara aponta para cima
%   roll     : graus; rotacao da camara em torno do eixo otico (ver camera_axes)
%   ref      : ponto do poster ate ao qual se mediu a distancia ([0 0 0] = origem)
%   measured : distancia medida (cm) da camara a esse ponto
%
% Como ler o grafico:
%   - Cada camara e desenhada na posicao calculada, com uma piramide (campo de visao) e os
%     eixos x/y/z da camara. A aresta de cima da imagem esta a traco grosso.
%   - Os dois planos semi-transparentes sao paralelos ao poster, a 121 cm e a 220 cm
%     (as distancias medidas). Quanto mais afastada do plano esta uma camara, maior e o erro.
%     (Os planos marcam a distancia PERPENDICULAR ao poster; nos testes 1 e 3 a distancia foi
%     medida ate a origem com a camara inclinada, por isso diferem ligeiramente.)
%   - Telemovel: marcador quadrado, piramide a cheio. Logitech: triangulo, piramide tracejada.
%   - Cada teste tem uma cor; as cores do telemovel e da Logitech sao diferentes.
%   - A tabela com os numeros (medida, calculada, erro) e impressa na janela de comandos.
%
% Nota sobre o roll: o roll so afeta a ORIENTACAO desenhada da piramide (a imagem), nao a
% posicao nem a direcao do eixo otico.
%  - Telemovel, testes 2 e 4: -90.7 e -90.2, calculados a partir do rvec do programa
%    (a foto e guardada em 1920x1080 com o telemovel na vertical, por isso o poster
%    aparece rodado 90 graus na imagem). Testes 1 e 3: nao esta nos resultados; assumiu-se -90.
%  - Logitech: o roll nao esta nos resultados; assumiu-se -90. Se a rotacao for ao contrario, use +90.
%
% Uso:  plot_poster_3d

% ------------------------------------------------------------------ dados
W = 61;  H = 91;                                  % dimensoes do poster (cm)
corners = [0 0 0; W 0 0; W H 0; 0 H 0];           % pontos 1..4 (X, Y, Z)
center  = [W/2 H/2 0];
origin  = [0 0 0];

fxPhone = 1327.7;                                 % focal (px) do telemovel (para o campo de visao)
fxLog   = 1419.0;                                 % focal (px) da Logitech
imgW = 1920;  imgH = 1080;
rollLog = -90;                                    % roll assumido da Logitech (ver nota acima)

showPhone    = true;                              % mostrar os resultados do telemovel
showLogitech = true;                              % mostrar os resultados da Logitech
planeDist    = [121 220];                         % distancias (cm) dos planos paralelos ao poster
planeColors  = [0.45 0.70 1.00;  1.00 0.65 0.25]; % cor de cada plano
planeAlpha   = 0.18;                              % transparencia dos planos
frustumDepth = 25;                                % profundidade da piramide desenhada (cm)
axisLen      = 15;                                % comprimento dos eixos da camara (cm)
saveFigs     = false;                             % true = guarda o grafico em PNG

% estilo por dispositivo: marcador, tracejado da piramide, transparencia e 4 cores (testes 1..4)
style.Telemovel = struct('marker', 's', 'ls', '-',  'fa', 0.25, 'colors', ...
    [0.000 0.447 0.741;  0.850 0.325 0.098;  0.929 0.694 0.125;  0.494 0.184 0.556]);
style.Logitech  = struct('marker', '^', 'ls', '--', 'fa', 0.12, 'colors', ...
    [0.200 0.650 0.200;  0.000 0.600 0.600;  0.850 0.200 0.650;  0.300 0.300 0.300]);

mk = @(dev,name,pos,yaw,pitch,roll,ref,meas,err,fx) struct('dev',dev,'name',name,'pos',pos, ...
    'yaw',yaw,'pitch',pitch,'roll',roll,'ref',ref,'measured',meas,'err',err,'fx',fx);

tests = { ...
    mk('Telemovel','Teste 1: 121 cm (origem, inclinado)', [ 1.4  1.5 137.5], 10.6, 14.7, -90.0, origin, 121, 3.11, fxPhone), ...
    mk('Telemovel','Teste 2: 121 cm (centro)',            [32.5 53.2 122.7], -1.6, -1.7, -90.7, center, 121, 3.27, fxPhone), ...
    mk('Telemovel','Teste 3: 220 cm (origem, inclinado)', [ 2.4  1.6 231.2],  5.4,  3.8, -90.0, origin, 220, 1.44, fxPhone), ...
    mk('Telemovel','Teste 4: 220 cm (centro)',            [34.6 52.8 215.1], -1.5,  0.0, -90.2, center, 220, 2.30, fxPhone), ...
    mk('Logitech', 'Teste 1: 121 cm (origem, inclinado)', [ 2.1  2.9 120.2],  9.2, 16.7, rollLog, origin, 121, 1.12, fxLog), ...
    mk('Logitech', 'Teste 2: 121 cm (centro)',            [24.2 40.5 135.4], -0.4, -1.6, rollLog, center, 121, 3.23, fxLog), ...
    mk('Logitech', 'Teste 3: 220 cm (origem, inclinado)', [-0.1  5.2 192.4],  9.0, 10.0, rollLog, origin, 220, 1.64, fxLog), ...
    mk('Logitech', 'Teste 4: 220 cm (centro)',            [19.4 36.9 185.2], -2.6, -0.5, rollLog, center, 220, 2.92, fxLog) };

% remove os dispositivos desligados
keep = true(1, numel(tests));
for i = 1:numel(tests)
    if (strcmp(tests{i}.dev, 'Telemovel') && ~showPhone) || (strcmp(tests{i}.dev, 'Logitech') && ~showLogitech)
        keep(i) = false;
    end
end
tests = tests(keep);
nT = numel(tests);

% ------------------------------------------------- tabela no ecra de comandos
fprintf('\n%-10s %-38s %8s %9s %9s %8s %9s\n', 'Camara', 'Teste', 'Medida', 'Calculada', 'Erro', 'Erro', 'Z');
fprintf('%-10s %-38s %8s %9s %9s %8s %9s\n', '', '', '(cm)', '(cm)', '(cm)', '(%)', '(cm)');
for i = 1:nT
    t = tests{i};
    dCalc = norm(t.pos - t.ref);
    fprintf('%-10s %-38s %8.1f %9.1f %+9.1f %+8.1f %9.1f\n', t.dev, t.name, t.measured, dCalc, ...
        dCalc - t.measured, 100*(dCalc - t.measured)/t.measured, t.pos(3));
end
fprintf('\n');

% ------------------------------------------------- figura: todos os testes
f1 = figure('Name', 'Todos os testes', 'Color', 'w', 'Units', 'normalized', ...
    'OuterPosition', [0.02 0.04 0.96 0.92]);
[hPoster, hOrigin] = setup_scene(corners, W, H);

% planos paralelos ao poster, a distancia fixa (mesmos limites X/Y dos eixos)
nP = numel(planeDist);
hPlane = zeros(1, nP);
planeNames = cell(1, nP);
for k = 1:nP
    hPlane(k) = draw_plane(planeDist(k), [-20 W+60], [-10 H+20], planeColors(k,:), planeAlpha);
    planeNames{k} = sprintf('plano a %g cm do poster', planeDist(k));
end

% cameras
hCam = zeros(1, nT);
camNames = cell(1, nT);
for i = 1:nT
    t = tests{i};
    st  = style.(t.dev);
    col = st.colors(condIndex(t.name), :);
    Rc = camera_axes(t.yaw, t.pitch, t.roll);
    hCam(i) = draw_camera(t.pos, Rc, col, t.fx, imgW, imgH, frustumDepth, axisLen, st);
    draw_aim(t.pos, Rc, col);
    camNames{i} = sprintf('%s | %s', t.dev, t.name);
end

legend([hPoster hOrigin hPlane hCam], ...
    [{sprintf('poster (%g x %g cm)', W, H), 'origem (ponto 1)'}, planeNames, camNames], ...
    'Location', 'eastoutside', 'FontSize', 10);
title('Poster, planos de distancia e posicao/orientacao calculada das cameras', 'FontSize', 12);
set(gca, 'FontSize', 11);
view(-60, 20);

if saveFigs
    print(f1, 'poster_todos.png', '-dpng', '-r200');
end
end

% ============================================================ funcoes locais

function k = condIndex(name)
% numero da condicao (1..4) a partir do nome "Teste N: ..."
k = sscanf(name, 'Teste %d');
end

function h = draw_plane(zPlane, xl, yl, col, alpha)
% Plano Z = zPlane (paralelo ao poster), semi-transparente, com os limites xl e yl.
P = [xl(1) yl(1) zPlane;  xl(2) yl(1) zPlane;  xl(2) yl(2) zPlane;  xl(1) yl(2) zPlane];
h = fill3(pp(P,1), pp(P,2), pp(P,3), col, 'FaceAlpha', alpha, 'EdgeColor', col, 'LineWidth', 1);
end

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

function [hPoster, hOrigin] = setup_scene(corners, W, H)
% Poster (plano Z = 0) e os 4 pontos. Eixos do grafico: (X, Z, Y) com Z invertido,
% para o Y ficar na vertical e o sistema continuar direito.
hold on; grid on; box on;
hPoster = fill3(pp(corners,1), pp(corners,2), pp(corners,3), [0.85 0.85 0.85], 'FaceAlpha', 0.6, ...
    'EdgeColor', 'k', 'LineWidth', 2);
plot3(pp(corners(2:4,:),1), pp(corners(2:4,:),2), pp(corners(2:4,:),3), 'ko', ...
    'MarkerFaceColor', 'k', 'MarkerSize', 6);
hOrigin = plot3(pp(corners(1,:),1), pp(corners(1,:),2), pp(corners(1,:),3), 'ko', ...
    'MarkerFaceColor', 'w', 'MarkerSize', 10, 'LineWidth', 2);
axis equal;
xlabel('X (cm, direita +)'); ylabel('Z (cm, afastamento ao poster)'); zlabel('Y (cm, cima +)');
set(gca, 'YDir', 'reverse');
xlim([-20 W+60]); zlim([-10 H+20]);
end

function h = draw_camera(C, R, col, fx, imgW, imgH, d, axisLen, st)
% Piramide da camara (ate ao plano da imagem a distancia d), com a aresta de cima da
% imagem a cheio, e os eixos x (vermelho), y (verde) e z (azul) da camara.
xc = R(:,1).';  yc = R(:,2).';  zc = R(:,3).';
hw = (imgW/2)/fx*d;  hh = (imgH/2)/fx*d;
c0 = C + d*zc;
q = [c0 - hw*xc - hh*yc;       % canto superior esquerdo da imagem (y aponta para baixo)
     c0 + hw*xc - hh*yc;       % superior direito
     c0 + hw*xc + hh*yc;       % inferior direito
     c0 - hw*xc + hh*yc];      % inferior esquerdo
for k = 1:4
    seg(C, q(k,:), st.ls, 'Color', col, 'LineWidth', 1.5);
end
fill3(pp(q,1), pp(q,2), pp(q,3), col, 'FaceAlpha', st.fa, 'EdgeColor', col);
seg(q(1,:), q(2,:), '-', 'Color', col, 'LineWidth', 3.5);      % aresta de cima da imagem
h = plot3(pp(C,1), pp(C,2), pp(C,3), st.marker, 'MarkerSize', 11, 'MarkerFaceColor', col, 'MarkerEdgeColor', 'k');
dirs = {xc, yc, zc};  cc = {'r', [0 0.6 0], 'b'};
for k = 1:3
    seg(C, C + axisLen*dirs{k}, '-', 'Color', cc{k}, 'LineWidth', 1.5);
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