// Event dots drawn with WebGL: one point sprite per dot, shaped in the fragment shader. The GPU redraws
// all of them every frame in well under a millisecond, so dots stay crisp while panning and zooming.

const VERTEX = `
attribute vec2 a_pos;      // projected position at zoom 1, in CSS pixels
attribute float a_r;       // radius in CSS pixels
attribute vec3 a_color;
attribute float a_precise; // 1 = exact location, 0 = approximate (region/country)
attribute vec2 a_years;    // start and end year
uniform vec2 u_range;      // visible years: events overlapping this range are drawn
uniform vec3 u_t;          // zoom k, translate x, translate y
uniform vec2 u_size;       // viewport in CSS pixels
uniform float u_dpr;
uniform float u_spread;    // 1 for dots, larger for the glow pass
uniform float u_zoomSize;  // dots are smaller when zoomed out (see sizeAtZoom)
varying vec3 v_color;
varying float v_precise;
varying float v_r;         // radius in device pixels
void main() {
  if (a_years.y < u_range.x || a_years.x > u_range.y) { gl_Position = vec4(2.0, 2.0, 0.0, 1.0); gl_PointSize = 0.0; return; }
  vec2 p = a_pos * u_t.x + u_t.yz;
  vec2 clip = p / u_size * 2.0 - 1.0;
  gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
  float r = a_r * (a_precise > 0.5 ? 1.0 : 1.5) * u_spread * u_zoomSize * u_dpr;
  gl_PointSize = 2.0 * r + 2.0;
  v_color = a_color;
  v_precise = a_precise;
  v_r = r;
}`;

const FRAGMENT = `
precision mediump float;
uniform float u_alpha;
uniform float u_glow;      // 1 in the glow pass
uniform vec4 u_outline;    // outline colour (premultiplied by its alpha below)
varying vec3 v_color;
varying float v_precise;
varying float v_r;
void main() {
  float d = length(gl_PointCoord * 2.0 - 1.0) * (v_r + 1.0); // distance from centre in device pixels
  if (u_glow > 0.5) {
    float a = exp(-3.0 * (d / v_r) * (d / v_r)) * (v_precise > 0.5 ? 0.045 : 0.015);
    gl_FragColor = vec4(v_color * a, a);
    return;
  }
  float disc = 1.0 - smoothstep(v_r - 0.8, v_r + 0.4, d);          // anti-aliased edge
  if (disc <= 0.0) discard;
  if (v_precise < 0.5) {                                             // approximate: soft translucent disc
    float a = disc * u_alpha * 0.35;
    gl_FragColor = vec4(v_color * a, a);
    return;
  }
  float rim = smoothstep(v_r - 1.6, v_r - 0.6, d) * u_outline.a     // thin outline just inside the edge,
            * smoothstep(2.5, 4.5, v_r);                           // only once dots are big enough to have one
  vec3 c = mix(v_color, u_outline.rgb, rim);
  float a = disc * u_alpha;
  gl_FragColor = vec4(c * a, a);
}`;

const FIELDS = 9; // x, y, r, red, green, blue, precise, start year, end year

/** Dot size multiplier: 0.6x at world view, growing to 1.2x by about 30x zoom. */
function sizeAtZoom(k) {
  return Math.min(1.2, 0.6 + 0.12 * Math.log2(k));
}

function compile(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader));
  return shader;
}

function rgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16 & 255) / 255, (n >> 8 & 255) / 255, (n & 255) / 255];
}

export function createDots(canvas) {
  const gl = canvas.getContext('webgl', { premultipliedAlpha: true, antialias: false });
  if (!gl) throw new Error('WebGL is not available');
  const program = gl.createProgram();
  gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, VERTEX));
  gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, FRAGMENT));
  gl.linkProgram(program);
  gl.useProgram(program);
  const buffer = gl.createBuffer();
  const u = Object.fromEntries(['u_t', 'u_size', 'u_dpr', 'u_spread', 'u_zoomSize', 'u_alpha', 'u_glow', 'u_outline', 'u_range']
    .map((n) => [n, gl.getUniformLocation(program, n)]));
  let count = 0;

  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  [['a_pos', 2, 0], ['a_r', 1, 2], ['a_color', 3, 3], ['a_precise', 1, 6], ['a_years', 2, 7]].forEach(([name, size, offset]) => {
    const loc = gl.getAttribLocation(program, name);
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, size, gl.FLOAT, false, FIELDS * 4, offset * 4);
  });

  return {
    /** dots: [{x, y, r, color: '#rrggbb', precise, y0, y1}] in projected zoom-1 CSS pixels; drawn in this order. */
    setDots(dots) {
      const data = new Float32Array(dots.length * FIELDS);
      dots.forEach((d, i) => data.set([d.x, d.y, d.r, ...rgb(d.color), d.precise ? 1 : 0, d.y0, d.y1], i * FIELDS));
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
      count = dots.length;
    },

    draw(transform, style, years = [-1e9, 1e9]) {
      const dpr = window.devicePixelRatio || 1;
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      if (!count) return;
      gl.enable(gl.BLEND);
      gl.uniform3f(u.u_t, transform.k, transform.x, transform.y);
      gl.uniform2f(u.u_size, canvas.width / dpr, canvas.height / dpr);
      gl.uniform1f(u.u_dpr, dpr);
      gl.uniform1f(u.u_zoomSize, sizeAtZoom(transform.k));
      gl.uniform1f(u.u_alpha, style.alpha);
      gl.uniform4f(u.u_outline, ...style.outline);
      gl.uniform2f(u.u_range, years[0], years[1]);
      if (style.glow) {
        gl.blendFunc(gl.ONE, gl.ONE); // additive: dense areas light up
        gl.uniform1f(u.u_glow, 1);
        gl.uniform1f(u.u_spread, 3);
        gl.drawArrays(gl.POINTS, 0, count);
      }
      gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      gl.uniform1f(u.u_glow, 0);
      gl.uniform1f(u.u_spread, 1);
      gl.drawArrays(gl.POINTS, 0, count);
    },
  };
}
