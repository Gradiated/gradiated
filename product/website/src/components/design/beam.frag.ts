/**
 * The beam's fragment shader.
 *
 * Kept as its own file because it is a language of its own — mixing GLSL into
 * a template literal inside the component hides it from every tool that could
 * help read it.
 *
 * WHAT IT DRAWS. A cone whose point is at the right and whose mouth is off the
 * left edge. Every pixel is described by two numbers relative to that point:
 * how far away it is, and how far off-axis. The first fades the field in from
 * the point and out at the far end; the second is a gaussian that makes the
 * edges soft without a blur. Everything else — the flow, the wobble — is a
 * modulation of those two, which is why it stays smooth at any size.
 */
export const BEAM_FRAGMENT = /* glsl */ `
precision highp float;

uniform vec2  uRes;
uniform float uTime;
uniform vec3  uHot;    /* ember red */
uniform vec3  uWarm;   /* the shared amber */
uniform vec3  uOlive;  /* grove */
uniform vec3  uCool;   /* shallows teal */
uniform vec3  uPlum;   /* plum */
uniform float uAlpha;  /* how far the field is allowed to come up */
uniform float uApexY;  /* the point's height, as a fraction of the canvas —
                          a uniform because the canvas now runs PAST the fold
                          so the colour can bleed into the next section, and
                          the point must stay centred on the fold rather than
                          on the taller buffer. */

/* THE COLOUR TRAVELS. The first version held the ramp stationary and moved
   only brightness bands through it, which read as a shimmer on a still
   object. The design's intent is the opposite: the gradients themselves are
   the energy, streaming down the cone in continuous succession — ember, then
   shallows, then ember again. The two share the same amber endpoint, so the
   cycle red -> amber -> teal -> amber closes seamlessly and the flow never
   shows a seam. */

/* Value noise. Cheap, and the field is so soft that nothing better would
   survive being smoothed by the falloffs anyway. */
float hash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(
    mix(hash(i + vec2(0.0, 0.0)), hash(i + vec2(1.0, 0.0)), u.x),
    mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x),
    u.y
  );
}

/* Three octaves is enough: the falloffs erase anything finer. */
float fbm(vec2 p) {
  float total = 0.0;
  float amp = 0.5;
  for (int i = 0; i < 3; i += 1) {
    total += noise(p) * amp;
    p *= 2.02;
    amp *= 0.5;
  }
  return total;
}

void main() {
  vec2 p = gl_FragCoord.xy / uRes;
  p.y = 1.0 - p.y;

  float aspect = uRes.x / uRes.y;

  /* The point sits ON the right edge, vertically centred on the FOLD; the
     mouth owns the whole left edge. Fractionally past 1.0 so the very tip —
     where the cone is a pixel wide — closes just off screen rather than
     dying visibly on the edge. */
  vec2 apex = vec2(1.01, uApexY);
  vec2 d = p - apex;
  d.x *= aspect;

  float r = length(d);
  /* Angle off the axis, which runs from the point back toward the left. */
  float a = atan(d.y, -d.x);

  /* DISTANCE IS NORMALISED TO THE SCREEN'S OWN SPAN. Raw r is aspect-scaled,
     so on a portrait phone the entire viewport sits within half a unit of
     the point — inside the zone where the envelope below is at full strength
     and before the colour cycle has run even once. That is the solar flare:
     a screen of undimmed, uncycled colour. rr makes "the left edge" the same
     distance on every screen; the 1.716 keeps a 16:9 desktop numerically
     identical to how it was tuned. The ANGLE stays physical, so the cone's
     shape is not distorted — only the measuring tape along it changes. */
  float rr = r * (1.716 / max(1.01 * aspect, 0.25));

  /* Off-axis falloff. A gaussian rather than a hard edge, so the cone has no
     boundary to see — this is what a blur would otherwise be doing. */
  float spread = 0.42;
  float cone = exp(-(a * a) / (2.0 * spread * spread));

  /* Behind the apex there is no cone at all, only its reflection — kill it. */
  cone *= smoothstep(0.0, 0.06, -d.x);

  /* Along the axis: in from the point, and holding almost to the left edge —
     the mouth is meant to be ON the edge, not fading politely before it. */
  float along = smoothstep(0.0, 0.22, rr) * (1.0 - smoothstep(1.45, 2.3, rr));

  /* THE FLOW: the gradient cycle streaming toward the point. sqrt(r) bends
     the spacing so the colours crowd and accelerate as the channel narrows —
     from a lot to streamlined. Subtracting time moves the whole succession
     tipward. The small angular noise term shears the fronts so they arrive
     as energy, not as printed stripes. */
  /* PLUS time, not minus. A colour front sits at constant phase, so with
     -time the fronts drift outward from the point — right to left. The flow
     is meant to run WITH the taper, left to right into the point, which is
     +time. The shear is heavier than before and the frequency lower: fewer,
     wavier fronts read as a wash of energy where many straight ones read as
     a stripe pattern. */
  /* ANISOTROPIC, and that is the aerodynamics. High frequency ACROSS the
     flow, low frequency ALONG it: each angular filament keeps its offset for
     most of the cone's length, so the texture is long streaks combed toward
     the point — streamlines — where equal frequencies gave round cells that
     read as weather. */
  /* THE TEMPO, and its companions. 0.35 is the settled middle ground — at
     0.55 the flow read as frantic to some of the room. The shear and cloud
     drifts below scale WITH it (they sat at 0.55/0.30/0.25; the ratios are
     kept), because slowing only the colour leaves the grain visibly sliding
     at a different speed and the beam stops reading as one moving thing. */
  float shear = fbm(vec2(a * 4.5, rr * 0.6 + uTime * 0.19)) * 0.65;
  float phase = fract(sqrt(max(rr, 0.0001)) * 1.05 + uTime * 0.35 + shear);

  /* One closed cycle around the palette's own wheel, so no leg is a jump:
     red -> amber -> olive -> teal -> plum -> red. Olive sits between amber
     and teal on the wheel and plum between teal and red, which is exactly
     the two bridges the three-colour cycle lacked — without them it cycled
     through primaries and read like a test card. */
  vec3 col;
  float seg = phase * 5.0;
  if (seg < 1.0)      col = mix(uHot,   uWarm,  smoothstep(0.0, 1.0, seg));
  else if (seg < 2.0) col = mix(uWarm,  uOlive, smoothstep(0.0, 1.0, seg - 1.0));
  else if (seg < 3.0) col = mix(uOlive, uCool,  smoothstep(0.0, 1.0, seg - 2.0));
  else if (seg < 4.0) col = mix(uCool,  uPlum,  smoothstep(0.0, 1.0, seg - 3.0));
  else                col = mix(uPlum,  uHot,   smoothstep(0.0, 1.0, seg - 4.0));

  /* Brightness barely breathes. The pulse used to reinforce every colour
     front with a brightness front on top, which is half of what made the
     stripes; the colour succession alone is the motion now. */
  float pulse = 0.90 + 0.10 * sin(6.2831853 * phase + 1.2);

  float cloud = fbm(vec2(rr * 0.9 - uTime * 0.16, a * 5.0));

  float intensity = cone * along * pulse * (0.62 + 0.75 * cloud);

  /* PREMULTIPLIED on purpose — the alpha is baked into the RGB before it
     leaves the shader. Straight alpha with premultipliedAlpha:false is
     honoured by desktop Chrome and IGNORED by iOS WebKit, which composites
     the buffer as premultiplied regardless: our full-strength colour was
     added over the pale ground and every mid-alpha pixel clipped to white —
     the mobile "solar flare". Premultiplying ourselves is the one form both
     engines agree on. */
  float field = clamp(intensity, 0.0, 1.0) * uAlpha;
  gl_FragColor = vec4(col * field, field);
}
`;
