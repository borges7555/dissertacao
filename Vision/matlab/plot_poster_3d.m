function plot_poster_3d()
% PLOT_POSTER_3D  Poster + calculated camera position and orientation + distance planes.
% Compares the phone and Logitech webcam in the same tests.
%
% Coordinate system (the same as in the Python program), in cm:
%   origin = bottom-left corner of the poster
%   X = to the right, Y = upwards, Z = out of the poster (towards the viewer)
%
% For each test:
%   dev      : 'Phone' or 'Logitech'
%   pos      : calculated camera position [X Y Z]
%   yaw      : degrees; > 0 = camera points to the right of the poster normal
%   pitch    : degrees; > 0 = camera points upwards
%   roll     : degrees; camera rotation around the optical axis (see camera_axes)
%   ref      : poster point to which the distance was measured ([0 0 0] = origin)
%   measured : measured distance (cm) from the camera to that point
%
% How to read the plot:
%   - Each camera is drawn at the calculated position, with a pyramid (field of view) and the
%     camera x/y/z axes. The top edge of the image is drawn with a thick line.
%   - The two semi-transparent planes are parallel to the poster, at 121 cm and 220 cm
%     (the measured distances). The farther a camera is from the plane, the greater the error.
%     (The planes mark the PERPENDICULAR distance to the poster.)
%   - Phone: square marker, filled pyramid. Logitech: triangle, dashed pyramid.
%   - Each test has a color; the phone and Logitech colors are different.
%   - The table with the values (measured, calculated, error) is printed in the command window..
%
% Usage:  plot_poster_3d

% ------------------------------------------------------------------ data
W = 61;  H = 91;                                  % poster dimensions (cm)
corners = [0 0 0; W 0 0; W H 0; 0 H 0];           % points 1..4 (X, Y, Z)
center  = [W/2 H/2 0];
origin  = [0 0 0];

fxPhone = 1327.7;                                 % phone focal length (px) (for the field of view)
fxLog   = 1419.0;                                 % Logitech focal length (px)
imgW = 1920;  imgH = 1080;
rollLog = -90;                                    % assumed Logitech roll (see note above)

showPhone    = true;                              % show phone results
showLogitech = true;                              % show Logitech results
planeDist    = [121 220];                         % distances (cm) of the planes parallel to the poster
planeColors  = [0.45 0.70 1.00;  1.00 0.65 0.25]; % color of each plane
planeAlpha   = 0.18;                              % plane transparency
frustumDepth = 25;                                % depth of the drawn pyramid (cm)
axisLen      = 15;                                % camera axis length (cm)
saveFigs     = false;                             % true = save the plot as PNG

% style per device: marker, pyramid line style, transparency, and 4 colors (tests 1..4)
style.Phone = struct('marker', 's', 'ls', '-',  'fa', 0.25, 'colors', ...
    [0.000 0.447 0.741;  0.850 0.325 0.098;  0.929 0.694 0.125;  0.494 0.184 0.556]);
style.Logitech  = struct('marker', '^', 'ls', '--', 'fa', 0.12, 'colors', ...
    [0.200 0.650 0.200;  0.000 0.600 0.600;  0.850 0.200 0.650;  0.300 0.300 0.300]);

mk = @(dev,name,pos,yaw,pitch,roll,ref,meas,err,fx) struct('dev',dev,'name',name,'pos',pos, ...
    'yaw',yaw,'pitch',pitch,'roll',roll,'ref',ref,'measured',meas,'err',err,'fx',fx);

tests = { ...
    mk('Phone','Test 1: 121 cm (origin, tilted)', [ 1.4  1.5 137.5], 10.6, 14.7, -90.0, origin, 121, 3.11, fxPhone), ...
    mk('Phone','Test 2: 121 cm (center)',          [32.5 53.2 122.7], -1.6, -1.7, -90.7, center, 121, 3.27, fxPhone), ...
    mk('Phone','Test 3: 220 cm (origin, tilted)', [ 2.4  1.6 231.2],  5.4,  3.8, -90.0, origin, 220, 1.44, fxPhone), ...
    mk('Phone','Test 4: 220 cm (center)',          [34.6 52.8 215.1], -1.5,  0.0, -90.2, center, 220, 2.30, fxPhone), ...
    mk('Logitech', 'Test 1: 121 cm (origin, tilted)', [ 2.1  2.9 120.2],  9.2, 16.7, rollLog, origin, 121, 1.12, fxLog), ...
    mk('Logitech', 'Test 2: 121 cm (center)',          [24.2 40.5 135.4], -0.4, -1.6, rollLog, center, 121, 3.23, fxLog), ...
    mk('Logitech', 'Test 3: 220 cm (origin, tilted)', [-0.1  5.2 192.4],  9.0, 10.0, rollLog, origin, 220, 1.64, fxLog), ...
    mk('Logitech', 'Test 4: 220 cm (center)',          [19.4 36.9 185.2], -2.6, -0.5, rollLog, center, 220, 2.92, fxLog) };

% remove disabled devices
keep = true(1, numel(tests));
for i = 1:numel(tests)
    if (strcmp(tests{i}.dev, 'Phone') && ~showPhone) || (strcmp(tests{i}.dev, 'Logitech') && ~showLogitech)
        keep(i) = false;
    end
end
tests = tests(keep);
nT = numel(tests);

% ------------------------------------------------- command-window table
fprintf('\n%-10s %-38s %8s %9s %9s %8s %9s\n', 'Camera', 'Test', 'Measured', 'Calculated', 'Error', 'Error', 'Z');
fprintf('%-10s %-38s %8s %9s %9s %8s %9s\n', '', '', '(cm)', '(cm)', '(cm)', '(%)', '(cm)');
for i = 1:nT
    t = tests{i};
    dCalc = norm(t.pos - t.ref);
    fprintf('%-10s %-38s %8.1f %9.1f %+9.1f %+8.1f %9.1f\n', t.dev, t.name, t.measured, dCalc, ...
        dCalc - t.measured, 100*(dCalc - t.measured)/t.measured, t.pos(3));
end
fprintf('\n');

% ------------------------------------------------- figure: all tests
f1 = figure('Name', 'All tests', 'Color', 'w', 'Units', 'normalized', ...
    'OuterPosition', [0.02 0.04 0.96 0.92]);
[hPoster, hOrigin] = setup_scene(corners, W, H);

% parallel planes at a fixed distance from the poster (same X/Y axis limits)
nP = numel(planeDist);
hPlane = zeros(1, nP);
planeNames = cell(1, nP);
for k = 1:nP
    hPlane(k) = draw_plane(planeDist(k), [-20 W+60], [-10 H+20], planeColors(k,:), planeAlpha);
    planeNames{k} = sprintf('plane at %g cm from poster', planeDist(k));
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
    [{sprintf('poster (%g x %g cm)', W, H), 'origin (point 1)'}, planeNames, camNames], ...
    'Location', 'eastoutside', 'FontSize', 10);
title('Poster, distance planes, and calculated camera position/orientation', 'FontSize', 12);
set(gca, 'FontSize', 11);
view(-60, 20);

if saveFigs
    print(f1, 'poster_todos.png', '-dpng', '-r200');
end
end

% ============================================================ local functions

function k = condIndex(name)
% condition number (1..4) from the name "Test N: ..."
k = sscanf(name, 'Test %d');
end

function h = draw_plane(zPlane, xl, yl, col, alpha)
% Plane Z = zPlane (parallel to the poster), semi-transparent, with xl and yl limits.
P = [xl(1) yl(1) zPlane;  xl(2) yl(1) zPlane;  xl(2) yl(2) zPlane;  xl(1) yl(2) zPlane];
h = fill3(pp(P,1), pp(P,2), pp(P,3), col, 'FaceAlpha', alpha, 'EdgeColor', col, 'LineWidth', 1);
end

function R = camera_axes(yawDeg, pitchDeg, rollDeg)
% Returns R (3x3), whose COLUMNS are the camera axes expressed in world coordinates:
%   column 1 = image x (right), column 2 = image y (down), column 3 = optical axis.
% yaw > 0: points to the right of the poster normal; pitch > 0: points upwards.
% roll: rotation around the optical axis (0 = "upright" image, -90 = image rotated 90 degrees).
yaw = yawDeg*pi/180;  pitch = pitchDeg*pi/180;  roll = rollDeg*pi/180;
z = [cos(pitch)*sin(yaw); sin(pitch); -cos(pitch)*cos(yaw)];   % direction the camera points
up0 = [0; 1; 0];
u  = up0 - (up0.'*z)*z;   u = u / norm(u);                     % world "up", perpendicular to z
y0 = -u;                                                      % image y points downwards
x0 = cross(y0, z);
x  =  cos(roll)*x0 - sin(roll)*y0;
y  =  sin(roll)*x0 + cos(roll)*y0;
R  = [x, y, z];
end

function [hPoster, hOrigin] = setup_scene(corners, W, H)
% Poster (Z = 0 plane) and the 4 points. Plot axes: (X, Z, Y) with Z inverted,
% so Y is vertical and the system remains right-handed.
hold on; grid on; box on;
hPoster = fill3(pp(corners,1), pp(corners,2), pp(corners,3), [0.85 0.85 0.85], 'FaceAlpha', 0.6, ...
    'EdgeColor', 'k', 'LineWidth', 2);
plot3(pp(corners(2:4,:),1), pp(corners(2:4,:),2), pp(corners(2:4,:),3), 'ko', ...
    'MarkerFaceColor', 'k', 'MarkerSize', 6);
hOrigin = plot3(pp(corners(1,:),1), pp(corners(1,:),2), pp(corners(1,:),3), 'ko', ...
    'MarkerFaceColor', 'w', 'MarkerSize', 10, 'LineWidth', 2);
axis equal;
xlabel('X (cm, right +)'); ylabel('Z (cm, distance from poster)'); zlabel('Y (cm, up +)');
set(gca, 'YDir', 'reverse');
xlim([-20 W+60]); zlim([-10 H+20]);
end

function h = draw_camera(C, R, col, fx, imgW, imgH, d, axisLen, st)
% Camera pyramid (up to the image plane at distance d), with the top image edge
% solid, and the camera x (red), y (green), and z (blue) axes.
xc = R(:,1).';  yc = R(:,2).';  zc = R(:,3).';
hw = (imgW/2)/fx*d;  hh = (imgH/2)/fx*d;
c0 = C + d*zc;
q = [c0 - hw*xc - hh*yc;       % top-left image corner (y points down)
     c0 + hw*xc - hh*yc;       % top-right
     c0 + hw*xc + hh*yc;       % bottom-right
     c0 - hw*xc + hh*yc];      % bottom-left
for k = 1:4
    seg(C, q(k,:), st.ls, 'Color', col, 'LineWidth', 1.5);
end
fill3(pp(q,1), pp(q,2), pp(q,3), col, 'FaceAlpha', st.fa, 'EdgeColor', col);
seg(q(1,:), q(2,:), '-', 'Color', col, 'LineWidth', 3.5);      % top image edge
h = plot3(pp(C,1), pp(C,2), pp(C,3), st.marker, 'MarkerSize', 11, 'MarkerFaceColor', col, 'MarkerEdgeColor', 'k');
dirs = {xc, yc, zc};  cc = {'r', [0 0.6 0], 'b'};
for k = 1:3
    seg(C, C + axisLen*dirs{k}, '-', 'Color', cc{k}, 'LineWidth', 1.5);
end
end

function draw_aim(C, R, col)
% Where the optical axis "hits" the poster plane (Z = 0).
zc = R(:,3).';
if zc(3) < 0
    t = -C(3)/zc(3);
    hit = C + t*zc;
    seg(C, hit, '--', 'Color', col, 'LineWidth', 1);
    plot3(pp(hit,1), pp(hit,2), pp(hit,3), 'x', 'MarkerSize', 10, 'LineWidth', 2, 'Color', col);
end
end

% --- helpers: world coordinates (X,Y,Z) -> plot axes (X, Z, Y)
function v = pp(M, k)
perm = [1 3 2];
v = M(:, perm(k));
end

function seg(p, q, varargin)
plot3([p(1) q(1)], [p(3) q(3)], [p(2) q(2)], varargin{:});
end